import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = ROOT / "script" / "headless_integrated_benchmark.py"
spec = importlib.util.spec_from_file_location("headless_integrated_benchmark", WRAPPER_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class FakeExtractor:
    def __init__(self, semantics=None, device="cpu", compute_type="float32"):
        self._semantics = semantics
        self._device = device
        self._compute_type = compute_type

    def runtime_semantics(self):
        return self._semantics


class FakeSearcher:
    def __init__(self):
        self._extractors = {
            "language_qwen_vl": {
                "feature_extractor": FakeExtractor(None, device="cuda:0", compute_type="float16"),
                "target_features": ["qwen_vl"],
            },
            "text_bge_m3": {
                "feature_extractor": FakeExtractor({
                    "backend": "onnx",
                    "execution_provider": "DmlExecutionProvider",
                    "compute_type": "float32",
                }),
                "target_features": ["ocr_dense", "asr_dense"],
            },
        }


class IntegratedHeadlessWrapperTests(unittest.TestCase):
    def test_stable_result_key_uses_score_then_frame_then_timeline(self):
        rows = [
            {"distance": 0.5, "entity": {"frame_id": "V1#20"}},
            {"distance": 0.7, "entity": {"frame_id": "V1#30"}},
            {"distance": 0.7, "entity": {"frame_id": "V1#10"}},
        ]
        ordered = sorted(rows, key=module.stable_result_key)
        self.assertEqual([row["entity"]["frame_id"] for row in ordered], ["V1#10", "V1#30", "V1#20"])

    def test_capture_extractor_runtime_includes_qwen_and_bge_targets(self):
        captured = module.capture_extractor_runtime(FakeSearcher())
        self.assertEqual(captured["language_qwen_vl"]["target_features"], ["qwen_vl"])
        self.assertEqual(captured["language_qwen_vl"]["runtime_semantics"]["device"], "cuda:0")
        self.assertEqual(
            captured["text_bge_m3"]["target_features"],
            ["ocr_dense", "asr_dense"],
        )
        self.assertEqual(
            captured["text_bge_m3"]["runtime_semantics"]["execution_provider"],
            "DmlExecutionProvider",
        )


if __name__ == "__main__":
    unittest.main()
