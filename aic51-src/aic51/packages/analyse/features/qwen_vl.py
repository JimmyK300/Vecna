from math import ceil
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer

import aic51.packages.constant as constant
from aic51.packages.logger import logger

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


@FeatureExtractorFactory.register("qwen_vl_embedding")
class QwenVLEmbedding(FeatureExtractor):
    @staticmethod
    def require_input() -> Any:
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(pretrained_model: str, *args, **kwargs) -> "QwenVLEmbedding":
        return QwenVLEmbedding(pretrained_model=pretrained_model, *args, **kwargs)

    @staticmethod
    def _resolve_device(device: str | torch.device) -> torch.device:
        requested = torch.device(device)
        if requested.type == "cuda" and not torch.cuda.is_available():
            logger.warning(
                "Qwen-VL embedding: CUDA was requested but is unavailable; "
                "falling back to CPU. Inference will be much slower."
            )
            return torch.device("cpu")
        if requested.type not in {"cuda", "cpu"}:
            logger.warning(
                f"Qwen-VL embedding: device {requested} is not currently supported; "
                "falling back to CPU."
            )
            return torch.device("cpu")
        return requested

    def __init__(
        self,
        pretrained_model: str,
        name: str = "qwen_vl",
        batch_size: int = 1,
        device: str | torch.device = "cpu",
        *args,
        **kwargs,
    ) -> None:
        requested_device = self._resolve_device(device)

        # Generic analyser/searcher constructor fields not consumed by the
        # Sentence Transformers multimodal model.
        kwargs.pop("source", None)
        kwargs.pop("arch_name", None)
        kwargs.pop("work_dir", None)
        kwargs.pop("text_source", None)

        model_kwargs = kwargs.pop("model_kwargs", None)
        if model_kwargs is None:
            if requested_device.type == "cuda":
                dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            else:
                dtype = torch.float16
            model_kwargs = {"torch_dtype": dtype, "low_cpu_mem_usage": True}
            self._compute_type = str(dtype).removeprefix("torch.")
        else:
            self._compute_type = str(model_kwargs.get("torch_dtype", "model_default"))

        processor_kwargs = kwargs.pop("processor_kwargs", None)
        self._model = SentenceTransformer(
            pretrained_model,
            device=str(requested_device),
            model_kwargs=model_kwargs,
            processor_kwargs=processor_kwargs,
        )

        if not self._model.supports("image") or not self._model.supports("text"):
            raise RuntimeError(
                f"{pretrained_model} must support both image and text embeddings"
            )

        if requested_device.type == "cpu":
            logger.warning(
                "Qwen-VL embedding backend: CPU. This is supported, but "
                "Qwen3-VL-Embedding-2B inference is expected to be slow."
            )
        else:
            logger.info(f"Qwen-VL embedding backend: {requested_device}")

        super().__init__(name, batch_size, requested_device)

    def _empty_features(self) -> np.ndarray:
        dimension = self._model.get_sentence_embedding_dimension() or 2048
        return np.empty((0, dimension), dtype=np.float32)

    def _encode(
        self,
        items: list,
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        if not items:
            return self._empty_features()

        outputs = []
        num_batches = ceil(len(items) / self._batch_size)
        if callback:
            callback(self, 0, num_batches, None)

        for batch_index, start in enumerate(range(0, len(items), self._batch_size)):
            batch = items[start : start + self._batch_size]
            batch_features = self._model.encode(
                batch,
                batch_size=len(batch),
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
                device=str(self._device),
            )
            outputs.append(np.asarray(batch_features, dtype=np.float32))
            if callback:
                callback(self, batch_index + 1, num_batches, None)

        return np.concatenate(outputs, axis=0)

    def get_features(
        self,
        images: list[Path | str] | np.ndarray | torch.Tensor | list[Image.Image],
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        if isinstance(images, torch.Tensor):
            images = list(images)
        elif isinstance(images, np.ndarray):
            images = [images] if images.ndim == 3 else list(images)
        else:
            images = list(images)

        normalized_images = [str(image) if isinstance(image, Path) else image for image in images]
        return self._encode(normalized_images, callback)

    def get_text_features(
        self,
        texts: list[str] | str | np.ndarray,
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        if isinstance(texts, np.ndarray):
            texts = texts.tolist()
        if isinstance(texts, str):
            texts = [texts]
        return self._encode(list(texts), callback)

    def to(self, device: str | torch.device):
        requested_device = self._resolve_device(device)
        if requested_device.type == "cpu" and getattr(self, "_device", None) != requested_device:
            logger.warning(
                "Qwen-VL embedding moved to CPU; inference is supported but expected to be slow."
            )
        self._device = requested_device
        self._model.to(requested_device)
        return self
