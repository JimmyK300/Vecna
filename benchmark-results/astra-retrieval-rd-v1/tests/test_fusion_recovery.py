#!/usr/bin/env python3
"""Focused regressions for evidence recovery; no model/runtime dependencies."""
import hashlib
import importlib.util
import lzma
import sys
import tempfile
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1] / "code"
sys.path.insert(0, str(CODE))
from hydrate_fusion_capture import hydrate, verify_bytes
from analyze_fusion_headroom import coverage

class TinyScorer:
    @staticmethod
    def ranked(items):
        return [{**row, "_rank": row["rank"]} for row in items]
    @staticmethod
    def norm_video(video):
        return video
    @staticmethod
    def p3_target_hit(row, target):
        return row["frame_id"] == target["frame_id"] and row["video_id"] == target["video_id"]
    @staticmethod
    def first_rank(ranks):
        return ranks[0] if ranks else None
    @staticmethod
    def hit_at(rank, k):
        return rank is not None and rank <= k
    @staticmethod
    def reciprocal(rank):
        return 1 / rank if rank is not None and rank <= 20 else 0

class RecoveryTests(unittest.TestCase):
    def identities(self, raw):
        packed = lzma.compress(raw)
        return packed, (len(packed), hashlib.sha256(packed).hexdigest()), (len(raw), hashlib.sha256(raw).hexdigest())
    def test_verified_hydration_is_idempotent(self):
        raw = b'{"query_id":"fixture"}\n'
        packed, aid, rid = self.identities(raw)
        with tempfile.TemporaryDirectory() as directory:
            archive, target = Path(directory) / "raw.xz", Path(directory) / "raw.jsonl"
            archive.write_bytes(packed)
            self.assertTrue(hydrate(archive, target, aid, rid)["created"])
            self.assertEqual(target.read_bytes(), raw)
            self.assertFalse(hydrate(archive, target, aid, rid)["created"])
    def test_foreign_existing_raw_is_preserved(self):
        packed, aid, rid = self.identities(b"expected")
        with tempfile.TemporaryDirectory() as directory:
            archive, target = Path(directory) / "raw.xz", Path(directory) / "raw"
            archive.write_bytes(packed)
            target.write_bytes(b"foreign")
            with self.assertRaises(ValueError):
                hydrate(archive, target, aid, rid)
            self.assertEqual(target.read_bytes(), b"foreign")
    def test_corrupt_archive_creates_no_raw(self):
        packed, aid, rid = self.identities(b"expected")
        with tempfile.TemporaryDirectory() as directory:
            archive, target = Path(directory) / "raw.xz", Path(directory) / "raw"
            archive.write_bytes(packed[:-1] + bytes([packed[-1] ^ 1]))
            with self.assertRaises(ValueError):
                hydrate(archive, target, aid, rid)
            self.assertFalse(target.exists())
    def test_wrong_decompressed_identity_creates_no_raw(self):
        packed, aid, rid = self.identities(b"expected")
        with tempfile.TemporaryDirectory() as directory:
            archive, target = Path(directory) / "raw.xz", Path(directory) / "raw"
            archive.write_bytes(packed)
            with self.assertRaises(ValueError):
                hydrate(archive, target, aid, (rid[0], "0" * 64))
            self.assertFalse(target.exists())
    def test_set_coverage_ignores_inherited_provider_ranks(self):
        truth = {"truth_tier": "p3_source_text", "task_type": "trake", "accepted_groups": [[
            {"video_id": "v", "frame_id": "v_10"}, {"video_id": "v", "frame_id": "v_20"}
        ]]}
        items = [{"video_id": "v", "frame_id": "v_10", "rank": 1000},
                 {"video_id": "v", "frame_id": "v_20", "rank": 1001}]
        all_items = coverage(items, truth, TinyScorer)
        one_item = coverage(items[:1], truth, TinyScorer)
        empty = coverage([], truth, TinyScorer)
        self.assertEqual(all_items["target_present"], [True, True])
        self.assertEqual(all_items["target_coverage"], 1)
        self.assertEqual(one_item["target_present"], [True, False])
        self.assertEqual(one_item["target_coverage"], .5)
        self.assertEqual(empty["target_present"], [False, False])
        self.assertFalse(empty["accepted_video_present"])

if __name__ == "__main__":
    unittest.main()
