import unittest

from aic51.packages.search.searcher import Searcher


def _hit(video_id, frame_id, score, rank_score=None):
    result = {
        "entity": {"frame_id": f"{video_id}#{frame_id:06d}"},
        "distance": score,
        "scores": {"final": score, "clip": score},
    }
    if rank_score is not None:
        result["_temporal_rank_score"] = rank_score
    return result


class _FakeVectorDatabase:
    def __init__(self, vectors):
        self.vectors = vectors

    @staticmethod
    def process_field_name(field_name):
        return field_name

    def get_many(self, ids, output_fields=None):
        return [
            {"frame_id": frame_id, "image_siglip2_so400m_378": self.vectors[frame_id]}
            for frame_id in ids
            if frame_id in self.vectors
        ]


class TemporalFrameDPTest(unittest.TestCase):
    def _searcher(self, vectors=None):
        searcher = Searcher.__new__(Searcher)
        searcher._database = _FakeVectorDatabase(vectors or {})
        searcher._single_search_cluster_frame_gap = 150
        searcher._single_search_cluster_similarity = 0.95
        searcher._single_search_cluster_vector_field = "image_siglip2_so400m_378"
        return searcher

    def test_temporal_candidates_are_not_shot_clustered(self):
        vectors = {
            "V1#000010": [1.0, 0.0],
            "V1#000012": [0.999, 0.001],
            "V1#000030": [0.0, 1.0],
            "V1#000300": [1.0, 0.0],
        }
        searcher = self._searcher(vectors)

        clusters, candidate_count = searcher._cluster_temporal_stage(
            [
                _hit("V1", 10, 0.8, 0.9),
                _hit("V1", 12, 0.9, 0.7),
                _hit("V1", 30, 0.6, 0.6),
                _hit("V1", 300, 0.5, 0.5),
            ]
        )

        self.assertEqual(candidate_count, 4)
        self.assertEqual(len(clusters), 4)
        self.assertTrue(all(len(cluster["hits"]) == 1 for cluster in clusters))

    def test_returns_one_best_timeline_per_video(self):
        searcher = self._searcher()
        results, debug = searcher._combine_temporal_results(
            [
                [_hit("V1", 10, 0.9), _hit("V1", 30, 0.8), _hit("V2", 11, 0.7)],
                [_hit("V1", 20, 0.7), _hit("V1", 40, 0.95), _hit("V2", 21, 0.6)],
            ],
            max_interval=100,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(len({result["temporal"]["video_id"] for result in results}), 2)
        self.assertEqual(debug["full_match_video_count"], 2)

    def test_candidate_shortlist_reserves_quota_for_each_stage(self):
        searcher = self._searcher()
        shared = [
            _hit(f"S{i}", i, 0.9, 0.9)
            for i in range(10)
        ]
        stage_a = [
            _hit(f"A{i}", i, 1.0 - i * 0.01, 1.0 - i * 0.01)
            for i in range(5)
        ] + shared
        stage_b = [
            _hit(f"B{i}", i, 1.0 - i * 0.01, 1.0 - i * 0.01)
            for i in range(5)
        ] + shared

        selected = searcher._select_temporal_candidate_videos(
            [stage_a, stage_b],
            max_videos=10,
        )

        self.assertEqual(set(selected), {f"A{i}" for i in range(5)} | {f"B{i}" for i in range(5)})

    def test_max_interval_rejects_distant_two_event_match(self):
        searcher = self._searcher()
        results, debug = searcher._combine_temporal_results(
            [[_hit("V1", 10, 0.9)], [_hit("V1", 100, 0.9)]],
            max_interval=20,
        )

        self.assertEqual(results, [])
        self.assertEqual(debug["failure_reason"], "no_valid_ordered_sequence")

    def test_similar_frames_remain_available_as_dp_timing_choices(self):
        vectors = {
            "V1#000010": [1.0, 0.0],
            "V1#000040": [1.0, 0.0],
            "V1#000030": [1.0, 0.0],
            "V1#000050": [1.0, 0.0],
        }
        searcher = self._searcher(vectors)
        results, _ = searcher._combine_temporal_results(
            [
                [_hit("V1", 40, 0.9), _hit("V1", 10, 0.7)],
                [_hit("V1", 30, 0.8), _hit("V1", 50, 0.6)],
            ],
            max_interval=100,
        )

        self.assertEqual(len(results), 1)
        first, second = (int(value) for value in results[0]["time_line"])
        self.assertLess(first, second)

    def test_three_events_can_fallback_to_exactly_two_in_order(self):
        searcher = self._searcher()
        results, debug = searcher._combine_temporal_results(
            [[_hit("V1", 10, 0.9)], [], [_hit("V1", 30, 0.8)]],
            max_interval=100,
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["temporal"]["partial"])
        self.assertAlmostEqual(results[0]["temporal"]["coverage"], 2 / 3)
        self.assertEqual(results[0]["temporal"]["matched_stage_indices"], [0, 2])
        self.assertTrue(debug["used_relaxed_fallback"])


if __name__ == "__main__":
    unittest.main()
