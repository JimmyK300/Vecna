import re
from math import ceil
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch
from PIL import Image

import aic51.packages.constant as constant
from aic51.packages.logger import logger

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


@FeatureExtractorFactory.register("yolo")
class YOLOFeature(FeatureExtractor):
    @staticmethod
    def require_input():
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(
        pretrained_model: str = "yolov8x.pt",
        source: str = "ultralytics",
        confidence: float = 0.25,
        *args,
        **kwargs,
    ) -> "YOLOFeature":
        if source.lower() == "ultralytics":
            return UltralyticsYOLO(pretrained_model=pretrained_model, confidence=confidence, *args, **kwargs)
        else:
            raise RuntimeError(f"YOLO: source={source} is invalid")


@FeatureExtractorFactory.register("yoloe")
class YOLOEFeature(FeatureExtractor):
    @staticmethod
    def require_input():
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(
        pretrained_model: str = "yolov8x-worldv2.pt",
        source: str = "ultralytics",
        confidence: float = 0.15,
        *args,
        **kwargs,
    ) -> "YOLOEFeature":
        if source.lower() == "ultralytics":
            return UltralyticsYOLOE(pretrained_model=pretrained_model, confidence=confidence, *args, **kwargs)
        else:
            raise RuntimeError(f"YOLOE: source={source} is invalid")


class UltralyticsYOLO(YOLOFeature):
    def __init__(
        self,
        pretrained_model: str = "yolov8x.pt",
        confidence: float = 0.25,
        name: str = "yolo",
        batch_size: int = 16,
        device: torch.device = torch.device("cpu"),
        *args,
        **kwargs,
    ):
        from ultralytics import YOLO

        self.name = name
        self._batch_size = batch_size
        self._confidence = confidence
        self._device = torch.device(device)
        self._model = YOLO(pretrained_model)

    def get_features(
        self,
        images: list[Path | str] | np.ndarray | torch.Tensor | list[Image.Image],
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        image_features = []
        num_batches = ceil(len(images) / self._batch_size)
        if callback:
            callback(self, 0, num_batches, image_features)

        for b in range(num_batches):
            batch_images = images[b * self._batch_size : (b + 1) * self._batch_size]
            # Convert paths to string for ultralytics predict
            input_sources = []
            for img in batch_images:
                if isinstance(img, (str, Path)):
                    input_sources.append(str(img))
                else:
                    input_sources.append(img)

            # Predict using YOLO
            results = self._model.predict(
                source=input_sources,
                conf=self._confidence,
                device=self._device,
                verbose=False,
            )

            for res in results:
                detected_names = []
                if res.boxes is not None and len(res.boxes) > 0:
                    cls_ids = res.boxes.cls.cpu().numpy().astype(int)
                    names_dict = res.names
                    detected_names = [names_dict[cid] for cid in cls_ids if cid in names_dict]

                # Join detected names into a normalized space-separated string
                normalized_text = self._normalize_labels(detected_names)
                image_features.append(np.array(normalized_text))

            if callback:
                callback(self, b + 1, num_batches, image_features)

        return np.array(image_features)

    def _normalize_labels(self, labels: list[str]) -> str:
        if not labels:
            return ""
        # Clean labels to lowercase and replace spaces with underscores
        cleaned = [re.sub(r"\s+", "_", l.strip().lower()) for l in labels]
        return " ".join(cleaned)

    def get_text_features(self, texts: list[str] | str | np.ndarray, callback: Optional[Callable] = None) -> Any:
        return texts

    def to(self, device: str | torch.device):
        self._device = torch.device(device)
        if hasattr(self._model, "to"):
            self._model.to(self._device)


class UltralyticsYOLOE(YOLOEFeature):
    """
    Open-vocabulary YOLO feature extractor using YOLO-World / YOLOE model.
    Supports 1203 LVIS categories instead of the 80 fixed COCO classes,
    resulting in richer keyword extraction for BM25 search.
    """

    def __init__(
        self,
        pretrained_model: str = "yolov8x-worldv2.pt",
        confidence: float = 0.15,
        name: str = "yolo",
        batch_size: int = 8,
        device: torch.device = torch.device("cpu"),
        vocabulary: Optional[list[str]] = None,
        *args,
        **kwargs,
    ):
        from ultralytics import YOLO
        from .lvis_classes import LVIS_CLASSES

        self.name = name
        self._batch_size = batch_size
        self._confidence = confidence
        self._device = torch.device(device)

        logger.info(f"[YOLOE] Loading model: {pretrained_model}")
        self._model = YOLO(pretrained_model)

        # Use provided vocabulary or fall back to LVIS 1203 classes
        self._vocab = vocabulary if vocabulary is not None else LVIS_CLASSES
        logger.info(f"[YOLOE] Setting {len(self._vocab)} classes from {'custom' if vocabulary else 'LVIS'} vocabulary")
        self._model.set_classes(self._vocab)

    def get_features(
        self,
        images: list[Path | str] | np.ndarray | torch.Tensor | list[Image.Image],
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        image_features = []
        num_batches = ceil(len(images) / self._batch_size)
        if callback:
            callback(self, 0, num_batches, image_features)

        for b in range(num_batches):
            batch_images = images[b * self._batch_size : (b + 1) * self._batch_size]
            # Convert paths to string for ultralytics predict
            input_sources = []
            for img in batch_images:
                if isinstance(img, (str, Path)):
                    input_sources.append(str(img))
                else:
                    input_sources.append(img)

            # Predict using YOLOE
            results = self._model.predict(
                source=input_sources,
                conf=self._confidence,
                device=self._device,
                verbose=False,
            )

            for res in results:
                detected_tokens: list[str] = []
                if res.boxes is not None and len(res.boxes) > 0:
                    cls_ids = res.boxes.cls.cpu().numpy().astype(int)
                    names_dict = res.names
                    for cid in cls_ids:
                        if cid in names_dict:
                            label = names_dict[cid]
                            detected_tokens.append(label.strip())

                # Deduplicate while preserving order
                seen = set()
                unique_tokens = []
                for tok in detected_tokens:
                    if tok not in seen:
                        seen.add(tok)
                        unique_tokens.append(tok)

                # Normalize: lowercase, replace internal spaces with underscore for BM25
                normalized = self._normalize_labels(unique_tokens)
                image_features.append(np.array(normalized))

            if callback:
                callback(self, b + 1, num_batches, image_features)

        return np.array(image_features)

    def _normalize_labels(self, labels: list[str]) -> str:
        if not labels:
            return ""
        # Each label may contain spaces (e.g. "aerosol can spray can")
        # Replace internal spaces with underscore for BM25 tokenization
        cleaned = [re.sub(r"\s+", "_", l.strip().lower()) for l in labels]
        return " ".join(cleaned)

    def get_text_features(self, texts: list[str] | str | np.ndarray, callback: Optional[Callable] = None) -> Any:
        # For BM25 search: normalize spaces in query to underscores to match stored tokens
        if isinstance(texts, str):
            return re.sub(r"\s+", "_", texts.strip().lower())
        elif isinstance(texts, list):
            return [re.sub(r"\s+", "_", t.strip().lower()) for t in texts]
        return texts

    def to(self, device: str | torch.device):
        self._device = torch.device(device)
        if hasattr(self._model, "to"):
            self._model.to(self._device)

