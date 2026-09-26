import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aic51" / "packages" / "search" / "camera_metadata.py"
spec = importlib.util.spec_from_file_location("camera_metadata", MODULE_PATH)
camera_metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera_metadata)


class CameraMetadataTest(unittest.TestCase):
    def test_camera_filters_combine_road_and_lighting_before_search(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "camera.json"
            metadata_path.write_text(json.dumps([
                {"video_id": "N001-V001", "intersection_type": "4-Way Intersection", "time_of_day": "07:59:49"},
                {"video_id": "N001-V002", "intersection_type": "4-Way Intersection", "time_of_day": "18:59:56"},
                {"video_id": "N002-V001", "intersection_type": "Roundabout", "time_of_day": "18:11:44"},
                {"video_id": "N003-V001", "intersection_type": "Roundabout", "time_of_day": "00.00.03"},
                {"video_id": "N004-V001", "intersection_type": "Roundabout", "time_of_day": "00.00.03", "lighting_label": "day"},
            ]), encoding="utf-8")

            self.assertEqual(camera_metadata.build_camera_filter("four_way", "night", metadata_path), 'frame_id like "N001-V002#%"')
            self.assertEqual(camera_metadata.build_camera_filter("roundabout", "night", metadata_path), 'frame_id like "N002-V001#%"')
            self.assertEqual(camera_metadata.build_camera_filter("roundabout", "unknown", metadata_path), 'frame_id like "N003-V001#%"')
            self.assertEqual(camera_metadata.build_camera_filter("roundabout", "day", metadata_path), 'frame_id like "N004-V001#%"')
            self.assertEqual(camera_metadata.build_camera_filter("three_way", "", metadata_path), 'frame_id == "__no_camera_match__"')

    def test_camera_filter_rejects_unknown_values(self):
        with self.assertRaisesRegex(ValueError, "Invalid road type"):
            camera_metadata.build_camera_filter("roundabout && true")
        with self.assertRaisesRegex(ValueError, "Invalid lighting filter"):
            camera_metadata.build_camera_filter("", "sunset")

    def test_updated_metadata_file_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "camera.json"
            row = {"video_id": "N019-V001", "intersection_type": "3-Way Intersection", "time_of_day": "07:59:59"}
            metadata_path.write_text(json.dumps([row]), encoding="utf-8")
            self.assertIn("N019-V001", camera_metadata.build_camera_filter("three_way", path=metadata_path))
            row["intersection_type"] = "4-Way Intersection"
            metadata_path.write_text(json.dumps([row]), encoding="utf-8")
            stat = metadata_path.stat()
            os.utime(metadata_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            self.assertIn("N019-V001", camera_metadata.build_camera_filter("four_way", path=metadata_path))
            self.assertNotIn("N019-V001", camera_metadata.build_camera_filter("three_way", path=metadata_path))

    def test_main_dataset_classifies_n019_as_four_way(self):
        metadata_path = Path(__file__).resolve().parents[2] / "camera_info_workspace2_road_classification.json"
        data = camera_metadata.load_camera_metadata(str(metadata_path))
        for video_id in ("N019-V001", "N019-V002", "N019-V003"):
            self.assertEqual(data[video_id]["road_type"], "4-Way Intersection")
            self.assertIn(video_id, camera_metadata.build_camera_filter("four_way", path=metadata_path))
            self.assertNotIn(video_id, camera_metadata.build_camera_filter("three_way", path=metadata_path))


if __name__ == "__main__":
    unittest.main()
