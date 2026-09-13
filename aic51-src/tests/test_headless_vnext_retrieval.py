from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "aic51-src" / "script" / "run_headless_vnext_retrieval.py"
SPEC = importlib.util.spec_from_file_location("run_headless_vnext_retrieval", RUNNER_PATH)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(runner)


class FakeEncoder:
    def get_text_features(self, _query):
        return [0.1, 0.2, 0.3]


class FakeDatabase:
    def search(self, *args, **kwargs):
        field = kwargs.get("anns_field", args[4] if len(args) >= 5 else "")
        return [[{"distance": 0.5, "entity": {"frame_id": f"L21_V001#1", "field": field}}]]


class FakeSearcher:
    def __init__(self):
        self._extractors = {
            name: {"feature_extractor": FakeEncoder()}
            for name in (
                "language_qwen_vl",
                "language_siglip_so400m-384",
                "text_bge_m3",
            )
        }
        self._database = FakeDatabase()
        self.calls = None

    def search_multimodal(self, *args, **kwargs):
        self.calls = (args, kwargs)
        for target in args[3]:
            encoder_name = {
                "qwen_vl": "language_qwen_vl",
                "image_siglip_so400m-384": "language_siglip_so400m-384",
            }[target]
            self._extractors[encoder_name]["feature_extractor"].get_text_features(args[0])
            self._database.search([], anns_field=target)
        if kwargs["ocr_weight"] > 0:
            self._extractors["text_bge_m3"]["feature_extractor"].get_text_features(args[0])
            self._database.search([], anns_field="ocr_sparse")
            self._database.search([], anns_field="ocr_dense")
        if kwargs["asr_weight"] > 0:
            self._extractors["text_bge_m3"]["feature_extractor"].get_text_features(args[0])
            self._database.search([], anns_field="asr_sparse")
            self._database.search([], anns_field="asr_dense")
        return {
            "results": [
                {
                    "entity": {"frame_id": "L21_V001#1"},
                    "distance": 0.5,
                    "scores": {"final": 0.5},
                }
            ]
        }


class HeadlessVNextRetrievalPacketTests(unittest.TestCase):
    def test_authority_is_exact_48_row_p0_p1_without_p2(self):
        result = runner.validate_manifest()
        self.assertEqual(result["counts"]["execution_rows"], 48)
        self.assertEqual(result["counts"]["p0_rows"], 23)
        self.assertEqual(result["counts"]["p1_rows"], 25)
        self.assertEqual(result["counts"]["p2_rows"], 0)
        self.assertEqual(result["counts"]["range_scoreable_non_trake"], 44)

    def test_registry_is_frozen_and_deterministic(self):
        first = runner.validate_registry()
        second = runner.validate_registry()
        self.assertEqual(first, second)
        self.assertEqual(
            sorted(first["arms"]),
            [
                "all_fusion_v1",
                "qwen_only_v1",
                "semantic_evidence_shadow_v1",
                "siglip_only_v1",
            ],
        )

    def test_frozen_arm_parameters_disable_rewriting(self):
        for name in ("qwen_only_v1", "all_fusion_v1", "siglip_only_v1"):
            arm = runner.FROZEN_ARMS[name]
            self.assertFalse(arm["reranking"])
            self.assertFalse(arm["llm_query_expansion"])
            self.assertFalse(arm["yolo_query_rewrite"])
            self.assertFalse(arm["auto_translate"])
            self.assertFalse(arm["en_to_vi_translate"])
            self.assertEqual(arm["top_k"], 20)
            self.assertEqual(arm["nprobe"], 32)
            self.assertEqual(arm["temporal_k"], 2000)

        self.assertEqual(
            runner.FROZEN_ARMS["all_fusion_v1"]["target_features"],
            ["qwen_vl", "image_siglip_so400m-384"],
        )
        self.assertEqual(runner.FROZEN_ARMS["all_fusion_v1"]["ocr_weight"], 0.25)
        self.assertEqual(runner.FROZEN_ARMS["all_fusion_v1"]["asr_weight"], 0.25)
        self.assertEqual(runner.FROZEN_ARMS["all_fusion_v1"]["ocr_alpha"], 0.7)
        self.assertEqual(runner.FROZEN_ARMS["all_fusion_v1"]["asr_alpha"], 0.7)

    def test_instrumented_synthetic_call_proves_all_six_provider_paths(self):
        audit = runner.ProviderAudit()
        searcher = FakeSearcher()
        runner.instrument_searcher(searcher, audit)
        response = runner.invoke_frozen_search(searcher, "fixture", "all_fusion_v1")
        report = audit.assert_requested(runner.FROZEN_ARMS["all_fusion_v1"]["provider_paths"])
        self.assertTrue(report["all_requested_nonzero"])
        self.assertEqual(set(report["paths"]), set(runner.REQUIRED_PROVIDER_PATHS))
        self.assertTrue(all(item["nonzero"] for item in report["paths"].values()))
        self.assertEqual(response["results"][0]["entity"]["frame_id"], "L21_V001#1")
        args, kwargs = searcher.calls
        self.assertEqual(args[1:3], (0, 20))
        self.assertEqual(args[3], ["qwen_vl", "image_siglip_so400m-384"])
        self.assertEqual(kwargs["nprobe"], 32)
        self.assertEqual(kwargs["temporal_k"], 2000)
        self.assertEqual(kwargs["ocr_alpha"], 0.7)
        self.assertEqual(kwargs["asr_alpha"], 0.7)
        self.assertFalse(kwargs["auto_translate"])
        self.assertFalse(kwargs["en_to_vi_translate"])

        runner.invoke_frozen_search(
            searcher,
            "fixture",
            "all_fusion_v1",
            visual_query_translate=True,
        )
        _, translated_kwargs = searcher.calls
        self.assertTrue(translated_kwargs["auto_translate"])
        self.assertFalse(translated_kwargs["en_to_vi_translate"])

    def test_provider_audit_stops_when_one_path_has_no_positive_hit(self):
        audit = runner.ProviderAudit()
        for path_name, spec in runner.REQUIRED_PROVIDER_PATHS.items():
            for field in spec["fields"]:
                audit.record_search(field, 1, 0 if path_name == "asr_dense_bge_m3" else 1)
            for encoder_name in spec["encoder_names"]:
                audit.record_encoder(encoder_name)
        with self.assertRaisesRegex(runner.PacketError, "asr_dense_bge_m3"):
            audit.assert_requested(runner.FROZEN_ARMS["all_fusion_v1"]["provider_paths"])

    def test_result_serializer_preserves_order_and_timeline(self):
        response = {
            "results": [
                {
                    "entity": {"frame_id": "L30_V046#6350"},
                    "distance": 0.9,
                    "scores": {"final": 0.9, "clip": 0.9},
                    "time_line": ["L30_V046#6350", "L30_V046#6360"],
                },
                {
                    "entity": {"frame_id": "L30_V046#6860"},
                    "distance": 0.8,
                    "scores": {"final": 0.8},
                },
            ]
        }
        rows = runner.convert_search_response(response, "all_fusion_v1", 20)
        self.assertEqual([row["rank"] for row in rows], [1, 2])
        self.assertEqual([row["frame_id"] for row in rows], [6350, 6860])
        self.assertEqual(rows[0]["time_line"], [6350, 6360])
        self.assertEqual(rows[0]["video_id"], "L30_V046")

    def test_complete_empty_rankings_are_accepted_by_issue76_scorer(self):
        manifest = runner.load_json(runner.MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "complete.jsonl"
            path.write_text(
                "".join(
                    json.dumps(
                        {
                            "canonical_query_id": row["canonical_query_id"],
                            "results": [],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                    for row in manifest["records"]
                ),
                encoding="utf-8",
            )
            result = runner.validate_saved_rankings(path)
        self.assertEqual(result["status"], "scorer_compatible")
        self.assertEqual(result["query_rows"], 48)

    def test_incomplete_47_row_arm_is_rejected(self):
        manifest = runner.load_json(runner.MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incomplete.jsonl"
            path.write_text(
                "".join(
                    json.dumps({"canonical_query_id": row["canonical_query_id"], "results": []}) + "\n"
                    for row in manifest["records"][:-1]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "incomplete saved-ranking arm"):
                runner.validate_saved_rankings(path)

    def test_preflight_does_not_claim_runtime_provider_proof(self):
        result = runner.preflight("all_fusion_v1", live=False)
        self.assertEqual(result["status"], "preflight_pass")
        self.assertEqual(result["scope"]["retrieval_queries_executed"], 0)
        self.assertFalse(result["provider_audit"]["nonzero_contribution_proof"])
        self.assertEqual(
            result["provider_audit"]["required_paths"],
            runner.FROZEN_ARMS["all_fusion_v1"]["provider_paths"],
        )

    def test_cpu_is_an_explicit_execution_device_without_arm_changes(self):
        result = runner.runtime_versions("cpu")
        self.assertEqual(result["device"]["requested"], "cpu")
        self.assertEqual(runner.FROZEN_ARMS["qwen_only_v1"]["top_k"], 20)
        self.assertEqual(runner.FROZEN_ARMS["all_fusion_v1"]["ocr_weight"], 0.25)

    def test_experimental_translation_chunks_oversized_external_inputs(self):
        text = "word " * 120
        chunks = runner._translation_chunks(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 450 for chunk in chunks))
        self.assertEqual(" ".join(chunks), " ".join(text.split()))

    def test_benchmark_overlay_disables_dict_style_llm_config(self):
        result = runner.apply_benchmark_config(runner.ROOT / "config.yaml")
        self.assertTrue(result["llm_query_expansion_off"])
        from aic51.packages.config import GlobalConfig

        self.assertEqual(GlobalConfig.get("searcher", "llm"), {"enable": False})


if __name__ == "__main__":
    unittest.main()
