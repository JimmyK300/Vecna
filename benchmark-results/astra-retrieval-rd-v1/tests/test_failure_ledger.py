"""Reconstructed integrity tests for Packet D, including outage recovery gates."""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("failure_ledger", ROOT / "code/build_failure_ledger.py")
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)
AUDIT = ledger.load_audit(ROOT)
SCORER = AUDIT.load_scorer(ROOT / "reference/evaluate_reranker_fusion.py")

class FailureEvidenceTests(unittest.TestCase):
    def source(self, hit=False, video=1, targets=True):
        return {"frozen": {"baseline": {"metrics": {"R@20": float(hit)}}},
                "candidate_pool": {"video_first_rank_at_100": video, "all_required_targets_present": targets}}

    def test_success_is_not_forced_into_a_failure_category(self):
        self.assertEqual(ledger.baseline_failure(self.source(hit=True)), "none")

    def test_pool_absence_distinguishes_video_from_required_event(self):
        self.assertEqual(ledger.baseline_failure(self.source(video=None, targets=False)), "candidate_generation_missing_video")
        self.assertEqual(ledger.baseline_failure(self.source(video=50, targets=False)), "candidate_generation_missing_event")
        self.assertEqual(ledger.baseline_failure(self.source(video=50, targets=True)), "unresolved")

    def test_visual_or_channel_tags_do_not_become_causes(self):
        row = self.source()
        row["capability_tags"] = ["OCR", "ASR", "VIS_ATTR"]
        row["primary_challenge"] = "OCR/readout_QA"
        self.assertEqual(ledger.baseline_failure(row), "unresolved")

    def test_proxy_truth_qualifies_without_claiming_main_cause(self):
        result = ledger.weak_truth({"truth_tier": "frozen_headless_benchmark_truth", "effective_truth_basis": "provisional_submission_anchor"})
        self.assertTrue(result["provisional_or_proxy"])
        self.assertFalse(result["main_failure_cause_established"])

    def test_missing_fusion_is_null_not_a_failed_score(self):
        with tempfile.TemporaryDirectory() as directory:
            result = ledger.fusion_evidence(Path(directory) / "missing.jsonl", {}, AUDIT, SCORER)
        self.assertEqual(result["status"], "NOT_RUN")
        self.assertIsNone(result["best_global_arm"])
        self.assertEqual(result["per_query"], {})

    def test_archived_fusion_requires_hydration_before_regeneration(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "study_results.jsonl"
            for filename in ("summary.json", "per_query.jsonl"):
                evidence = Path(directory) / filename
                evidence.write_text("{}\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Hydrate outputs/fusion/evaluation/study_results.jsonl"):
                    ledger.fusion_evidence(raw, {}, AUDIT, SCORER)
                evidence.unlink()

    def fusion_fixture(self, directory):
        truth, rows, evaluated = {}, [], []
        identity = "a" * 64
        for i in range(115):
            q, text = f"q{i:03}", f"query{i}"
            truth[q] = {"query_id": q, "query": text, "scoreable": i < 113, "task_type": "tkis",
                        "accepted_groups": [[{"kind": "interval", "video_id": "CORRECT", "start": 10, "end": 20}]]}
            arms = {}
            for arm in ledger.FUSION_ARMS:
                correct = (arm == "fusion_rrf" and i < 60) or (arm == "fusion_minmax_sum" and 60 <= i < 113)
                item = {"rank": 1, "video_id": "CORRECT" if correct else "WRONG", "frame_id": 15}
                arms[arm] = {"frames": [item], "videos": [item]}
            rows.append({"query_id": q, "query_text_sha256": hashlib.sha256(text.encode()).hexdigest(), "run_identity_sha256": identity, "arms": arms})
            if i < 113:
                scored = {"query_id": q, "query_text_sha256": rows[-1]["query_text_sha256"], "run_identity_sha256": identity, "arms": {}}
                for name, arm in arms.items():
                    scored["arms"][name] = {"frozen_frame_range_event": AUDIT.score_frozen(arm["frames"], truth[q], SCORER),
                        "frame_position_video": AUDIT.score_video(arm["frames"], truth[q], SCORER),
                        "distinct_video": AUDIT.score_video(arm["videos"], truth[q], SCORER)}
                scored["arms"][ledger.MATCHED_QWEN] = copy.deepcopy(scored["arms"]["fusion_rrf"])
                evaluated.append(scored)
        evaluation_dir = Path(directory) / "evaluation"
        capture_dir = Path(directory) / "capture-full115-v1"
        evaluation_dir.mkdir()
        capture_dir.mkdir()
        config = {"output_frame_k": 100, "output_video_k": 100, "visual_providers": ["qwen", "siglip"],
                  "ocr_alpha": 0, "asr_alpha": 0, "ocr_weight": 0.25, "asr_weight": 0.25}
        (Path(directory) / "frozen_config.json").write_text(json.dumps(config), encoding="utf-8")
        provider_rows = []
        for exported in rows:
            q = exported["query_id"]
            hits = [{**f, "frame_id": f"{f['video_id']}#000015"} for f in exported["arms"]["fusion_rrf"]["frames"]]
            providers = {"qwen": {"state": "ok", "hits": hits, "raw_hit_count": len(hits)}}
            providers.update({p: {"state": "empty", "hits": [], "raw_hit_count": 0} for p in ("siglip", "ocr_sparse", "asr_sparse")})
            provider_rows.append({"query_id": q, "query_text": truth[q]["query"], "query_text_sha256": exported["query_text_sha256"],
                "run_identity_sha256": identity, "providers": providers, "candidate_tie_order": [f["frame_id"] for f in hits]})
        provider_path = capture_dir / "provider_rankings.jsonl"
        provider_path.write_text("".join(json.dumps(r) + "\n" for r in provider_rows), encoding="utf-8")
        for row in evaluated:
            q = row["query_id"]
            hits = next(r for r in provider_rows if r["query_id"] == q)["providers"]["qwen"]["hits"]
            frozen = AUDIT.score_frozen(hits, truth[q], SCORER, depth=100)
            row["arms"][ledger.MATCHED_QWEN].update({
                "distinct_video_rank_observed": AUDIT.score_video(hits, truth[q], SCORER, depth=100)["first_success_rank"],
                "frame_position_video_rank_observed": AUDIT.score_video(hits, truth[q], SCORER, depth=100)["first_success_rank"],
                "frozen_rank_observed": frozen["first_success_rank"], "required_target_coverage_at_retained100": frozen["target_coverage_at_depth"],
                "all_required_targets_at_retained100": frozen["all_required_targets_present"]})
        raw, selection, per_query = (evaluation_dir / name for name in ("study_results.jsonl", "summary.json", "per_query.jsonl"))
        raw.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        per_query.write_text("".join(json.dumps(r) + "\n" for r in evaluated), encoding="utf-8")
        summary = {"descriptive_best_global_arm": "fusion_rrf", "transform_proof": {
            "queries": 115, "arms": list(ledger.FUSION_ARMS), "ground_truth_read": False,
            "output_sha256": ledger.sha256(raw), "run_identity_sha256": identity,
            "rankings_sha256": ledger.sha256(provider_path),
            "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()}}
        selection.write_text(json.dumps(summary), encoding="utf-8")
        return truth, rows, evaluated, summary, raw, selection, per_query

    def test_fusion_requires_evaluation_and_uses_one_global_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            truth, rows, evaluated, summary, raw, selection, per_query = self.fusion_fixture(directory)
            per_query.unlink()
            self.assertEqual(ledger.fusion_evidence(raw, truth, AUDIT, SCORER)["status"], "EVALUATION_PENDING")
            per_query.write_text("".join(json.dumps(r) + "\n" for r in evaluated), encoding="utf-8")
            result = ledger.fusion_evidence(raw, truth, AUDIT, SCORER)
            self.assertEqual(result["best_global_arm"], "fusion_rrf")
            self.assertEqual(result["per_query"]["q090"][result["best_global_arm"]]["frozen"]["metrics"]["R@20"], 0)
            matched = ledger.matched_b_contrasts(result)
            self.assertEqual(matched["layers"]["frozen"]["R@20"]["improved_query_ids"], [])
            self.assertEqual(matched["layers"]["frozen"]["R@20"]["regressed_query_ids"], [])
            summary["descriptive_best_global_arm"] = "fusion_minmax_sum"
            selection.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "global arm disagrees"):
                ledger.fusion_evidence(raw, truth, AUDIT, SCORER)

    def test_present_partial_study_cannot_erase_completed_b(self):
        with tempfile.TemporaryDirectory() as directory:
            truth, rows, evaluated, summary, raw, selection, per_query = self.fusion_fixture(directory)
            raw.write_text("".join(json.dumps(r) + "\n" for r in rows[:-1]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "partial or foreign study cohort"):
                ledger.fusion_evidence(raw, truth, AUDIT, SCORER)
            rows[0]["arms"].pop("fusion_rrf")
            raw.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing or foreign study arms"):
                ledger.fusion_evidence(raw, truth, AUDIT, SCORER)

    def test_foreign_summary_hash_or_run_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            truth, rows, evaluated, summary, raw, selection, per_query = self.fusion_fixture(directory)
            summary["transform_proof"]["run_identity_sha256"] = "b" * 64
            selection.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "summary transform_proof run identity"):
                ledger.fusion_evidence(raw, truth, AUDIT, SCORER)
            summary["transform_proof"]["run_identity_sha256"] = "a" * 64
            summary["transform_proof"]["output_sha256"] = "c" * 64
            selection.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "actual study SHA256"):
                ledger.fusion_evidence(raw, truth, AUDIT, SCORER)

    def test_reported_matched_qwen_must_reproduce_from_bound_raw_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            truth, rows, evaluated, summary, raw, selection, per_query = self.fusion_fixture(directory)
            evaluated[0]["arms"][ledger.MATCHED_QWEN]["frozen_frame_range_event"]["metrics"]["R@20"] = 0.0
            per_query.write_text("".join(json.dumps(r) + "\n" for r in evaluated), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "matched-Qwen scores do not reproduce"):
                ledger.fusion_evidence(raw, truth, AUDIT, SCORER)

    def test_fresh_pool_evidence_prevents_stale_missing_video_label(self):
        c = self.source(video=None, targets=False)
        c["candidate_pool"]["target_first_ranks_at_100"] = [None]
        empty = {"accepted_video_present": False, "target_present": [False]}
        video = {"accepted_video_present": True, "target_present": [False]}
        target = {"accepted_video_present": True, "target_present": [True]}
        b = {"active_provider_union": video, "fusion_current_control": {"retained_frame_pool": video},
             ledger.MATCHED_QWEN: {"retained_frame_pool": empty}}
        self.assertEqual(ledger.baseline_failure(c), "candidate_generation_missing_video")
        observed = ledger.observed_pool_evidence(c, b, "fusion_current_control")
        self.assertEqual(ledger.remaining_failure(observed, True), "candidate_generation_missing_event")
        b["active_provider_union"] = target
        observed = ledger.observed_pool_evidence(c, b, "fusion_current_control")
        self.assertEqual(ledger.remaining_failure(observed, True), "unresolved")
        self.assertEqual(ledger.remaining_failure(observed, False), "none")
        self.assertEqual(ledger.baseline_failure(c), "candidate_generation_missing_video")

    def test_evaluated_row_identity_must_match_study(self):
        with tempfile.TemporaryDirectory() as directory:
            truth, rows, evaluated, summary, raw, selection, per_query = self.fusion_fixture(directory)
            evaluated[0]["run_identity_sha256"] = "b" * 64
            per_query.write_text("".join(json.dumps(r) + "\n" for r in evaluated), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "scored/transformed identity mismatch"):
                ledger.fusion_evidence(raw, truth, AUDIT, SCORER)

class FrozenLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.truth = ledger.index(ledger.read_jsonl(ROOT / "inputs/canonical_truth.jsonl"))
        cls.crows = ledger.read_jsonl(ROOT / "outputs/reranker/per_query.jsonl")
        cls.sample = ledger.read_json(ROOT / "outputs/dataset-audit/sample_manifest.json")
        cls.inventory = ledger.read_jsonl(ROOT / "outputs/dataset-audit/temporal_inventory.jsonl")
        cls.temporal = ledger.read_json(ROOT / "outputs/temporal-multi-image/summary.json")
        selected = ledger.dataset_join(ledger.read_jsonl(ROOT / "outputs/dataset-audit/audit.jsonl"), cls.sample, {q for q, t in cls.truth.items() if t["scoreable"]})
        cls.fusion = {"status": "NOT_RUN", "best_global_arm": None, "per_query": {}}
        cls.rows = ledger.build_rows(cls.truth, cls.crows, selected, cls.temporal, cls.inventory, cls.fusion)

    def test_113_rows_null_fusion_and_38_channel_join(self):
        self.assertEqual(len(self.rows), 113)
        ids = {r["query_id"] for r in self.rows}
        self.assertFalse(ids & {"p0_q15", "p3_q09"})
        self.assertIn("p2_q17", ids)
        self.assertEqual(sum(len(r["dataset_audit"]["selected_channels"]) for r in self.rows), 38)
        self.assertEqual(sum(bool(r["dataset_audit"]["selected_channels"]) for r in self.rows), 30)
        self.assertTrue(all(r["best_fusion"] is None and r["best_fusion_rank"] is None for r in self.rows))
        self.assertTrue(all(r["matched_b_qwen"] is None and r["matched_b_qwen_rank"] is None for r in self.rows))
        summary = ledger.summarize(self.rows, self.fusion)
        self.assertIsNone(summary["arm_interactions"]["reranker_improved_mrr_but_fusion_did_not"])
        self.assertEqual(len(summary["truth"]["provisional_or_proxy_query_ids"]), 41)

    def test_remaining_failures_exclude_any_observed_success(self):
        self.assertEqual(sum(not r["remaining_miss_after_observed_arms"] for r in self.rows), 77)
        self.assertEqual(sum(r["remaining_miss_after_observed_arms"] for r in self.rows), 36)
        indexed = ledger.index(self.rows)
        self.assertEqual(indexed["p2_q14"]["primary_failure"], "none")
        self.assertTrue(indexed["p2_q14"]["reranker_regression"])
        self.assertEqual(indexed["p2_q17"]["primary_failure"], "candidate_generation_missing_video")
        self.assertEqual(indexed["p3_q06"]["primary_failure"], "none")
        self.assertEqual(indexed["p3_q06"]["baseline_primary_failure"], "unresolved")

    def test_source_reviews_attach_without_replacing_truth_or_scores(self):
        dataset = ledger.dataset_join(ledger.read_jsonl(ROOT / "outputs/dataset-audit/audit.jsonl"), self.sample, {q for q, t in self.truth.items() if t["scoreable"]})
        ledger.attach_dataset_reviews(dataset, ledger.read_jsonl(ROOT / "outputs/dataset-audit/reviewed_audit.jsonl"), self.truth)
        proposals = ledger.read_jsonl(ROOT / "outputs/temporal-truth-review/proposed_truth.reviewed.jsonl")
        reviews = ledger.temporal_review_join(proposals, self.truth, self.inventory, ledger.sha256(ROOT / "inputs/canonical_truth.jsonl"))
        rows = ledger.build_rows(self.truth, self.crows, dataset, self.temporal, self.inventory, self.fusion, reviews)
        before = ledger.index(self.rows)
        for row in rows:
            for field in ("baseline_rank", "reranker_rank", "primary_failure", "baseline_primary_failure", "candidate_ceiling", "truth_qualification"):
                self.assertEqual(row[field], before[row["query_id"]][field])
        summary = ledger.summarize(rows, self.fusion)
        self.assertEqual(summary["truth"]["source_review"]["reviewed_anchors"], 31)
        self.assertEqual(summary["truth"]["source_review"]["proposed_locator_counts"], {"point": 16, "unknown": 15})
        self.assertEqual(summary["truth"]["source_review"]["first_occurrence_claims"], 0)
        self.assertEqual(summary["dataset_audit"]["source_images_inspected_ocr"], 20)
        self.assertEqual(summary["dataset_audit"]["source_audio_captured_not_heard_asr"], 18)
        self.assertEqual(summary["dataset_audit"]["source_audio_heard_asr"], 0)

    def test_source_overlay_rejects_truth_promotion_and_unheard_audio_claim(self):
        proposals = ledger.read_jsonl(ROOT / "outputs/temporal-truth-review/proposed_truth.reviewed.jsonl")
        proposals[0]["metric_policy"]["truth_tier_promoted"] = True
        with self.assertRaisesRegex(ValueError, "must not alter scoring"):
            ledger.temporal_review_join(proposals, self.truth, self.inventory, ledger.sha256(ROOT / "inputs/canonical_truth.jsonl"))
        dataset = ledger.dataset_join(ledger.read_jsonl(ROOT / "outputs/dataset-audit/audit.jsonl"), self.sample, {q for q, t in self.truth.items() if t["scoreable"]})
        reviewed = ledger.read_jsonl(ROOT / "outputs/dataset-audit/reviewed_audit.jsonl")
        next(row for row in reviewed if row["channel"] == "asr")["source_media_inspected"] = True
        with self.assertRaisesRegex(ValueError, "Unheard ASR capture"):
            ledger.attach_dataset_reviews(copy.deepcopy(dataset), reviewed, self.truth)

if __name__ == "__main__":
    unittest.main()
