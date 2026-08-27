from __future__ import annotations

from collections import Counter
from math import ceil
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch
from PIL import Image

import aic51.packages.constant as constant
from aic51.packages.logger import logger

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


def _position_bucket(cx: float, cy: float) -> str:
    """Map normalized box centre to a coarse spatial phrase."""
    if cx < 1 / 3:
        horizontal = "left"
    elif cx > 2 / 3:
        horizontal = "right"
    else:
        horizontal = "center"

    if cy < 1 / 3:
        vertical = "upper"
    elif cy > 2 / 3:
        vertical = "lower"
    else:
        vertical = "middle"

    if horizontal == "center" and vertical == "middle":
        return "center"
    if vertical == "middle":
        return horizontal
    if horizontal == "center":
        return f"{vertical} center"
    return f"{vertical} {horizontal}"


def _size_bucket(area_ratio: float) -> str:
    if area_ratio >= 0.25:
        return "large"
    if area_ratio >= 0.07:
        return "medium"
    return "small"


def _semantic_text(detections: list[dict[str, Any]], max_details: int = 12) -> str:
    """Convert detector output into stable text useful to BM25 and BGE-M3."""
    if not detections:
        return ""

    counts = Counter(str(det["label"]).strip().lower() for det in detections if det.get("label"))
    object_summary = "; ".join(
        f"{label} x{count}" if count > 1 else label
        for label, count in counts.most_common()
    )

    ranked = sorted(
        detections,
        key=lambda d: (float(d.get("confidence", 0.0)), float(d.get("area_ratio", 0.0))),
        reverse=True,
    )[:max_details]
    details = "; ".join(
        f"{str(det['label']).strip().lower()} {det['position']} {det['size']}"
        for det in ranked
        if det.get("label")
    )

    if details:
        return f"objects: {object_summary}. details: {details}."
    return f"objects: {object_summary}."


@FeatureExtractorFactory.register("yolo")
class YOLOFeature(FeatureExtractor):
    """YOLO/YOLOE detector whose output is semantic text per keyframe.

    The saved feature is deliberately text rather than a detector-specific tensor:
    - the text field can be indexed directly with BM25 for object-name lookup;
    - the same text can be consumed by Vecna's existing text_embedding extractor
      to create a BGE-M3 semantic vector;
    - provenance still records the detector checkpoint and runtime semantics.

    This keeps detection independent from the search stack while making detector
    knowledge a normal retrieval feature.
    """

    identity_aware_outputs = True

    @staticmethod
    def require_input() -> Any:
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(
        pretrained_model: str = "yoloe-26s-seg-pf.pt",
        *args,
        **kwargs,
    ) -> "YOLOFeature":
        return YOLOFeature(pretrained_model=pretrained_model, *args, **kwargs)

    def __init__(
        self,
        pretrained_model: str = "yoloe-26s-seg-pf.pt",
        name: str = "yolo",
        batch_size: int = 16,
        device: str | torch.device = "cpu",
        confidence: float = 0.20,
        imgsz: int = 640,
        max_det: int = 100,
        iou: float = 0.7,
        max_details: int = 12,
        vocabulary: Optional[list[str]] = None,
        *args,
        **kwargs,
    ) -> None:
        kwargs.pop("source", None)
        kwargs.pop("arch_name", None)
        kwargs.pop("work_dir", None)

        from ultralytics import YOLO, YOLOE

        self._pretrained_model = pretrained_model
        self._confidence = float(confidence)
        self._imgsz = int(imgsz)
        self._max_det = int(max_det)
        self._iou = float(iou)
        self._max_details = int(max_details)
        self._device = torch.device(device)
        self._vocabulary = list(vocabulary) if vocabulary else None

        if str(pretrained_model).lower().startswith("yoloe"):
            self._model = YOLOE(pretrained_model)
            # Prompt-free checkpoints already carry their built-in vocabulary.
            # Prompted YOLOE checkpoints can optionally receive a curated list.
            if self._vocabulary:
                self._model.set_classes(self._vocabulary)
        else:
            self._model = YOLO(pretrained_model)

        logger.info(
            "YOLO semantic extractor: model=%s device=%s conf=%.2f imgsz=%d batch=%d",
            pretrained_model,
            self._device,
            self._confidence,
            self._imgsz,
            batch_size,
        )
        super().__init__(name, batch_size, self._device)

    def runtime_semantics(self) -> dict[str, Any]:
        return {
            "backend": "ultralytics",
            "pretrained_model": self._pretrained_model,
            "device": str(self._device),
            "confidence": self._confidence,
            "imgsz": self._imgsz,
            "max_det": self._max_det,
            "iou": self._iou,
            "semantic_format": "objects-counts-position-size-v1",
            "vocabulary_size": len(self._vocabulary) if self._vocabulary else None,
        }

    @staticmethod
    def _result_detections(result) -> list[dict[str, Any]]:
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        orig_h, orig_w = getattr(result, "orig_shape", (1, 1))
        orig_w = max(float(orig_w), 1.0)
        orig_h = max(float(orig_h), 1.0)
        names = getattr(result, "names", {}) or {}

        detections: list[dict[str, Any]] = []
        for box in boxes:
            xyxy = box.xyxy[0].detach().cpu().tolist()
            x1, y1, x2, y2 = [float(v) for v in xyxy]
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            label = names.get(cls_id, f"class_{cls_id}")

            width = max(0.0, x2 - x1)
            height = max(0.0, y2 - y1)
            area_ratio = min(1.0, (width * height) / (orig_w * orig_h))
            cx = min(1.0, max(0.0, ((x1 + x2) / 2.0) / orig_w))
            cy = min(1.0, max(0.0, ((y1 + y2) / 2.0) / orig_h))

            detections.append(
                {
                    "label": str(label),
                    "confidence": confidence,
                    "area_ratio": area_ratio,
                    "position": _position_bucket(cx, cy),
                    "size": _size_bucket(area_ratio),
                }
            )
        return detections

    def get_features(
        self,
        images: list[Path | str] | np.ndarray | torch.Tensor | list[Image.Image],
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        images = list(images)
        if not images:
            return np.empty((0,), dtype=object)

        outputs: list[np.ndarray] = []
        num_batches = ceil(len(images) / self._batch_size)
        if callback:
            callback(self, 0, num_batches, outputs)

        for batch_idx in range(num_batches):
            batch = images[
                batch_idx * self._batch_size : (batch_idx + 1) * self._batch_size
            ]
            sources = [str(item) if isinstance(item, (str, Path)) else item for item in batch]

            results = self._model.predict(
                source=sources,
                conf=self._confidence,
                imgsz=self._imgsz,
                max_det=self._max_det,
                iou=self._iou,
                device=str(self._device),
                verbose=False,
            )
            for result in results:
                detections = self._result_detections(result)
                outputs.append(np.array(_semantic_text(detections, self._max_details)))

            if callback:
                callback(self, batch_idx + 1, num_batches, outputs)

        return np.asarray(outputs, dtype=object)

    def get_text_features(
        self,
        texts: list[str] | str | np.ndarray,
        callback: Optional[Callable] = None,
    ) -> Any:
        # The detector itself is never used to embed a text query. Search uses
        # BM25 on the saved detector text or BGE-M3 via yolo_semantic.
        return texts

    def to(self, device: str | torch.device):
        self._device = torch.device(device)
        if hasattr(self._model, "to"):
            self._model.to(self._device)
        return self
