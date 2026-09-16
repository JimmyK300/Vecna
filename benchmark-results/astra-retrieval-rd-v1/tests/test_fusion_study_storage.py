#!/usr/bin/env python3
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from fusion_study import ARMS, ContractError, digest_bytes
from fusion_study_storage import serialized, timing_rows, restore_timing_bytes

class StudyStorageTests(unittest.TestCase):
    def fixture(self):
        rows = [{"query_id": "fixture", "arms": {
            arm: {"frames": [{"frame_id": "video#1", "score": 0.12345678901234567}],
                  "videos": [{"video_id": "video"}], "fusion_wall_ns": 100 + i, "fusion_cpu_ns": 0}
            for i, arm in enumerate(ARMS)}}]
        raw = serialized(rows)
        replayed = copy.deepcopy(rows)
        for value in replayed[0]["arms"].values():
            value["fusion_wall_ns"] = 999
            value["fusion_cpu_ns"] = 888
        return rows, replayed, raw
    def test_restore_only_timings_reconstructs_exact_bytes(self):
        rows, replayed, raw = self.fixture()
        before = copy.deepcopy(replayed)
        result = restore_timing_bytes(replayed, timing_rows(rows), len(raw), digest_bytes(raw))
        self.assertEqual(result, raw)
        self.assertEqual(replayed, before)
    def test_changed_timing_fails_exact_sha_gate(self):
        rows, replayed, raw = self.fixture()
        saved = timing_rows(rows)
        saved[0][1][0][0] += 1
        with self.assertRaisesRegex(ContractError, "byte-exact"):
            restore_timing_bytes(replayed, saved, len(raw), digest_bytes(raw))
    def test_nontiming_score_change_cannot_be_hidden(self):
        rows, replayed, raw = self.fixture()
        replayed[0]["arms"][ARMS[0]]["frames"][0]["score"] += 0.1
        with self.assertRaisesRegex(ContractError, "byte-exact"):
            restore_timing_bytes(replayed, timing_rows(rows), len(raw), digest_bytes(raw))
    def test_missing_or_misidentified_query_fails(self):
        rows, replayed, raw = self.fixture()
        for saved in ([], [["wrong", timing_rows(rows)[0][1]]]):
            with self.subTest(saved=saved), self.assertRaises(ContractError):
                restore_timing_bytes(replayed, saved, len(raw), digest_bytes(raw))
    def test_negative_bool_or_noninteger_timings_fail(self):
        rows, replayed, raw = self.fixture()
        for invalid in (-1, True, 0.5, None):
            saved = timing_rows(rows)
            saved[0][1][0][0] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ContractError, "integer"):
                restore_timing_bytes(replayed, saved, len(raw), digest_bytes(raw))
    def test_wrong_arm_count_and_missing_field_fail(self):
        rows, replayed, raw = self.fixture()
        saved = timing_rows(rows)
        saved[0][1].pop()
        with self.assertRaisesRegex(ContractError, "arm count"):
            restore_timing_bytes(replayed, saved, len(raw), digest_bytes(raw))
        replayed[0]["arms"][ARMS[0]].pop("fusion_cpu_ns")
        with self.assertRaisesRegex(ContractError, "field"):
            restore_timing_bytes(replayed, timing_rows(rows), len(raw), digest_bytes(raw))

if __name__ == "__main__":
    unittest.main()
