import unittest

from aic51.packages.search.searcher import Searcher, SegmentClustering


def _hit(video_id, frame_id, distance):
    return {
        "distance": distance,
        "entity": {"frame_id": f"{video_id}#{frame_id:06d}"},
    }


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


class _FailingVectorDatabase(_FakeVectorDatabase):
    def get_many(self, ids, output_fields=None):
        raise RuntimeError("vector field unavailable")


class SingleSearchClusteringTest(unittest.TestCase):
    def _searcher(self, vectors):
        searcher = Searcher.__new__(Searcher)
        searcher._database = _FakeVectorDatabase(vectors)
        searcher._single_search_cluster_frame_gap = 150
        searcher._single_search_cluster_similarity = 0.95
        searcher._single_search_cluster_vector_field = "image_siglip2_so400m_378"
        return searcher

    def test_nearby_visual_duplicates_keep_the_best_ranked_result(self):
        results = [
            _hit("V1", 160, 0.95),
            _hit("V2", 120, 0.90),
            _hit("V1", 100, 0.85),
            _hit("V1", 220, 0.80),
            _hit("V1", 400, 0.75),
        ]
        vectors = {
            "V1#000160": [1.0, 0.0],
            "V2#000120": [1.0, 0.0],
            "V1#000100": [0.999, 0.001],
            "V1#000220": [0.0, 1.0],
            "V1#000400": [1.0, 0.0],
        }

        diversified = self._searcher(vectors)._diversify_single_search_results(results)

        self.assertEqual(
            [item["entity"]["frame_id"] for item in diversified],
            ["V1#000160", "V2#000120", "V1#000220", "V1#000400"],
        )

    def test_nearby_duplicates_from_different_videos_are_not_grouped(self):
        results = [_hit("V1", 100, 0.9), _hit("V2", 110, 0.8)]
        vectors = {
            "V1#000100": [1.0, 0.0],
            "V2#000110": [1.0, 0.0],
        }

        diversified = self._searcher(vectors)._diversify_single_search_results(results)

        self.assertEqual(len(diversified), 2)

    def test_missing_vector_keeps_the_result(self):
        results = [_hit("V1", 100, 0.9), _hit("V1", 110, 0.8)]
        vectors = {"V1#000100": [1.0, 0.0]}

        diversified = self._searcher(vectors)._diversify_single_search_results(results)

        self.assertEqual(diversified, results)

    def test_vector_fetch_failure_keeps_all_ranked_results(self):
        results = [_hit("V1", 100, 0.9), _hit("V1", 110, 0.8)]
        searcher = self._searcher({})
        searcher._database = _FailingVectorDatabase({})

        diversified = searcher._diversify_single_search_results(results)

        self.assertEqual(diversified, results)

    def test_legacy_segment_map_does_not_collapse_unmapped_video(self):
        clustering = SegmentClustering.__new__(SegmentClustering)
        clustering.map = {
            "MAPPED": {"fids": [100], "segs": [0]},
        }
        results = [_hit("UNMAPPED", 100, 0.9), _hit("UNMAPPED", 110, 0.8)]

        diversified = clustering.diversify(results)

        self.assertEqual(diversified, results)


if __name__ == "__main__":
    unittest.main()
