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
