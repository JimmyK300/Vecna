"""Issue #89: exercise production text aggregation without models or retrieval.

Only external I/O is substituted. AST isolation avoids importing the model/DB
stack; all scoring, normalization, phrase filtering and query helpers come from
the production file. Frozen method pins make that isolation reviewable.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from typing import Callable
import unicodedata
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "aic51/packages/search/searcher.py"
FIXED_METHOD_SHA256 = "92a8ff1f7fdca8a6a5b945fdd805690ab175abbb0204ca05c23f1808d246277d"
BASE_METHOD_SHA256 = "8f772e5e97046e2a310c0c680cf7786df1bb6da5232471ee4a02dd3a40c5d409"
OLD_LOOP = "        for fid in all_frame_ids:\n"
NEW_LOOP = (
    "        # Canonical frame ID order breaks exact score ties independently of hash seed.\n"
    "        # The stable descending score sort below preserves this order only for ties.\n"
    "        for fid in sorted(all_frame_ids):\n"
)
SEEDS = ("0", "1", "82")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class QuietLogger:
    def info(self, *args, **kwargs):
        pass


class ArrayConversion:
    """Substitute only asarray(...).reshape(-1).tolist() for a fixed test vector."""
    def __init__(self, values):
        self.values = values

    def reshape(self, shape):
        if shape != -1:
            raise AssertionError("Unexpected dense conversion")
        return self

    def tolist(self):
        def flatten(value):
            if isinstance(value, (list, tuple)):
                return [item for part in value for item in flatten(part)]
            return [value]
        return flatten(self.values)


class NumpyConversionOnly:
    asarray = staticmethod(ArrayConversion)


def production_harness(legacy=False):
    source = SOURCE.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    module = ast.parse(source)
    searcher = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "Searcher")
    method = next(n for n in searcher.body if isinstance(n, ast.FunctionDef) and n.name == "_search_text_component")
    method_source = "\n".join(source.splitlines()[method.lineno - 1:method.end_lineno]) + "\n"
    if sha256(method_source.encode()) != FIXED_METHOD_SHA256:
        raise AssertionError("Production text method changed; review and update its frozen test pin")
    if method_source.count(NEW_LOOP) != 1:
        raise AssertionError("Expected exactly the reviewed deterministic loop")
    if legacy:
        original = method_source.replace(NEW_LOOP, OLD_LOOP)
        if sha256(original.encode()) != BASE_METHOD_SHA256:
            raise AssertionError("Reconstructed pre-fix production method does not match its pin")
        if source.count(method_source) != 1:
            raise AssertionError("Production method is not unique")
        source = source.replace(method_source, original)
        module = ast.parse(source)
        searcher = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "Searcher")

    helper_names = {"_check_cancelled", "remove_diacritics", "_build_exact_regex", "check_exact_phrases"}
    method_names = {"_normalize_scores", "_text_field_from_index_field", "_extract_query_texts", "_search_text_component"}
    helpers = [n for n in module.body if isinstance(n, ast.FunctionDef) and n.name in helper_names]
    cancellation = [n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "SearchCancelledException"]
    methods = [n for n in searcher.body if isinstance(n, ast.FunctionDef) and n.name in method_names]
    if ({n.name for n in helpers} != helper_names or
            {n.name for n in methods} != method_names or len(cancellation) != 1):
        raise AssertionError("Incomplete production dependency selection")
    selected = ast.fix_missing_locations(ast.Module(body=cancellation + helpers + [
        ast.ClassDef(name="TextHarness", bases=[], keywords=[], body=methods, decorator_list=[])
    ], type_ignores=[]))
    namespace = {"re": re, "unicodedata": unicodedata, "threading": threading,
                 "Callable": Callable, "logger": QuietLogger(), "np": NumpyConversionOnly()}
    exec(compile(selected, str(SOURCE), "exec"), namespace)
    return namespace["TextHarness"]()


def hit(frame, score, channel, text="needle", origin="fixture"):
    return {"distance": score, "entity": {"frame_id": frame, channel: text, "origin": origin}}


def fixtures():
    cases = {}
    ids = [f"L01_V001#{n:06d}" for n in range(1, 25)]
    for mode, alpha in (("sparse", 0.0), ("dense", 1.0), ("hybrid", 0.5)):
        for kind, rows, query in (
            ("ties", [(fid, 2.0, "needle") for fid in reversed(ids)], "needle"),
            ("near", [("L01_V001#000001", 1.0, "needle"),
                      ("L01_V001#000024", 1.00000001, "needle"),
                      ("L01_V001#000002", 0.5, "needle")], "needle"),
            ("phrase", [("L01_V001#000024", 4.0, "NEEDLE"),
                        ("L01_V001#000001", 4.0, "a needle here"),
                        ("L01_V001#000002", 100.0, "needles")], '"needle"'),
        ):
            channel = "asr" if kind == "phrase" else "ocr"
            cases[f"{kind}_{mode}"] = {
                "alpha": alpha, "channel": channel, "queries": [query],
                "sparse": [hit(fid, score, channel, text, "sparse") for fid, score, text in rows],
                "dense": [hit(fid, score, channel, text, "dense") for fid, score, text in reversed(rows)],
            }
    cases["hybrid_complementary"] = {
        "alpha": 0.5, "channel": "ocr", "queries": ["needle"],
        "sparse": [hit("L02_V001#000002", 8, "ocr", origin="sparse"),
                   hit("L01_V001#000010", 0, "ocr", origin="sparse"),
                   hit("L01_V001#000002", 2, "ocr", origin="sparse")],
        "dense": [hit("L01_V001#000010", 8, "ocr", origin="dense"),
                  hit("L02_V001#000002", 0, "ocr", origin="dense"),
                  hit("L01_V001#000002", 2, "ocr", origin="dense")],
    }
    cases["multiple_queries"] = {
        "alpha": 0.5, "channel": "asr", "queries": ["one", "two"],
        "sparse_batches": [
            [hit("L01_V001#000001", 2, "asr", origin="first-sparse"),
             hit("L01_V001#000002", 1, "asr", origin="first-sparse")],
            [hit("L01_V001#000001", 1, "asr", origin="later-sparse"),
             hit("L01_V001#000003", 4, "asr", origin="later-sparse")]],
        "dense_batches": [
            [hit("L01_V001#000002", 3, "asr", origin="first-dense")],
            [hit("L01_V001#000004", 2, "asr", origin="later-dense"),
             hit("L01_V001#000001", 1, "asr", origin="later-dense")]],
    }
    cases["zero_normalization"] = {
        "alpha": 0.0, "channel": "ocr", "queries": ["needle"],
        "sparse": [hit(fid, score, "ocr") for fid, score in
                   (("L01_V001#000003", -2), ("L01_V001#000001", -1), ("L01_V001#000002", 0))],
        "dense": [],
    }
    cases["empty_queries"] = {
        "alpha": 0.5, "channel": "ocr", "queries": [], "sparse": [], "dense": [],
    }
    return cases


def execute(case, legacy=False):
    harness = production_harness(legacy=legacy)

    class FrozenDatabase:
        def __init__(self):
            self.calls = []
            self.counts = {"sparse": 0, "dense": 0}

        def search(self, **kwargs):
            self.calls.append(copy.deepcopy(kwargs))
            provider = kwargs["anns_field"].rsplit("_", 1)[1]
            index = self.counts[provider]
            self.counts[provider] += 1
            batches = case.get(provider + "_batches")
            rows = batches[index] if batches is not None else case[provider]
            return [copy.deepcopy(rows)]

    class FrozenExtractor:
        def __init__(self):
            self.calls = []

        def get_text_features(self, texts):
            self.calls.append(copy.deepcopy(texts))
            return [[0.25, 0.5]]

    database, extractor = FrozenDatabase(), FrozenExtractor()
    harness._database = database
    harness._extractors = {"fixture-dense": {"feature_extractor": extractor}}
    channel = case["channel"]
    results, entities = harness._search_text_component(
        query_features={channel: copy.deepcopy(case["queries"])},
        feature_key=channel, sparse_field=channel + "_sparse",
        dense_field=channel + "_dense", dense_model_name="fixture-dense",
        video_filter="", subquery_limit=50, nprobe=8, hybrid_alpha=case["alpha"],
    )
    return {"results": results, "entities": entities,
            "provider_calls": database.calls, "extractor_calls": extractor.calls}


def assert_preserved(fixed, original):
    # Compare complete unrounded entries, entity selection and external requests.
    fixed_by_id = {r["entity"]["frame_id"]: r for r in fixed["results"]}
    old_by_id = {r["entity"]["frame_id"]: r for r in original["results"]}
    if fixed_by_id != old_by_id:
        raise AssertionError("Membership, entity content or candidate score changed")
    for key in ("entities", "provider_calls", "extractor_calls"):
        if fixed[key] != original[key]:
            raise AssertionError(f"Pre-existing behavior changed: {key}")
    if [r["distance"] for r in fixed["results"]] != [r["distance"] for r in original["results"]]:
        raise AssertionError("Non-tied score order changed")
    expected = sorted(fixed["results"], key=lambda r: (-r["distance"], r["entity"]["frame_id"]))
    if list(fixed["results"]) != expected:
        raise AssertionError("Canonical full-score/frame-ID order not satisfied")


def seed_probe():
    if os.environ.get("PYTHONHASHSEED") not in SEEDS:
        raise AssertionError("Launch a fresh process with a predeclared hash seed")
    output = {}
    for name, case in fixtures().items():
        fixed, original = execute(case), execute(case, legacy=True)
        assert_preserved(fixed, original)
        output[name] = {"fixed": fixed, "original_order": [r["entity"]["frame_id"] for r in original["results"]]}
    return output


class TextTieOrderTests(unittest.TestCase):
    def compare(self, name):
        case = fixtures()[name]
        fixed, original = execute(case), execute(case, legacy=True)
        assert_preserved(fixed, original)
        return fixed

    def test_sparse_exact_ties_are_canonical(self):
        rows = self.compare("ties_sparse")["results"]
        self.assertEqual([r["entity"]["frame_id"] for r in rows],
                         sorted(r["entity"]["frame_id"] for r in rows))

    def test_dense_exact_ties_are_canonical(self):
        self.compare("ties_dense")

    def test_hybrid_exact_ties_are_canonical(self):
        self.compare("ties_hybrid")
        rows = self.compare("hybrid_complementary")["results"]
        self.assertEqual([r["entity"]["frame_id"] for r in rows[:2]],
                         ["L01_V001#000010", "L02_V001#000002"])
        self.assertEqual(rows[0]["distance"], rows[1]["distance"])

    def test_near_ties_use_full_precision_in_all_modes(self):
        for mode in ("sparse", "dense", "hybrid"):
            with self.subTest(mode=mode):
                rows = self.compare("near_" + mode)["results"]
                self.assertEqual(rows[0]["entity"]["frame_id"], "L01_V001#000024")
                self.assertGreater(rows[0]["distance"], rows[1]["distance"])
                self.assertEqual(rows[0]["scores"]["final"], rows[1]["scores"]["final"])

    def test_exact_phrase_filter_and_boost_remain_in_all_modes(self):
        for mode in ("sparse", "dense", "hybrid"):
            with self.subTest(mode=mode):
                result = self.compare("phrase_" + mode)
                self.assertEqual([r["entity"]["frame_id"] for r in result["results"]],
                                 ["L01_V001#000001", "L01_V001#000024"])
                for row in result["results"]:
                    raw = row["scores"]["dense_raw"] if mode == "dense" else row["scores"]["sparse_raw"]
                    self.assertEqual(raw, 6.0)
                self.assertTrue(all(c["limit"] == 500 for c in result["provider_calls"]))

    def test_multiple_queries_keep_accumulation_and_first_entity(self):
        result = self.compare("multiple_queries")
        rows = {r["entity"]["frame_id"]: r for r in result["results"]}
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows["L01_V001#000001"]["scores"]["sparse_raw"], 3)
        self.assertEqual(rows["L01_V001#000001"]["entity"]["origin"], "first-sparse")
        self.assertEqual(len(result["provider_calls"]), 4)

    def test_nonpositive_scores_keep_zero_normalization(self):
        rows = self.compare("zero_normalization")["results"]
        self.assertEqual([r["distance"] for r in rows], [0.0, 0.0, 0.0])

    def test_empty_query_keeps_existing_empty_return(self):
        result = self.compare("empty_queries")
        self.assertEqual(result["results"], {})
        self.assertEqual(result["entities"], {})
        self.assertEqual(result["provider_calls"], [])

    def test_independent_hash_seed_processes_have_identical_effective_order(self):
        probes = []
        for seed in SEEDS:
            env = dict(os.environ, PYTHONHASHSEED=seed)
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--seed-probe"],
                                       env=env, capture_output=True, text=True, check=True, timeout=30)
            probes.append(json.loads(completed.stdout))
        expected = {name: result["fixed"] for name, result in probes[0].items()}
        for probe in probes[1:]:
            self.assertEqual({name: result["fixed"] for name, result in probe.items()}, expected)
        # This fixture also reproduces the original defect, so the test is not vacuous.
        self.assertGreater(len({tuple(p["ties_sparse"]["original_order"]) for p in probes}), 1)


if __name__ == "__main__":
    if sys.argv[1:] == ["--seed-probe"]:
        print(json.dumps(seed_probe(), sort_keys=True, ensure_ascii=True))
    else:
        unittest.main()
