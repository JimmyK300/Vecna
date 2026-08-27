import unittest

import numpy as np

from aic51.packages.analyse.features.yolo_onnx import (
    LetterboxTransform,
    decode_detections,
)


class YoloEndToEndOrderTest(unittest.TestCase):
    def test_max_det_preserves_export_order_instead_of_resorting(self):
        transform = LetterboxTransform(
            orig_w=640,
            orig_h=640,
            ratio=1.0,
            left=0,
            top=0,
            input_w=640,
            input_h=640,
        )
        # Ultralytics' end-to-end path confidence-filters in model order and
        # takes the first max_det. Deliberately make row 2 higher-confidence so
        # this test fails if Vecna re-sorts the export.
        output = np.array(
            [[
                [10, 10, 100, 100, 0.80, 0],
                [20, 20, 120, 120, 0.95, 1],
            ]],
            dtype=np.float32,
        )
        detections = decode_detections(
            output,
            transform,
            {0: "first", 1: "second"},
            confidence=0.20,
            max_det=1,
        )
        self.assertEqual([item["label"] for item in detections], ["first"])


if __name__ == "__main__":
    unittest.main()
