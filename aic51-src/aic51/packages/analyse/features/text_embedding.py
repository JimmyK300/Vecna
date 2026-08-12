from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

import aic51.packages.constant as constant

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


@FeatureExtractorFactory.register("text_embedding")
class TextEmbedding(FeatureExtractor):
    @staticmethod
    def require_input() -> Any:
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(source: str, *args, **kwargs) -> "TextEmbedding":
        if source.lower() in {"hf", "transformers"}:
            return HFTextEmbedding(*args, **kwargs)
        raise RuntimeError(f"TextEmbedding: source={source} is invalid")


class HFTextEmbedding(TextEmbedding):
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
    ):
        self.name = name
        self._batch_size = batch_size
        self._pretrained_model = pretrained_model
        self._text_source = text_source
        self._work_dir = Path(work_dir)
        self._tokenizer = AutoTokenizer.from_pretrained(pretrained_model)
        self._model = AutoModel.from_pretrained(pretrained_model)
        self._model.eval()
        self.to(device)

    def _load_text_for_keyframe(self, image_path: Path | str) -> str:
        if self._text_source is None:
            return str(image_path)

        image_path = Path(image_path)
        text_path = self._work_dir.parent / constant.FEATURE_DIR / image_path.parent.stem / image_path.stem / f"{self._text_source}.npy"
        print(f"Loading text from {text_path}", flush=True)
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

        if value is None:
            return ""
        return str(value)

    def _mean_pool(self, last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
        masked_embeddings = last_hidden_state * mask
        summed = masked_embeddings.sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1.0)
        return summed / counts

    def _encode_texts(self, texts: list[str]) -> np.ndarray:
        if len(texts) == 0:
            return np.array([])

        tokenized = self._tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        tokenized = {k: v.to(self._device) for k, v in tokenized.items()}

        with torch.no_grad():
            outputs = self._model(**tokenized)
            pooled = self._mean_pool(outputs.last_hidden_state, tokenized["attention_mask"])
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=-1)

        return pooled.cpu().numpy()

    def get_features(self, images, callback: Optional[Callable] = None):
        if len(images) == 0:
            return np.array([])

        texts = [self._load_text_for_keyframe(image) for image in images]
        num_batches = max(1, (len(texts) + self._batch_size - 1) // self._batch_size)
        features = []

        if callback:
            callback(self, 0, len(texts), [])

        for batch_index in range(num_batches):
            batch_texts = texts[batch_index * self._batch_size : (batch_index + 1) * self._batch_size]
            if not batch_texts:
                continue
            features.append(self._encode_texts(batch_texts))
            if callback:
                completed = min(len(texts), (batch_index + 1) * self._batch_size)
                callback(self, completed, len(texts), features)

        if len(features) == 0:
            return np.array([])

        return np.concatenate(features, axis=0)

    def get_text_features(self, texts: list[str] | str | np.ndarray, callback: Optional[Callable] = None) -> Any:
        if isinstance(texts, np.ndarray):
            texts = list(texts.tolist())
        if isinstance(texts, str):
            texts = [texts]
        return self._encode_texts([str(text) for text in texts])

    def to(self, device):
        self._device = torch.device(device)
        self._model.to(self._device)