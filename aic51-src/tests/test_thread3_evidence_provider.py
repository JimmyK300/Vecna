import json
import tempfile
import unittest
from pathlib import Path

from aic51.packages.search.evidence_provider import (
    EvidenceBundleError,
    attach_thread3_evidence_provider,
    load_thread3_evidence_bundle,
)


class FakeSearcher:
    def __init__(self):
        self.calls = []

    def search_multimodal(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"results": [{"id": "baseline"}], "total": 1, "offset": 0}


class Thread3EvidenceProviderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "fused_candidates.json").write_text(
            json.dumps(
                {
                    "query_id": "query-p2-4-kis",
                    "task_type": "KIS",
                    "fused_candidates": [
                        {
                            "media_id": "L30_V072",
                            "best_frame": "001234",
                            "rrf_score": 0.03125,
                            "best_frame_fused_rank": 8,
                            "fused_rank": 12,
                            "modalities_supporting": ["semantic_index", "siglip"],
                            "contributors": [
                                {"modality": "siglip", "rank": 3, "score": 0.8}
                            ],
                            "timestamp_provenance": {
                                "semantic_record": {
                                    "segment_id": "L30_V072__3",
                                    "start_sec": 10.0,
                                    "end_sec": 20.0,
                                    "path": "semantic-index/L30_V072.jsonl",
                                }
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.root / "verification_queue.json").write_text(
            json.dumps(
                {
                    "query_id": "query-p2-4-kis",
                    "verification_queue": [
                        {
                            "media_id": "L30_V072",
                            "best_frame": "001234",
                            "fused_rank": 12,
                            "rrf_score": 0.03125,
                            "already_ruled_out": True,
                            "verification_status": "ruled_out",
                            "needs_visual_inspection": False,
                            "repeat_verification": False,
                            "priority_rank": 999,
                            "ruling_source": "historical-p2-q4",
                            "ruling_conclusion": "reject",
                            "ruling_observed_content": "visual mismatch",
                            "verification_obligations": [
                                {
                                    "obligation": "banner matches",
                                    "verdict_space": ["PASS", "FAIL", "UNKNOWN"],
                                }
                            ],
                            "calibration_notice": "Retrieval scores are ranking signals only.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.root / "manifest.json").write_text(
            json.dumps(
                {
                    "runner_script_sha256": "a" * 64,
                    "git_commit": "upstream-head",
                    "indices": {"n_canonical_videos": 873},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_preserves_provenance_and_rejection(self):
        provider = load_thread3_evidence_bundle(self.root)
        self.assertEqual(provider["provider"], "thread3_evidence")
        self.assertEqual(provider["query_id"], "query-p2-4-kis")
        candidate = provider["candidates"][0]
        self.assertEqual(candidate["video_id"], "L30_V072")
        self.assertEqual(candidate["frame_id"], "001234")
        self.assertEqual(candidate["segment_id"], "L30_V072__3")
        self.assertEqual(
            candidate["time_range"],
            {"start_sec": 10.0, "end_sec": 20.0, "source": "semantic_record"},
        )
        self.assertEqual(candidate["upstream_rank"], 12)
        self.assertEqual(candidate["upstream_score"]["value"], 0.03125)
        self.assertNotIn("confidence", candidate)
        self.assertTrue(candidate["verification"]["already_ruled_out"])
        self.assertEqual(candidate["verification"]["ruling_conclusion"], "reject")
        self.assertEqual(
            provider["source"]["upstream_manifest"]["indices"]["n_canonical_videos"],
            873,
        )

    def test_disabled_provider_is_exact_baseline_return_and_call(self):
        cls = type("LocalFakeSearcher", (FakeSearcher,), {})
        attach_thread3_evidence_provider(cls)
        searcher = cls()
        result = searcher.search_multimodal("query", limit=7)
        self.assertEqual(
            result,
            {"results": [{"id": "baseline"}], "total": 1, "offset": 0},
        )
        self.assertNotIn("evidence_provider", result)
        self.assertEqual(searcher.calls, [(("query",), {"limit": 7})])

    def test_enabled_provider_adds_separate_channel_without_reordering_baseline(self):
        cls = type("LocalFakeSearcher", (FakeSearcher,), {})
        attach_thread3_evidence_provider(cls)
        searcher = cls()
        result = searcher.search_multimodal(
            "query",
            limit=7,
            evidence_bundle_path=self.root,
        )
        self.assertEqual(result["results"], [{"id": "baseline"}])
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["offset"], 0)
        self.assertEqual(searcher.calls, [(("query",), {"limit": 7})])
        self.assertEqual(
            result["evidence_provider"]["candidates"][0]["video_id"],
            "L30_V072",
        )

    def test_attach_is_idempotent(self):
        cls = type("LocalFakeSearcher", (FakeSearcher,), {})
        attach_thread3_evidence_provider(cls)
        first = cls.search_multimodal
        attach_thread3_evidence_provider(cls)
        self.assertIs(first, cls.search_multimodal)

    def test_enabled_provider_fails_closed_on_invalid_bundle(self):
        cls = type("LocalFakeSearcher", (FakeSearcher,), {})
        attach_thread3_evidence_provider(cls)
        invalid = self.root / "invalid"
        invalid.mkdir()
        with self.assertRaises(EvidenceBundleError):
            cls().search_multimodal("query", evidence_bundle_path=invalid)


if __name__ == "__main__":
    unittest.main()
