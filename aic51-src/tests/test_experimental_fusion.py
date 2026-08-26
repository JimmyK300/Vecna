from __future__ import annotations

import copy

import pytest

from aic51.packages.search.experimental_fusion import (
    LEGACY_STRATEGY,
    OPENCUBEE_MODEL_WEIGHTED_STRATEGY,
    fuse_model_results,
    select_visual_fusion,
)


def hit(frame_id: str, score: float) -> dict:
    return {"entity": {"frame_id": frame_id, "video_id": frame_id.split("#")[0]}, "distance": score}


def test_legacy_strategy_returns_original_sequence_unchanged():
    legacy = [hit("V1#0001", 0.9), hit("V2#0002", 0.8)]
    selected = select_visual_fusion(LEGACY_STRATEGY, legacy_results=legacy)
    assert selected is legacy
    assert selected == legacy


def test_model_weights_are_normalized_across_active_models():
    fused = fuse_model_results(
        {
            "clip": [hit("V1#0001", 1.0)],
            "siglip": [hit("V1#0001", 0.5), hit("V2#0002", 1.0)],
        },
        {"clip": 1.0, "siglip": 3.0},
    )
    by_id = {item["entity"]["frame_id"]: item for item in fused}
    assert by_id["V1#0001"]["distance"] == pytest.approx(0.25 * 1.0 + 0.75 * 0.5)
    assert by_id["V2#0002"]["distance"] == pytest.approx(0.75)
    assert by_id["V1#0001"]["experimental_fusion"]["normalized_model_weights"] == {
        "clip": 0.25,
        "siglip": 0.75,
    }


def test_missing_or_empty_model_is_not_allowed_to_dilute_active_weights():
    fused = fuse_model_results(
        {"clip": [hit("V1#0001", 0.8)], "siglip": []},
        {"clip": 1.0, "siglip": 9.0, "qwen": 100.0},
    )
    assert len(fused) == 1
    assert fused[0]["distance"] == pytest.approx(0.8)
    assert fused[0]["experimental_fusion"]["normalized_model_weights"] == {"clip": 1.0}


def test_candidate_absent_from_one_model_gets_zero_contribution_from_that_model():
    fused = fuse_model_results(
        {
            "clip": [hit("V1#0001", 1.0)],
            "siglip": [hit("V2#0002", 1.0)],
        },
        {"clip": 1.0, "siglip": 1.0},
    )
    assert [item["entity"]["frame_id"] for item in fused] == ["V1#0001", "V2#0002"]
    assert [item["distance"] for item in fused] == pytest.approx([0.5, 0.5])


def test_equal_scores_have_deterministic_frame_identity_tie_break():
    fused = fuse_model_results(
        {"clip": [hit("V2#0002", 1.0), hit("V1#0001", 1.0)]},
        {"clip": 1.0},
    )
    assert [item["entity"]["frame_id"] for item in fused] == ["V1#0001", "V2#0002"]


def test_fusion_does_not_mutate_input_rankings():
    rankings = {
        "clip": [hit("V1#0001", 0.9)],
        "siglip": [hit("V1#0001", 0.7)],
    }
    before = copy.deepcopy(rankings)
    fuse_model_results(rankings, {"clip": 1.0, "siglip": 1.0})
    assert rankings == before


def test_explicit_donor_strategy_requires_per_model_inputs():
    with pytest.raises(ValueError):
        select_visual_fusion(
            OPENCUBEE_MODEL_WEIGHTED_STRATEGY,
            legacy_results=[hit("V1#0001", 1.0)],
        )


def test_unknown_strategy_is_rejected():
    with pytest.raises(ValueError):
        select_visual_fusion("mystery", legacy_results=[])
