from aic51.packages.search.experimental_similarity_labels import (
    classify_similarity_match,
    find_similar_frames,
    parse_frame_identity,
)


class FakeDatabase:
    def __init__(self, hits):
        self._collection_name = "test_collection"
        self._hits = hits
        self.search_calls = []

    @staticmethod
    def process_field_name(name):
        return name.replace("-", "_")

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return [self._hits]


class FakeSearcher:
    def __init__(self, source_id, source_vector, hits):
        self.source_id = source_id
        self._database = FakeDatabase(hits)
        self._record = {
            "frame_id": source_id,
            "image_siglip_so400m_384": source_vector,
        }

    def get(self, frame_id):
        return [self._record] if frame_id == self.source_id else []


def test_parse_frame_identity_requires_canonical_video_frame():
    parsed = parse_frame_identity("L21_V001#000123")
    assert parsed.video_id == "L21_V001"
    assert parsed.frame == 123
    assert parse_frame_identity("L21_V001") is None
    assert parse_frame_identity("L21_V001#abc") is None


def test_cross_video_match_is_dup():
    assert classify_similarity_match("L21_V001#1000", "L21_V002#1000") == "DUP"


def test_near_temporal_neighbor_is_hidden():
    assert classify_similarity_match("L21_V001#1000", "L21_V001#1050", intro_min_frame_gap=100) is None


def test_distant_same_video_opening_match_is_intro():
    assert classify_similarity_match(
        "L21_V001#120", "L21_V001#1400", intro_min_frame_gap=100, intro_start_window_frames=300
    ) == "INTRO"


def test_distant_same_video_late_match_is_reuse():
    assert classify_similarity_match(
        "L21_V001#900", "L21_V001#1400", intro_min_frame_gap=100, intro_start_window_frames=300
    ) == "REUSE"


def test_self_and_malformed_matches_are_hidden():
    assert classify_similarity_match("L21_V001#1000", "L21_V001#1000") is None
    assert classify_similarity_match("bad", "L21_V001#1000") is None


def test_lookup_filters_threshold_and_neighbours_without_writes():
    source = "L21_V001#1000"
    hits = [
        {"entity": {"frame_id": source}, "distance": 1.0},
        {"entity": {"frame_id": "L21_V002#1200"}, "distance": 0.997},
        {"entity": {"frame_id": "L21_V001#1050"}, "distance": 0.996},
        {"entity": {"frame_id": "L21_V001#1500"}, "distance": 0.995},
        {"entity": {"frame_id": "L21_V003#1300"}, "distance": 0.980},
    ]
    searcher = FakeSearcher(source, [0.1, 0.2], hits)

    result = find_similar_frames(searcher, source, threshold=0.985, limit=20)

    assert [item["frame_id"] for item in result["results"]] == [
        "L21_V002#1200",
        "L21_V001#1500",
    ]
    assert [item["relation"] for item in result["results"]] == ["DUP", "REUSE"]
    assert result["collection"] == "test_collection"
    assert len(searcher._database.search_calls) == 1
    call = searcher._database.search_calls[0]
    assert call["anns_field"] == "image_siglip_so400m-384"
    assert call["search_params"] == {"nprobe": 32, "metric_type": "COSINE"}


def test_lookup_order_is_deterministic_for_equal_scores():
    source = "L21_V001#1000"
    hits = [
        {"entity": {"frame_id": "L21_V003#1000"}, "distance": 0.99},
        {"entity": {"frame_id": "L21_V002#1000"}, "distance": 0.99},
    ]
    searcher = FakeSearcher(source, [0.1, 0.2], hits)
    result = find_similar_frames(searcher, source, threshold=0.985)
    assert [item["frame_id"] for item in result["results"]] == [
        "L21_V002#1000",
        "L21_V003#1000",
    ]
