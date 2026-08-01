import tempfile
import unittest
from pathlib import Path

import numpy as np

from aic51.packages.provenance import build_frame_record


class IndexRecordTests(unittest.TestCase):
    def test_keeps_available_features_when_another_feature_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "000060"
            frame.mkdir()
            np.save(frame / "clip.npy", np.ones(2, dtype=np.float16))

            record, availability = build_frame_record(frame, "L21_V001", ["clip", "ocr"])

            self.assertEqual(record["frame_id"], "L21_V001#000060")
            self.assertIn("clip", record)
            self.assertNotIn("ocr", record)
            self.assertEqual(availability["clip"]["status"], "ready")
            self.assertEqual(availability["ocr"]["status"], "missing")

    def test_does_not_load_a_present_disabled_feature(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "000060"
            frame.mkdir()
            np.save(frame / "ocr.npy", np.array("text"))

            record, availability = build_frame_record(
                frame,
                "L21_V001",
                ["ocr"],
                enabled_features=[],
            )

            self.assertNotIn("ocr", record)
            self.assertEqual(availability["ocr"]["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
