import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aic51.packages.webui.backend import file as file_backend
from aic51.packages.webui.backend import utils


class _FakeCapture:
    def __init__(self, fps):
        self.fps = fps

    def get(self, property_id):
        if property_id == utils.cv2.CAP_PROP_FPS:
            return self.fps
        return 0

    def release(self):
        pass


class WebUiFpsTests(unittest.TestCase):
    def tearDown(self):
        utils.get_fps.cache_clear()

    def test_source_media_fps_overrides_stale_sidecar(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            info_dir = Path(temp_dir) / "video_info"
            info_dir.mkdir()
            (info_dir / "L21_V002.json").write_text(
                json.dumps({"frame_rate": 25}),
                encoding="utf-8",
            )

            with (
                patch.object(utils.constant, "VIDEO_INFO_DIR", str(info_dir)),
                patch.object(utils, "resolve_video_path", return_value=Path("video.mp4")),
                patch.object(utils.cv2, "VideoCapture", return_value=_FakeCapture(30.0)),
            ):
                self.assertEqual(utils.get_fps("L21_V002"), 30.0)

    def test_metadata_remains_fallback_when_source_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            info_dir = Path(temp_dir) / "video_info"
            info_dir.mkdir()
            (info_dir / "legacy.json").write_text(
                json.dumps({"frame_rate": 25}),
                encoding="utf-8",
            )

            with (
                patch.object(utils.constant, "VIDEO_INFO_DIR", str(info_dir)),
                patch.object(utils, "resolve_video_path", return_value=None),
            ):
                self.assertEqual(utils.get_fps("legacy"), 25.0)

    def test_map_keyframes_use_resolved_source_fps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "L21_V002.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["n", "pts_time", "frame_idx"])
                writer.writeheader()
                writer.writerow({"n": 1, "pts_time": 559.6, "frame_idx": 16788})

            with (
                patch.object(file_backend, "_get_map_keyframes_path", return_value=csv_path),
                patch.object(file_backend, "get_fps", return_value=30.0),
            ):
                rows = file_backend._load_map_keyframes_data("L21_V002")

            self.assertEqual(rows[0]["fps"], 30.0)


if __name__ == "__main__":
    unittest.main()
