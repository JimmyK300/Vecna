import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from PIL import Image

from aic51.packages.analyse.features.yolo import _select_backend
from aic51.packages.analyse.features.yolo_onnx import (
    DirectMLUnavailable,
    LetterboxTransform,
    create_session,
    decode_detections,
    letterbox_rgb,
    resolve_class_names,
    resolve_provider_choice,
)


class _ModelMeta:
    def __init__(self, metadata):
        self.custom_metadata_map = metadata


class _SessionWithMeta:
    def __init__(self, metadata):
        self._metadata = metadata

    def get_modelmeta(self):
        return _ModelMeta(self._metadata)


class YoloOnnxBackendTest(unittest.TestCase):
    def test_explicit_dml_requires_provider(self):
        with patch(
            "aic51.packages.analyse.features.yolo_onnx.available_providers",
            return_value=["CPUExecutionProvider"],
        ):
            with self.assertRaises(DirectMLUnavailable):
                resolve_provider_choice("dml", allow_gpu=True)

    def test_auto_prefers_dml_without_torch_cuda(self):
        with patch(
            "aic51.packages.analyse.features.yolo_onnx.available_providers",
            return_value=["DmlExecutionProvider", "CPUExecutionProvider"],
        ):
            choice, warning = resolve_provider_choice("auto", allow_gpu=True)
        self.assertEqual(choice, "dml")
        self.assertIsNone(warning)

    def test_no_gpu_forces_cpu(self):
        choice, warning = resolve_provider_choice("dml", allow_gpu=False)
        self.assertEqual(choice, "cpu")
        self.assertIn("disabled", warning or "")

    def test_onnx_metadata_names_are_used(self):
        session = _SessionWithMeta({"names": "{0: 'traffic sign', 1: 'doodle'}"})
        self.assertEqual(
            resolve_class_names(session),
            {0: "traffic sign", 1: "doodle"},
        )

    def test_explicit_names_file_overrides_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "names.txt"
            path.write_text("alpha\nbeta\n", encoding="utf-8")
            session = _SessionWithMeta({"names": "{0: 'wrong'}"})
            self.assertEqual(resolve_class_names(session, path), {0: "alpha", 1: "beta"})

    def test_letterbox_has_fixed_shape_and_records_padding(self):
        image = Image.new("RGB", (1280, 720), (10, 20, 30))
        tensor, transform = letterbox_rgb(image, 640)
        self.assertEqual(tensor.shape, (1, 3, 640, 640))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertAlmostEqual(transform.ratio, 0.5)
        self.assertEqual(transform.left, 0)
        self.assertEqual(transform.top, 140)

    def test_decode_filters_top_max_det_and_deletterboxes(self):
        transform = LetterboxTransform(
            orig_w=1280,
            orig_h=720,
            ratio=0.5,
            left=0,
            top=140,
            input_w=640,
            input_h=640,
        )
        # Letterboxed coordinates.  First row maps to [100, 50, 300, 250]
        # in the original frame. Third row is below threshold.
        output = np.array(
            [[
                [50, 165, 150, 265, 0.90, 1],
                [10, 150, 60, 200, 0.80, 0],
                [30, 160, 80, 210, 0.10, 0],
            ]],
            dtype=np.float32,
        )
        detections = decode_detections(
            output,
            transform,
            {0: "traffic sign", 1: "doodle"},
            confidence=0.20,
            max_det=1,
        )
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0]["label"], "doodle")
        np.testing.assert_allclose(
            detections[0]["bbox"],
            [100.0, 50.0, 300.0, 250.0],
            atol=1e-5,
        )

    def test_auto_backend_keeps_cuda_on_ultralytics(self):
        choice = _select_backend(
            "auto",
            device=torch.device("cuda:0"),
            allow_gpu=True,
            onnx_provider="dml",
            onnx_model_path="some-export.onnx",
        )
        self.assertEqual(choice, "ultralytics")

    def test_auto_backend_can_select_onnx_on_amd_style_host(self):
        choice = _select_backend(
            "auto",
            device=torch.device("cpu"),
            allow_gpu=True,
            onnx_provider="dml",
            onnx_model_path="some-export.onnx",
        )
        self.assertEqual(choice, "onnx")

    def test_directml_session_options_are_applied(self):
        captured = {}

        class FakeOptions:
            def __init__(self):
                self.graph_optimization_level = None
                self.log_severity_level = None
                self.enable_mem_pattern = True
                self.execution_mode = None

        class FakeSession:
            def __init__(self, path, sess_options, providers):
                captured["path"] = path
                captured["options"] = sess_options
                captured["providers"] = providers

            def get_providers(self):
                return ["DmlExecutionProvider", "CPUExecutionProvider"]

        class FakeOrt:
            class GraphOptimizationLevel:
                ORT_ENABLE_ALL = "all"

            class ExecutionMode:
                ORT_SEQUENTIAL = "sequential"

            SessionOptions = FakeOptions
            InferenceSession = FakeSession

        with patch(
            "aic51.packages.analyse.features.yolo_onnx.import_onnxruntime",
            return_value=FakeOrt,
        ):
            create_session(Path("model.onnx"), "dml")

        self.assertFalse(captured["options"].enable_mem_pattern)
        self.assertEqual(captured["options"].execution_mode, "sequential")
        self.assertEqual(captured["providers"][0][0], "DmlExecutionProvider")


if __name__ == "__main__":
    unittest.main()
