from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

import aic51.packages.constant as constant

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


@FeatureExtractorFactory.register("text_embedding")
class TextEmbedding(FeatureExtractor):
    """Dense text embedding extractor used for OCR/ASR BGE-M3 channels."""

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
        self._tokenizer = AutoTokenizer.from_pretrained(pretrained_model)

        model_dtype = torch.float16 if requested_device.type == "cuda" else torch.float32
        self._compute_type = str(model_dtype).removeprefix("torch.")
        self._model = AutoModel.from_pretrained(pretrained_model, torch_dtype=model_dtype)
        self._model.eval()
        super().__init__(name, batch_size, requested_device)

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
        if not text_path.exists():
            return ""

        try:
            payload = np.load(text_path, allow_pickle=True)
        except Exception:
            return ""

        if isinstance(payload, np.ndarray):
            if payload.size == 0:
                return ""
            value = payload.reshape(-1)[0]
        else:
            value = payload
        return "" if value is None else str(value)

    def _encode_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 1024), dtype=np.float32)

        tokenized = self._tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=1024,
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
        outputs = []
        total = len(texts)
        if callback:
            callback(self, 0, total, None)
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
        self._model.to(self._device)
        return self
