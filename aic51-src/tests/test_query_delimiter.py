import unittest

from aic51.packages.search.utils import Query


class QueryDelimiterTest(unittest.TestCase):

  def test_newline_splits_temporal_blocks(self):
    query = Query("chef cuts the shrimp\nchef plates the shrimp")

    self.assertTrue(query.temporal)
    self.assertEqual(
        [item["raw"] for item in query.data],
        ["chef cuts the shrimp", "chef plates the shrimp"],
    )

  def test_slash_stays_inside_one_block(self):
    query = Query("2 yellow pieces / 1 green piece inside a red pan")

    self.assertFalse(query.temporal)
    self.assertEqual(len(query.data), 1)
    self.assertEqual(
        query.data[0]["features"]["text"],
        "2 yellow pieces / 1 green piece inside a red pan",
    )

  def test_windows_newlines_are_supported(self):
    query = Query("first event\r\nsecond event")

    self.assertEqual([item["raw"] for item in query.data], ["first event", "second event"])

  def test_visual_text_fills_empty_ocr_and_asr_channels(self):
    query = Query("the chef adds salt")
    features = query.data[0]["features"]

    self.assertEqual(features["ocr"], ["the chef adds salt"])
    self.assertEqual(features["asr"], ["the chef adds salt"])

  def test_explicit_ocr_and_asr_override_fallback(self):
    query = Query("the chef cooks [OCR: menu] [asr: add salt]")
    features = query.data[0]["features"]

    self.assertEqual(features["ocr"], ["menu"])
    self.assertEqual(features["asr"], ["add salt"])


if __name__ == "__main__":
  unittest.main()
