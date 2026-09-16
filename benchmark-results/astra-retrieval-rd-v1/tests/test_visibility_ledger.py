"""Saved-evidence integrity and causal-boundary tests; no models or retrieval."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "code" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

visibility = module("test_visibility_helper", "visibility_ledger.py")
ledger = module("test_visibility_failure_ledger", "build_failure_ledger.py")
audit = ledger.load_audit(ROOT)

class VisibilityLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.truth = ledger.index(ledger.read_jsonl(ROOT / "inputs/canonical_truth.jsonl"))
        cls.sample = ledger.read_json(ROOT / "outputs/dataset-audit/sample_manifest.json")
        cls.scorer = audit.load_scorer(ROOT / "reference/evaluate_reranker_fusion.py")
        cls.captured = ledger.read_jsonl(ROOT / "outputs/source-visibility/sparse-v1/sparse_rankings.jsonl")
        cls.scored = ledger.read_jsonl(ROOT / "outputs/source-visibility/evaluation-v1/sparse_visibility.jsonl")
        cls.queries = ledger.read_jsonl(ROOT / "outputs/source-visibility/sparse_queries.jsonl")
        cls.pairs = {(row["query_id"], row["channel"]) for row in cls.queries}
        cls.review_sha = ledger.sha256(ROOT / "outputs/dataset-audit/reviewed_audit.jsonl")
        cls.reader = visibility.Reader(ROOT)
        cls.provider, cls.rows = visibility.load_provider(cls.reader, "sparse", cls.truth, cls.sample, audit, cls.scorer)

    def join(self, scored=None, captured=None):
        return visibility.join_rows("sparse", scored or self.scored, captured or self.captured, self.queries,
            self.truth, self.pairs, self.review_sha, {}, audit, self.scorer)

    def test_saved_sparse38_reproduces_known_visibility_and_repeats(self):
        self.assertEqual(len(self.rows), 38)
        self.assertEqual(len({q for q, _ in self.rows}), 30)
        expected = {"ocr": (20, 7, 4, 344), "asr": (18, 13, 11, 1682)}
        for channel, (count, videos, targets, repeats) in expected.items():
            rows = [row for (_, c), row in self.rows.items() if c == channel]
            self.assertEqual(len(rows), count)
            for order in ("raw", "main_eligible"):
                self.assertEqual(sum(row[order]["video_hit"]["R@100"] for row in rows), videos)
                self.assertEqual(sum(row[order]["strict_all_targets_hit"]["R@100"] for row in rows), targets)
                self.assertEqual(sum(row[order]["observed_repeated_text"]["same_video_exact_text_repeat_excess"] for row in rows), repeats)
        self.assertTrue(all(row["provider_state"] == "success_output" for row in self.rows.values()))

    def test_absent_dense_is_unavailable_without_invented_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider, rows = visibility.load_provider(visibility.Reader(tmp), "dense", self.truth, self.sample, audit, self.scorer)
        self.assertEqual(provider["status"], "EVALUATION_NOT_AVAILABLE")
        self.assertIsNone(provider["evidence"])
        self.assertEqual(rows, {})
        self.assertNotIn("channels", provider)

    def test_corrupted_provenance_bytes_fail_before_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            path.write_text('{"value":1}\n', encoding="utf-8")
            reader = visibility.Reader(tmp)
            original = visibility.digest(path.read_bytes())
            reader.bind("source.json", original)
            path.write_text('{"value":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "input changed"):
                reader.unchanged()
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                visibility.Reader(tmp).bind("source.json", original)

    def test_wrong_canonical_text_or_channel_is_rejected(self):
        scored = copy.deepcopy(self.scored)
        scored[0]["canonical_query"] += " changed"
        with self.assertRaisesRegex(ValueError, "canonical text mismatch"):
            self.join(scored=scored)
        scored = copy.deepcopy(self.scored)
        scored[0]["channel"] = "asr"
        with self.assertRaises(ValueError):
            self.join(scored=scored)

    def test_scores_duplicates_and_frame_identity_are_rechecked(self):
        scored = copy.deepcopy(self.scored)
        scored[0]["raw"]["observed_repeated_text"]["same_video_exact_text_repeat_excess"] += 1
        with self.assertRaisesRegex(ValueError, "repeated-text counts mismatch"):
            self.join(scored=scored)
        captured = copy.deepcopy(self.captured)
        captured[0]["raw_hits"][0]["frame_idx"] += 1
        with self.assertRaisesRegex(ValueError, "frame identity mismatch"):
            self.join(captured=captured)
        captured = copy.deepcopy(self.captured)
        captured[0]["raw_hits"][0]["bm25_score"] = float("inf")
        with self.assertRaisesRegex(ValueError, "text hash or score mismatch"):
            self.join(captured=captured)
        scored = copy.deepcopy(self.scored)
        scored[0]["raw"]["video_hit"]["R@100"] = not scored[0]["raw"]["video_hit"]["R@100"]
        with self.assertRaisesRegex(ValueError, "hit indicators mismatch"):
            self.join(scored=scored)

    def test_nonempty_raw_pool_can_have_empty_main_eligible_output(self):
        captured, scored = copy.deepcopy(self.captured), copy.deepcopy(self.scored)
        raw, row = captured[0], scored[0]
        raw.update(state="empty", eligible_hit_count=0, effective_frame_order=[])
        for hit in raw["raw_hits"]:
            hit.update(eligible_after_main_phrase_filter=False, eligible_rank=None, main_normalized_score=None)
        row["capture_state"] = "empty"
        target = self.truth[row["query_id"]]
        frozen = audit.score_frozen([], target, self.scorer, depth=100)
        video = audit.score_video([], target, self.scorer, depth=100)
        row["main_eligible"] = {"returned_depth": 0, "frozen_range_or_event": frozen, "frame_position_video": video,
            "distinct_video_within_retained_frame_pool": video, "first_any_target_rank": None,
            **{name: {f"R@{k}": False for k in visibility.KS} for name in ("video_hit", "any_target_hit", "strict_all_targets_hit")},
            "observed_repeated_text": {name: 0 for name in ("hit_count", "distinct_video_count", "nonempty_text_hit_count", "unique_nonempty_text_count",
                "exact_text_repeat_excess", "same_video_exact_text_repeat_excess", "largest_same_video_exact_text_group")}}
        row["ranking_order_effect"].update(eligible_frame_order_changed=False, moved_frame_count=0, moved_frames=[], raw_score_sequence_preserved=True, changes_confined_to_equal_bm25_scores=False)
        joined = self.join(scored=scored, captured=captured)[(row["query_id"], row["channel"])]
        self.assertEqual(joined["provider_state"], "success_empty")
        self.assertEqual(joined["raw_provider_state"], "success_output")
        self.assertEqual(joined["raw"]["returned_depth"], 100)
        self.assertEqual(joined["main_eligible"]["returned_depth"], 0)

    def test_dense_audit_summary_flags_cannot_hide_inconsistent_records(self):
        # A tiny synthetic audit exercises record guards; never serialized as model evidence.
        config = {"model": {"files": [{"relative_path": "pytorch_model.bin", "bytes": 8, "mtime_ns": 1,
            "sha256": "a" * 64, "digest_pin_scope": "checksum_verified_against_identity_probe"}],
            "snapshot_top_level_files": ["pytorch_model.bin"], "checkpoint_file": "pytorch_model.bin"}}
        records = [{"parameter": "encoder.weight", "checkpoint_key": "roberta.encoder.weight", "checkpoint_file": "pytorch_model.bin",
            "shape": [2], "elements": 2, "equal_after_declared_dtype_cast": True}]
        model = {"files": [{**config["model"]["files"][0], "size_and_mtime_stable_after_loading": True}],
            "snapshot_top_level_files": ["pytorch_model.bin"], "loading_info": {"missing_keys": [], "unexpected_keys": [], "mismatched_keys": [], "error_msgs": []},
            "core_encoder_missing_keys": [], "core_encoder_unexpected_keys": [],
            "checkpoint_parameter_audit": {"active_parameter_tensor_count": 1, "active_parameter_elements": 2, "all_active_encoder_parameters_equal_cached_checkpoint": True,
                "parameter_mapping_sha256": visibility.stable_digest(records), "parameters": records}}
        visibility.validate_dense_model(model, config)
        broken = copy.deepcopy(model)
        broken["files"][0]["sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "checksum differs"):
            visibility.validate_dense_model(broken, config)
        broken = copy.deepcopy(model)
        broken["checkpoint_parameter_audit"]["parameters"][0]["equal_after_declared_dtype_cast"] = False
        with self.assertRaisesRegex(ValueError, "digest/count differs"):
            visibility.validate_dense_model(broken, config)
        broken["checkpoint_parameter_audit"]["parameter_mapping_sha256"] = visibility.stable_digest(broken["checkpoint_parameter_audit"]["parameters"])
        with self.assertRaisesRegex(ValueError, "unequal or inconsistent"):
            visibility.validate_dense_model(broken, config)
        broken = copy.deepcopy(model)
        broken["loading_info"]["mismatched_keys"] = ["encoder.weight"]
        with self.assertRaisesRegex(ValueError, "mismatches or errors"):
            visibility.validate_dense_model(broken, config)

    def test_dense_sdk_empty_params_allowance_is_narrow(self):
        # Boundary-only adaptation of saved sparse candidates; no dense model claim.
        def adapt(value):
            if isinstance(value, dict):
                return {k.replace("bm25", "cosine"): adapt(v) for k, v in value.items()}
            if isinstance(value, list):
                return [adapt(v) for v in value]
            return value
        captured, scored = adapt(self.captured), adapt(self.scored)
        for raw, row in zip(captured, scored):
            raw["schema"] = "vecna82-dense-visibility-row-v1"
            row["schema"] = "vecna82-dense-visibility-scored-row-v1"
            raw["raw_call"]["anns_field"] = raw["channel"] + "_dense"
            raw["raw_call"]["search_params"] = {"metric_type": "COSINE", "nprobe": 32, "params": {}}
            row["native_query_state"] = copy.deepcopy(raw["raw_call"])
            raw["query_embedding"] = {"dimension": 1024, "l2_norm": 1.0}
            row["query_embedding"] = copy.deepcopy(raw["query_embedding"])
            row["corpus_query_encoder_compatibility"] = "unresolved"
        result = visibility.join_rows("dense", scored, captured, self.queries, self.truth, self.pairs, self.review_sha, {}, audit, self.scorer)
        self.assertEqual(len(result), 38)
        captured[0]["raw_call"]["search_params"]["params"] = {"nprobe": 1}
        scored[0]["native_query_state"] = copy.deepcopy(captured[0]["raw_call"])
        with self.assertRaisesRegex(ValueError, "provider request mismatch"):
            visibility.join_rows("dense", scored, captured, self.queries, self.truth, self.pairs, self.review_sha, {}, audit, self.scorer)

    def test_all_seed_orders_are_retained_without_seed_selection(self):
        self.assertEqual(self.provider["process_seed_tie_replay"]["rows_with_process_seed_order_variation"], 38)
        proof = ledger.read_json(ROOT / "outputs/source-visibility/tie-replay-v1/tie_proof.json")
        expected = visibility.pair_index(proof["rows"])
        for key, row in self.rows.items():
            replay = row["process_seed_tie_replay"]
            self.assertIsNone(replay["selection"])
            self.assertEqual(replay["predeclared_seeds"], [0, 1, 82])
            self.assertEqual(replay["frozen_range_or_event_by_observed_order"], expected[key]["scores"])
        values = {label: sum(row["process_seed_tie_replay"]["frozen_range_or_event_by_observed_order"][label]["metrics"]["MRR@20"] for (_, c), row in self.rows.items() if c == "asr") for label in ("host", "0", "1", "82")}
        self.assertGreater(len(set(values.values())), 1)

    def test_tie_membership_not_trusted_from_flags(self):
        source = "outputs/source-visibility/tie-replay-v1/seed-0.json"
        replay = ledger.read_json(ROOT / source)
        replay["rows"][0]["effective_frame_order"][0] = replay["rows"][0]["effective_frame_order"][1]
        parent_reader = visibility.Reader(ROOT)
        class AlteredSeedReader:
            root = ROOT
            hashes = parent_reader.hashes
            def json(self, path):
                return replay if path == source else parent_reader.json(path)
            def bind(self, path, expected):
                parent_reader.bind(path, expected)
        capture = ledger.read_json(ROOT / "outputs/source-visibility/sparse-v1/collection_manifest.json")
        with self.assertRaisesRegex(ValueError, "candidate membership changed"):
            visibility.tie_replay(AlteredSeedReader(), self.captured, self.truth, self.provider["provenance"], capture["code_identity"], audit, self.scorer)

    def test_attachment_preserves_all_labels_ranks_and_success_union(self):
        selected = {q for q, t in self.truth.items() if t["scoreable"]}
        dataset = ledger.dataset_join(ledger.read_jsonl(ROOT / "outputs/dataset-audit/audit.jsonl"), self.sample, selected)
        temporal = ledger.read_json(ROOT / "outputs/temporal-multi-image/summary.json")
        inventory = ledger.read_jsonl(ROOT / "outputs/dataset-audit/temporal_inventory.jsonl")
        crows = ledger.read_jsonl(ROOT / "outputs/reranker/per_query.jsonl")
        fusion = {"status": "NOT_RUN", "best_global_arm": None, "per_query": {}}
        per_query = {}
        for (q, channel), row in self.rows.items():
            per_query.setdefault(q, {})[channel] = {"sparse": row, "dense": {"status": "EVALUATION_NOT_AVAILABLE", "evidence": None}}
        overlay = {"per_query": per_query, "providers": {"sparse": self.provider}}
        before = ledger.build_rows(self.truth, crows, dataset, temporal, inventory, fusion)
        after = ledger.build_rows(self.truth, crows, dataset, temporal, inventory, fusion, visibility=overlay)
        self.assertEqual(len(after), 113)
        for old, new in zip(before, after):
            self.assertEqual({k: v for k, v in old.items() if k != "source_visibility"}, {k: v for k, v in new.items() if k != "source_visibility"})
            self.assertFalse(new["source_visibility"]["changes_primary_failure"])
            self.assertFalse(new["source_visibility"]["included_in_observed_arm_union"])
        s1, s2 = ledger.summarize(before, fusion), ledger.summarize(after, fusion, overlay)
        self.assertEqual({k: v for k, v in s1.items() if k != "source_visibility"}, {k: v for k, v in s2.items() if k != "source_visibility"})

if __name__ == "__main__":
    unittest.main()
