import unittest

from aic51.packages.search.utils import translate_en_to_vi


class TranslationFallbackTests(unittest.TestCase):
    def test_translation_is_safe_when_optional_dependency_is_unavailable(self):
        self.assertEqual(translate_en_to_vi("hello"), "hello")


if __name__ == "__main__":
    unittest.main()
