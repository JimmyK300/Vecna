import tempfile
import unittest
from pathlib import Path

from aic51.packages.provenance import build_manifest


class ManifestTests(unittest.TestCase):
    def test_records_config_feature_policy_and_empty_data_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.yaml").write_text(
                "features:\n  ocr:\n    enabled: false\n    model: ocr\n",
                encoding="utf-8",
            )

            report = build_manifest(root)

            self.assertEqual(report["videos"]["count"], 0)
            self.assertFalse(report["feature_policy"]["ocr"]["enabled"])
            self.assertEqual(len(report["config"]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
