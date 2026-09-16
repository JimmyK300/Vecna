import copy
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

import cv2
import numpy as np
import torch

import aic51.packages.constant as constant

from .feature_extractor import FeatureExtractorFactory
from .qwen_vl import QwenVLEmbedding


@FeatureExtractorFactory.register("qwen_vl_embedding_temporal")
class QwenVLTemporalEmbedding(QwenVLEmbedding):
    """Native Qwen3-VL video embedding over the short clips around keyframes."""

    @staticmethod
    def require_input():
        return constant.VIDEO_CLIP_DIR

    @staticmethod
    def from_pretrained(
        pretrained_model: str, *args, **kwargs
    ) -> "QwenVLTemporalEmbedding":
        return QwenVLTemporalEmbedding(
            pretrained_model=pretrained_model, *args, **kwargs
        )

    def __init__(
        self,
        *args,
        max_frames: int = 16,
        **kwargs,
    ) -> None:
        self._max_frames = max(1, int(max_frames))
        self._video_encode_lock = Lock()
        super().__init__(*args, **kwargs)
        if not self._model.supports("video"):
            raise RuntimeError(
                "Qwen3-VL temporal embedding requires Sentence Transformers >=5.4 "
                "and a checkpoint with native video support"
            )

    def runtime_semantics(self) -> dict:
        return {
            "input_modality": "video",
            "video_loader": "opencv_uniform_rgb",
            "max_frames": self._max_frames,
            "per_clip_video_metadata": True,
        }

    @staticmethod
    def _normalize_fps(fps: float) -> float:
        if not np.isfinite(fps) or fps <= 0:
            return 1.0
        return float(fps)

    def _read_video(self, path: Path | str) -> tuple[np.ndarray, dict]:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open video clip: {path}")

        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = self._normalize_fps(float(cap.get(cv2.CAP_PROP_FPS)))
            frames = []
            frame_indices = []

            if frame_count > 0:
                sample_count = min(self._max_frames, frame_count)
                indices = np.linspace(
                    0, frame_count - 1, sample_count, dtype=np.int64
                )
                for frame_index in indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
                    ok, frame = cap.read()
                    if not ok:
                        continue
                    frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    frame_indices.append(int(frame_index))
            else:
                while len(frames) < self._max_frames:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    frame_indices.append(len(frame_indices))
                    frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                frame_count = len(frames)
        finally:
            cap.release()

        if not frames:
            raise RuntimeError(f"No decodable frames in video clip: {path}")

        metadata = {
            "total_num_frames": max(frame_count, len(frames)),
            "fps": fps,
            "frames_indices": frame_indices,
        }
        return np.stack(frames, axis=0), metadata

    @staticmethod
    def _default_metadata(video: np.ndarray) -> dict:
        frame_count = int(video.shape[0])
        return {
            "total_num_frames": frame_count,
            "fps": 1.0,
            "frames_indices": list(range(frame_count)),
        }

    def _prepare_video(self, video) -> tuple[np.ndarray, dict]:
        if isinstance(video, (Path, str)):
            return self._read_video(video)

        metadata = None
        if isinstance(video, dict):
            if "array" not in video:
                raise ValueError("Video dict input must contain an 'array' key")
            metadata = video.get("video_metadata")
            video = video["array"]

        if isinstance(video, torch.Tensor):
            video = video.detach().cpu().numpy()

        video = np.asarray(video)
        if video.ndim != 4:
            raise ValueError(
                "Qwen3-VL temporal input must be a video array shaped "
                "[frames, height, width, channels]"
            )
        if metadata is None:
            metadata = self._default_metadata(video)
        return video, metadata

    def _encode_video(self, video: np.ndarray, metadata: dict) -> np.ndarray:
        # Sentence Transformers 5.4 stores modality processor kwargs on the
        # Transformer module and rejects them as per-call encode kwargs. Keep
        # the normal SentenceTransformer encode/prompt/pooling path, but scope
        # each clip's metadata to this call and restore the shared module state.
        input_module = self._model[0]
        if not hasattr(input_module, "processing_kwargs"):
            raise RuntimeError(
                "Sentence Transformers video processor configuration is unavailable"
            )

        with self._video_encode_lock:
            original_processing_kwargs = input_module.processing_kwargs
            processing_kwargs = copy.deepcopy(original_processing_kwargs or {})
            video_kwargs = dict(processing_kwargs.get("video") or {})
            video_kwargs.update(
                {
                    "do_sample_frames": False,
                    "video_metadata": metadata,
                }
            )
            processing_kwargs["video"] = video_kwargs
            input_module.processing_kwargs = processing_kwargs
            try:
                features = self._model.encode(
                    [{"video": video}],
                    batch_size=1,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    device=str(self._device),
                )
            finally:
                input_module.processing_kwargs = original_processing_kwargs

        return np.asarray(features, dtype=np.float32)

    def get_features(
        self,
        videos,
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        if isinstance(videos, torch.Tensor):
            videos = [videos] if videos.ndim == 4 else list(videos)
        elif isinstance(videos, np.ndarray):
            videos = [videos] if videos.ndim == 4 else list(videos)
        else:
            videos = list(videos)

        if not videos:
            return self._empty_features()

        outputs = []
        if callback:
            callback(self, 0, len(videos), None)

        for index, video in enumerate(videos):
            frames, metadata = self._prepare_video(video)
            outputs.append(self._encode_video(frames, metadata))
            if callback:
                callback(self, index + 1, len(videos), None)

        return np.concatenate(outputs, axis=0)
