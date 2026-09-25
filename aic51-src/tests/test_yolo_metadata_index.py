import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from aic51.cli.commands.index import IndexCommand
from aic51.packages.config import GlobalConfig


class FakeDatabase:
    def __init__(self):
        self.rows = []

    @staticmethod
    def process_field_name(field_name):
        return field_name.replace("-", "_")

    def insert(self, rows, do_update=False):
        self.rows.extend(rows)


class YoloMetadataIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmp.name)
        (self.work_dir / "config.yaml").write_text(
            """
features:
  yolo26x_seg:
    model: yolo26x_seg
    index:
      datatype: FLOAT_VECTOR
      dim: 32
      metadata_fields:
        object_keys: yolo_objects
        relation_keys: yolo_relations
""".strip(),
            encoding="utf-8",
        )
        GlobalConfig.set_work_dir(self.work_dir)

    def tearDown(self):
        GlobalConfig.set_work_dir(None)
        self.tmp.cleanup()

    def test_loads_object_and_relation_arrays_from_json_sidecar(self):
        frame_dir = self.work_dir / "features" / "N001" / "000001"
        frame_dir.mkdir(parents=True)
        (frame_dir / "yolo26x_seg.json").write_text(
            json.dumps(
                {
                    "object_keys": ["red:car", "blue:bus"],
                    "relation_keys": ["red:car:left_of:blue:bus"],
                }
            ),
            encoding="utf-8",
        )

        result = IndexCommand._load_metadata_fields(frame_dir, "yolo26x_seg")

        self.assertEqual(result["yolo_objects"], ["red:car", "blue:bus"])
        self.assertEqual(result["yolo_relations"], ["red:car:left_of:blue:bus"])

    def test_missing_sidecar_produces_empty_arrays(self):
        frame_dir = self.work_dir / "features" / "N001" / "000002"
        frame_dir.mkdir(parents=True)

        result = IndexCommand._load_metadata_fields(frame_dir, "yolo26x_seg")

        self.assertEqual(result, {"yolo_objects": [], "yolo_relations": []})

    def test_rejects_non_string_array_metadata(self):
        frame_dir = self.work_dir / "features" / "N001" / "000003"
        frame_dir.mkdir(parents=True)
        (frame_dir / "yolo26x_seg.json").write_text(
            json.dumps({"object_keys": ["red:car", 123], "relation_keys": []}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "array of strings"):
            IndexCommand._load_metadata_fields(frame_dir, "yolo26x_seg")

    def test_indexes_npy_vector_and_json_arrays_as_one_row(self):
        frame_dir = self.work_dir / "features" / "N001" / "000004"
        frame_dir.mkdir(parents=True)
        np.save(frame_dir / "yolo26x_seg.npy", np.zeros(32, dtype=np.float32))
        (frame_dir / "yolo26x_seg.json").write_text(
            json.dumps(
                {
                    "object_keys": ["red:car", "blue:bus"],
                    "relation_keys": ["red:car:left_of:blue:bus"],
                }
            ),
            encoding="utf-8",
        )
        command = object.__new__(IndexCommand)
        command._work_dir = self.work_dir
        database = FakeDatabase()

        inserted, _, _, failed_video = command._index_one_video(
            database,
            "N001",
            False,
            lambda **kwargs: None,
            {},
        )

        self.assertEqual(inserted, 1)
        self.assertIsNone(failed_video)
        self.assertEqual(database.rows[0]["frame_id"], "N001#000004")
        self.assertEqual(database.rows[0]["yolo_objects"], ["red:car", "blue:bus"])
        self.assertEqual(
            database.rows[0]["yolo_relations"],
            ["red:car:left_of:blue:bus"],
        )
        self.assertEqual(database.rows[0]["yolo26x_seg"].shape, (32,))


if __name__ == "__main__":
    unittest.main()
