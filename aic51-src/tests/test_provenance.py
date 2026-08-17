import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from aic51.packages.utils.provenance import ProvenanceStore, stable_id


class DummyExtractor:
    pass


class ProvenanceStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmp.name)
        (self.work_dir / "data/videos").mkdir(parents=True)
        (self.work_dir / "data/video_info").mkdir(parents=True)
        (self.work_dir / "data/keyframes/V001").mkdir(parents=True)
        (self.work_dir / "features/V001/000001").mkdir(parents=True)
        (self.work_dir / "data/videos/V001.mp4").write_bytes(b"test-video")
        (self.work_dir / "data/keyframes/V001/000001.jpg").write_bytes(b"frame")
        with open(self.work_dir / "data/video_info/V001.json", "w", encoding="utf-8") as f:
            json.dump({"frame_rate": 25}, f)
        self.store = ProvenanceStore(self.work_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stable_id_is_order_independent_for_dicts(self):
        self.assertEqual(
            stable_id("x", {"a": 1, "b": 2}),
            stable_id("x", {"b": 2, "a": 1}),
        )

    def test_source_and_frame_registration_are_stable(self):
        source_a = self.store.ensure_source("V001")
        source_b = self.store.ensure_source("V001")
        self.assertEqual(
            source_a["logical_source"]["source_id"],
            source_b["logical_source"]["source_id"],
        )
        self.assertEqual(source_a["renditions"][0]["legacy_rounded_fps"], 25)
        self.assertIsNotNone(source_a["renditions"][0]["asset_sha256"])

        selection_a = self.store.ensure_keyframe_generation("V001")
        selection_b = self.store.ensure_keyframe_generation("V001")
        self.assertEqual(
            selection_a["selection_generation_id"],
            selection_b["selection_generation_id"],
        )
        frame_map = self.store.frame_evidence_map("V001")
        self.assertIn("000001", frame_map)

    def test_source_refresh_adds_rendition_without_rewriting_source(self):
        source_a = self.store.ensure_source("V001")
        original_source_id = source_a["logical_source"]["source_id"]
        original_rendition_id = source_a["current_rendition_id"]

        (self.work_dir / "data/videos/V001.mp4").write_bytes(b"re-encoded-video")
        source_b = self.store.ensure_source("V001", refresh=True)

        self.assertEqual(source_b["logical_source"]["source_id"], original_source_id)
        self.assertNotEqual(source_b["current_rendition_id"], original_rendition_id)
        self.assertEqual(len(source_b["renditions"]), 2)

    def test_keyframe_generation_registry_keeps_history(self):
        observed = self.store.ensure_keyframe_generation("V001")
        generated = self.store.record_keyframe_generation(
            "V001",
            ["000001"],
            producer_configuration={"max_scene_length_seconds": 1},
            producer_identity={"name": "test-selector", "version": 1},
        )
        self.assertNotEqual(
            observed["selection_generation_id"],
            generated["selection_generation_id"],
        )

        with open(self.store.keyframe_path("V001"), "r", encoding="utf-8") as f:
            registry = json.load(f)
        self.assertEqual(
            registry["current_selection_generation_id"],
            generated["selection_generation_id"],
        )
        self.assertEqual(len(registry["generations"]), 2)

    def test_analysis_manifest_preserves_legacy_output_and_fixity(self):
        provider = self.store.provider_generation(
            feature_name="image_test",
            model_name="image_test",
            source="test",
            arch_name="test-arch",
            pretrained_model="test-weights",
            batch_size=4,
            extractor=DummyExtractor(),
        )
        run = self.store.begin_analysis_run(
            video_id="V001",
            feature_name="image_test",
            provider_generation=provider,
            requested_frame_ids=["000001"],
        )

        feature_path = self.work_dir / "features/V001/000001/image_test.npy"
        feature = np.array([0.25, 0.75], dtype=np.float32)
        np.save(feature_path, feature)
        output = self.store.output_record(
            run=run,
            frame_id="000001",
            feature_path=feature_path,
            feature=feature,
            model_name="image_test",
            frame_evidence_id=self.store.frame_evidence_map("V001")["000001"],
        )
        self.store.finish_analysis_run(run, status="success", outputs=[output])

        latest = self.store.latest_frame_provider_generations("V001", "image_test")
        self.assertEqual(latest["000001"], provider["provider_generation_id"])
        self.assertEqual(output["path"], "features/V001/000001/image_test.npy")
        self.assertEqual(output["shape"], [2])
        self.assertEqual(output["dtype"], "float32")
        self.assertEqual(len(output["content_sha256"]), 64)
        manifest_path = self.store.analysis_path(
            "V001",
            "image_test",
            run["analysis_run_id"],
        )
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(
            manifest["outputs"][0]["artifact_id"],
            output["artifact_id"],
        )


if __name__ == "__main__":
    unittest.main()
