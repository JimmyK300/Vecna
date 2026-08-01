import tempfile
import unittest
from pathlib import Path

from aic51.packages.provenance import project_timed_segments, write_json_artifact


class EvidenceProjectionTests(unittest.TestCase):
    def test_projects_containing_and_nearest_segments(self):
        texts, projections = project_timed_segments(
            [{"start": 1.0, "end": 2.0, "text": " Hello   World "}],
            ["000030", "000090", "000180"],
            30,
        )

        self.assertEqual(texts, ["hello world", "hello world", ""])
        self.assertEqual(projections[0]["projection_rule"], "containing_segment")
        self.assertEqual(projections[1]["projection_rule"], "nearest_segment")
        self.assertEqual(projections[2]["projection_rule"], "no_segment")

    def test_json_artifact_is_created_with_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw" / "evidence.json"
            write_json_artifact(path, {"text": "đúng"})
            self.assertIn("đúng", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
