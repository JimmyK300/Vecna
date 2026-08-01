import unittest

from aic51.packages.webui.backend.utils import process_searcher_results


class SearchResponseTests(unittest.TestCase):
    def test_envelope_adds_evidence_without_removing_legacy_fields(self):
        response = process_searcher_results(
            {
                "results": [
                    {
                        "entity": {
                            "frame_id": "L21_V001#000060",
                            "ocr": "visible text",
                            "feature_availability": {"clip": {"status": "ready"}},
                        },
                        "scores": {"final": 0.8, "clip": 0.8, "ocr": 0.2, "asr": 0.0},
                    }
                ],
                "total": 1,
                "offset": 0,
                "fusion_method": "VecnaWeightedFusion",
            }
        )

        frame = response["frames"][0]
        self.assertEqual(frame["id"], "L21_V001#000060")
        self.assertEqual(frame["scores"]["final"], 0.8)
        self.assertEqual(frame["result_schema_version"], "2")
        self.assertEqual(frame["matched_modalities"], ["clip", "ocr"])
        self.assertEqual(frame["matched_text"], {"ocr": "visible text"})
        self.assertEqual(frame["fusion_method"], "VecnaWeightedFusion")
        self.assertEqual(frame["source_artifact_ids"], ["L21_V001#000060"])
        self.assertEqual(frame["feature_availability"]["clip"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
