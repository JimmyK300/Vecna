import tempfile
import unittest
from pathlib import Path

import numpy as np

from aic51.cli.commands.analyse import AnalyseCommand
from aic51.packages.utils.provenance import ProvenanceStore, atomic_save_npy


class _IdentityExtractor:
    identity_aware_outputs = True
    name = "ocr_dense"

    def discover_frame_ids(self, work_dir, video_id):
        video_dir = Path(work_dir) / "features" / video_id
        return sorted(path.name for path in video_dir.iterdir() if path.is_dir())


class TextEmbeddingIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmp.name)
        (self.work_dir / "features" / "V001" / "000001").mkdir(parents=True)
        np.save(self.work_dir / "features" / "V001" / "000001" / "ocr.npy", np.array("hello"))
        self.command = AnalyseCommand(self.work_dir)
        self.extractor = _IdentityExtractor()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_dense_with_generation(self, generation_id: str):
        feature_path = self.work_dir / "features" / "V001" / "000001" / "ocr_dense.npy"
        atomic_save_npy(feature_path, np.ones(1024, dtype=np.float32))
        store = ProvenanceStore(self.work_dir)
        (self.work_dir / "data" / "videos").mkdir(parents=True, exist_ok=True)
        (self.work_dir / "data" / "keyframes" / "V001").mkdir(parents=True, exist_ok=True)
        (self.work_dir / "data" / "videos" / "V001.mp4").write_bytes(b"video")
        (self.work_dir / "data" / "keyframes" / "V001" / "000001.jpg").write_bytes(b"frame")
        provider = {
            "provider_generation_id": generation_id,
            "descriptor": {"backend": "onnx"},
        }
        run = store.begin_analysis_run(
            video_id="V001",
            feature_name="ocr_dense",
            provider_generation=provider,
            requested_frame_ids=["000001"],
        )
        output = store.output_record(
            run=run,
            frame_id="000001",
            feature_path=feature_path,
            feature=np.ones(1024, dtype=np.float32),
            model_name="text_embedding",
            frame_evidence_id=None,
        )
        store.finish_analysis_run(run, status="success", outputs=[output])

    def test_skips_matching_onnx_generation(self):
        self._write_dense_with_generation("prv_same")
        pending, skipped = self.command._get_keyframes_list(
            self.extractor,
            "V001",
            do_overwrite=False,
            provider_generation_id="prv_same",
        )
        self.assertEqual(pending, [])
        self.assertEqual(skipped, 1)
        self.assertTrue(
            (self.work_dir / "features" / "V001" / "000001" / "ocr_dense.npy").exists()
        )

    def test_preserves_foreign_generation_instead_of_overwrite(self):
        self._write_dense_with_generation("prv_pytorch")
        pending, skipped = self.command._get_keyframes_list(
            self.extractor,
            "V001",
            do_overwrite=False,
            provider_generation_id="prv_onnx_dml",
        )
        self.assertEqual(pending, ["000001"])
        self.assertEqual(skipped, 0)
        self.assertFalse(
            (self.work_dir / "features" / "V001" / "000001" / "ocr_dense.npy").exists()
        )
        preserved = list(
            (self.work_dir / "features" / "V001" / "000001").glob("ocr_dense.preserved.*")
        )
        self.assertEqual(len(preserved), 1)

    def test_compatible_onnx_generation_is_skipped(self):
        self._write_dense_with_generation("prv_0638be1bff617104a44e6f89")
        pending, skipped = self.command._get_keyframes_list(
            self.extractor,
            "V001",
            do_overwrite=False,
            provider_generation_id="prv_new_pipeline",
            compatible_generation_ids={"prv_0638be1bff617104a44e6f89"},
        )
        self.assertEqual(pending, [])
        self.assertEqual(skipped, 1)
        self.assertTrue(
            (self.work_dir / "features" / "V001" / "000001" / "ocr_dense.npy").exists()
        )

    def test_unfinished_compatible_run_skips_written_vectors(self):
        feature_path = self.work_dir / "features" / "V001" / "000001" / "ocr_dense.npy"
        atomic_save_npy(feature_path, np.ones(1024, dtype=np.float32))
        store = ProvenanceStore(self.work_dir)
        (self.work_dir / "data" / "videos").mkdir(parents=True, exist_ok=True)
        (self.work_dir / "data" / "keyframes" / "V001").mkdir(parents=True, exist_ok=True)
        (self.work_dir / "data" / "videos" / "V001.mp4").write_bytes(b"video")
        (self.work_dir / "data" / "keyframes" / "V001" / "000001.jpg").write_bytes(b"frame")
        store.begin_analysis_run(
            video_id="V001",
            feature_name="ocr_dense",
            provider_generation={
                "provider_generation_id": "prv_onnx_dml",
                "descriptor": {"backend": "onnx"},
            },
            requested_frame_ids=["000001"],
        )
        pending, skipped = self.command._get_keyframes_list(
            self.extractor,
            "V001",
            do_overwrite=False,
            provider_generation_id="prv_onnx_dml",
        )
        self.assertEqual(pending, [])
        self.assertEqual(skipped, 1)
        self.assertTrue(feature_path.exists())

    def test_unprovenanced_existing_vector_is_preserved(self):
        atomic_save_npy(
            self.work_dir / "features" / "V001" / "000001" / "ocr_dense.npy",
            np.ones(1024, dtype=np.float32),
        )
        pending, skipped = self.command._get_keyframes_list(
            self.extractor,
            "V001",
            do_overwrite=False,
            provider_generation_id="prv_onnx_dml",
        )
        self.assertEqual(pending, ["000001"])
        self.assertEqual(skipped, 0)
        preserved = list(
            (self.work_dir / "features" / "V001" / "000001").glob("ocr_dense.preserved.*")
        )
        self.assertEqual(len(preserved), 1)


if __name__ == "__main__":
    unittest.main()
