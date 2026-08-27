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

DEFAULT_YOLOE_MODEL = "yoloe-26x-seg.pt"


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

    counts = Counter(
        str(det["label"]).strip().lower()
        for det in detections
        if det.get("label")
    )
    object_summary = "; ".join(
        f"{label} x{count}" if count > 1 else label
        for label, count in counts.most_common()
    )

    ranked = sorted(
        detections,
        key=lambda d: (
            float(d.get("confidence", 0.0)),
            float(d.get("area_ratio", 0.0)),
        ),
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


def _semantic_detection(
    *,
    label: str,
    confidence: float,
    bbox: list[float],
    orig_w: float,
    orig_h: float,
) -> dict[str, Any] | None:
    x1, y1, x2, y2 = [float(value) for value in bbox]
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    if width <= 0 or height <= 0:
        return None
    orig_w = max(float(orig_w), 1.0)
    orig_h = max(float(orig_h), 1.0)
    area_ratio = min(1.0, (width * height) / (orig_w * orig_h))
    cx = min(1.0, max(0.0, ((x1 + x2) / 2.0) / orig_w))
    cy = min(1.0, max(0.0, ((y1 + y2) / 2.0) / orig_h))
    return {
        "label": str(label),
        "confidence": float(confidence),
        "area_ratio": area_ratio,
        "position": _position_bucket(cx, cy),
        "size": _size_bucket(area_ratio),
    }


def _select_backend(
    requested: str,
    *,
    device: torch.device,
    allow_gpu: bool,
    onnx_provider: str,
    onnx_model_path: str | Path | None,
) -> str:
    """Choose CUDA/Ultralytics or ONNX without pretending DML is a torch device."""
    choice = (requested or "auto").strip().lower()
    if choice not in {"auto", "ultralytics", "onnx"}:
        raise ValueError(
            f"unknown YOLO backend {requested!r}; use auto|ultralytics|onnx"
        )
    if choice != "auto":
        return choice

    # CUDA is the preferred path for RTX hosts even when a DML artifact exists.
    if device.type == "cuda":
        return "ultralytics"

    # --no-gpu is an explicit request for a CPU path; preserve the legacy
    # Ultralytics behavior instead of silently using DirectML.
    if not allow_gpu:
        return "ultralytics"

    provider = (onnx_provider or "auto").strip().lower()
    if onnx_model_path:
        # An explicitly configured artifact means this host is prepared for the
        # ONNX path.  Explicit dml will fail loudly if the provider is missing.
        return "onnx"

    from .yolo_onnx import has_directml, resolve_onnx_model_path

    try:
        resolve_onnx_model_path(None)
    except FileNotFoundError:
        if provider == "dml":
            # The config asked for DML; do not hide a missing artifact behind a
            # 30x slower CPU PyTorch fallback.
            return "onnx"
        return "ultralytics"

    if provider == "dml" or (provider == "auto" and has_directml()):
        return "onnx"
    if provider == "cpu":
        return "onnx"
    return "ultralytics"


@FeatureExtractorFactory.register("yolo")
class YOLOFeature(FeatureExtractor):
    """YOLO/YOLOE detector whose output is semantic text per keyframe.

    Backends:
    - ``ultralytics``: PyTorch/CUDA path for RTX hosts.
    - ``onnx``: ONNX Runtime path, including DirectML for Windows AMD GPUs.
    - ``auto``: CUDA first; otherwise a configured/proven DML artifact; otherwise
      the legacy Ultralytics path.

    The saved feature is deliberately text rather than a detector-specific
    tensor.  It can be BM25-indexed directly and projected through BGE-M3 into
    the ``yolo_semantic`` vector feature.
    """

    identity_aware_outputs = True

    @staticmethod
    def require_input() -> Any:
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(
        pretrained_model: str = DEFAULT_YOLOE_MODEL,
        *args,
        **kwargs,
    ) -> "YOLOFeature":
        return YOLOFeature(pretrained_model=pretrained_model, *args, **kwargs)

    def __init__(
        self,
        pretrained_model: str = DEFAULT_YOLOE_MODEL,
        name: str = "yolo",
        batch_size: int = 1,
        device: str | torch.device = "cpu",
        confidence: float = 0.20,
        imgsz: int = 640,
        max_det: int = 100,
        iou: float = 0.7,
        max_details: int = 12,
        vocabulary: Optional[list[str]] = None,
        backend: str = "auto",
        onnx_provider: str = "dml",
        onnx_model_path: str | Path | None = None,
        onnx_class_names_path: str | Path | None = None,
        onnx_device_id: int = 0,
        allow_gpu: bool | None = None,
        *args,
        **kwargs,
    ) -> None:
        kwargs.pop("source", None)
        kwargs.pop("arch_name", None)
        kwargs.pop("work_dir", None)

        self._pretrained_model = pretrained_model
        self._confidence = float(confidence)
        self._imgsz = int(imgsz)
        self._max_det = int(max_det)
        self._iou = float(iou)
        self._max_details = int(max_details)
        self._device = torch.device(device)
        self._vocabulary = list(vocabulary) if vocabulary else None
        self._onnx_provider = (onnx_provider or "auto").strip().lower()
        self._onnx_model_path = onnx_model_path
        self._onnx_class_names_path = onnx_class_names_path
        self._onnx_device_id = int(onnx_device_id)
        if allow_gpu is None:
            allow_gpu = self._device.type != "cpu"
        self._allow_gpu = bool(allow_gpu)

        self._backend = _select_backend(
            backend,
            device=self._device,
            allow_gpu=self._allow_gpu,
            onnx_provider=self._onnx_provider,
            onnx_model_path=self._onnx_model_path,
        )
        self._model = None
        self._onnx = None

        if self._backend == "onnx":
            from .yolo_onnx import YOLOOnnxBackend

            self._onnx = YOLOOnnxBackend(
                self._onnx_model_path,
                provider=self._onnx_provider,
                allow_gpu=self._allow_gpu,
                imgsz=self._imgsz,
                class_names_path=self._onnx_class_names_path,
                device_id=self._onnx_device_id,
            )
            if not self._onnx.names:
                logger.warning(
                    "YOLO ONNX artifact exposes no class names; semantic output "
                    "will use class_<id>. Provide onnx_class_names_path if needed."
                )
            logger.info(
                "YOLO semantic extractor: backend=onnx provider=%s model=%s "
                "conf=%.2f imgsz=%d",
                self._onnx.execution_provider,
                self._onnx.model_path,
                self._confidence,
                self._imgsz,
            )
        else:
            from ultralytics import YOLO, YOLOE

            if str(pretrained_model).lower().startswith("yoloe"):
                self._model = YOLOE(pretrained_model)
                if self._vocabulary:
                    self._model.set_classes(self._vocabulary)
            else:
                self._model = YOLO(pretrained_model)
            logger.info(
                "YOLO semantic extractor: backend=ultralytics model=%s device=%s "
                "conf=%.2f imgsz=%d batch=%d",
                pretrained_model,
                self._device,
                self._confidence,
                self._imgsz,
                batch_size,
            )

        super().__init__(name, batch_size, self._device)

    def runtime_semantics(self) -> dict[str, Any]:
        semantics: dict[str, Any] = {
            "backend": self._backend,
            "pretrained_model": self._pretrained_model,
            "device": str(self._device),
            "confidence": self._confidence,
            "imgsz": self._imgsz,
            "max_det": self._max_det,
            "iou": self._iou,
            "semantic_format": "objects-counts-position-size-v1",
            "vocabulary_size": len(self._vocabulary) if self._vocabulary else None,
        }
        if self._onnx is not None:
            semantics.update(self._onnx.runtime_semantics())
        return semantics

    @staticmethod
    def _result_detections(result) -> list[dict[str, Any]]:
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        orig_h, orig_w = getattr(result, "orig_shape", (1, 1))
        names = getattr(result, "names", {}) or {}
        detections: list[dict[str, Any]] = []
        for box in boxes:
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            label = names.get(cls_id, f"class_{cls_id}")
            detection = _semantic_detection(
                label=str(label),
                confidence=confidence,
                bbox=[x1, y1, x2, y2],
                orig_w=float(orig_w),
                orig_h=float(orig_h),
            )
            if detection is not None:
                detections.append(detection)
        return detections

    @staticmethod
    def _onnx_detections(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        detections: list[dict[str, Any]] = []
        for item in raw:
            orig_h, orig_w = item.get("orig_shape", [1, 1])
            detection = _semantic_detection(
                label=str(item.get("label", f"class_{item.get('class_id', -1)}")),
                confidence=float(item.get("confidence", 0.0)),
                bbox=list(item.get("bbox", [0, 0, 0, 0])),
                orig_w=float(orig_w),
                orig_h=float(orig_h),
            )
            if detection is not None:
                detections.append(detection)
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
        if self._onnx is not None:
            total = len(images)
            if callback:
                callback(self, 0, total, outputs)
            for index, source in enumerate(images, start=1):
                raw = self._onnx.predict_source(
                    source,
                    confidence=self._confidence,
                    max_det=self._max_det,
                )
                detections = self._onnx_detections(raw)
                outputs.append(np.array(_semantic_text(detections, self._max_details)))
                if callback:
                    callback(self, index, total, outputs)
            return np.asarray(outputs, dtype=object)

        num_batches = ceil(len(images) / self._batch_size)
        if callback:
            callback(self, 0, num_batches, outputs)

        for batch_idx in range(num_batches):
            batch = images[
                batch_idx * self._batch_size : (batch_idx + 1) * self._batch_size
            ]
            sources = [
                str(item) if isinstance(item, (str, Path)) else item
                for item in batch
            ]
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
        # BM25 on detector text or BGE-M3 via yolo_semantic.
        return texts

    def to(self, device: str | torch.device):
        self._device = torch.device(device)
        if self._backend == "ultralytics" and self._model is not None:
            self._model.to(self._device)
        # DirectML provider selection belongs to the ORT session, not torch.
        return self
