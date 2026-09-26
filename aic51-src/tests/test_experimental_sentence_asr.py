from copy import deepcopy

from aic51.packages.search.experimental_sentence_asr import (
    group_frame_hits_by_sentence,
    normalize_asr_text,
    raw_flooding_stats,
    raw_top_frame_hits,
)


def hit(frame_id, text, score):
    return {"entity": {"frame_id": frame_id, "asr": text}, "distance": score}


def test_normalization_is_case_and_whitespace_only():
    assert normalize_asr_text("  Hello   WORLD! \n") == "hello world!"


def test_identical_text_same_video_groups_and_uses_max_score():
    groups = group_frame_hits_by_sentence([
        hit("L01_V001#000200", "same words", 0.7),
        hit("L01_V001#000100", " Same   Words ", 0.9),
    ])
    assert len(groups) == 1
    assert groups[0]["score"] == 0.9
    assert [m["frame"] for m in groups[0]["member_frames"]] == [100, 200]


def test_same_text_different_video_stays_separate():
    groups = group_frame_hits_by_sentence([
        hit("L01_V001#000100", "same", 0.9),
        hit("L01_V002#000100", "same", 0.8),
    ])
    assert len(groups) == 2
    assert [g["video_id"] for g in groups] == ["L01_V001", "L01_V002"]


def test_different_text_same_video_stays_separate():
    groups = group_frame_hits_by_sentence([
        hit("L01_V001#000100", "alpha", 0.9),
        hit("L01_V001#000200", "beta", 0.8),
    ])
    assert len(groups) == 2


def test_empty_and_malformed_hits_are_ignored():
    groups = group_frame_hits_by_sentence([
        hit("L01_V001#000100", "   ", 1.0),
        hit("not-a-frame", "words", 1.0),
        {"entity": {"frame_id": "L01_V001#000200"}, "distance": 1.0},
    ])
    assert groups == []


def test_group_order_and_limit_are_deterministic():
    groups = group_frame_hits_by_sentence([
        hit("L01_V002#000100", "beta", 0.8),
        hit("L01_V001#000100", "zeta", 0.8),
        hit("L01_V001#000200", "alpha", 0.8),
        hit("L01_V003#000100", "top", 0.9),
    ], limit=3)
    assert [(g["video_id"], g["normalized_asr_text"]) for g in groups] == [
        ("L01_V003", "top"),
        ("L01_V001", "alpha"),
        ("L01_V001", "zeta"),
    ]


def test_raw_arm_and_flooding_stats_use_same_identity_contract():
    raw = raw_top_frame_hits([
        hit("L01_V001#000100", "same", 1.0),
        hit("L01_V001#000200", " same ", 0.9),
        hit("L01_V002#000100", "same", 0.8),
        hit("L01_V003#000100", "other", 0.7),
    ], limit=4)
    assert raw_flooding_stats(raw) == {
        "raw_slots": 4,
        "unique_sentence_groups": 3,
        "largest_identical_sentence_slot_count": 2,
    }


def test_grouping_does_not_mutate_input():
    source = [
        hit("L01_V001#000200", "same words", 0.7),
        hit("L01_V001#000100", "same words", 0.9),
    ]
    before = deepcopy(source)
    group_frame_hits_by_sentence(source)
    assert source == before
