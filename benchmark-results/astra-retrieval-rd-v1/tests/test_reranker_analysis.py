"""Semantic regression tests for the retained-reranker audit contract."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reranker_analysis", ROOT / "code/analyze_reranker.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
SCORER = audit.load_scorer(ROOT / "reference/evaluate_reranker_fusion.py")


def candidate(rank, frame, video="V"):
    return {"rank": rank, "video_id": video, "frame_id": frame}


class RerankerSemantics(unittest.TestCase):
    def test_source_numbers_not_current_ordinals_join_capabilities(self):
        truth = {"query_id": "p0_q24", "canonical_source_key": "query-p0-18-trake"}
        self.assertEqual(audit.capability_key(truth), "p0-q18")
        self.assertEqual(audit.capability_key({"canonical_source_key": "p3_q08"}), "p3-q8")

    def test_duplicate_query_ids_fail_before_join(self):
        with self.assertRaises(ValueError):
            audit.unique_index([{"query_id": "a"}, {"query_id": "a"}])

    def test_original_rank_disambiguates_identical_frame_different_timelines(self):
        base = [{**candidate(1, 10), "time_line": [10, 20]}, {**candidate(2, 10), "time_line": [10, 30]}]
        rerank = [{**candidate(1, 10), "original_baseline_rank": 2}]
        restored = audit.validate_candidates(base, rerank, SCORER)
        self.assertEqual(restored[0]["time_line"], [10, 30])
        with self.assertRaises(ValueError):
            audit.validate_candidates(base, [{**candidate(1, 11), "original_baseline_rank": 2}], SCORER)

    def test_one_baseline_item_cannot_be_reused_twice(self):
        base = [candidate(1, 10)]
        rerank = [{**candidate(i, 10), "original_baseline_rank": 1} for i in (1, 2)]
        with self.assertRaises(ValueError):
            audit.validate_candidates(base, rerank, SCORER)

    def test_strict_historical_trake_does_not_credit_partial_coverage(self):
        truth = {"query_id": "test", "truth_tier": "frozen_headless_benchmark_truth", "task_type": "trake", "accepted_video_id": "V",
                 "trake_event_truth": [{"proxy_window": {"start_frame": 10, "end_frame": 10}}, {"proxy_window": {"start_frame": 100, "end_frame": 100}}]}
        partial = audit.score_frozen([candidate(1, 10)], truth, SCORER)
        self.assertEqual(partial["metrics"]["R@20"], 0)
        self.assertEqual(partial["metrics"]["MRR@20"], 0)
        self.assertEqual(partial["target_coverage_at_depth"], .5)
        complete = audit.score_frozen([candidate(1, 10), candidate(5, 100)], truth, SCORER)
        self.assertEqual(complete["metrics"]["R@1"], 0)
        self.assertEqual(complete["metrics"]["R@5"], 1)
        self.assertEqual(complete["metrics"]["MRR@20"], .2)

    def test_p3_fractional_targets_and_pool_extension_do_not_invent_mrr(self):
        truth = {"query_id": "test", "task_type": "trake", "accepted_groups": [[
            {"kind": "point", "video_id": "V", "frame": 10}, {"kind": "point", "video_id": "V", "frame": 500}]]}
        rows = [candidate(1, 60), candidate(21, 500)]
        score = audit.score_frozen(rows, truth, SCORER)
        self.assertEqual(score["metrics"]["R@1"], .5)  # inclusive frozen tolerance = 50 frames
        self.assertEqual(score["target_first_ranks"], [1, None])
        pool = audit.score_frozen(rows, truth, SCORER, 100)
        self.assertTrue(pool["all_required_targets_present"])
        only_late = audit.score_frozen([candidate(21, 500)], truth, SCORER, 100)
        self.assertEqual(only_late["metrics"]["MRR@20"], 0)

    def test_video_hit_does_not_imply_localization_hit(self):
        truth = {"query_id": "test", "truth_tier": "frozen_headless_benchmark_truth", "task_type": "kis", "accepted_video_id": "V",
                 "accepted_ranges": [{"start_frame": 100, "end_frame": 200}]}
        rows = [candidate(1, 99), candidate(2, 200, "OTHER")]
        self.assertEqual(audit.score_video(rows, truth, SCORER)["metrics"]["R@1"], 1)
        self.assertEqual(audit.score_frozen(rows, truth, SCORER)["metrics"]["R@20"], 0)
        self.assertEqual(audit.score_frozen([candidate(1, 200)], truth, SCORER)["metrics"]["R@1"], 1)

    def test_unobserved_top20_is_censored_not_a_known_rank(self):
        truth = {"query_id": "test", "task_type": "tkis", "accepted_groups": [[{"kind": "interval", "video_id": "V", "start": 10, "end": 20}]]}
        score = audit.score_frozen([candidate(25, 15)], truth, SCORER)
        self.assertIsNone(score["first_success_rank"])
        self.assertEqual(score["rank_status"], "not_observed_within_20")
        self.assertEqual(audit.score_frozen([candidate(25, 15)], truth, SCORER, 100)["first_success_rank"], 25)

    def test_bootstrap_is_paired_and_reproducible(self):
        a = audit.paired_bootstrap([1, -1, 0], 82, 200)
        self.assertEqual(a, audit.paired_bootstrap([1, -1, 0], 82, 200))
        self.assertEqual(a["mean_delta"], 0)
        self.assertEqual(audit.paired_bootstrap([.25] * 4, 82, 200)["percentile_95_ci"], [.25, .25])


class FrozenEvidenceRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.truth = audit.unique_index(audit.read_jsonl(ROOT / "inputs/canonical_truth.jsonl"))
        cls.base = audit.unique_index(audit.read_jsonl(ROOT / "inputs/qwen_only_top100.jsonl"))
        cls.rerank = audit.unique_index(audit.read_json(ROOT / "inputs/qwen3_vl_reranker_2b_top100.json")["per_query"])

    def test_exact_frozen113_controls(self):
        expected = {"baseline": (41, 56, 65, 68, .4243397927170307), "reranker": (40, 61, 64, 76, .4320209858309944)}
        scored = [q for q, t in self.truth.items() if t["scoreable"]]
        self.assertEqual(len(scored), 113)
        self.assertEqual(set(self.truth)-set(scored), {"p0_q15", "p3_q09"})
        for arm in expected:
            values = []
            for q in scored:
                items = self.base[q]["candidates_top100"] if arm == "baseline" else self.rerank[q]["reranked_candidates_top20"]
                values.append(audit.score_frozen(items, self.truth[q], SCORER)["metrics"])
            for i, k in enumerate((1, 5, 10, 20)):
                self.assertEqual(sum(v[f"R@{k}"] for v in values), expected[arm][i])
            self.assertAlmostEqual(sum(v["MRR@20"] for v in values)/113, expected[arm][-1], places=7)

    def test_timeline_restoration_keeps_observed_reranker_metrics(self):
        affected = []
        for q, b in self.base.items():
            if not any(c.get("time_line") for c in b["candidates_top100"]):
                continue
            affected.append(q)
            r = self.rerank[q]["reranked_candidates_top20"]
            restored = audit.validate_candidates(b["candidates_top100"], r, SCORER)
            self.assertEqual(audit.score_frozen(r, self.truth[q], SCORER)["metrics"], audit.score_frozen(restored, self.truth[q], SCORER)["metrics"])
        self.assertEqual(affected, ["p0_q06", "p1_q18", "p2_q03", "p3_q13", "p3_q16", "p3_q36"])
        # The baseline evidence change is material for this query: rank1 ->14.
        q = "p3_q36"
        base = self.base[q]["candidates_top100"]
        first_frames = [{k: v for k, v in c.items() if k != "time_line"} for c in base]
        self.assertEqual(audit.score_frozen(base, self.truth[q], SCORER)["first_success_rank"], 1)
        self.assertEqual(audit.score_frozen(first_frames, self.truth[q], SCORER)["first_success_rank"], 14)

    def test_legacy_video_control_uses_a_different_candidate_run(self):
        rows = []
        for q, truth in self.truth.items():
            if not truth["scoreable"]:
                continue
            row = {"query_id": q, "scoreable": True, "task_type": truth["task_type"]}
            for layer, scorer in (("video", audit.score_video), ("frozen", audit.score_frozen)):
                row[layer] = {"baseline": scorer(self.base[q]["candidates_top100"], truth, SCORER),
                              "reranker": scorer(self.rerank[q]["reranked_candidates_top20"], truth, SCORER)}
            rows.append(row)
        result = audit.audit_legacy_video_control(audit.read_jsonl(ROOT / "inputs/legacy_temporal_control_113.jsonl"), rows, self.truth, self.base, SCORER)
        self.assertEqual([result["legacy_baseline"][f"R@{k}"]["sum"] for k in (1, 5, 10, 20)], [57, 70, 76, 83])
        self.assertEqual([result["current_baseline"][f"R@{k}"]["sum"] for k in (1, 5, 10, 20)], [59, 69, 76, 82])
        self.assertEqual(result["top20_candidate_order_or_identity_changed_queries"], 105)
        self.assertEqual(result["exact8_temporal_current_video"]["baseline"]["R@20"]["sum"], 6)
        self.assertEqual(result["exact8_temporal_current_video"]["reranker"]["R@20"]["sum"], 7)


if __name__ == "__main__":
    unittest.main()
