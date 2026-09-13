from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "aic51-src" / "script" / "run_headless_vnext_retrieval.py"
WRAPPER_PATH = ROOT / "aic51-src" / "script" / "score_headless_vnext_p0_p1_p2.py"
PACKET = ROOT / "benchmark-results" / "headless-vnext-p0-p1-p2-v1"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


runner = _load(RUNNER_PATH, "run_headless_vnext_retrieval")
wrapper = _load(WRAPPER_PATH, "score_headless_vnext_p0_p1_p2")


class HeadlessVNextP0P1P2PacketTests(unittest.TestCase):
    def test_frozen_48_row_authority_still_validates_without_p2(self):
        result = runner.validate_manifest()
        self.assertEqual(result["counts"]["execution_rows"], 48)
        self.assertEqual(result["counts"]["p2_rows"], 0)
        frozen = json.loads((ROOT / "benchmark-results" / "headless-vnext" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(frozen["purpose"], runner.FROZEN_MANIFEST_PURPOSE)
        self.assertEqual(runner.sha256_file(runner.MANIFEST_PATH), runner.EXPECTED_MANIFEST_SHA)
        self.assertEqual(runner.sha256_file(runner.CANONICAL_TEXT_PATH), runner.EXPECTED_CANONICAL_TEXT_SHA)
        self.assertEqual(runner.sha256_file(runner.SCORER_PATH), runner.EXPECTED_SCORER_SHA)

    def test_p2_packet_is_exactly_30_and_combined_is_78(self):
        p2 = json.loads((PACKET / "p2-only-manifest.json").read_text(encoding="utf-8"))
        combined = json.loads((PACKET / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(p2["records"]), 30)
        self.assertEqual(p2["counts"]["p2_rows"], 30)
        self.assertEqual(len(combined["records"]), 78)
        self.assertEqual(combined["counts"]["p0_rows"], 23)
        self.assertEqual(combined["counts"]["p1_rows"], 25)
        self.assertEqual(combined["counts"]["p2_rows"], 30)
        self.assertEqual(combined["counts"]["p2_video_scoreable"], 26)
        self.assertEqual(combined["counts"]["p2_unscoreable"], 4)
        self.assertNotEqual(p2["purpose"], runner.FROZEN_MANIFEST_PURPOSE)
        self.assertNotEqual(combined["purpose"], runner.FROZEN_MANIFEST_PURPOSE)
        runner.validate_extended_manifest(PACKET / "p2-only-manifest.json", PACKET / "canonical-query-texts.json")
        runner.validate_extended_manifest(PACKET / "manifest.json", PACKET / "canonical-query-texts.json")

    def test_p2_count_guard_fails_when_not_30(self):
        p2 = json.loads((PACKET / "p2-only-manifest.json").read_text(encoding="utf-8"))
        p2["records"] = p2["records"][:29]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p2.json"
            path.write_text(json.dumps(p2), encoding="utf-8")
            with self.assertRaisesRegex(runner.PacketError, r"P2 count 29 != 30"):
                runner.validate_extended_manifest(path, PACKET / "canonical-query-texts.json")

    def test_p3_text_contamination_is_rejected(self):
        p2 = json.loads((PACKET / "p2-only-manifest.json").read_text(encoding="utf-8"))
        p3_texts = runner.p3_normalized_texts()
        self.assertEqual(len(p3_texts), 36)
        for record in p2["records"]:
            norm = " ".join(record["query_text"].split()).casefold()
            self.assertNotIn(norm, p3_texts)
        p2["records"][0]["query_text"] = next(iter(p3_texts))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p2.json"
            path.write_text(json.dumps(p2), encoding="utf-8")
            with self.assertRaisesRegex(runner.PacketError, "P3 text contamination"):
                runner.validate_extended_manifest(path, PACKET / "canonical-query-texts.json")

    def test_duplicate_canonical_ids_are_rejected(self):
        p2 = json.loads((PACKET / "p2-only-manifest.json").read_text(encoding="utf-8"))
        p2["records"][1]["canonical_query_id"] = p2["records"][0]["canonical_query_id"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p2.json"
            path.write_text(json.dumps(p2), encoding="utf-8")
            with self.assertRaisesRegex(runner.PacketError, "duplicate canonical_query_id"):
                runner.validate_extended_manifest(path, PACKET / "canonical-query-texts.json")

    def test_round_identity_is_not_inferred_from_organizer_prefix(self):
        p2 = json.loads((PACKET / "p2-only-manifest.json").read_text(encoding="utf-8"))
        for record in p2["records"]:
            self.assertEqual(runner.canonical_round_of(record), "P2")
            self.assertTrue(str(record["raw_query_id"]).startswith("query-p2-"))
            self.assertEqual(record["canonical_source_id"], "actual_p2_official")
            self.assertEqual(
                record["canonical_query_id"],
                f"actual_p2_official::{record['raw_query_id']}",
            )
        fake = copy.deepcopy(p2["records"][0])
        fake["canonical_source_id"] = "p3_round3_benchmark_v1"
        fake["canonical_query_id"] = f"p3_round3_benchmark_v1::{fake['raw_query_id']}"
        with self.assertRaisesRegex(runner.PacketError, "cannot assign canonical round from organizer prefix"):
            runner.canonical_round_of(fake)
        p2["records"][0]["canonical_source_id"] = "p3_round3_benchmark_v1"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p2.json"
            path.write_text(json.dumps(p2), encoding="utf-8")
            with self.assertRaisesRegex(runner.PacketError, "actual_p2_official"):
                runner.validate_extended_manifest(path, PACKET / "canonical-query-texts.json")

    def test_unscoreable_p2_rows_remain_in_packet_but_are_not_video_scoreable(self):
        p2 = json.loads((PACKET / "p2-only-manifest.json").read_text(encoding="utf-8"))
        unscored = [r for r in p2["records"] if not r["scoreability"]["video"]]
        self.assertEqual(
            {r["raw_query_id"] for r in unscored},
            {"query-p2-5-kis", "query-p2-6-kis", "query-p2-18-kis", "query-p2-29-qa"},
        )
        for record in unscored:
            self.assertEqual(record["accepted_video_id"], "")
            self.assertEqual(record["accepted_ranges"], [])

    def test_wrapper_excludes_unscoreable_rows_from_denominators(self):
        p2 = json.loads((PACKET / "p2-only-manifest.json").read_text(encoding="utf-8"))
        rankings = {}
        for record in p2["records"]:
            video = record["accepted_video_id"] or "L21_V001"
            rankings[record["canonical_query_id"]] = [
                {"rank": 1, "video_id": video, "frame_id": 1, "time_line": [1]}
            ]
        all_rows, summary, scoreable = wrapper.score_packet(p2, rankings)
        self.assertEqual(len(all_rows), 30)
        self.assertEqual(len(scoreable), 26)
        self.assertEqual(summary["scored_counts"]["queries"], 26)
        self.assertEqual(summary["scored_counts"]["p2_unscoreable"], 4)
        self.assertEqual(summary["scored_counts"]["p2_execution_rows"], 30)
        self.assertEqual(summary["video"]["R@1"], 1.0)
        self.assertEqual(len(summary["unscoreable"]), 4)
        self.assertIn("kis", summary["by_task_type"])
        self.assertIn("qa", summary["by_task_type"])
        self.assertIn("trake", summary["by_task_type"])


if __name__ == "__main__":
    unittest.main()
