"""Guard the matched temporal experiment against partial or stale comparisons."""
import builtins
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "code" / "temporal_matched.py"
SPEC = importlib.util.spec_from_file_location("temporal_matched", SCRIPT)
matched = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matched)
RUN_FINGERPRINT = "test-only-fully-matched-run"


def unit_vector(first=1.0):
    return [first, math.sqrt(max(0.0, 1.0 - first * first))] + [0.0] * 2046


def complete_records(plan):
    """Distinct scores force rank changes without loading a model."""
    queries = [{
        "query_id": row["query_id"],
        "query_text_sha256": row["text_sha256"],
        "vector": unit_vector(),
        "run_fingerprint": RUN_FINGERPRINT,
    } for row in plan["queries"]]
    embeddings = [{
        "candidate_key": row["candidate_key"],
        "arm": arm,
        "frame_source_ids": [frame["source_frame_id"] for frame in row["frames"]],
        "input_fingerprint": matched.input_fingerprint(row, arm),
        "vector": unit_vector({1: 0.0, 2: 0.6, 3: 1.0}[row["current_baseline_rank"]]),
        "run_fingerprint": RUN_FINGERPRINT,
    } for row in plan["candidates"] for arm in matched.ARMS]
    return queries, embeddings


class MatchedTemporalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = [json.loads(line) for line in
                       (ROOT / "inputs" / "qwen_only_top100.jsonl").read_text().splitlines()]
        cls.cached = json.loads((ROOT / "inputs" / "temporal_processor_probe.json").read_text())["candidate_rows"]
        cls.frozen_plan = matched.build_plan(cls.current, cls.cached)
        # Synthetic identities make stale-image tests independent of host paths.
        for row in cls.frozen_plan["candidates"]:
            row["frame_file_sha256"] = [hashlib.sha256(frame["source_frame_id"].encode()).hexdigest()
                                        for frame in row["frames"]]

    def setUp(self):
        self.plan = copy.deepcopy(self.frozen_plan)
        self.queries, self.embeddings = complete_records(self.plan)

    def validate(self, queries=None, embeddings=None, plan=None):
        return matched.validate_complete(
            self.plan if plan is None else plan,
            self.queries if queries is None else queries,
            self.embeddings if embeddings is None else embeddings,
            RUN_FINGERPRINT,
        )

    def test_plan_is_exact_eight_by_three_and_all_three_arms(self):
        self.assertEqual(set(self.plan["query_ids"]), set(matched.QUERY_IDS))
        self.assertEqual(len(self.plan["queries"]), 8)
        self.assertEqual(len(self.plan["candidates"]), 24)
        self.assertEqual(len(set(self.plan["arms"])), 3)
        self.assertEqual(len(self.embeddings), 72)
        for qid in matched.QUERY_IDS:
            ranks = [row["current_baseline_rank"] for row in self.plan["candidates"] if row["query_id"] == qid]
            self.assertEqual(sorted(ranks), [1, 2, 3])
        for query in self.plan["queries"]:
            self.assertEqual(query["text_sha256"], hashlib.sha256(query["text"].encode()).hexdigest())

    def test_current_rank_swap_maps_by_source_identity(self):
        rows = sorted((row for row in self.plan["candidates"] if row["query_id"] == "p3_q34"),
                      key=lambda row: row["current_baseline_rank"])
        self.assertEqual([row["source_frame_id"] for row in rows], [
            "L24_V011#014136", "L24_V013#000224", "L24_V011#013988"])
        self.assertEqual([row["legacy_candidate_id"] for row in rows], [
            "p3_q34:w3_d60:r001", "p3_q34:w3_d60:r003", "p3_q34:w3_d60:r002"])
        for row in rows:
            self.assertEqual(row["candidate_key"], row["query_id"] + "|" + row["source_frame_id"])
            self.assertEqual([frame["frame_id"] for frame in row["frames"]],
                             [row["center_frame_id"] + offset for offset in (-60, 0, 60)])

    def test_module_and_plan_need_no_torch_truth_images_or_weights(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.split(".", 1)[0] in {"torch", "transformers"}:
                raise AssertionError("Planning must not import inference libraries")
            return original_import(name, *args, **kwargs)

        isolated_spec = importlib.util.spec_from_file_location("temporal_matched_no_inference", SCRIPT)
        isolated = importlib.util.module_from_spec(isolated_spec)
        with mock.patch("builtins.__import__", side_effect=guarded_import):
            isolated_spec.loader.exec_module(isolated)
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("Unexpected planning file read")), \
                 mock.patch.object(Path, "read_text", side_effect=AssertionError("Unexpected planning file read")), \
                 mock.patch.object(Path, "open", side_effect=AssertionError("Unexpected planning file read")):
                plan = isolated.build_plan(self.current, self.cached)
        self.assertEqual(len(plan["candidates"]), 24)

    def test_missing_cached_identity_is_not_replaced_by_same_rank(self):
        rows = [row for row in self.cached if row["candidate_id"] != "p3_q34:w3_d60:r003"]
        with self.assertRaises(ValueError):
            matched.build_plan(self.current, rows)

    def test_wrong_cached_frame_order_is_rejected(self):
        rows = copy.deepcopy(self.cached)
        row = next(row for row in rows if row["candidate_id"] == "p3_q34:w3_d60:r001")
        row["frames"] = list(reversed(row["frames"]))
        with self.assertRaises(ValueError):
            matched.build_plan(self.current, rows)

    def test_complete_matched_coverage_is_accepted(self):
        self.validate()

    def test_one_missing_candidate_or_query_blocks_comparison(self):
        with self.assertRaises(ValueError):
            self.validate(embeddings=self.embeddings[:-1])
        with self.assertRaises(ValueError):
            self.validate(queries=self.queries[:-1])

    def test_duplicates_cannot_inflate_completion(self):
        with self.assertRaises(ValueError):
            self.validate(queries=self.queries + [self.queries[0]])
        with self.assertRaises(ValueError):
            self.validate(embeddings=self.embeddings + [self.embeddings[0]])
        rows = copy.deepcopy(self.embeddings)
        rows[-1] = copy.deepcopy(rows[0])
        with self.assertRaises(ValueError):
            self.validate(embeddings=rows)

    def test_wrong_query_text_is_rejected(self):
        self.queries[0]["query_text_sha256"] = "a different query"
        with self.assertRaises(ValueError):
            self.validate()

    def test_wrong_source_identity_or_arm_is_rejected(self):
        changes = [
            ("candidate_key", "unknown|V#000001"),
            ("frame_source_ids", ["V#000001", "V#000061", "V#000121"]),
            ("arm", "unrequested-experiment"),
        ]
        for key, value in changes:
            with self.subTest(key=key):
                rows = copy.deepcopy(self.embeddings)
                rows[0][key] = value
                with self.assertRaises(ValueError):
                    self.validate(embeddings=rows)

    def test_stale_run_fingerprint_rejected_for_both_record_kinds(self):
        for name in ("queries", "embeddings"):
            with self.subTest(record_kind=name):
                rows = copy.deepcopy(getattr(self, name))
                rows[0]["run_fingerprint"] = "old-bfloat16-run"
                with self.assertRaises(ValueError):
                    self.validate(**{name: rows})

    def test_wrong_input_fingerprint_or_changed_file_hash_is_rejected(self):
        rows = copy.deepcopy(self.embeddings)
        rows[0]["input_fingerprint"] = "old-image-input"
        with self.assertRaises(ValueError):
            self.validate(embeddings=rows)
        self.plan["candidates"][0]["frame_file_sha256"][0] = "changed-image-bytes"
        with self.assertRaises(ValueError):
            self.validate()

    def test_vector_dimensions_and_finiteness_are_required(self):
        for name in ("queries", "embeddings"):
            for vector in ([1.0], [float("nan")] + [0.0] * 2047, [float("inf")] + [0.0] * 2047):
                with self.subTest(record_kind=name, first_value=vector[0]):
                    rows = copy.deepcopy(getattr(self, name))
                    rows[0]["vector"] = vector
                    with self.assertRaises(ValueError):
                        self.validate(**{name: rows})

    def test_all_arms_rank_from_one_and_preserve_candidate_identity(self):
        for arm in matched.ARMS:
            ranked = matched.rank_candidates(self.plan, self.queries, self.embeddings, arm, RUN_FINGERPRINT)
            self.assertEqual(set(ranked), set(matched.QUERY_IDS))
            for qid, rows in ranked.items():
                self.assertEqual([row["rank"] for row in rows], [1, 2, 3])
                expected = sorted((row for row in self.plan["candidates"] if row["query_id"] == qid),
                                  key=lambda row: -row["current_baseline_rank"])
                self.assertEqual([(row["video_id"], int(row["frame_id"])) for row in rows],
                                 [(row["video_id"], row["center_frame_id"]) for row in expected])

    def test_ranking_refuses_partial_other_arm_even_if_requested_arm_is_complete(self):
        missing_arm = matched.ARMS[-1]
        rows = [row for row in self.embeddings if row["arm"] != missing_arm]
        with self.assertRaises(ValueError):
            matched.rank_candidates(self.plan, self.queries, rows, matched.ARMS[0], RUN_FINGERPRINT)


if __name__ == "__main__":
    unittest.main()
