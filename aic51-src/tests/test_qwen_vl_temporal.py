import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import aic51.packages.constant as constant
from aic51.packages.analyse.features.feature_extractor import FeatureExtractorFactory
from aic51.packages.analyse.features.qwen_vl_temporal import QwenVLTemporalEmbedding


class _FakeInputModule:
    def __init__(self):
        self.processing_kwargs = {"video": {"fps": 2.0}, "common": {"padding": True}}


class _FakeSentenceTransformer:
    def __init__(self, *args, **kwargs):
        self.last_items = None
        self.processing_kwargs_during_encode = None
        self.input_module = _FakeInputModule()

    def __getitem__(self, index):
        if index != 0:
            raise IndexError(index)
        return self.input_module

    def supports(self, modality):
        return modality in {"text", "image", "video"}

    def get_sentence_embedding_dimension(self):
        return 2048

    def encode(self, items, **kwargs):
        self.last_items = items
        self.processing_kwargs_during_encode = copy.deepcopy(
            self.input_module.processing_kwargs
        )
        return np.ones((len(items), 2048), dtype=np.float32)

    def to(self, device):
        return self


class QwenVLTemporalEmbeddingTest(unittest.TestCase):
    def _extractor(self):
        with patch(
            "aic51.packages.analyse.features.qwen_vl.SentenceTransformer",
            _FakeSentenceTransformer,
        ):
            return QwenVLTemporalEmbedding.from_pretrained(
                pretrained_model="fake-qwen",
                device="cpu",
                max_frames=8,
            )

    def test_factory_constructs_temporal_extractor(self):
        extractor_cls = FeatureExtractorFactory.get("qwen_vl_embedding_temporal")
        self.assertIs(extractor_cls, QwenVLTemporalEmbedding)
        with patch(
            "aic51.packages.analyse.features.qwen_vl.SentenceTransformer",
            _FakeSentenceTransformer,
        ):
            extractor = extractor_cls.from_pretrained(
                pretrained_model="fake-qwen",
                device="cpu",
                max_frames=8,
            )
        self.assertIsInstance(extractor, QwenVLTemporalEmbedding)
        self.assertEqual(extractor.require_input(), constant.VIDEO_CLIP_DIR)

    def test_numpy_video_scopes_metadata_to_native_video_encode(self):
        extractor = self._extractor()
        original = copy.deepcopy(extractor._model[0].processing_kwargs)
        video = np.zeros((4, 8, 8, 3), dtype=np.uint8)
        result = extractor.get_features([video])

        self.assertEqual(result.shape, (1, 2048))
        self.assertEqual(list(extractor._model.last_items[0].keys()), ["video"])
        self.assertEqual(extractor._model.last_items[0]["video"].shape, video.shape)
        self.assertEqual(
            extractor._model.processing_kwargs_during_encode,
            {
                "video": {
                    "fps": 2.0,
                    "do_sample_frames": False,
                    "video_metadata": {
                        "total_num_frames": 4,
                        "fps": 1.0,
                        "frames_indices": [0, 1, 2, 3],
                    },
                },
                "common": {"padding": True},
            },
        )
        self.assertEqual(extractor._model[0].processing_kwargs, original)

    def test_path_video_keeps_decoder_metadata_and_restores_processor_state(self):
        extractor = self._extractor()
        original = extractor._model[0].processing_kwargs
        frames = np.zeros((3, 8, 8, 3), dtype=np.uint8)
        metadata = {
            "total_num_frames": 30,
            "fps": 15.0,
            "frames_indices": [0, 14, 29],
        }
        with patch.object(
            extractor, "_read_video", return_value=(frames, metadata)
        ) as read_video:
            result = extractor.get_features([Path("000123.mp4")])

        self.assertEqual(result.shape, (1, 2048))
        read_video.assert_called_once_with(Path("000123.mp4"))
        self.assertEqual(
            extractor._model.processing_kwargs_during_encode["video"][
                "video_metadata"
            ],
            metadata,
        )
        self.assertIs(extractor._model[0].processing_kwargs, original)

    def test_video_dict_can_supply_explicit_metadata(self):
        extractor = self._extractor()
        frames = np.zeros((2, 8, 8, 3), dtype=np.uint8)
        metadata = {
            "total_num_frames": 10,
            "fps": 5.0,
            "frames_indices": [1, 8],
        }
        extractor.get_features(
            [{"array": frames, "video_metadata": metadata}]
        )
        self.assertEqual(
            extractor._model.processing_kwargs_during_encode["video"][
                "video_metadata"
            ],
            metadata,
        )

    def test_runtime_semantics_record_temporal_sampling(self):
        extractor = self._extractor()
        self.assertEqual(
            extractor.runtime_semantics(),
            {
                "input_modality": "video",
                "video_loader": "opencv_uniform_rgb",
                "max_frames": 8,
                "per_clip_video_metadata": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
