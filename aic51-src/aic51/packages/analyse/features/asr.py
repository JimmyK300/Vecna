import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch

import aic51.packages.constant as constant
from aic51.packages.logger import logger
from aic51.packages.utils.provenance import stable_id

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


@FeatureExtractorFactory.register("asr")
class ASR(FeatureExtractor):
    @staticmethod
    def require_input():
        # Used to identify which video/frame set to project onto; image bytes are not ASR input.
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(source: str, *args, **kwargs) -> "ASR":
        if source.lower() == "whisperx":
            return WhisperX(*args, **kwargs)
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
        self._work_dir = Path(work_dir)
        self._compute_type_gpu = "float16"
        self._model = None
        self._last_evidence_payload = None
        self.to(device)

    def to(self, device):
        import whisperx

        self._device = torch.device(device)
        device_str = "cuda" if self._device.type == "cuda" else "cpu"
        compute_type = self._compute_type_gpu if device_str == "cuda" else "int8"
        self._compute_type = compute_type

        logger.info(
            f"asr: loading whisperx model={self._arch_name} "
            f"device={device_str} compute_type={compute_type}"
        )
        self._model = whisperx.load_model(
            self._arch_name,
            device=device_str,
            compute_type=compute_type,
        )

    def get_features(self, images: list[Path], callback: Optional[Callable] = None) -> np.ndarray:
        num_frames = len(images)
        if callback:
            callback(self, 0, num_frames, [])
        if num_frames == 0:
            self._last_evidence_payload = {
                "evidence_kind": "asr",
                "provider_generation_id": getattr(self, "_vecna_provider_generation_id", "unknown"),
                "segments": [],
                "frame_projections": [],
            }
            return np.array([])

        video_id = images[0].parent.stem
        segments, fps, transcript_meta = self._transcribe_video(video_id)

        source_context = getattr(self, "_vecna_source_context", {})
        provider_generation_id = getattr(self, "_vecna_provider_generation_id", "unknown")

        evidence_segments = []
        for idx, seg in enumerate(segments):
            if "norm_text" not in seg:
                seg["norm_text"] = self._normalize_text(seg.get("text", ""))
            evidence_id = stable_id(
                "ev_asr",
                {
                    "provider_generation_id": provider_generation_id,
                    "source_id": source_context.get("source_id"),
                    "rendition_id": source_context.get("rendition_id"),
                    "segment_index": idx,
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": seg.get("text", ""),
                },
            )
            seg["_vecna_evidence_id"] = evidence_id
            evidence_record = {
                "evidence_id": evidence_id,
                "kind": "asr_utterance",
                "direct_or_generated": "direct",
                "source_id": source_context.get("source_id"),
                "rendition_id": source_context.get("rendition_id"),
                "natural_locator": {
                    "kind": "native_time_interval",
                    "start_seconds": seg.get("start"),
                    "end_seconds": seg.get("end"),
                    "timing_quality": "provider_native",
                },
                "raw_text": seg.get("text", ""),
                "normalized_text": seg["norm_text"],
            }
            if "words" in seg:
                evidence_record["words"] = seg["words"]
            evidence_segments.append(evidence_record)

        text_features = []
        frame_projections = []
        step = max(1, num_frames // 50)
        for i, keyframe_path in enumerate(images):
            frame_idx = int(keyframe_path.stem)
            timestamp = frame_idx / fps if fps else 0.0
            segment, relation, distance = self._find_segment(segments, timestamp)
            text = segment["norm_text"] if segment is not None else ""
            text_features.append(np.array(text))
            frame_projections.append(
                {
                    "frame_id": keyframe_path.stem,
                    "frame_evidence_id": source_context.get("frame_evidence_map", {}).get(keyframe_path.stem),
                    "projected_time_seconds": timestamp,
                    "time_projection_quality": (
                        "reconstructed_from_rounded_fps" if fps else "unknown"
                    ),
                    "rounded_fps": fps or None,
                    "matched_asr_evidence_id": (
                        segment.get("_vecna_evidence_id") if segment is not None else None
                    ),
                    "projection_relation": relation,
                    "distance_seconds": distance,
                }
            )
            if callback and ((i + 1) % step == 0 or (i + 1) == num_frames):
                callback(self, i + 1, num_frames, text_features)

        self._last_evidence_payload = {
            "evidence_kind": "asr",
            "provider_generation_id": provider_generation_id,
            "source_id": source_context.get("source_id"),
            "rendition_id": source_context.get("rendition_id"),
            "audio_input": transcript_meta["audio_input"],
            "language": transcript_meta.get("language"),
            "model": self._arch_name,
            "runtime": {
                "device": self._device.type,
                "compute_type": self._compute_type,
            },
            "segments": evidence_segments,
            "frame_projections": frame_projections,
            "legacy_projection": {
                "description": "normalized ASR text projected to keyframes remains in existing .npy output",
                "nearest_segment_fallback_seconds": 2.0,
            },
        }
        return np.array(text_features)

    def _transcribe_video(self, video_id: str):
        import whisperx

        audio_path = self._work_dir / constant.AUDIO_DIR / f"{video_id}.wav"
        if not audio_path.exists():
            raise RuntimeError(
                f'asr: {audio_path} does not exist. Run "aic51-cli add -a" for video_id={video_id}'
            )

        logger.info(f"asr: transcribing {audio_path}")
        audio = whisperx.load_audio(str(audio_path))
        result = self._model.transcribe(
            audio,
            batch_size=self._batch_size,
            print_progress=True,
        )
        segments = result.get("segments", [])

        for seg in segments:
            seg["norm_text"] = self._normalize_text(seg.get("text", ""))

        fps = self._get_fps(video_id)
        transcript_meta = {
            "audio_input": str(audio_path),
            "language": result.get("language"),
        }
        return segments, fps, transcript_meta

    def _get_fps(self, video_id: str) -> int:
        video_path = self._work_dir / constant.VIDEO_DIR / f"{video_id}{constant.VIDEO_EXTENSION}"
        ffprobe_cmd = ["ffprobe", "-v", "quiet", "-of", "compact=p=0"] + [
            "-select_streams",
            "0",
            "-show_entries",
            "stream=r_frame_rate",
            str(video_path),
        ]
        res = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        fraction = str(res.stdout).split("=")[1].split("/")
        return round(int(fraction[0]) / int(fraction[1]))

    def _find_segment(self, segments: list, timestamp: float):
        if not segments:
            return None, "no_asr_evidence", None

        import bisect

        start_times = [s["start"] for s in segments]
        idx = bisect.bisect_right(start_times, timestamp)

        candidates = []
        if idx > 0:
            candidates.append(segments[idx - 1])
        if idx < len(segments):
            candidates.append(segments[idx])
        if idx + 1 < len(segments):
            candidates.append(segments[idx + 1])

        for seg in candidates:
            if seg["start"] <= timestamp <= seg["end"]:
                return seg, "within_native_interval", 0.0

        best, best_dist = None, None
        for seg in candidates:
            dist = min(abs(seg["start"] - timestamp), abs(seg["end"] - timestamp))
            if best_dist is None or dist < best_dist:
                best, best_dist = seg, dist

        if best is not None and best_dist is not None and best_dist <= 2.0:
            return best, "nearest_within_2s_legacy_projection", float(best_dist)
        return None, "no_projection_match", float(best_dist) if best_dist is not None else None

    def _find_segment_text(self, segments: list, timestamp: float) -> str:
        segment, _, _ = self._find_segment(segments, timestamp)
        return segment["norm_text"] if segment is not None else ""

    def _normalize_text(self, text: str) -> str:
        res = text.strip().lower()
        return re.sub(r"\s+", " ", res)

    def get_last_evidence_payload(self):
        return self._last_evidence_payload

    def get_text_features(self, texts, callback: Optional[Callable] = None) -> Any:
        return texts
