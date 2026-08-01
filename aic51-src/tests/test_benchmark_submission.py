import unittest

from aic51.packages.webui.backend.submission import (
    SubmissionValidationError,
    validate_submission_payload,
)


class SubmissionTests(unittest.TestCase):
    def test_validates_offline_payload(self):
        result = validate_submission_payload({"video_id": "L21_V001", "frame_id": "000060"}, rule_version="test")
        self.assertTrue(result["valid"])
        self.assertEqual(result["rule_version"], "test")

    def test_rejects_missing_location(self):
        with self.assertRaises(SubmissionValidationError):
            validate_submission_payload({"video_id": "L21_V001"})


if __name__ == "__main__":
    unittest.main()
