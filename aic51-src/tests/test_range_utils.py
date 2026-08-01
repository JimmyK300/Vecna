import unittest

from aic51.packages.webui.backend.range_utils import parse_byte_range


class RangeUtilsTests(unittest.TestCase):
    def test_full_and_partial_ranges(self):
        self.assertIsNone(parse_byte_range(None, 100))
        self.assertEqual(parse_byte_range("bytes=10-19", 100), (10, 19))
        self.assertEqual(parse_byte_range("bytes=10-", 100), (10, 99))
        self.assertEqual(parse_byte_range("bytes=-10", 100), (90, 99))

    def test_rejects_invalid_ranges(self):
        with self.assertRaises(ValueError):
            parse_byte_range("bytes=100-101", 100)
        with self.assertRaises(ValueError):
            parse_byte_range("bytes=1-2,4-5", 100)


if __name__ == "__main__":
    unittest.main()
