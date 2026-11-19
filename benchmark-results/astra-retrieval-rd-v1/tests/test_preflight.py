"""Identity and denominator regressions for the offline Vecna #82 control."""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
import preflight


class PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = preflight.read_jsonl(ROOT / "inputs/canonical_truth.jsonl")
        cls.baseline = preflight.read_jsonl(ROOT / "inputs/qwen_only_top100.jsonl")
        cls.reranker = preflight.read_json(ROOT / "inputs/qwen3_vl_reranker_2b_top100.json")["per_query"]

    def test_exact_control_reproduces_from_canonical_truth(self):
        manifest = preflight.build_manifest(ROOT)
        self.assertGreaterEqual(len(manifest["sources"]), 17)
        self.assertEqual(manifest["query_surface"]["total"], 115)
        self.assertEqual(len(manifest["query_surface"]["scoreable_ids"]), 113)
        self.assertEqual(manifest["query_surface"]["excluded_ids"], ["p0_q15", "p3_q09"])
        self.assertEqual(manifest["truth_surface"]["historical_trake_count"], 6)
        self.assertEqual(manifest["truth_surface"]["p3_trake_count"], 2)
        controls = manifest["controls"]["metrics"]
        self.assertEqual(controls["baseline"]["recall_at_20"], 68)
        self.assertEqual(controls["reranker"]["recall_at_20"], 76)
        self.assertAlmostEqual(controls["baseline"]["mrr_at_20"], 0.4243397949150161)
        self.assertAlmostEqual(controls["reranker"]["mrr_at_20"], 0.4320209888728889)

    def test_byte_tampering_fails_before_reference_code_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inputs").mkdir()
            shutil.copyfile(ROOT / "inputs/sources.json", root / "inputs/sources.json")
            (root / "inputs/canonical_truth.jsonl").write_bytes((ROOT / "inputs/canonical_truth.jsonl").read_bytes() + b"\n")
            with self.assertRaisesRegex(preflight.PreflightError, "Git blob mismatch"):
                preflight.verify_sources(root)

    def test_source_pin_cannot_be_replaced_by_editing_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inputs").mkdir()
            sources = preflight.read_json(ROOT / "inputs/sources.json")
            sources[0]["commit"] = "0" * 40
            (root / "inputs/sources.json").write_text(json.dumps(sources))
            with self.assertRaisesRegex(preflight.PreflightError, "immutable pins"):
                preflight.verify_sources(root)

    def test_same_count_with_different_identity_fails(self):
        changed = copy.deepcopy(self.baseline)
        changed[0]["query_id"] = "p0_q99"
        with self.assertRaisesRegex(preflight.PreflightError, "identity mismatch"):
            preflight.verify_queries(self.canonical, baseline=changed)

    def test_duplicate_query_id_fails_instead_of_overwriting_a_row(self):
        changed = copy.deepcopy(self.baseline)
        changed[0]["query_id"] = changed[1]["query_id"]
        with self.assertRaisesRegex(preflight.PreflightError, "Duplicate query identity"):
            preflight.verify_queries(self.canonical, baseline=changed)

    def test_query_text_drift_is_not_silently_normalized(self):
        changed = copy.deepcopy(self.baseline)
        changed[0]["query"] += " "
        with self.assertRaisesRegex(preflight.PreflightError, "Exact query-text mismatch"):
            preflight.verify_queries(self.canonical, baseline=changed)

    def test_canonical_text_change_breaks_frozen_text_hash(self):
        changed = copy.deepcopy(self.canonical)
        changed[0]["query"] += " changed"
        with self.assertRaisesRegex(preflight.PreflightError, "query-text hash"):
            preflight.verify_queries(changed)

    def test_new_exclusion_cannot_remove_the_empty_retrieval_case(self):
        changed = copy.deepcopy(self.canonical)
        next(row for row in changed if row["query_id"] == "p2_q17")["scoreable"] = False
        with self.assertRaisesRegex(preflight.PreflightError, "exclusions changed"):
            preflight.verify_queries(changed)

    def test_truth_edit_cannot_survive_projection_check(self):
        changed = copy.deepcopy(self.canonical)
        changed[0]["accepted_video_id"] = "L00_V000"
        with self.assertRaisesRegex(preflight.PreflightError, "provenance-backed"):
            preflight.verify_projection(ROOT, changed)

    def test_reranker_cannot_invent_a_candidate(self):
        changed = copy.deepcopy(self.reranker)
        changed[0]["reranked_candidates_top20"][0]["video_id"] = "L00_V000"
        with self.assertRaisesRegex(preflight.PreflightError, "outside frozen baseline mapping"):
            preflight.verify_candidates(self.baseline, changed)

    def test_existing_duplicates_and_empty_row_are_preserved(self):
        surface = preflight.verify_candidates(self.baseline, self.reranker)
        self.assertEqual(surface["empty_query_ids"], ["p2_q17"])
        self.assertEqual(surface["reranked_candidates_verified_in_frozen_pool"], 2280)
        self.assertEqual(sum(surface["duplicate_occurrences_preserved"]["baseline"].values()), 318)
        self.assertEqual(sum(surface["duplicate_occurrences_preserved"]["reranker"].values()), 63)
        self.assertFalse(surface["full_top100_reranker_scores_saved"])

    def test_optional_host_evidence_cannot_claim_different_json_is_equivalent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inputs").mkdir()
            for filename in ("previous_controls.json", "historical_manifest.json", "comparison_qwen_vs_reranker.json", "qwen3_vl_reranker_2b_top100.json"):
                shutil.copyfile(ROOT / "inputs" / filename, root / "inputs" / filename)
            identity = {"raw_sha256": "9cc4d5cc7a8432aa36f3cc3ac8d08dabc4b17ab35c195d1344e6f6afa4c4d0b4",
                        "lf_sha256": "4e949d95916c9fed7b11327ace67e207eb9238bb9f3beb4e66ff4873cb3ec8be",
                        "canonical_json_sha256": "0" * 64, "source_url": "test"}
            (root / "inputs/host_reranker_identity.json").write_text(json.dumps(identity))
            with self.assertRaisesRegex(preflight.PreflightError, "JSON identity differs"):
                preflight.legacy_checksum_reconciliation(root)

    def test_saved_analysis_does_not_claim_current_runtime_parity(self):
        manifest = preflight.build_manifest(ROOT)
        self.assertEqual(manifest["packet_readiness"]["C_saved_reranker"]["status"], "ready")
        surface = manifest["model_index_surface"]
        self.assertIsNone(surface["index_fingerprint"])
        self.assertIsNone(surface["current_package_versions"])
        self.assertEqual(surface["host_observations"]["loaded_model_index_parity"], "unverified")


if __name__ == "__main__":
    unittest.main()
