from math import ceil
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer

import aic51.packages.constant as constant

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


@FeatureExtractorFactory.register("qwen_vl_embedding")
class QwenVLEmbedding(FeatureExtractor):
    @staticmethod
    def require_input() -> Any:
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(pretrained_model: str, *args, **kwargs) -> "QwenVLEmbedding":
        return QwenVLEmbedding(pretrained_model=pretrained_model, *args, **kwargs)

    def __init__(
        self,
        pretrained_model: str,
        name: str = "qwen_vl",
        batch_size: int = 1,
        device: str | torch.device = torch.device("cuda"),
        *args,
        **kwargs,
    ) -> None:
        requested_device = torch.device(device)
        self._require_cuda(requested_device)

        # These are part of the generic analyser constructor contract but are
        # not used by the Sentence Transformers-backed Qwen extractor.
        kwargs.pop("source", None)
        kwargs.pop("arch_name", None)

        model_kwargs = kwargs.pop("model_kwargs", None)
        if model_kwargs is None:
            model_kwargs = {
                "torch_dtype": torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
            }

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

        super().__init__(name, batch_size, requested_device)

    @staticmethod
    def _require_cuda(device: torch.device) -> None:
        if device.type != "cuda" or not torch.cuda.is_available():
            raise RuntimeError("QwenVL embedding extractor requires a CUDA device")

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
            outputs.append(np.asarray(batch_features))

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
            if images.ndim == 3:
                images = [images]
            else:
                images = list(images)
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
        requested_device = torch.device(device)
        self._require_cuda(requested_device)
        self._device = requested_device
        self._model.to(requested_device)
        return self
