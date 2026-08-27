import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from aic51.packages.analyse.features.bge_onnx import (
    DirectMLUnavailable,
    adaptive_batch_limit,
    build_ready_batches,
    create_session,
    estimate_preload_bytes,
    l2_normalize,
    length_bucket,
    pad_token_lists,
    pooled_dense,
    preload_shard_size,
    resolve_provider_choice,
)


class _Output:
    def __init__(self, name):
        self.name = name


class BgeOnnxBackendTest(unittest.TestCase):
    def test_l2_normalize_unit_norm(self):
        vecs = np.array([[3.0, 4.0], [0.0, 2.0]], dtype=np.float32)
        out = l2_normalize(vecs)
        norms = np.linalg.norm(out, axis=-1)
        np.testing.assert_allclose(norms, np.ones(2), atol=1e-6)

    def test_cls_pooling_from_hidden_states(self):
        hidden = np.zeros((2, 4, 1024), dtype=np.float32)
        hidden[0, 0, 0] = 1.0
        hidden[1, 0, 1] = 1.0
        hidden[:, 1, :] = 9.0

        class Session:
            def get_outputs(self):
                return [_Output("last_hidden_state")]

        vecs = pooled_dense(Session(), [hidden])
        self.assertEqual(vecs.shape, (2, 1024))
        np.testing.assert_allclose(np.linalg.norm(vecs, axis=-1), np.ones(2), atol=1e-6)
        self.assertGreater(vecs[0, 0], 0.9)
        self.assertGreater(vecs[1, 1], 0.9)

    def test_auto_prefers_dml_when_allowed(self):
        with patch(
            "aic51.packages.analyse.features.bge_onnx.available_providers",
            return_value=["DmlExecutionProvider", "CPUExecutionProvider"],
        ):
            choice, warning = resolve_provider_choice("auto", allow_gpu=True)
        self.assertEqual(choice, "dml")
        self.assertIsNone(warning)

    def test_auto_falls_back_without_claiming_dml(self):
        with patch(
            "aic51.packages.analyse.features.bge_onnx.available_providers",
            return_value=["CPUExecutionProvider"],
        ):
            choice, warning = resolve_provider_choice("auto", allow_gpu=True)
        self.assertEqual(choice, "cpu")
        self.assertIn("DirectML unavailable", warning or "")

    def test_no_gpu_forces_cpu_even_if_dml_exists(self):
        with patch(
            "aic51.packages.analyse.features.bge_onnx.available_providers",
            return_value=["DmlExecutionProvider", "CPUExecutionProvider"],
        ):
            choice, warning = resolve_provider_choice("auto", allow_gpu=False)
        self.assertEqual(choice, "cpu")
        self.assertIsNotNone(warning)

    def test_explicit_dml_without_provider_raises(self):
        with patch(
            "aic51.packages.analyse.features.bge_onnx.available_providers",
            return_value=["CPUExecutionProvider"],
        ):
            with self.assertRaises(DirectMLUnavailable):
                resolve_provider_choice("dml", allow_gpu=True)

    def test_provider_choice_does_not_use_torch_cuda(self):
        with patch(
            "aic51.packages.analyse.features.bge_onnx.available_providers",
            return_value=["DmlExecutionProvider", "CPUExecutionProvider"],
        ):
            choice, _ = resolve_provider_choice("auto", allow_gpu=True)
        self.assertEqual(choice, "dml")

    def test_directml_session_disables_mem_pattern_and_parallel_execution(self):
        captured = {}

        class FakeOptions:
            def __init__(self):
                self.graph_optimization_level = None
                self.log_severity_level = None
                self.enable_mem_pattern = True
                self.execution_mode = None

        class FakeSession:
            def __init__(self, path, sess_options, providers, disabled_optimizers=None):
                captured["path"] = path
                captured["options"] = sess_options
                captured["providers"] = providers
                captured["disabled_optimizers"] = disabled_optimizers

        class FakeOrt:
            class GraphOptimizationLevel:
                ORT_ENABLE_ALL = "all"

            class ExecutionMode:
                ORT_SEQUENTIAL = "sequential"

            SessionOptions = FakeOptions
            InferenceSession = FakeSession

        with patch(
            "aic51.packages.analyse.features.bge_onnx.import_onnxruntime",
            return_value=FakeOrt,
        ):
            create_session(Path("bge.onnx"), "dml")

        self.assertFalse(captured["options"].enable_mem_pattern)
        self.assertEqual(captured["options"].execution_mode, "sequential")
        self.assertEqual(captured["providers"][0][0], "DmlExecutionProvider")

    def test_length_buckets_group_short_and_long(self):
        self.assertEqual(length_bucket(12), 32)
        self.assertEqual(length_bucket(70), 80)
        self.assertEqual(length_bucket(256), 256)

    def test_ready_batches_pad_to_batch_max_not_global_max(self):
        tokens = [
            [0, 2],
            [0, 3, 4, 2],
            [0] + list(range(10, 80)) + [2],
        ]
        ready = build_ready_batches(tokens, batch_size=2, max_length=256)
        self.assertGreaterEqual(len(ready), 2)
        short = next(batch for batch in ready if batch.pad_width < 40)
        self.assertLess(short.pad_width, 80)
        self.assertEqual(short.encoded["input_ids"].dtype, np.int64)
        self.assertEqual(short.encoded["attention_mask"].dtype, np.int64)

    def test_ready_batches_preserve_original_indices(self):
        tokens = [[0, 2], [0, 1, 1, 1, 2], [0, 5, 2]]
        ready = build_ready_batches(tokens, batch_size=2, max_length=32)
        seen = []
        for batch in ready:
            seen.extend(batch.indices)
        self.assertEqual(sorted(seen), [0, 1, 2])

    def test_pad_token_lists_attention_mask(self):
        encoded = pad_token_lists([[0, 2], [0, 3, 4, 2]])
        self.assertEqual(encoded["input_ids"].shape, (2, 4))
        np.testing.assert_array_equal(encoded["attention_mask"][0], [1, 1, 0, 0])
        np.testing.assert_array_equal(encoded["attention_mask"][1], [1, 1, 1, 1])

    def test_preload_fits_current_corpus_estimate(self):
        self.assertLess(estimate_preload_bytes(322924, 256), 4 * 1024 * 1024 * 1024)
        self.assertEqual(preload_shard_size(322924, 256), 322924)

    def test_adaptive_batch_grows_for_short_sequences(self):
        self.assertEqual(
            adaptive_batch_limit(256, ref_batch=16, ref_seq=256, max_batch=128),
            16,
        )
        self.assertEqual(
            adaptive_batch_limit(128, ref_batch=16, ref_seq=256, max_batch=128),
            64,
        )
        self.assertEqual(
            adaptive_batch_limit(2, ref_batch=16, ref_seq=256, max_batch=128),
            128,
        )

    def test_adaptive_pack_uses_more_rows_on_short_docs(self):
        tokens = [[0, 2] for _ in range(40)]
        ready = build_ready_batches(
            tokens,
            batch_size=16,
            max_length=256,
            max_batch=32,
            adapt="auto",
        )
        self.assertEqual(len(ready), 2)
        self.assertEqual(len(ready[0].indices), 32)
        self.assertEqual(ready[0].pad_width, 2)

    def test_adaptive_pack_keeps_full_length_at_ref_batch(self):
        tokens = [[0] + list(range(3, 257)) + [2] for _ in range(20)]
        ready = build_ready_batches(
            tokens,
            batch_size=16,
            max_length=256,
            max_batch=128,
            adapt="auto",
        )
        self.assertEqual([len(batch.indices) for batch in ready], [16, 4])
        self.assertEqual(ready[0].pad_width, 256)

    def test_adapt_off_keeps_fixed_batch_size(self):
        tokens = [[0, 2] for _ in range(20)]
        ready = build_ready_batches(
            tokens,
            batch_size=16,
            max_length=256,
            max_batch=128,
            adapt="off",
        )
        self.assertEqual([len(batch.indices) for batch in ready], [16, 4])


if __name__ == "__main__":
    unittest.main()
