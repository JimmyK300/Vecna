"""Meaningful parity tests against functions extracted from exact main source."""
from __future__ import annotations

import ast
import copy
import json
import math
import re
import sys
import tempfile
import unittest
import unicodedata
from collections import UserList, UserDict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from fusion_study import (ContractError, ARMS, current_scores, digest_bytes, digest_json,
                          nominal_weights, run, run_identity_digest, study_query, transform, validate_config)
from collect_fusion_providers import (capture_query, configure_cpu_threads, metadata_json,
                                      preprocessing_identity, SearchOnlyDatabase)
from evaluate_fusion_study import contribution_ablations, matched_qwen_items, paired, score_arm, select_global_arm
from analyze_reranker import load_scorer


class Array:
    def __init__(self, flat=False):
        self.flat = flat
    def reshape(self, *args):
        return Array(True)
    def tolist(self):
        return [0.1] if self.flat else [[0.1]]


class Encoder:
    def get_text_features(self, query):
        return Array()


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def search(self, **kwargs):
        self.calls.append(kwargs)
        return [self.rows.get(kwargs["anns_field"], [])[:kwargs["limit"]]]


def source_class():
    source = (ROOT / "outputs/fusion/source/searcher_main.py").read_text()
    assert digest_bytes(source.encode()) == "6f94bdd147c4b2b29b522a1f4bbbf004fb726fdfdf68a7cb316a4aec9e869e51"
    tree = ast.parse(source)
    wanted = {"_normalize_scores", "_text_field_from_index_field", "_extract_query_texts",
              "_search_text_component", "_filter_exclude_videos", "_similarity_search",
              "_get_video_filter"}
    source_searcher = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Searcher")
    source_searcher.body = [node for node in source_searcher.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name in {"remove_diacritics", "_build_exact_regex", "check_exact_phrases"}]
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                             *helpers, source_searcher], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"logger": SimpleNamespace(info=lambda *a: None, warning=lambda *a: None),
                 "_check_cancelled": lambda event: None, "np": SimpleNamespace(asarray=lambda x: x),
                 "re": re, "unicodedata": unicodedata}
    exec(compile(module, "inspected-main-searcher-subset", "exec"), namespace)
    return namespace["Searcher"]


def config(**changes):
    result = json.loads((ROOT / "outputs/fusion/frozen_config.json").read_text())
    result.update(changes)
    return result


def hit(frame, score, text=""):
    return {"entity": {"frame_id": frame, "ocr": text, "asr": text}, "distance": score}


def fixture(rows=None, **changes):
    cfg = config(**changes)
    searcher = source_class()()
    searcher._ocr_name, searcher._asr_name = "ocr_sparse", "asr_sparse"
    searcher._ocr_dense_name, searcher._asr_dense_name = "ocr_dense", "asr_dense"
    searcher._features = {"qwen_vl": "qwen", "image_siglip_so400m-384": "siglip",
                          "ocr_dense": "bge", "asr_dense": "bge"}
    searcher._extractors = {name: {"feature_extractor": Encoder()} for name in ("qwen", "siglip", "bge")}
    defaults = {
        "qwen_vl": [hit("A#0001", 0.9), hit("B#0002", 0.8)],
        "image_siglip_so400m-384": [hit("B#0002", 0.5), hit("C#0003", 0.3)],
        "ocr_sparse": [hit("C#0003", 12), hit("B#0002", 3)],
        "asr_sparse": [hit("D#0004", 4), hit("A#0001", 2)],
        "ocr_dense": [hit("C#0003", 0.8), hit("A#0001", 0.4)],
        "asr_dense": [hit("D#0004", 0.7), hit("B#0002", 0.6)],
    }
    database = FakeDatabase(defaults if rows is None else rows)
    searcher._database = database
    row = capture_query(searcher, {"query_id": "synthetic", "query_text": "unchanged full query"}, cfg, "0" * 64)
    return cfg, row, searcher, database


class FusionTests(unittest.TestCase):
    def test_source_parity_four_active_providers_and_exact_weights(self):
        cfg, row, _, database = fixture()
        result = study_query(row, cfg)
        self.assertTrue(result["current_control_replay_verified"])
        self.assertEqual(set(result["arms"]), set(ARMS))
        expected = {"A#0001": 0.5 * 0.9 / 1.3 + 0.25 * 0.5,
                    "B#0002": 0.5 + 0.25 * 0.25,
                    "C#0003": 0.5 * 0.3 / 1.3 + 0.25,
                    "D#0004": 0.25}
        for frame in result["arms"]["fusion_current_control"]["frames"]:
            self.assertAlmostEqual(frame["score"], expected[frame["frame_id"]])
            self.assertAlmostEqual(frame["score"], sum(frame["contributions"].values()))
        self.assertEqual(len(database.calls), 4)
        self.assertTrue(all(call["limit"] == 100 for call in database.calls))
        self.assertEqual(row["providers"]["ocr_sparse"]["raw_call"]["requested_native_limit"], 200)
        self.assertEqual(row["providers"]["ocr_dense"]["state"], "disabled")

    def test_source_parity_six_active_with_nested_text_normalization(self):
        cfg, row, _, database = fixture(ocr_alpha=0.5, asr_alpha=0.5)
        result = study_query(row, cfg)
        self.assertEqual(len(database.calls), 6)
        self.assertTrue(all(provider["state"] == "ok" for provider in row["providers"].values()))
        for frame in result["arms"]["fusion_current_control"]["frames"]:
            self.assertAlmostEqual(frame["score"], sum(frame["contributions"].values()))

    def test_quote_filter_and_boost_use_exact_main_source(self):
        cfg, _, searcher, _ = fixture()
        searcher._database = FakeDatabase({"ocr_sparse": [hit("A#1", 10, "wrong text"),
                                                           hit("B#2", 4, "news about ca phe")],
                                           "qwen_vl": [hit("C#3", 0.7)]})
        row = capture_query(searcher, {"query_id": "quoted", "query_text": 'find "cà phê"'}, cfg, "0" * 64)
        provider = row["providers"]["ocr_sparse"]
        self.assertEqual(provider["raw_hit_count"], 2)
        self.assertEqual(provider["hits"][0]["frame_id"], "B#2")
        self.assertEqual(provider["hits"][0]["score"], 6)
        self.assertEqual(provider["raw_call"]["requested_native_limit"], 500)

    def test_all_arms_use_same_exported_tie_order(self):
        rows = {"qwen_vl": [hit("B#2", 1), hit("A#1", 1)],
                "image_siglip_so400m-384": [hit("D#4", 1), hit("C#3", 1)]}
        cfg, row, _, _ = fixture(rows, ocr_weight=0.0, asr_weight=0.0)
        result = study_query(row, cfg)
        for arm in ("fusion_current_control", "fusion_minmax_sum", "fusion_robust_z_sum", "fusion_softmax_sum"):
            self.assertEqual([f["frame_id"] for f in result["arms"][arm]["frames"]], row["candidate_tie_order"])

    def test_frame_truncation_precedes_video_collapse(self):
        rows = {"qwen_vl": [hit("A#1", 0.9), hit("A#2", 0.8), hit("B#3", 0.7)]}
        cfg, row, _, _ = fixture(rows, ocr_weight=0.0, asr_weight=0.0, output_frame_k=2)
        result = study_query(row, cfg)
        for arm in ARMS:
            videos = result["arms"][arm]["videos"]
            self.assertEqual([v["video_id"] for v in videos], ["A"])
        self.assertEqual(result["candidate_count"], 3)

    def test_signed_cosine_exact_main_maxscale(self):
        cfg, row, _, _ = fixture({"qwen_vl": [hit("A#1", 0.5), hit("B#2", -0.2)]},
                                 ocr_weight=0.0, asr_weight=0.0)
        scores = study_query(row, cfg)["arms"]["fusion_current_control"]["frames"]
        self.assertEqual(scores[1]["score"], -0.4)

    def test_equal_lists_and_zero_mad_policy(self):
        self.assertEqual(transform({"A": 2, "B": 2}, "fusion_minmax_sum")[0], {"A": 1, "B": 1})
        robust, diagnostics = transform({"A": 2, "B": 2, "C": 100}, "fusion_robust_z_sum")
        self.assertTrue(diagnostics["zero_mad_fallback"])
        self.assertGreater(robust["C"], robust["A"])
        self.assertEqual(transform({"A": 2}, "fusion_robust_z_sum")[0]["A"], 0.5)

    def test_softmax_numerically_stable_and_not_calibrated_probability(self):
        values, _ = transform({"A": 10000, "B": 9999, "C": -10000}, "fusion_softmax_sum")
        self.assertAlmostEqual(sum(values.values()), 1)
        self.assertTrue(all(math.isfinite(value) for value in values.values()))
        self.assertGreater(values["A"], values["B"])

    def test_no_provider_weight_renormalization_on_missing(self):
        cfg, row, _, _ = fixture({"qwen_vl": [hit("A#1", 0.9)]})
        frame = study_query(row, cfg)["arms"]["fusion_minmax_sum"]["frames"][0]
        self.assertEqual(frame["score"], 0.25)
        self.assertEqual(row["providers"]["siglip"]["state"], "empty")

    def test_source_control_mismatch_is_hard_stop(self):
        cfg, row, _, _ = fixture()
        row["current_control_reference"][0]["score"] += 0.01
        with self.assertRaisesRegex(ContractError, "control score"):
            study_query(row, cfg)

    def test_input_contract_rejects_ambiguity_and_corruption(self):
        cfg, original, _, _ = fixture()
        mutations = [
            lambda row: row.pop("candidate_tie_order"),
            lambda row: row.update(query_text="rewritten query"),
            lambda row: row["providers"]["qwen"].update(score_orientation="lower_is_better"),
            lambda row: row["providers"]["qwen"]["hits"][0].update(score=float("nan")),
            lambda row: row["providers"]["qwen"]["hits"].append(row["providers"]["qwen"]["hits"][0]),
            lambda row: row["providers"]["qwen"].update(state="failed", hits=[]),
            lambda row: row["transformations"].update(translation=True),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                row = copy.deepcopy(original)
                mutation(row)
                with self.assertRaises(ContractError):
                    study_query(row, cfg)

    def test_input_objects_are_unchanged(self):
        cfg, row, _, _ = fixture()
        frozen = copy.deepcopy(row)
        study_query(row, cfg)
        self.assertEqual(row, frozen)

    def test_config_never_invents_project_weights_or_parameters(self):
        for changes in ({"weight_authority": None}, {"alpha_authority": None},
                        {"rrf_k": 20}, {"softmax_temperature": 0.1},
                        {"ocr_weight": 0.8, "asr_weight": 0.5}, {"ocr_alpha": float("inf")}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                validate_config(config(**changes))

    def test_search_only_adapter_never_auto_loads_or_mutates(self):
        class Client:
            def search(self, *args, **kwargs):
                return [[hit("A#1", 0.9)]]
        adapter = SearchOnlyDatabase(Client(), "existing", {"frame_id", "qwen_vl"})
        result = adapter.search(data=[[0.1]], anns_field="qwen_vl", search_params={"metric_type": "COSINE"})
        self.assertEqual(result[0][0]["entity"]["frame_id"], "A#1")
        self.assertFalse(hasattr(adapter, "insert"))
        self.assertFalse(hasattr(adapter, "__del__"))
        with self.assertRaises(ContractError):
            adapter.search(data=[[0.1]], anns_field="missing", search_params={"metric_type": "COSINE"})

    def test_metadata_json_preserves_types_and_rejects_unstable_values(self):
        metadata = UserDict({"fields": UserList([{"name": "vector", "dim": 768}]),
                             "enabled": True, "score": 0.5, "aliases": ("a", "b"), "empty": None})
        expected = {"fields": [{"name": "vector", "dim": 768}], "enabled": True,
                    "score": 0.5, "aliases": ["a", "b"], "empty": None}
        normalized = metadata_json(metadata)
        self.assertEqual(normalized, expected)
        self.assertIs(type(normalized["fields"][0]["dim"]), int)
        self.assertIs(type(normalized["enabled"]), bool)
        self.assertEqual(digest_json(normalized), digest_json(expected))
        for unsupported in ({1: "non-string key"}, {"unordered"}, object(), float("nan"), b"bytes"):
            with self.subTest(value_type=type(unsupported)), self.assertRaises(ContractError):
                metadata_json(unsupported)

    def test_metadata_json_real_protobuf_repeated_containers_and_message(self):
        try:
            from google.protobuf.descriptor_pb2 import FileDescriptorProto
        except ImportError:
            self.skipTest("protobuf is not installed in this analysis runtime")
        proto = FileDescriptorProto(name="metadata.proto", dependency=["a.proto", "b.proto"],
                                    public_dependency=[0, 1])
        proto.message_type.add(name="Example")
        normalized = metadata_json({"strings": proto.dependency, "integers": proto.public_dependency,
                                    "messages": proto.message_type, "message": proto})
        self.assertEqual(normalized["strings"], ["a.proto", "b.proto"])
        self.assertEqual(normalized["integers"], [0, 1])
        self.assertEqual(normalized["messages"], [{"name": "Example"}])
        self.assertEqual(normalized["message"]["name"], "metadata.proto")
        self.assertEqual(normalized["message"]["public_dependency"], [0, 1])
        self.assertEqual(json.loads(json.dumps(normalized)), normalized)

    def test_cpu_parallelism_is_bounded_and_actual_settings_are_recorded(self):
        class Runtime:
            def __init__(self):
                self.requests = []
            def set_num_threads(self, count):
                self.requests.append(count)
            def get_num_threads(self):
                return self.requests[-1]
            def get_num_interop_threads(self):
                return 4
        runtime = Runtime()
        identity = configure_cpu_threads(runtime, 6)
        self.assertEqual(identity, {"requested_intraop_threads": 6,
                                    "actual_intraop_threads": 6, "actual_interop_threads": 4})
        for invalid in (0, -1, True, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(ContractError):
                configure_cpu_threads(runtime, invalid)
        self.assertEqual(runtime.requests, [6])

    def test_tokenizer_identity_includes_vocab_and_template(self):
        class Tokenizer:
            chat_template = "template A"
            special_tokens_map = {"eos_token": "END"}
            def get_vocab(self):
                return {"token": 1, "END": 2}
        tokenizer = Tokenizer()
        extractor = SimpleNamespace(_tokenizer=tokenizer)
        first = preprocessing_identity(extractor, SimpleNamespace())
        tokenizer.chat_template = "template B"
        second = preprocessing_identity(extractor, SimpleNamespace())
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assertTrue(first["text_tokenization_bound"])

    def test_pretrained_config_loader_is_never_called_as_getter(self):
        class Config:
            def to_dict(self):
                return {"max_length": 100}
            @classmethod
            def get_config_dict(cls, pretrained_model_name_or_path, **kwargs):
                raise AssertionError("configuration loader must never be called")
        class Tokenizer:
            def get_vocab(self):
                return {"token": 1}
        result = preprocessing_identity(SimpleNamespace(_tokenizer=Tokenizer()), SimpleNamespace(config=Config()))
        self.assertTrue(result["text_tokenization_bound"])

    def test_completed_manifest_and_one_run_identity_required(self):
        cfg, row, _, _ = fixture(expected_query_count=1)
        projection = {row["query_id"]: row["query_text_sha256"]}
        cfg["canonical_query_projection_sha256"] = digest_json(projection)
        row["config_sha256"] = digest_json(cfg)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            queries = [{"query_id": row["query_id"], "query_text": row["query_text"]}]
            (path / "queries.jsonl").write_text(json.dumps(queries[0]) + "\n")
            manifest = {"status": "complete", "scope": "full_query_projection", "rows_written": 1,
                        "run_id": "synthetic-run", "identity": {"fixture": "exact source replay"},
                        "collector_sha256": "0" * 64, "config_sha256": digest_json(cfg),
                        "canonical_queries_sha256": digest_bytes((path / "queries.jsonl").read_bytes())}
            manifest["run_identity_sha256"] = run_identity_digest(manifest)
            row["run_identity_sha256"] = manifest["run_identity_sha256"]
            (path / "rankings.jsonl").write_text(json.dumps(row) + "\n")
            manifest["rankings_sha256"] = digest_bytes((path / "rankings.jsonl").read_bytes())
            (path / "manifest.json").write_text(json.dumps(manifest))
            (path / "config.json").write_text(json.dumps(cfg))
            args = (path / "rankings.jsonl", path / "config.json", path / "queries.jsonl")
            result = run(*args, path / "output.jsonl", path / "manifest.json")
            self.assertEqual(result["queries"], 1)
            manifest["status"] = "failed_closed"
            (path / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ContractError, "manifest is incomplete"):
                run(*args, path / "blocked-output.jsonl", path / "manifest.json")
            manifest["status"] = "complete"
            row["run_identity_sha256"] = "f" * 64
            (path / "rankings.jsonl").write_text(json.dumps(row) + "\n")
            manifest["rankings_sha256"] = digest_bytes((path / "rankings.jsonl").read_bytes())
            (path / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ContractError, "mixed or foreign"):
                run(*args, path / "blocked-output.jsonl", path / "manifest.json")

    def test_global_selection_is_one_arm_with_paired_rescues_regressions(self):
        rows = []
        def score(rank):
            return {"first_success_rank": rank,
                    "metrics": {**{f"R@{k}": float(rank is not None and rank <= k) for k in (1, 5, 10, 20)},
                                "MRR@20": 1 / rank if rank else 0}}
        for query_id, before, after in (("q0", 1, 2), ("q1", None, 1), ("q2", 20, None)):
            row = {"query_id": query_id, "arms": {arm: {"distinct_video": score(before)} for arm in ARMS}}
            row["arms"]["fusion_rrf"]["distinct_video"] = score(after)
            rows.append(row)
        self.assertEqual(select_global_arm(rows), "fusion_rrf")
        comparison = paired(rows, "distinct_video", "fusion_rrf", "fusion_current_control")
        self.assertEqual(comparison["metrics"]["R@20"]["improved_query_ids"], ["q1"])
        self.assertEqual(comparison["metrics"]["R@20"]["regressed_query_ids"], ["q2"])

    def test_video_collapse_and_frame_position_scoring_stay_distinct(self):
        cfg, raw, _, _ = fixture({"qwen_vl": [hit("A#1", .9), hit("A#2", .8), hit("B#3", .7)]})
        frames, videos = matched_qwen_items(raw, cfg)
        target = {"truth_tier": "frozen_headless_benchmark_truth", "task_type": "kis",
                  "accepted_video_id": "B", "accepted_ranges": [{"start_frame": 3, "end_frame": 3}]}
        scorer = load_scorer(ROOT / "reference/evaluate_reranker_fusion.py")
        result = score_arm(frames, videos, target, scorer)
        self.assertEqual(result["distinct_video"]["first_success_rank"], 2)
        self.assertEqual(result["frame_position_video"]["first_success_rank"], 3)
        self.assertEqual(result["frozen_frame_range_event"]["first_success_rank"], 3)

    def test_ablation_preserves_tiny_surviving_softmax_contribution(self):
        cfg, raw, _, _ = fixture({"qwen_vl": [hit("A#1", .9), hit("B#2", .8)],
                                  "ocr_sparse": [hit("C#3", 100), hit("A#1", 60)]})
        raw["candidate_tie_order"] = ["B#2", "A#1", "C#3"]
        tiny = .25 * transform({"C#3": 100, "A#1": 60}, "fusion_softmax_sum")[0]["A#1"]
        large = .25 * transform({"A#1": .9, "B#2": .8}, "fusion_softmax_sum")[0]["A#1"]
        self.assertGreater(tiny, 0)
        self.assertEqual((large + tiny) - large, 0)
        target = {"truth_tier": "frozen_headless_benchmark_truth", "task_type": "kis",
                  "accepted_video_id": "A", "accepted_ranges": [{"start_frame": 1, "end_frame": 1}]}
        scorer = load_scorer(ROOT / "reference/evaluate_reranker_fusion.py")
        result = contribution_ablations(raw, cfg, target, scorer)
        self.assertEqual(result["fusion_softmax_sum"]["qwen"]["first_success_rank"], 2)


if __name__ == "__main__":
    unittest.main()
