"""Reject the concrete false-success/provenance failure modes in Packet A."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("temporal_audit", ROOT / "code" / "temporal_audit.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class TemporalEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = audit.load_probe(ROOT / "inputs" / "temporal_processor_probe.json")
        cls.candidates = cls.probe["candidate_rows"]
        cls.embeddings = cls.probe["embedding_rows"]

    def test_global_complete_cache_is_not_eight_query_completion(self):
        result = audit.assess_cached_completion(self.candidates, self.embeddings)
        self.assertEqual(result["completed_embedding_count"], 11)
        self.assertEqual(result["prepared_candidate_window_count"], 48)
        self.assertEqual(result["paired_complete_query_ids"], [])
        self.assertFalse(result["matched_eight_query_experiment_complete"])
        p3 = next(row for row in result["per_query"] if row["query_id"] == "p3_q34")
        self.assertEqual(p3["modes"]["contact_sheet"]["completed_candidate_count"], 3)
        self.assertEqual(p3["modes"]["native3"]["completed_candidate_count"], 1)
        self.assertFalse(p3["complete_contact_sheet_and_native3_pair"])

    def test_duplicate_embedding_cannot_inflate_completion(self):
        with self.assertRaisesRegex(ValueError, "Duplicate cached"):
            audit.assess_cached_completion(self.candidates, self.embeddings + [self.embeddings[0]])

    def test_rank_id_reuse_with_changed_frames_is_rejected(self):
        rows = copy.deepcopy(self.embeddings)
        rows[0]["frame_ids"][1] += 1
        with self.assertRaisesRegex(ValueError, "frame identities"):
            audit.assess_cached_completion(self.candidates, rows)

    def test_bad_vector_and_changed_model_cannot_count_as_complete(self):
        for field, value in (("vector_finite", False), ("vector_dimensions", 1024), ("model_snapshot", "other-snapshot")):
            rows = copy.deepcopy(self.embeddings)
            rows[0][field] = value
            with self.assertRaises(ValueError):
                audit.assess_cached_completion(self.candidates, rows)

    def test_missing_timing_is_unknown_not_zero(self):
        result = audit.timing_estimates(self.embeddings, self.probe["stage2b_surface_manifest.json"])
        self.assertEqual(result["contact_sheet"]["measured_candidate_count"], 7)
        self.assertEqual(result["contact_sheet"]["cached_rows_without_timing"], 3)
        self.assertAlmostEqual(result["native3"]["measured_per_candidate_s"][0], 5433.048)
        self.assertAlmostEqual(result["native3"]["estimated_remaining_candidate_s"], 5433.048 * 23)

    def test_actual_processor_proves_order_and_equal_visual_budget(self):
        result = audit.assess_processor_proof(self.probe)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["image_token_count_ratio_to_sheet"]["native3_matched_384x216"], 1)
        self.assertGreater(result["image_token_count_ratio_to_sheet"]["native3_original"], 10)

    def test_repeated_image_cannot_pass_native_distinctness(self):
        probe = copy.deepcopy(self.probe)
        probe["processor_proof"]["native3_original"]["ordered_patch_chunk_hashes"] = ["same"] * 3
        self.assertNotEqual(audit.assess_processor_proof(probe)["status"], "PASS")

    def test_reordered_or_truncated_input_cannot_pass(self):
        for field, value in (("each_patch_chunk_equals_individual_image_processing", [False, True, False]), ("all_image_tokens_present", False)):
            probe = copy.deepcopy(self.probe)
            probe["processor_proof"]["native3_matched_384x216"][field] = value
            self.assertNotEqual(audit.assess_processor_proof(probe)["status"], "PASS")

    def test_current_pool_same_sets_but_p3_rank_swap_is_detected(self):
        pools, candidates = audit.compare_candidate_pools(
            audit.read_rows(ROOT / "inputs" / "legacy_temporal_control_113.jsonl"),
            audit.read_rows(ROOT / "inputs" / "qwen_only_top100.jsonl"))
        self.assertEqual(len(candidates), 24)
        self.assertTrue(all(row["candidate_sets_equal"] for row in pools))
        changed = [row for row in pools if not row["ordered_equal"]]
        self.assertEqual([row["query_id"] for row in changed], ["p3_q34"])
        self.assertEqual(changed[0]["current_to_historical_rank"], [1, 3, 2])

    def test_tampered_recovered_manifest_is_rejected(self):
        bundle = json.loads((ROOT / "inputs" / "stage2b_recovered.json").read_text())
        bundle["files"][0]["content"] += "changed"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit.recover_manifests(bundle)


if __name__ == "__main__":
    unittest.main()
