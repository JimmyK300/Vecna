import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

from tools.inspect_data_contract import build_report


class InspectDataContractTests(unittest.TestCase):
    def test_report_describes_artifacts_and_missing_features(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            video_path = workspace / "data" / "videos" / "video-001.mp4"
            keyframe_path = workspace / "data" / "keyframes" / "video-001" / "000001.jpg"
            feature_path = (
                workspace
                / "features"
                / "video-001"
                / "000001"
                / "image_siglip_so400m-384.npy"
            )

            video_path.parent.mkdir(parents=True)
            keyframe_path.parent.mkdir(parents=True)
            feature_path.parent.mkdir(parents=True)

            video_path.write_bytes(b"synthetic-video")
            Image.new("RGB", (2, 3), color=(12, 34, 56)).save(keyframe_path)
            np.save(feature_path, np.zeros(1152, dtype=np.float32))

            (workspace / "config.yaml").write_text(
                yaml.safe_dump(
                    {
                        "features": {
                            "image_siglip_so400m-384": {
                                "model": "image_siglip",
                                "source": "open_clip",
                                "arch_name": "ViT-SO400M-14-SigLIP-384",
                                "pretrained_model": "webli",
                                "index": {
                                    "datatype": "FLOAT_VECTOR",
                                    "dim": 1152,
                                },
                            },
                            "ocr": {
                                "model": "ocr",
                                "source": "tesseract",
                                "index": {
                                    "datatype": "VARCHAR",
                                    "max_length": 8192,
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(
                workspace,
                repo_root=None,
                include_content=True,
                inspect_images=True,
            )

            self.assertEqual(report["videos"]["count"], 1)
            self.assertIsNotNone(report["videos"]["videos"][0]["sha256"])

            keyframes = report["keyframes"]["videos"]["video-001"]
            self.assertEqual(keyframes["frame_ids"], ["000001"])
            self.assertEqual(keyframes["image_dimensions"], ["2x3"])
            self.assertEqual(keyframes["image_errors"], [])

            features = report["features"]["videos"]["video-001"]
            self.assertEqual(features["frame_count"], 1)
            self.assertEqual(features["feature_counts"]["image_siglip_so400m-384"], 1)
            self.assertEqual(features["missing_counts"]["image_siglip_so400m-384"], 0)
            self.assertEqual(features["missing_counts"]["ocr"], 1)
            self.assertEqual(
                features["samples"]["image_siglip_so400m-384"][0]["shape"],
                [1152],
            )
            self.assertEqual(
                features["samples"]["image_siglip_so400m-384"][0]["dtype"],
                "float32",
            )
            self.assertIsNotNone(
                features["feature_manifests"]["image_siglip_so400m-384"]
            )
            self.assertEqual(report["milvus"]["enabled"], False)


if __name__ == "__main__":
    unittest.main()
