import unittest

from aic51.packages.provenance import assess_legacy_migration


class MigrationTests(unittest.TestCase):
    def test_policy_change_requires_keyframe_reextraction_but_allows_feature_verification(self):
        legacy = {
            "features": {
                "videos": {
                    "L21_V001": {
                        "artifacts": {
                            "image_clip_pe-l-14-336.npy": {"contract": {"shape": [1024]}},
                            "ocr.npy": {"contract": {"shape": []}},
                        }
                    }
                }
            }
        }
        result = assess_legacy_migration(
            legacy,
            target_features={
                "image_clip_pe-l-14-336": {"index": {"dim": 1024}},
                "asr": {"index": {"dim": None}},
            },
            legacy_keyframe_policy="ffprobe_iframe",
            target_keyframe_policy="transnetv2",
        )

        self.assertEqual(result["keyframes"], "reextract_required")
        self.assertEqual(result["features"]["image_clip_pe-l-14-336"]["decision"], "reuse_after_frame_verification")
        self.assertEqual(result["features"]["asr"]["decision"], "analyse_required")
        self.assertEqual(result["ocr_quality"], "unverified")


if __name__ == "__main__":
    unittest.main()
