from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch

import aic51.packages.constant as constant
from aic51.packages.logger import logger

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


def _load_frame_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        payload = np.load(path, allow_pickle=True)
    except Exception:
        return ""
    if isinstance(payload, np.ndarray):
        if payload.size == 0:
            return ""
        value = payload.reshape(-1)[0]
    else:
        value = payload
    return "" if value is None else str(value)


@FeatureExtractorFactory.register("text_embedding")
class TextEmbedding(FeatureExtractor):
    """Dense text embedding extractor used for OCR/ASR BGE-M3 channels.

    `backend=pytorch` preserves the original Transformers implementation.
    `backend=onnx` is an additional ONNX Runtime path (DirectML or CPU).
    """

    identity_aware_outputs = True

    @staticmethod
    def require_input() -> Any:
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(pretrained_model: str, *args, **kwargs) -> "TextEmbedding":
        return TextEmbedding(pretrained_model=pretrained_model, *args, **kwargs)

    def __init__(
        self,
        pretrained_model: str,
        name: str = "text_embedding",
        batch_size: int = 16,
        device: str | torch.device = "cpu",
        text_source: str | None = None,
        work_dir: Path | str = ".",
        backend: str = "pytorch",
        onnx_provider: str = "auto",
        onnx_model_path: str | Path | None = None,
        onnx_tokenizer_path: str | Path | None = None,
        onnx_max_length: int | None = None,
        max_length: int | None = None,
        allow_gpu: bool | None = None,
        *args,
        **kwargs,
    ) -> None:
        kwargs.pop("source", None)
        kwargs.pop("arch_name", None)

        requested_device = torch.device(device)
        self._pretrained_model = pretrained_model
        if text_source is None and name.endswith("_dense"):
            inferred_source = name.removesuffix("_dense")
            if inferred_source in {"ocr", "asr"}:
                text_source = inferred_source
        self._text_source = text_source
        self._work_dir = Path(work_dir)
        self._backend = (backend or "pytorch").strip().lower()
        if self._backend not in {"pytorch", "onnx"}:
            raise ValueError(f"unknown text_embedding backend {backend!r}; use pytorch|onnx")

        self._onnx_backend = None
        self._model = None
        self._tokenizer = None

        if allow_gpu is None:
            allow_gpu = requested_device.type != "cpu"
        self._allow_gpu = bool(allow_gpu)

        if self._backend == "onnx":
            from .bge_onnx import DEFAULT_MAX_LENGTH, BgeM3OnnxBackend

            resolved_max = onnx_max_length if onnx_max_length is not None else max_length
            if resolved_max is None:
                resolved_max = DEFAULT_MAX_LENGTH
            self._onnx_backend = BgeM3OnnxBackend(
                model_path=onnx_model_path,
                tokenizer_path=onnx_tokenizer_path,
                provider=onnx_provider or "auto",
                allow_gpu=self._allow_gpu,
                max_length=int(resolved_max),
                pretrained_model=pretrained_model,
            )
            self._compute_type = self._onnx_backend.precision
        else:
            from transformers import AutoModel, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(pretrained_model)
            model_dtype = torch.float16 if requested_device.type == "cuda" else torch.float32
            self._compute_type = str(model_dtype).removeprefix("torch.")
            self._model = AutoModel.from_pretrained(pretrained_model, torch_dtype=model_dtype)
            self._model.eval()
            self._pytorch_max_length = 1024
            logger.info("BGE-M3 backend: PyTorch / Transformers")
            logger.info(f"BGE-M3 model: {pretrained_model}")
            logger.info(f"BGE-M3 device: {requested_device}")

        super().__init__(name, batch_size, requested_device)

    def runtime_semantics(self) -> dict[str, Any]:
        if self._onnx_backend is not None:
            semantics = self._onnx_backend.runtime_semantics()
            semantics["device"] = str(self._device)
            return semantics
        return {
            "backend": "pytorch",
            "execution_framework": "transformers",
            "device": str(getattr(self, "_device", "cpu")),
            "compute_type": self._compute_type,
            "pretrained_model": self._pretrained_model,
            "max_length": getattr(self, "_pytorch_max_length", 1024),
            "hidden_size": 1024,
        }

    def discover_video_ids(self, work_dir: Path | str | None = None) -> list[str]:
        root = Path(work_dir or self._work_dir) / constant.FEATURE_DIR
        if not root.is_dir():
            return []
        return sorted(
            path.name
            for path in root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        )

    def discover_frame_ids(self, work_dir: Path | str | None, video_id: str) -> list[str]:
        video_dir = Path(work_dir or self._work_dir) / constant.FEATURE_DIR / video_id
        if not video_dir.is_dir() or self._text_source is None:
            return []
        frames = []
        for frame_dir in video_dir.iterdir():
            if not frame_dir.is_dir() or frame_dir.name.startswith("."):
                continue
            if (frame_dir / f"{self._text_source}.npy").is_file():
                frames.append(frame_dir.name)
        return sorted(frames)

    def input_paths_for_frames(
        self,
        work_dir: Path | str | None,
        video_id: str,
        frame_ids: list[str],
    ) -> list[Path]:
        video_dir = Path(work_dir or self._work_dir) / constant.FEATURE_DIR / video_id
        return [video_dir / frame_id for frame_id in frame_ids]

    def _load_text_for_keyframe(self, image_path: Path | str) -> str:
        if self._text_source is None:
            return str(image_path)

        image_path = Path(image_path)
        text_path = (
            self._work_dir
            / constant.FEATURE_DIR
            / image_path.parent.stem
            / image_path.stem
            / f"{self._text_source}.npy"
        )
        return _load_frame_text(text_path)

    def _encode_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 1024), dtype=np.float32)
        if self._onnx_backend is not None:
            if len(texts) <= 1:
                return self._onnx_backend.embed(texts)
            return self._onnx_backend.embed_token_lists(
                self._onnx_backend.tokenize_unpadded(texts),
                batch_size=self._batch_size,
            )

        tokenized = self._tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self._pytorch_max_length,
        )
        tokenized = {key: value.to(self._device) for key, value in tokenized.items()}

        with torch.inference_mode():
            outputs = self._model(**tokenized)
            embeddings = outputs.last_hidden_state[:, 0]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=-1)
        return embeddings.float().cpu().numpy()

    def get_features(self, images, callback: Optional[Callable] = None) -> np.ndarray:
        images = list(images)
        if not images:
            return np.empty((0, 1024), dtype=np.float32)

        texts = [self._load_text_for_keyframe(image) for image in images]
        total = len(texts)
        if callback:
            callback(self, 0, total, None)
        if self._onnx_backend is not None:
            vectors = self._onnx_backend.embed_token_lists(
                self._onnx_backend.tokenize_unpadded(texts),
                batch_size=self._batch_size,
            )
            if callback:
                callback(self, total, total, None)
            return vectors
        outputs = []
        for start in range(0, total, self._batch_size):
            batch = texts[start : start + self._batch_size]
            outputs.append(self._encode_texts(batch))
            if callback:
                callback(self, min(start + len(batch), total), total, None)
        return np.concatenate(outputs, axis=0) if outputs else np.empty((0, 1024), dtype=np.float32)

    def get_text_features(
        self,
        texts: list[str] | str | np.ndarray,
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        if isinstance(texts, np.ndarray):
            texts = texts.tolist()
        if isinstance(texts, str):
            texts = [texts]
        values = [str(text) for text in texts]
        result = self._encode_texts(values)
        if callback:
            callback(self, len(values), len(values), None)
        return result

    def to(self, device: str | torch.device):
        self._device = torch.device(device)
        if self._backend == "onnx":
            return self
        if self._model is not None:
            self._model.to(self._device)
        return self
