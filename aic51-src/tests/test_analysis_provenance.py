import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from aic51.packages.analyse.features.asr import WhisperX
from aic51.packages.analyse.features.ocr import Tesseract
from aic51.packages.analyse.provenance import (
    build_artifact_record,
    compatibility_output_status,
    merge_artifact_records,
    provider_generation_id,
)


class ProvenanceIdentityTests(unittest.TestCase):
    def test_provider_generation_identity_is_stable_and_material_config_sensitive(self):
        base = {
            "provider_family": "ocr",
            "feature_name": "ocr",
            "source": "tesseract",
            "model": "ocr",
            "arch_name": None,
            "pretrained_model": None,
            "batch_size": 4,
            "input_kind": "keyframes",
        }
        reordered = dict(reversed(list(base.items())))
        changed = dict(base, batch_size=8)

        self.assertEqual(provider_generation_id(base), provider_generation_id(reordered))
        self.assertNotEqual(provider_generation_id(base), provider_generation_id(changed))

    def test_artifact_record_has_fixity_locator_and_truthful_empty_text_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "features" / "V001" / "000123" / "ocr.npy"
            artifact.parent.mkdir(parents=True)
            feature = np.array("")
            np.save(artifact, feature)

            record = build_artifact_record(
                artifact_path=artifact,
                root=root,
                video_id="V001",
                frame_id="000123",
                feature=feature,
            )

            self.assertEqual(record["natural_locator"]["frame_id"], "000123")
            self.assertEqual(record["status"], "success_empty")
            self.assertEqual(len(record["sha256"]), 64)
            self.assertEqual(record["artifact_path"], "features/V001/000123/ocr.npy")

    def test_legacy_records_are_not_discovered_or_fabricated(self):
        recorded = {
            "artifact_path": "features/V001/000124/ocr.npy",
            "natural_locator": {"frame_id": "000124"},
            "sha256": "abc",
        }
        merged = merge_artifact_records([], [recorded])
        self.assertEqual(merged, [recorded])

    def test_text_status_distinguishes_empty_from_numeric_output(self):
        self.assertEqual(compatibility_output_status(np.array("   ")), "success_empty")
        self.assertEqual(compatibility_output_status(np.array([0.0, 0.0])), "success_output")


class NativeOCRTests(unittest.TestCase):
    @patch("aic51.packages.analyse.features.ocr.pytesseract.image_to_data")
    def test_ocr_preserves_boxes_confidence_and_compatibility_text(self, image_to_data):
        image_to_data.side_effect = [
            {
                "text": ["Hello", ""],
                "conf": ["91.5", "-1"],
                "left": [10, 0],
                "top": [20, 0],
                "width": [30, 0],
                "height": [12, 0],
            },
            {
                "text": ["Xin"],
                "conf": ["88"],
                "left": [5],
                "top": [6],
                "width": [18],
                "height": [10],
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "000321.jpg"
            Image.new("RGB", (100, 90)).save(image_path)

            extractor = Tesseract(name="ocr", batch_size=1)
            features = extractor.get_features([image_path])
            evidence = extractor.get_native_evidence()

        self.assertEqual(str(features[0]), "hello xin")
        self.assertEqual(evidence["scope"], "frame")
        item = evidence["items"][0]
        self.assertEqual(item["frame_id"], "000321")
        self.assertEqual(item["status"], "success_output")
        self.assertEqual(item["normalized_text"], "hello xin")
        self.assertEqual(item["observations"][0]["region"]["x"], 10)
        self.assertEqual(item["observations"][0]["confidence"], 91.5)
        self.assertEqual(item["observations"][0]["language_pass"], "eng")

    @patch("aic51.packages.analyse.features.ocr.pytesseract.image_to_data")
    def test_ocr_valid_empty_is_not_failure(self, image_to_data):
        image_to_data.side_effect = [
            {"text": [""], "conf": ["-1"], "left": [0], "top": [0], "width": [0], "height": [0]},
            {"text": [""], "conf": ["-1"], "left": [0], "top": [0], "width": [0], "height": [0]},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "000001.jpg"
            Image.new("RGB", (20, 20)).save(image_path)
            extractor = Tesseract(name="ocr", batch_size=1)
            features = extractor.get_features([image_path])
            item = extractor.get_native_evidence()["items"][0]

        self.assertEqual(str(features[0]), "")
        self.assertEqual(item["status"], "success_empty")
        self.assertEqual(item["observations"], [])


class NativeASRTests(unittest.TestCase):
    def test_asr_preserves_native_timeline_separately_from_frame_projection(self):
        extractor = WhisperX.__new__(WhisperX)
        result = {
            "language": "vi",
            "segments": [
                {"start": 1.25, "end": 2.5, "text": "  Xin   Chào  "},
                {"start": 4.0, "end": 5.0, "text": ""},
            ],
        }
        evidence = extractor._build_native_evidence("V002", result)

        self.assertEqual(evidence["scope"], "video")
        self.assertEqual(evidence["language"], "vi")
        self.assertEqual(evidence["items"][0]["natural_locator"]["start_seconds"], 1.25)
        self.assertEqual(evidence["items"][0]["natural_locator"]["end_seconds"], 2.5)
        self.assertEqual(evidence["items"][0]["raw_text"], "  Xin   Chào  ")
        self.assertEqual(evidence["items"][0]["normalized_text"], "xin chào")
        self.assertEqual(evidence["items"][1]["status"], "success_empty")

        compatibility_segments = [
            {"start": 1.25, "end": 2.5, "norm_text": "xin chào"},
        ]
        self.assertEqual(extractor._find_segment_text(compatibility_segments, 2.0), "xin chào")


if __name__ == "__main__":
    unittest.main()
