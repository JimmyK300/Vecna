from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "aic51-src" / "script"
PRIMARY_SCRIPT = Path(r"C:\Users\minhc\Code\Vecna\aic51-src\script")
sys.path.insert(0, str(SCRIPT))
sys.path.insert(0, str(PRIMARY_SCRIPT))

import headless_benchmark as hb
import issue63_stage_b_scoring as scoring
import run_issue63_stage_b as stage_b


def raw(video: str, frame: int) -> dict:
    return {"entity": {"frame_id": f"{video}#{frame}"}, "distance": 1.0, "time_line": [frame]}


class StageBScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.truth = stage_b.freeze_inputs()

    def test_review_inventory_and_qualified_identity(self) -> None:
        rows = self.truth["records"]
        self.assertEqual(len(rows), 49)
        self.assertEqual(sum(row["scoreable"] for row in rows), 48)
        self.assertEqual(len({row["source_qualified_id"] for row in rows}), 49)
        self.assertEqual([row["source_qualified_id"] for row in rows if not row["scoreable"]], ["testing88_submission633::p1-21"])

    def test_preliminary_questions_are_user_supplied(self) -> None:
        rows = [row for row in self.truth["records"] if row["source_submission"] == "final_round1_10_4of13"]
        self.assertEqual(len(rows), 25)
        self.assertTrue(all(row["query_text_status"] == "user_supplied_preliminary_round1_25_questions" for row in rows))

    def test_interval_endpoints_alternatives_outside_and_wrong_video(self) -> None:
        record = {"video_id": "L1_V001", "reviewed_ranges": [{"start_frame": 10, "end_frame": 20}, {"start_frame": 40, "end_frame": 50}]}
        self.assertTrue(scoring.score_reconstructed(record, [{"video_id": "L1_V001", "frame_id": 10}])["hit"])
        self.assertTrue(scoring.score_reconstructed(record, [{"video_id": "L1_V001", "frame_id": 50}])["hit"])
        self.assertTrue(scoring.score_reconstructed(record, [{"video_id": "L1_V001", "frame_id": 45}])["hit"])
        self.assertFalse(scoring.score_reconstructed(record, [{"video_id": "L1_V001", "frame_id": 21}])["hit"])
        self.assertFalse(scoring.score_reconstructed(record, [{"video_id": "L1_V002", "frame_id": 10}])["hit"])

    def test_explicit_segment_overlap(self) -> None:
        record = {"video_id": "V", "reviewed_ranges": [{"start_frame": 10, "end_frame": 20}]}
        self.assertTrue(scoring.result_matches_interval(record, {"video_id": "V", "start_frame": 5, "end_frame": 10}))
        self.assertFalse(scoring.result_matches_interval(record, {"video_id": "V", "start_frame": 21, "end_frame": 30}))

    def test_ambiguous_record_cannot_score(self) -> None:
        row = next(row for row in self.truth["records"] if row["source_qualified_id"] == "testing88_submission633::p1-21")
        self.assertFalse(row["scoreable"])
        self.assertEqual(row["reviewed_ranges"], [])

    def test_legacy_matcher_remains_unchanged(self) -> None:
        interval = {"query_id": "legacy", "scoreable": True, "target_mode": "any", "task_type": "tkis", "accepted_groups": [[{"kind": "interval", "video_id": "V", "start": 10, "end": 20}]]}
        self.assertEqual(hb.metrics_for_results([raw("V", 10)], interval, 0)["first_correct_rank"], 1)
        point = {"query_id": "legacy-point", "scoreable": True, "target_mode": "any", "task_type": "qa", "accepted_groups": [[{"kind": "point", "video_id": "V", "frame": 10}]]}
        self.assertIsNone(hb.metrics_for_results([raw("V", 11)], point, 0)["first_correct_rank"])
        fractional = scoring.aggregate([
            {"first_correct_rank": 1, "recall_at_1": 0.25, "recall_at_5": 0.5, "recall_at_10": 0.75, "recall_at_20": 1.0},
            {"first_correct_rank": None, "recall_at_1": 0.0, "recall_at_5": 0.0, "recall_at_10": 0.0, "recall_at_20": 0.0},
        ])
        self.assertEqual(fractional["recall_at_5"], 0.25)

    def test_fixed_baseline_contract_and_no_tuning_options(self) -> None:
        self.assertEqual(stage_b.BASELINE, {
            "cell": "clip_siglip_qwen_sparse", "rerank": False, "ocr_weight": 0.25,
            "asr_weight": 0.25, "nprobe": 32, "temporal_k": 2000,
            "query_expansion": False, "translation": False,
        })
        source = (SCRIPT / "run_issue63_stage_b.py").read_text(encoding="utf-8")
        for forbidden in ("--cell", "--nprobe", "--temporal-k", "--ocr-weight", "--asr-weight"):
            self.assertNotIn(f'add_argument("{forbidden}"', source)


if __name__ == "__main__":
    unittest.main()
