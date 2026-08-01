import tempfile
import unittest
from pathlib import Path

import numpy as np

from aic51.packages.provenance import inspect_feature_availability


class FeatureAvailabilityTests(unittest.TestCase):
    def test_classifies_missing_disabled_ready_and_invalid_features(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory)
            np.save(frame / "clip.npy", np.zeros(2, dtype=np.float16))
            (frame / "broken.npy").write_bytes(b"not a numpy file")

            result = inspect_feature_availability(
                frame,
                ["clip", "siglip", "ocr", "broken"],
                enabled_features=["clip", "ocr", "broken"],
            )

            self.assertEqual(result["clip"]["status"], "ready")
            self.assertEqual(result["clip"]["shape"], [2])
            self.assertEqual(result["siglip"]["status"], "missing")
            self.assertEqual(result["ocr"]["status"], "missing")
            self.assertEqual(result["broken"]["status"], "invalid")

    def test_present_feature_can_be_disabled_without_being_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory)
            np.save(frame / "ocr.npy", np.array("text"))

            result = inspect_feature_availability(frame, ["ocr"], enabled_features=[])

            self.assertFalse(result["ocr"]["enabled"])
            self.assertTrue(result["ocr"]["present"])
            self.assertEqual(result["ocr"]["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
