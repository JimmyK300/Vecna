import tempfile
import unittest
from pathlib import Path

import numpy as np

from aic51.packages.provenance import build_legacy_manifest


class LegacyManifestTests(unittest.TestCase):
    def test_records_legacy_layout_and_marks_ocr_suspect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "video").mkdir()
            (root / "video" / "L21_V001.mp4").write_bytes(b"video")
            frame = root / "L21_V001" / "000060"
            frame.mkdir(parents=True)
            np.save(frame / "image_clip_pe-l-14-336.npy", np.zeros(1024, dtype=np.float16))
            np.save(frame / "image_siglip_so400m-384.npy", np.zeros(1152, dtype=np.float16))
            np.save(frame / "asr.npy", np.array("spoken text"))
            np.save(frame / "ocr.npy", np.array("suspect"))

            report = build_legacy_manifest(root)

            self.assertEqual(report["layout"], "video-and-feature-roots")
            self.assertEqual(report["ocr_status"], "excluded-suspect")
            self.assertEqual(report["videos"]["count"], 1)
            artifacts = report["features"]["videos"]["L21_V001"]["artifacts"]
            self.assertEqual(artifacts["image_clip_pe-l-14-336.npy"]["contract"]["shape"], [1024])
            self.assertEqual(artifacts["image_siglip_so400m-384.npy"]["contract"]["shape"], [1152])


if __name__ == "__main__":
    unittest.main()
