from aic51.packages.search.asr_operator import search_asr_operator


class FakeDatabase:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return [self.hits]


class FakeSearcher:
    def __init__(self, hits):
        self._database = FakeDatabase(hits)
        self._asr_name = "asr_sparse"

    def _get_video_filter(self, include_video_ids):
        return f"include={','.join(include_video_ids)}" if include_video_ids else ""

    @staticmethod
    def _filter_exclude_videos(results, exclude_video_ids):
        excluded = set(exclude_video_ids)
        return [
            hit
            for hit in results
            if hit["entity"]["frame_id"].split("#", 1)[0] not in excluded
        ]


def hit(frame_id, text, score):
    return {"entity": {"frame_id": frame_id, "asr": text, "ocr": ""}, "distance": score}


def test_raw_is_default_and_preserves_backend_order():
    searcher = FakeSearcher([
        hit("L01_V001#000200", "same", 9.0),
        hit("L01_V001#000100", "same", 8.0),
        hit("L01_V002#000300", "other", 7.0),
    ])
    result = search_asr_operator(searcher, "query", limit=2)
    assert result["mode"] == "raw"
    assert [r["entity"]["frame_id"] for r in result["results"]] == [
        "L01_V001#000200",
        "L01_V001#000100",
    ]
    assert result["total"] == 3


def test_sentence_mode_collapses_same_video_identical_text_and_retains_members():
    searcher = FakeSearcher([
        hit("L01_V001#000200", "Same words", 9.0),
        hit("L01_V001#000100", " same   WORDS ", 8.0),
        hit("L01_V002#000300", "Same words", 7.0),
    ])
    result = search_asr_operator(searcher, "query", sentence_level=True, limit=20)
    assert result["mode"] == "sentence"
    assert result["total"] == 2
    first = result["results"][0]
    assert first["entity"]["frame_id"] == "L01_V001#000200"
    assert first["time_line"] == ["100", "200"]
    assert first["sentence_group"]["member_count"] == 2


def test_sentence_mode_keeps_same_text_across_videos_separate():
    searcher = FakeSearcher([
        hit("L01_V001#000100", "same", 9.0),
        hit("L01_V002#000100", "same", 8.0),
    ])
    result = search_asr_operator(searcher, "query", sentence_level=True)
    assert [r["entity"]["frame_id"].split("#", 1)[0] for r in result["results"]] == [
        "L01_V001",
        "L01_V002",
    ]


def test_include_filter_is_passed_to_single_bm25_search():
    searcher = FakeSearcher([hit("L01_V001#000100", "same", 9.0)])
    search_asr_operator(searcher, "query", include_videos="L01_V001,L01_V002")
    assert len(searcher._database.calls) == 1
    call = searcher._database.calls[0]
    assert call["anns_field"] == "asr_sparse"
    assert call["search_params"]["metric_type"] == "BM25"
    assert call["filter"] == "include=L01_V001,L01_V002"


def test_exclude_filter_applies_without_second_search():
    searcher = FakeSearcher([
        hit("L01_V001#000100", "same", 9.0),
        hit("L01_V002#000100", "other", 8.0),
    ])
    result = search_asr_operator(searcher, "query", exclude_videos="L01_V001")
    assert len(searcher._database.calls) == 1
    assert [r["entity"]["frame_id"] for r in result["results"]] == ["L01_V002#000100"]


def test_empty_query_is_read_only_empty_result():
    searcher = FakeSearcher([hit("L01_V001#000100", "same", 9.0)])
    result = search_asr_operator(searcher, "   ", sentence_level=True)
    assert result == {"results": [], "total": 0, "offset": 0, "mode": "sentence"}
    assert searcher._database.calls == []
