import unittest

from aic51.packages.search.searcher import Searcher


class _FakeClustering:
    def __init__(self, segments):
        self.segments = segments

    def seg_of(self, video_id, frame_id):
        return self.segments.get((video_id, frame_id), -1)


def _hit(video_id, frame_id, score, rank_score=None):
    result = {
        "entity": {"frame_id": f"{video_id}#{frame_id:06d}"},
        "distance": score,
        "scores": {"final": score, "clip": score},
    }
    if rank_score is not None:
        result["_temporal_rank_score"] = rank_score
    return result


class TemporalSegmentDPTest(unittest.TestCase):
    def _searcher(self, segments):
        searcher = Searcher.__new__(Searcher)
        searcher._clustering = _FakeClustering(segments)
        return searcher

    def test_cluster_keeps_only_best_frame_per_segment(self):
        searcher = self._searcher({("V1", 10): 1, ("V1", 12): 1, ("V1", 30): 2})
        clusters, candidate_count = searcher._cluster_temporal_stage(
            [
                _hit("V1", 10, 0.8, 0.9),
                _hit("V1", 12, 0.9, 0.7),
                _hit("V1", 30, 0.6, 0.6),
            ]
        )

        self.assertEqual(candidate_count, 3)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0]["best_hit"]["frame_id"], 10)
        self.assertEqual(clusters[0]["cluster_score"], 0.9)

    def test_returns_only_one_best_timeline_per_video(self):
        segments = {
            ("V1", 10): 1,
            ("V1", 20): 2,
            ("V1", 30): 3,
            ("V1", 40): 4,
            ("V2", 11): 1,
            ("V2", 21): 2,
        }
        searcher = self._searcher(segments)
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
        self.assertTrue(debug["max_interval_enforced"])

    def test_max_interval_rejects_distant_two_block_match(self):
        searcher = self._searcher({("V1", 10): 1, ("V1", 100): 2})
        results, debug = searcher._combine_temporal_results(
            [[_hit("V1", 10, 0.9)], [_hit("V1", 100, 0.9)]],
            max_interval=20,
        )

        self.assertEqual(results, [])
        self.assertEqual(debug["failure_reason"], "no_valid_ordered_sequence")

    def test_distinct_events_in_the_same_segment_can_form_a_timeline(self):
        searcher = self._searcher(
            {("V1", 10): 1, ("V1", 30): 1, ("V1", 40): 1, ("V1", 50): 1}
        )
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
        self.assertNotEqual(results[0]["time_line"], ["40", "30"])

    def test_three_blocks_can_fallback_to_exactly_two_in_order(self):
        searcher = self._searcher({("V1", 10): 1, ("V1", 30): 2})
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
