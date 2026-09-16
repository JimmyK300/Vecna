"""Meaningful parity tests against functions extracted from exact main source."""
from __future__ import annotations

import ast
import copy
import json
import math
import re
import sys
import unittest
import unicodedata
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from fusion_study import (ContractError, ARMS, current_scores, digest_bytes, digest_json,
                          nominal_weights, study_query, transform, validate_config)
from collect_fusion_providers import capture_query, SearchOnlyDatabase


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


if __name__ == "__main__":
    unittest.main()
