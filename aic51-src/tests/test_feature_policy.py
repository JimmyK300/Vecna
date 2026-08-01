import unittest

from aic51.packages.provenance import enabled_feature_names, is_feature_enabled


class FeaturePolicyTests(unittest.TestCase):
    def test_legacy_missing_flag_stays_enabled(self):
        features = {"clip": {}, "ocr": {"enabled": False}, "asr": {"enabled": True}}

        self.assertTrue(is_feature_enabled(features, "clip"))
        self.assertFalse(is_feature_enabled(features, "ocr"))
        self.assertEqual(enabled_feature_names(features), ["clip", "asr"])

    def test_unknown_feature_is_disabled(self):
        self.assertFalse(is_feature_enabled({}, "siglip"))


if __name__ == "__main__":
    unittest.main()
