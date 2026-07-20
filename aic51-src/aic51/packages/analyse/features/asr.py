import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch

import aic51.packages.constant as constant
from aic51.packages.logger import logger
from aic51.packages.utils.files import get_path

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


@FeatureExtractorFactory.register("asr")
class ASR(FeatureExtractor):
    @staticmethod
    def require_input():
        # Chỉ dùng để biết video_id/frame nào cần xử lý, KHÔNG dùng nội dung ảnh
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(source: str, *args, **kwargs) -> "ASR":
        if source.lower() == "whisperx":
            return WhisperX(*args, **kwargs)
        else:
            raise RuntimeError(f"ASR: source={source} is invalid")


class WhisperX(ASR):
    def __init__(
        self,
        name: str = "asr",
        batch_size: int = 16,
        device: str | torch.device = "cpu",
        arch_name: str = "large-v3-turbo",
        work_dir: Path | str = ".",
        *args,
        **kwargs,
    ):
        self.name = name
        self._batch_size = batch_size
        self._arch_name = arch_name
        self._work_dir = get_path(work_dir)
        self._compute_type_gpu = "float16"  # workaround bug int8 trên Blackwell sm_120
        self._model = None
        self.to(device)

    def to(self, device):
        import whisperx

        self._device = torch.device(device)
        device_str = "cuda" if self._device.type == "cuda" else "cpu"
        compute_type = self._compute_type_gpu if device_str == "cuda" else "int8"

        logger.info(f"asr: loading whisperx model={self._arch_name} device={device_str} compute_type={compute_type}")
        # Không set language cố định -> auto-detect, nhưng giờ chỉ chạy 1 LẦN/VIDEO
        # (khác bản trước chạy per-clip) nên chi phí không còn đáng kể
        self._model = whisperx.load_model(self._arch_name, device=device_str, compute_type=compute_type)

    def get_features(self, images: list[Path], callback: Optional[Callable] = None) -> np.ndarray:
        num_frames = len(images)
        if callback:
            callback(self, 0, num_frames, [])
        if num_frames == 0:
            return np.array([])

        video_id = images[0].parent.stem
        segments, fps = self._transcribe_video(video_id)

        text_features = []
        for i, keyframe_path in enumerate(images):
            frame_idx = int(keyframe_path.stem)
            timestamp = frame_idx / fps if fps else 0.0
            text = self._find_segment_text(segments, timestamp)
            text_features.append(np.array(text))
            if callback:
                callback(self, i + 1, num_frames, text_features)

        return np.array(text_features)

    def _transcribe_video(self, video_id: str):
        import whisperx

        audio_path = self._work_dir / constant.AUDIO_DIR / f"{video_id}.wav"
        if not audio_path.exists():
            raise RuntimeError(f'asr: {audio_path} không tồn tại. Chạy "aic51-cli add -a" cho video_id={video_id}')

        logger.info(f"asr: transcribing {audio_path}")
        audio = whisperx.load_audio(str(audio_path))
        result = self._model.transcribe(audio, batch_size=self._batch_size, print_progress=True)
        segments = result.get("segments", [])

        fps = self._get_fps(video_id)
        return segments, fps

    def _get_fps(self, video_id: str) -> int:
        video_path = self._work_dir / constant.VIDEO_DIR / f"{video_id}{constant.VIDEO_EXTENSION}"
        ffprobe_cmd = ["ffprobe", "-v", "quiet", "-of", "compact=p=0"] + [
            "-select_streams", "0", "-show_entries", "stream=r_frame_rate", str(video_path),
        ]
        res = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        fraction = str(res.stdout).split("=")[1].split("/")
        return round(int(fraction[0]) / int(fraction[1]))

    def _find_segment_text(self, segments: list, timestamp: float) -> str:
        for seg in segments:
            if seg["start"] <= timestamp <= seg["end"]:
                return self._normalize_text(seg["text"])

        # Rơi vào khoảng lặng giữa 2 segment -> lấy segment gần nhất (trong ngưỡng 2s)
        best, best_dist = None, None
        for seg in segments:
            dist = min(abs(seg["start"] - timestamp), abs(seg["end"] - timestamp))
            if best_dist is None or dist < best_dist:
                best, best_dist = seg, dist

        if best is not None and best_dist is not None and best_dist <= 2.0:
            return self._normalize_text(best["text"])
        return ""

    def _normalize_text(self, text: str) -> str:
        res = text.strip().lower()
        return re.sub(r"\s+", " ", res)

    def get_text_features(self, texts, callback: Optional[Callable] = None) -> Any:
        return texts