import unittest

from aic51.packages.search.searcher import Searcher


class YoloRelationFilterTest(unittest.TestCase):
    def setUp(self):
        self.searcher = Searcher.__new__(Searcher)
        self.searcher._collection_fields = {"yolo_relations"}

    def test_valid_relation_builds_milvus_filter(self):
        self.assertEqual(
            self.searcher._get_relation_filter("red:car:left_of:blue:bus"),
            'ARRAY_CONTAINS(yolo_relations, "red:car:left_of:blue:bus")',
        )

    def test_invalid_relation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid YOLO relation key"):
            self.searcher._get_relation_filter("red:car:beside:blue:bus")


if __name__ == "__main__":
    unittest.main()
