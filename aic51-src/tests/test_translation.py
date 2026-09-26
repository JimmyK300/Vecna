import unittest
from unittest.mock import patch

from aic51.packages.search.utils import (
    Query,
    _is_translation_error,
    _raw_translate_vi_to_en,
    translate_en_to_vi,
    translate_vi_to_en,
    translate_vi_to_en_with_status,
)


class TranslationTest(unittest.TestCase):

  def test_is_translation_error(self):
    err_text = "Error 500 (Server Error)!!1500.That’s an error.There was an error."
    self.assertTrue(_is_translation_error(err_text))
    self.assertFalse(_is_translation_error("A bowl of steaming soup with flower-shaped cut vegetables."))

  def test_error_response_not_cached_and_fallbacks(self):
    err_text = "Error 500 (Server Error)!!1500.That’s an error."
    _raw_translate_vi_to_en.cache_clear()
    self.addCleanup(_raw_translate_vi_to_en.cache_clear)
    # Keep this test independent of the disk cache and external translation APIs.
    with patch("aic51.packages.search.utils._get_persistent_cache", return_value=None), \
         patch("aic51.packages.search.utils._save_persistent_cache"), \
         patch("aic51.packages.search.utils._translate_via_chrome_api", side_effect=RuntimeError("offline")), \
         patch("aic51.packages.search.utils._translate_via_mymemory", side_effect=RuntimeError("offline")):
      with patch("deep_translator.GoogleTranslator.translate", return_value=err_text):
        res1, success = translate_vi_to_en_with_status("Người đầu bếp")
        self.assertEqual(res1, "Người đầu bếp")
        self.assertFalse(success)
        self.assertEqual(_raw_translate_vi_to_en.cache_info().currsize, 0)

        q = Query("Người đầu bếp", auto_translate=True)
        self.assertTrue(q.translation_failed)

      # When the last fallback recovers, it successfully translates and caches.
      with patch("deep_translator.GoogleTranslator.translate", return_value="The chef"):
        res2, success2 = translate_vi_to_en_with_status("Người đầu bếp")
        self.assertEqual(res2, "The chef")
        self.assertTrue(success2)
        self.assertEqual(_raw_translate_vi_to_en.cache_info().currsize, 1)

        q2 = Query("Người đầu bếp", auto_translate=True)
        self.assertFalse(q2.translation_failed)


if __name__ == "__main__":
  unittest.main()
