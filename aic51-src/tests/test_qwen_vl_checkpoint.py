"""Regression tests for the loader defect; no downloaded model is required.

The runtime acceptance test must additionally compare all real 625 tensors.
These tests cover routing, caller policy, and rejection of a constructed model
whose shapes are right but one or more loaded values are wrong.
"""
import importlib.util
import sys
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np


HERE = Path(__file__).resolve().parent
PRODUCTION = HERE.parent / "aic51/packages/analyse/features"
FIXTURE = HERE / "fixtures/qwen3_vl_2b_loading_schema.json"
spec = importlib.util.spec_from_file_location("qwen_vl_checkpoint", PRODUCTION / "qwen_vl_checkpoint.py")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


class RoutingTests(unittest.TestCase):
    def test_complete_observed_625_shapes_accept_only_the_backbone_mapping(self):
        observation = json.loads(FIXTURE.read_text())
        expected = {row["name"]: row["shape"] for row in observation["expected_tensors"]}
        saved = {row["name"]: row["shape"] for row in observation["full_checkpoint_shapes"]}
        keys = list(expected)
        self.assertEqual(len(keys), 625)
        self.assertEqual(len(saved), 625)
        self.assertEqual(sum(k.startswith("language_model.") for k in keys), 310)
        self.assertEqual(sum(k.startswith("visual.") for k in keys), 315)
        self.assertEqual(set(saved), set(observation["checkpoint_keys"]))
        # Both complete schemas are captured from the real checkpoint/runtime.
        # The separate supervised audit also compares every actual tensor value.
        routes = loader.checkpoint_routes(saved, expected, loader.DEFAULT_KEY_MAPPING)
        self.assertEqual(set(routes.values()), set(expected))
        with self.assertRaises(loader.CheckpointLoadError):
            loader.checkpoint_routes(saved, expected, None)

    def test_complete_header_retains_observed_samples_and_dtype_cast_contract(self):
        observation = json.loads(FIXTURE.read_text())
        header = {row["name"]: row for row in observation["full_checkpoint_shapes"]}
        self.assertEqual(len(header), 625)
        self.assertTrue(all(row["dtype"] == "BF16" for row in header.values()))
        self.assertTrue(all(row["dtype"] == "torch.float32" and row["device"] == "cpu"
                            for row in observation["expected_tensors"]))
        for sample in observation["checkpoint_shape_samples"]:
            self.assertEqual(sample["shape"], header[sample["name"]]["shape"])
        self.assertEqual(sum(int(np.prod(row["shape"], dtype=np.int64)) for row in header.values()),
                         observation["verified_runtime"]["element_count"])

    def test_partial_mapping_missing_shape_and_collision_fail(self):
        expected = {"visual.weight": (2, 3), "language_model.weight": (4,)}
        saved = {"model." + key: shape for key, shape in expected.items()}
        with self.assertRaises(loader.CheckpointLoadError):
            loader.checkpoint_routes(saved, expected, {r"^model\.visual\.": "visual."})
        with self.assertRaises(loader.CheckpointLoadError):
            loader.checkpoint_routes({"model.visual.weight": (2, 3)}, expected, loader.DEFAULT_KEY_MAPPING)
        with self.assertRaises(loader.CheckpointLoadError):
            loader.checkpoint_routes(saved, {**expected, "visual.weight": (3, 2)}, loader.DEFAULT_KEY_MAPPING)
        with self.assertRaises(loader.CheckpointLoadError):
            loader.checkpoint_routes({"model.visual.weight": (2, 3), "visual.weight": (2, 3)}, {"visual.weight": (2, 3)}, loader.DEFAULT_KEY_MAPPING)

    def test_explicit_mapping_and_caller_dtype_are_not_overridden_or_mutated(self):
        for mapping in [None, {}, {r"^model\.": ""}]:
            caller = {"key_mapping": mapping, "torch_dtype": "caller_dtype", "revision": "caller_revision"}
            result, targeted = loader.prepare_model_kwargs(loader.MODEL_ID, caller)
            self.assertTrue(targeted)
            self.assertIsNot(result, caller)
            self.assertIs(result["key_mapping"], mapping)
            self.assertEqual(caller, result)
        empty, _ = loader.prepare_model_kwargs(loader.MODEL_ID, {})
        self.assertNotIn("torch_dtype", empty)

    def test_non_qwen_path_retains_original_kwargs(self):
        caller = {"torch_dtype": "original", "custom_option": 7}
        result, targeted = loader.prepare_model_kwargs("unrelated/image-text-model", caller)
        self.assertFalse(targeted)
        self.assertIs(result, caller)
        self.assertNotIn("key_mapping", result)

    def test_local_detection_requires_qwen_2b_sentence_transformer_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "config.json").write_text(json.dumps({"model_type": "qwen3_vl", "text_config": {"hidden_size": 2048}}))
            self.assertFalse(loader.is_qwen3_embedding(tmp))
            (directory / "config_sentence_transformers.json").write_text(json.dumps({"model_type": "SentenceTransformer"}))
            self.assertTrue(loader.is_qwen3_embedding(tmp))
            (directory / "config.json").write_text(json.dumps({"model_type": "unrelated", "text_config": {"hidden_size": 2048}}))
            self.assertFalse(loader.is_qwen3_embedding(tmp))


class ConstructorPolicyTests(unittest.TestCase):
    def extractor_module(self):
        """Import the actual production constructor with inert dependency stubs."""
        package_name = "qwen_loader_regression_features"
        package = types.ModuleType(package_name)
        package.__path__ = [str(PRODUCTION)]
        aic = types.ModuleType("aic51")
        aic.__path__ = []
        packages = types.ModuleType("aic51.packages")
        packages.__path__ = []
        constant = types.ModuleType("aic51.packages.constant")
        constant.KEYFRAME_DIR = "keyframes"
        packages.constant = constant
        logging = types.ModuleType("aic51.packages.logger")
        logging.logger = types.SimpleNamespace(warning=lambda *args: None, info=lambda *args: None)
        calls, audits = [], []

        class Device:
            def __init__(self, name):
                self.type = getattr(name, "type", str(name).split(":")[0])
            def __str__(self):
                return self.type

        class Base:
            def __init__(self, name, batch_size, device):
                self._batch_size, self._device = batch_size, device

        class SentenceModel:
            def __init__(self, *args, **kwargs):
                calls.append(kwargs)
            def supports(self, modality):
                return True

        feature = types.ModuleType(package_name + ".feature_extractor")
        feature.FeatureExtractor = Base
        feature.FeatureExtractorFactory = types.SimpleNamespace(register=lambda name: lambda cls: cls)
        torch = types.SimpleNamespace(device=Device, Tensor=Tensor, float32="torch.float32", float16="torch.float16", bfloat16="torch.bfloat16", cuda=types.SimpleNamespace(is_available=lambda: False, is_bf16_supported=lambda: False))
        modules = {package_name: package, package_name + ".feature_extractor": feature,
                   package_name + ".qwen_vl_checkpoint": loader,
                   "aic51": aic, "aic51.packages": packages,
                   "aic51.packages.constant": constant, "aic51.packages.logger": logging,
                   "torch": torch, "sentence_transformers": types.SimpleNamespace(SentenceTransformer=SentenceModel)}
        extractor_spec = importlib.util.spec_from_file_location(package_name + ".qwen_vl", PRODUCTION / "qwen_vl.py")
        module = importlib.util.module_from_spec(extractor_spec)
        with patch.dict(sys.modules, modules):
            extractor_spec.loader.exec_module(module)
        module.verify_loaded_checkpoint = lambda *args: audits.append(args) or {"status": "constructor-policy-test-only"}
        return module, calls, audits

    def test_none_and_empty_model_kwargs_keep_distinct_original_dtype_policies(self):
        module, calls, audits = self.extractor_module()
        default = module.QwenVLEmbedding(loader.MODEL_ID, model_kwargs=None)
        empty = module.QwenVLEmbedding(loader.MODEL_ID, model_kwargs={})
        self.assertEqual(calls[0]["model_kwargs"]["torch_dtype"], "torch.float32")
        self.assertNotIn("torch_dtype", calls[1]["model_kwargs"])
        self.assertEqual(default._compute_type, "float32")
        self.assertEqual(empty._compute_type, "model_default")
        self.assertEqual(len(audits), 2)

    def test_caller_processor_dtype_mapping_and_unrelated_model_are_preserved(self):
        module, calls, audits = self.extractor_module()
        caller = {"torch_dtype": "torch.float16", "key_mapping": {r"^model\.": ""}}
        processor = {"min_pixels": 512}
        module.QwenVLEmbedding(loader.MODEL_ID, model_kwargs=caller, processor_kwargs=processor)
        self.assertEqual(calls[0]["model_kwargs"], caller)
        self.assertIsNot(calls[0]["model_kwargs"], caller)
        self.assertIs(calls[0]["processor_kwargs"], processor)
        module.QwenVLEmbedding("unrelated/model", model_kwargs={})
        self.assertEqual(calls[1]["model_kwargs"], {})
        self.assertEqual(len(audits), 1)


class Tensor:
    def __init__(self, values, meta=False):
        self.array = np.asarray(values)
        self.shape, self.dtype = self.array.shape, self.array.dtype
        self.is_meta, self.is_quantized = meta, False
    def is_floating_point(self):
        return np.issubdtype(self.dtype, np.floating)
    def __getitem__(self, item):
        return Tensor(self.array[item])
    def detach(self):
        return self
    def to(self, device=None, dtype=None):
        return Tensor(self.array.astype(dtype or self.dtype, copy=False))
    def numel(self):
        return self.array.size


class Slice:
    def __init__(self, tensor, reads):
        self.tensor, self.reads = tensor, reads
    def get_shape(self):
        return self.tensor.shape
    def __getitem__(self, item):
        result = self.tensor[item]
        self.reads.append(result.numel())
        return result


class Reader:
    def __init__(self, state):
        self.state, self.reads = state, []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def keys(self):
        return self.state.keys()
    def get_slice(self, key):
        return Slice(self.state[key], self.reads)
    def get_tensor(self, key):
        return self.state[key]


class LoadedStateTests(unittest.TestCase):
    def verify(self, saved, loaded):
        model = type("Qwen3VLModel", (), {})()
        model.config = types.SimpleNamespace(model_type="qwen3_vl")
        model.base_model_prefix, model._checkpoint_conversion_mapping = "", {}
        model.state_dict = lambda: loaded
        sentence_model = [types.SimpleNamespace(auto_model=model)]
        reader = Reader(saved)
        torch = types.SimpleNamespace(equal=lambda a, b: np.array_equal(a.array, b.array))
        safetensors = types.SimpleNamespace(safe_open=lambda *args, **kwargs: reader)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "model.safetensors").write_bytes(b"mock-checkpoint-reader")
            with patch.dict("sys.modules", {"torch": torch, "safetensors": safetensors}):
                result = loader.verify_loaded_checkpoint(sentence_model, tmp, {"key_mapping": loader.DEFAULT_KEY_MAPPING})
        return result, reader

    def test_constructor_shape_success_does_not_accept_random_weights(self):
        saved = {"model.visual.weight": Tensor(np.array([1, 2], dtype=np.float16))}
        random = {"visual.weight": Tensor(np.array([0.01, -0.02], dtype=np.float32))}
        with self.assertRaisesRegex(loader.CheckpointLoadError, "differs from checkpoint"):
            self.verify(saved, random)

    def test_exact_cast_to_requested_dtype_is_verified(self):
        values = np.array([1.25, -2.5, 0.0], dtype=np.float16)
        result, _ = self.verify({"model.language_model.weight": Tensor(values)}, {"language_model.weight": Tensor(values.astype(np.float32))})
        self.assertEqual(result["status"], "VERIFIED_ALL_CHECKPOINT_TENSORS")
        self.assertEqual(result["element_count"], 3)
        self.assertFalse(result["second_model_loaded"])

    def test_last_value_after_chunk_boundary_is_checked(self):
        values = np.zeros(1_048_578, dtype=np.float32)
        result, reader = self.verify({"model.visual.weight": Tensor(values)}, {"visual.weight": Tensor(values.copy())})
        self.assertEqual(result["element_count"], values.size)
        self.assertEqual(reader.reads, [1_048_576, 2])
        altered = values.copy()
        altered[-1] = 1
        with self.assertRaisesRegex(loader.CheckpointLoadError, "differs from checkpoint"):
            self.verify({"model.visual.weight": Tensor(values)}, {"visual.weight": Tensor(altered)})

    def test_meta_tensor_cannot_be_reported_as_loaded(self):
        values = np.ones(2, dtype=np.float32)
        with self.assertRaisesRegex(loader.CheckpointLoadError, "Cannot establish"):
            self.verify({"model.visual.weight": Tensor(values)}, {"visual.weight": Tensor(values, meta=True)})


if __name__ == "__main__":
    unittest.main()
