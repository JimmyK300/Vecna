"""ONNX Runtime backend for baked-vocabulary YOLOE detection exports.

This module deliberately treats DirectML as an ONNX Runtime execution provider,
not as a torch device.  It is intended for fixed-shape, detection-only YOLOE
exports such as the proven RX 6900 XT artifact:

    1x3x640x640 -> 1x300x6

The six output values are expected to be ``x1, y1, x2, y2, confidence, class``
in letterboxed input coordinates.  The model is end-to-end/NMS-free; Vecna
therefore applies the same corpus-facing policy it expects from Ultralytics:
confidence filtering followed by top-``max_det`` selection, then scales boxes
back to the original image.
"""

from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from aic51.packages.utils.provenance import file_sha256

YOLO_ONNX_ENV_VAR = "VECNA_YOLO_ONNX"
YOLO_NAMES_ENV_VAR = "VECNA_YOLO_NAMES"
DEFAULT_ONNX_NAME = "yoloe-26x-det-ram-plus-640-b1.onnx"


class OnnxRuntimeUnavailable(RuntimeError):
    pass


class DirectMLUnavailable(RuntimeError):
    pass


def import_onnxruntime():
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise OnnxRuntimeUnavailable(
            "YOLO ONNX backend requested but ONNX Runtime is not installed. "
            "For the Windows AMD path install `onnxruntime-directml` and do not "
            "install `onnxruntime` in the same environment."
        ) from exc
    return ort


def available_providers() -> list[str]:
    return list(import_onnxruntime().get_available_providers())


def has_directml() -> bool:
    try:
        return "DmlExecutionProvider" in available_providers()
    except OnnxRuntimeUnavailable:
        return False


def resolve_onnx_model_path(explicit: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env = os.environ.get(YOLO_ONNX_ENV_VAR)
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(Path.cwd() / "models" / DEFAULT_ONNX_NAME)

    for path in candidates:
        if path.is_file():
            return path.resolve()
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        "YOLOE ONNX artifact not found. Set features.yolo.onnx_model_path or "
        f"{YOLO_ONNX_ENV_VAR}. Looked at: {searched}"
    )


def resolve_provider_choice(requested: str, *, allow_gpu: bool) -> tuple[str, str | None]:
    """Resolve to ``dml`` or ``cpu`` without consulting torch.cuda."""
    choice = (requested or "auto").strip().lower()
    if choice not in {"auto", "dml", "cpu"}:
        raise ValueError(f"unknown YOLO ONNX provider {requested!r}; use auto|dml|cpu")

    if choice == "cpu" or not allow_gpu:
        warning = None
        if choice == "dml" and not allow_gpu:
            warning = "DirectML disabled by --no-gpu / allow_gpu=false; using CPU."
        elif choice == "auto" and not allow_gpu:
            warning = "GPU execution disabled; using ONNX Runtime CPU."
        return "cpu", warning

    providers = available_providers()
    if "DmlExecutionProvider" not in providers:
        if choice == "dml":
            raise DirectMLUnavailable(
                "DmlExecutionProvider is not present in this ONNX Runtime build. "
                f"Available providers: {providers}. Install onnxruntime-directml."
            )
        return "cpu", "DirectML unavailable; using ONNX Runtime CPU."
    return "dml", None


def _session_providers(choice: str, device_id: int = 0) -> list:
    if choice == "dml":
        return [
            ("DmlExecutionProvider", {"device_id": int(device_id)}),
            "CPUExecutionProvider",
        ]
    return ["CPUExecutionProvider"]


def create_session(model_path: Path, choice: str, device_id: int = 0):
    """Create an ORT session with DirectML's required session constraints."""
    ort = import_onnxruntime()
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.log_severity_level = 3
    if choice == "dml":
        # DirectML requires sequential execution and does not support ORT's
        # memory-pattern optimization for sessions using this provider.
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    session = ort.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=_session_providers(choice, device_id=device_id),
    )
    assert_requested_provider(session, choice)
    return session


def active_execution_provider(session) -> str:
    providers = list(session.get_providers())
    if not providers:
        raise RuntimeError("YOLO ONNX session reported no execution providers")
    return providers[0]


def assert_requested_provider(session, choice: str) -> str:
    active = active_execution_provider(session)
    if choice == "dml" and active != "DmlExecutionProvider":
        raise DirectMLUnavailable(
            "DirectML was requested but the session did not activate it first: "
            f"{session.get_providers()}"
        )
    return active


def _parse_names_payload(raw: Any) -> dict[int, str]:
    if raw is None:
        return {}
    value = raw
    if isinstance(value, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                value = parser(value)
                break
            except Exception:
                continue
    if isinstance(value, list):
        return {index: str(name) for index, name in enumerate(value)}
    if isinstance(value, dict):
        result = {}
        for key, name in value.items():
            try:
                result[int(key)] = str(name)
            except (TypeError, ValueError):
                continue
        return result
    return {}


def _load_names_file(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    parsed = _parse_names_payload(text)
    if parsed:
        return parsed
    names = [line.strip() for line in text.splitlines() if line.strip()]
    return {index: name for index, name in enumerate(names)}


def resolve_class_names(session, explicit: str | Path | None = None) -> dict[int, str]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env = os.environ.get(YOLO_NAMES_ENV_VAR)
    if env:
        candidates.append(Path(env).expanduser())
    for path in candidates:
        if path.is_file():
            names = _load_names_file(path)
            if names:
                return names

    try:
        metadata = session.get_modelmeta().custom_metadata_map or {}
    except Exception:
        metadata = {}
    for key in ("names", "class_names", "classes"):
        names = _parse_names_payload(metadata.get(key))
        if names:
            return names
    return {}


@dataclass(frozen=True)
class LetterboxTransform:
    orig_w: int
    orig_h: int
    ratio: float
    left: int
    top: int
    input_w: int
    input_h: int


def letterbox_rgb(image: Image.Image, imgsz: int = 640, dtype=np.float32) -> tuple[np.ndarray, LetterboxTransform]:
    """Ultralytics-compatible centered letterbox for a square fixed input."""
    image = image.convert("RGB")
    array = np.asarray(image)
    orig_h, orig_w = array.shape[:2]
    input_h = input_w = int(imgsz)
    ratio = min(input_h / max(orig_h, 1), input_w / max(orig_w, 1))
    new_w = int(round(orig_w * ratio))
    new_h = int(round(orig_h * ratio))

    if (new_w, new_h) != (orig_w, orig_h):
        array = cv2.resize(array, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    dw = input_w - new_w
    dh = input_h - new_h
    left = int(round(dw / 2 - 0.1))
    right = int(round(dw / 2 + 0.1))
    top = int(round(dh / 2 - 0.1))
    bottom = int(round(dh / 2 + 0.1))
    array = cv2.copyMakeBorder(
        array,
        top,
        bottom,
        left,
        right,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    if array.shape[0] != input_h or array.shape[1] != input_w:
        raise RuntimeError(
            f"letterbox produced {array.shape[:2]}, expected {(input_h, input_w)}"
        )

    tensor = np.ascontiguousarray(array.transpose(2, 0, 1)[None], dtype=dtype)
    tensor /= np.asarray(255.0, dtype=dtype)
    return tensor, LetterboxTransform(
        orig_w=orig_w,
        orig_h=orig_h,
        ratio=ratio,
        left=left,
        top=top,
        input_w=input_w,
        input_h=input_h,
    )


def _rows_from_output(output: Any) -> np.ndarray:
    rows = np.asarray(output)
    if rows.ndim == 3 and rows.shape[0] == 1:
        rows = rows[0]
    if rows.ndim != 2:
        raise ValueError(f"unexpected YOLO ONNX output shape {rows.shape}; expected 1xNx6")
    if rows.shape[-1] != 6 and rows.shape[0] == 6:
        rows = rows.T
    if rows.shape[-1] != 6:
        raise ValueError(f"unexpected YOLO ONNX output shape {rows.shape}; expected Nx6")
    return rows.astype(np.float32, copy=False)


def decode_detections(
    output: Any,
    transform: LetterboxTransform,
    names: dict[int, str],
    *,
    confidence: float,
    max_det: int,
) -> list[dict[str, Any]]:
    """Filter the end-to-end export and restore boxes to original coordinates."""
    rows = _rows_from_output(output)
    if rows.size == 0:
        return []
    finite = np.isfinite(rows).all(axis=1)
    rows = rows[finite & (rows[:, 4] >= float(confidence))]
    if rows.size == 0:
        return []

    order = np.argsort(-rows[:, 4], kind="stable")
    rows = rows[order[: max(0, int(max_det))]]
    detections: list[dict[str, Any]] = []
    ratio = max(float(transform.ratio), 1e-12)

    for row in rows:
        x1, y1, x2, y2, score, class_value = [float(value) for value in row]
        x1 = (x1 - transform.left) / ratio
        x2 = (x2 - transform.left) / ratio
        y1 = (y1 - transform.top) / ratio
        y2 = (y2 - transform.top) / ratio
        x1 = min(max(x1, 0.0), float(transform.orig_w))
        x2 = min(max(x2, 0.0), float(transform.orig_w))
        y1 = min(max(y1, 0.0), float(transform.orig_h))
        y2 = min(max(y2, 0.0), float(transform.orig_h))
        if x2 <= x1 or y2 <= y1:
            continue
        class_id = int(round(class_value))
        detections.append(
            {
                "label": names.get(class_id, f"class_{class_id}"),
                "class_id": class_id,
                "confidence": score,
                "bbox": [x1, y1, x2, y2],
                "orig_shape": [transform.orig_h, transform.orig_w],
            }
        )
    return detections


class YOLOOnnxBackend:
    """Fixed-shape YOLOE ONNX Runtime backend (DirectML or CPU)."""

    def __init__(
        self,
        model_path: str | Path | None,
        provider: str = "dml",
        *,
        allow_gpu: bool = True,
        imgsz: int = 640,
        class_names_path: str | Path | None = None,
        device_id: int = 0,
    ) -> None:
        self.model_path = resolve_onnx_model_path(model_path)
        self.provider_choice, warning = resolve_provider_choice(provider, allow_gpu=allow_gpu)
        self.session = create_session(
            self.model_path,
            self.provider_choice,
            device_id=device_id,
        )
        self.execution_provider = active_execution_provider(self.session)
        self.names = resolve_class_names(self.session, class_names_path)
        self.imgsz = int(imgsz)
        self.model_sha256 = file_sha256(self.model_path)

        inputs = list(self.session.get_inputs())
        if len(inputs) != 1:
            raise ValueError(f"YOLO ONNX export must have one image input, found {len(inputs)}")
        self.input_name = inputs[0].name
        self.input_shape = list(inputs[0].shape)
        input_type = str(getattr(inputs[0], "type", "tensor(float)"))
        self.input_dtype = np.float16 if "float16" in input_type else np.float32

        if len(self.input_shape) != 4:
            raise ValueError(f"YOLO ONNX input must be NCHW, got {self.input_shape}")
        if isinstance(self.input_shape[0], int) and self.input_shape[0] != 1:
            raise ValueError(
                "Current Vecna DirectML path expects the proven static batch-1 export; "
                f"got input shape {self.input_shape}"
            )
        if warning:
            # Keep this backend dependency-light: caller/logger can surface the
            # provider through runtime_semantics; warning is retained for tests/debug.
            self.warning = warning
        else:
            self.warning = None

    def runtime_semantics(self) -> dict[str, Any]:
        return {
            "backend": "onnx",
            "execution_framework": "onnxruntime",
            "execution_provider": self.execution_provider,
            "provider_choice": self.provider_choice,
            "onnx_model_path": str(self.model_path),
            "onnx_sha256": self.model_sha256,
            "input_shape": self.input_shape,
            "input_dtype": str(np.dtype(self.input_dtype)),
            "vocabulary_size": len(self.names),
            "decode": "end-to-end conf-filter + top-max_det + deletterbox-v1",
        }

    def predict_one(
        self,
        image: Image.Image,
        *,
        confidence: float,
        max_det: int,
    ) -> list[dict[str, Any]]:
        tensor, transform = letterbox_rgb(image, imgsz=self.imgsz, dtype=self.input_dtype)
        outputs = self.session.run(None, {self.input_name: tensor})
        if not outputs:
            return []
        return decode_detections(
            outputs[0],
            transform,
            self.names,
            confidence=confidence,
            max_det=max_det,
        )

    def predict_source(
        self,
        source: str | Path | Image.Image,
        *,
        confidence: float,
        max_det: int,
    ) -> list[dict[str, Any]]:
        if isinstance(source, Image.Image):
            return self.predict_one(source, confidence=confidence, max_det=max_det)
        with Image.open(source) as image:
            return self.predict_one(image, confidence=confidence, max_det=max_det)
