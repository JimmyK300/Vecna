import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from aic51.cli.commands.analyse import AnalyseCommand
from aic51.packages.analyse import FeatureExtractorFactory


class _FakeYoloModel:
    names = {0: "person", 2: "car"}

    def __init__(self, model_path):
        self.model_path = model_path

    def predict(self, source, **kwargs):
        box = SimpleNamespace(
            cls=np.array([2]),
            conf=np.array([0.94]),
            xyxy=np.array([[10.0, 20.0, 110.0, 80.0]]),
        )
        masks = SimpleNamespace(
            xy=[np.array([[12.0, 22.0], [108.0, 22.0], [60.0, 78.0]])]
        )
        return [SimpleNamespace(boxes=[box], masks=masks) for _ in source]


class Yolo26xFeatureTest(unittest.TestCase):
    def test_cli_accepts_both_yolo26x_flag_spellings(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        AnalyseCommand(Path.cwd()).add_args(subparsers)

        short = parser.parse_args(
            ["analyse", "--use-yolo26x", "--input-folder", "frames"]
        )
        explicit = parser.parse_args(["analyse", "--use-yolo26x-seg"])

        self.assertTrue(short.use_yolo26x_seg)
        self.assertEqual(short.input_folder, "frames")
        self.assertTrue(explicit.use_yolo26x_seg)

    def test_yolo26x_alias_writes_per_frame_metadata(self):
        extractor_cls = FeatureExtractorFactory.get("yolo26x_seg")
        self.assertIsNotNone(extractor_cls)

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            model_path = work_dir / "yolo26x-seg.pt"
            model_path.write_bytes(b"test weight placeholder")
            frame_dir = work_dir / "data" / "keyframes" / "V001"
            frame_dir.mkdir(parents=True)
            frame_paths = [frame_dir / "000001.jpg", frame_dir / "000002.jpg"]
            for frame_path in frame_paths:
                frame_path.write_bytes(b"test image placeholder")

            fake_module = SimpleNamespace(YOLO=_FakeYoloModel)
            with patch.dict(sys.modules, {"ultralytics": fake_module}), patch(
                "aic51.packages.analyse.features.yolo_traffic.cv2.imread",
                return_value=np.zeros((100, 120, 3), dtype=np.uint8),
            ), patch(
                "aic51.packages.analyse.features.yolo_traffic.extract_vehicle_color_traffic_cam",
                return_value="đỏ",
            ):
                extractor = extractor_cls.from_pretrained(
                    name="yolo26x_seg",
                    pretrained_model=str(model_path),
                    batch_size=2,
                    device="cpu",
                    work_dir=work_dir,
                    input_dir=frame_dir.parent,
                )
                self.assertEqual(extractor.discover_video_ids(work_dir), ["V001"])
                self.assertEqual(
                    extractor.discover_frame_ids(work_dir, "V001"),
                    ["000001", "000002"],
                )
                self.assertEqual(
                    [
                        path.name
                        for path in extractor.input_paths_for_frames(
                            work_dir,
                            "V001",
                            ["000002"],
                        )
                    ],
                    ["000002.jpg"],
                )
                extractor._input_dir = frame_dir
                self.assertEqual(extractor.discover_video_ids(work_dir), ["V001"])
                self.assertEqual(
                    [
                        path.name
                        for path in extractor.input_paths_for_frames(
                            work_dir,
                            "V001",
                            ["000001"],
                        )
                    ],
                    ["000001.jpg"],
                )
                vectors = extractor.get_features(frame_paths)

            self.assertEqual(vectors.shape, (2, 32))
            self.assertEqual(vectors.dtype, np.float32)
            for frame_path in frame_paths:
                metadata_path = (
                    work_dir
                    / "features"
                    / "V001"
                    / frame_path.stem
                    / "yolo26x_seg.json"
                )
                self.assertTrue(metadata_path.is_file())
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["video_id"], "V001")
                self.assertEqual(payload["frame_id"], frame_path.stem)
                self.assertEqual(
                    payload["objects"][0],
                    {
                        "class_id": 2,
                        "class_name": "car",
                        "confidence": 0.94,
                        "color": "đỏ",
                        "bbox": {
                            "x1": 10.0,
                            "y1": 20.0,
                            "x2": 110.0,
                            "y2": 80.0,
                        },
                        "mask": {
                            "polygon": [
                                [12.0, 22.0],
                                [108.0, 22.0],
                                [60.0, 78.0],
                            ]
                        },
                        "subtype": "sedan",
                    },
                )


if __name__ == "__main__":
    unittest.main()
