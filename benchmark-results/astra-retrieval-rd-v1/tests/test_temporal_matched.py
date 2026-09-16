"""Guard the matched temporal experiment against partial or stale comparisons."""
import builtins
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
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

    def test_score_rejects_incomplete_artifacts_before_truth_or_scorer_read(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            manifest = {"plan": self.plan, "run_fingerprint": RUN_FINGERPRINT,
                        "status": "complete_unscored", "artifact_sources": []}
            (out / "run_manifest.json").write_text(json.dumps(manifest))
            (out / "query_embeddings.jsonl").write_text("\n".join(map(json.dumps, self.queries)) + "\n")
            (out / "image_embeddings.jsonl").write_text("\n".join(map(json.dumps, self.embeddings[:-1])) + "\n")
            args = SimpleNamespace(output_dir=out, truth=out / "truth_must_not_be_opened.jsonl",
                                   scorer=out / "scorer_must_not_be_opened.py")
            original_open = Path.open

            def guarded_open(path, *args_open, **kwargs):
                if path in (args.truth, args.scorer):
                    raise AssertionError("Incomplete experiment must not read truth or scorer")
                return original_open(path, *args_open, **kwargs)

            with mock.patch.object(Path, "open", new=guarded_open), \
                 mock.patch.object(matched, "hash_file", side_effect=AssertionError("No hash reads before completion")):
                with self.assertRaisesRegex(ValueError, "Incomplete paired experiment"):
                    matched.score(args)


class FrozenLocationRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "reference" / "evaluate_reranker_fusion.py"
        if hashlib.sha256(path.read_bytes()).hexdigest() != matched.SCORER_SHA:
            raise AssertionError("Location tests require the pinned frozen scorer")
        cls.scorer = matched.load_scorer(path)

    def test_historical_trake_preserves_strict_all_events_rule(self):
        truth = {"query_id": "historical-trake", "truth_tier": "frozen_headless_benchmark_truth",
                 "_source": "p3", "task_type": "trake", "accepted_video_id": "V",
                 "trake_event_truth": [{"proxy_window": {"start_frame": 10, "end_frame": 10}},
                                       {"proxy_window": {"start_frame": 100, "end_frame": 100}}]}
        partial = [{"rank": 1, "video_id": "V", "frame_id": 10}]
        result = matched.score_location(partial, truth, self.scorer)
        self.assertEqual(result["raw"]["family"], "historical_trake")
        self.assertEqual(result["recall_at_1"], 0)
        self.assertEqual(result["mrr_at_20"], 0)
        complete = partial + [{"rank": 3, "video_id": "V", "frame_id": 100}]
        result = matched.score_location(complete, truth, self.scorer)
        self.assertEqual(result["recall_at_1"], 0)
        self.assertAlmostEqual(result["mrr_at_20"], 1 / 3)
        self.assertEqual(result["raw"]["event_first_ranks"], [1, 3])

    def test_p3_localization_preserves_fractional_targets_and_tolerance(self):
        truth = {"query_id": "p3-example", "truth_tier": "provisional_source_text_verified_needs_corpus_validation",
                 "_source": "historical", "task_type": "trake", "accepted_groups": [[
                     {"kind": "point", "video_id": "V", "frame": 10},
                     {"kind": "point", "video_id": "V", "frame": 500}]]}
        items = [{"rank": 1, "video_id": "V", "frame_id": 60}]
        result = matched.score_location(items, truth, self.scorer)
        self.assertEqual(result["raw"]["family"], "p3")
        self.assertEqual(result["recall_at_1"], .5)  # Inclusive pinned tolerance: 50 frames.
        self.assertEqual(result["mrr_at_20"], 1)
        self.assertEqual(result["raw"]["target_ranks"], [1, None])
        outside = [{"rank": 1, "video_id": "V", "frame_id": 61}]
        result = matched.score_location(outside, truth, self.scorer)
        self.assertEqual(result["recall_at_1"], 0)

    def test_center_only_and_equal_window_localization_remain_distinct(self):
        truth = {"query_id": "historical-range", "truth_tier": "frozen_headless_benchmark_truth",
                 "task_type": "kis", "accepted_video_id": "V",
                 "accepted_ranges": [{"start_frame": 160, "end_frame": 160}]}
        center = [{"rank": 1, "video_id": "V", "frame_id": 100, "time_line": []}]
        window = [{**center[0], "time_line": [40, 100, 160]}]
        self.assertEqual(matched.score_location(center, truth, self.scorer)["recall_at_1"], 0)
        self.assertEqual(matched.score_location(window, truth, self.scorer)["recall_at_1"], 1)


class RecoveredWindowsScoreTests(unittest.TestCase):
    def test_windows_manifest_scores_byte_identical_artifacts_on_this_host(self):
        recovered = ROOT / "outputs" / "temporal-multi-image" / "matched-v1"
        manifest_bytes = (recovered / "run_manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["status"], "complete_unscored")
        self.assertEqual((manifest["query_embeddings_completed"], manifest["image_embeddings_completed"]), (8, 72))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "run_manifest.json").write_bytes(manifest_bytes)
            for record in manifest["artifact_sources"]:
                self.assertIn("\\", record["path"])
                filename = record["path"].replace("\\", "/").rsplit("/", 1)[-1]
                data = (recovered / filename).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])
                self.assertEqual(len(data), record["bytes"])
                (out / filename).write_bytes(data)
            args = SimpleNamespace(output_dir=out, truth=ROOT / "inputs" / "canonical_truth.jsonl",
                                   scorer=ROOT / "reference" / "evaluate_reranker_fusion.py")
            summary = matched.score(args)
            self.assertEqual(summary["paired_queries"], 8)
            self.assertEqual(summary["arms"]["native3"]["pool_video_r1"], .25)
            self.assertEqual(summary["arms"]["single_center"]["pool_video_r1"], 0)
            self.assertEqual(summary["arms"]["contact_sheet"]["pool_video_r1"], 0)
            scored = json.loads((out / "scores.json").read_text())
            movements = {row["query_id"]: tuple(row["arms"][arm]["pool_video_first_rank"]
                        for arm in ("single_center", "contact_sheet", "native3")) for row in scored["per_query"]}
            self.assertEqual(movements["p0_q23"], (2, 2, 1))
            self.assertEqual(movements["p3_q34"], (2, 3, 1))
            self.assertEqual(sum(rank[2] is not None for rank in movements.values()), 2)
            for row in scored["per_query"]:
                for arm in matched.ARMS:
                    self.assertEqual(row["arms"][arm]["center_only"]["mrr_at_20"], 0)
                    self.assertEqual(row["arms"][arm]["equal_three_frame_window"]["mrr_at_20"], 0)


if __name__ == "__main__":
    unittest.main()
