import copy
import unittest

from compare_data_contracts import compare_reports


def make_report(*, content_hashing=True, keyframe_manifest="keyframes-v1", feature_manifest="feature-v1"):
    return {
        "workspace": "workspace",
        "content_hashing": content_hashing,
        "config": {
            "add": {"keyframe_resize_ratio": 1.0},
            "features": {
                "image_clip": {
                    "model": "image_clip",
                    "dimension": 1024,
                }
            },
        },
        "videos": {
            "videos": [
                {
                    "id": "video-001",
                    "relative_path": "video-001.mp4",
                    "bytes": 10,
                    "sha256": "video-v1" if content_hashing else None,
                }
            ]
        },
        "keyframes": {
            "videos": {
                "video-001": {
                    "frame_ids": ["000001"],
                    "file_sizes": ["10 bytes"],
                    "image_dimensions": ["2x3"],
                    "manifest_sha256": keyframe_manifest,
                }
            }
        },
        "features": {
            "videos": {
                "video-001": {
                    "feature_counts": {"image_clip": 1},
                    "feature_frame_ids": {"image_clip": ["000001"]},
                    "feature_manifests": {"image_clip": feature_manifest},
                }
            }
        },
        "milvus": {
            "enabled": True,
            "exists": True,
            "schema": {"fields": ["image_clip"]},
            "indexes": ["image_clip_index"],
        },
    }


class CompareDataContractsTests(unittest.TestCase):
    def test_identical_reports_can_reuse_artifacts_and_index(self):
        report = make_report()
        comparison = compare_reports(report, copy.deepcopy(report))

        self.assertEqual(comparison["sources"]["video-001"]["decision"], "reuse")
        self.assertEqual(comparison["keyframes"]["video-001"]["decision"], "reuse")
        self.assertEqual(
            comparison["features"]["video-001"]["image_clip"]["decision"],
            "reuse",
        )
        self.assertEqual(comparison["milvus"]["decision"], "reuse_possible")
        self.assertEqual(comparison["index"]["decision"], "reuse_possible")

    def test_added_feature_requires_analysis(self):
        baseline = make_report()
        candidate = copy.deepcopy(baseline)
        candidate["config"]["features"]["image_siglip"] = {
            "model": "image_siglip",
            "dimension": 1152,
        }

        comparison = compare_reports(baseline, candidate)

        self.assertEqual(comparison["configuration"]["features_added"], ["image_siglip"])
        self.assertEqual(
            comparison["features"]["video-001"]["image_siglip"]["decision"],
            "analyse",
        )
        self.assertEqual(comparison["index"]["decision"], "rebuild_required")

    def test_changed_keyframes_require_reanalysis(self):
        baseline = make_report()
        candidate = make_report(keyframe_manifest="keyframes-v2")

        comparison = compare_reports(baseline, candidate)

        self.assertEqual(comparison["keyframes"]["video-001"]["decision"], "reprocess")
        self.assertEqual(
            comparison["features"]["video-001"]["image_clip"]["decision"],
            "reanalyse",
        )
        self.assertEqual(comparison["index"]["decision"], "rebuild_required")

    def test_without_content_hashes_report_requires_verification(self):
        report = make_report(content_hashing=False)
        comparison = compare_reports(report, copy.deepcopy(report))

        self.assertEqual(comparison["sources"]["video-001"]["decision"], "verify")
        self.assertEqual(comparison["keyframes"]["video-001"]["decision"], "verify")
        self.assertEqual(
            comparison["features"]["video-001"]["image_clip"]["decision"],
            "verify",
        )
        self.assertEqual(comparison["index"]["decision"], "rebuild_required")


if __name__ == "__main__":
    unittest.main()
