import re
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pytesseract
import torch
from PIL import Image

import aic51.packages.constant as constant

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


@FeatureExtractorFactory.register("ocr")
class OCR(FeatureExtractor):
    @staticmethod
    def require_input():
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(source: str, *args, **kwargs) -> "OCR":
        if source.lower() == "tesseract":
            return Tesseract(*args, **kwargs)
        else:
            raise RuntimeError(f"OCR: source={source} is invalid")


class Tesseract(OCR):
    def __init__(self, name: str = "ocr", batch_size: int = 1, *args, **kwargs):
        self.name = name
        self._batch_size = batch_size
        self._native_evidence = {"scope": "frame", "kind": "ocr_observation", "items": []}

    def _coerce_confidence(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_language_pass(self, image: Image.Image, language: str):
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, lang=language)
        observations = []
        raw_tokens = []

        texts = data.get("text", [])
        for index, raw_token in enumerate(texts):
            token = str(raw_token or "")
            if not token.strip():
                continue

            raw_tokens.append(token)
            confidence = self._coerce_confidence(data.get("conf", [None] * len(texts))[index])
            observation = {
                "raw_text": token,
                "normalized_text": self._normalize_text(token),
                "language_pass": language,
                "region": {
                    "coordinate_system": "source_image_pixels",
                    "x": int(data.get("left", [0] * len(texts))[index]),
                    "y": int(data.get("top", [0] * len(texts))[index]),
                    "width": int(data.get("width", [0] * len(texts))[index]),
                    "height": int(data.get("height", [0] * len(texts))[index]),
                },
            }
            if confidence is not None:
                observation["confidence"] = confidence
            observations.append(observation)

        return raw_tokens, observations

    def get_features(
        self,
        images: list[Path | str] | np.ndarray | torch.Tensor | list[Image.Image],
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        if len(images) == 0:
            self._native_evidence = {"scope": "frame", "kind": "ocr_observation", "items": []}
            return np.array([])

        image_features = []
        native_items = []
        num_batches = ceil(len(images) / self._batch_size)
        if callback:
            callback(self, 0, num_batches, image_features)

        with ThreadPoolExecutor(self._batch_size) as executor:

            def process_one_image(image_ref):
                frame_id = None
                if isinstance(image_ref, (str, Path)):
                    image_path = Path(image_ref)
                    frame_id = image_path.stem
                    image = Image.open(image_path)
                else:
                    image = image_ref

                width, height = image.size
                crop_height = round(height * 8 / 9)
                cropped_image = image.crop((0, 0, width, crop_height))

                eng_tokens, eng_observations = self._extract_language_pass(cropped_image, "eng")
                vie_tokens, vie_observations = self._extract_language_pass(cropped_image, "vie")
                raw_text = " ".join([*eng_tokens, *vie_tokens]).strip()
                normalized_text = self._normalize_text(raw_text)
                observations = [*eng_observations, *vie_observations]

                evidence = {
                    "kind": "ocr_observation",
                    "frame_id": str(frame_id) if frame_id is not None else "unknown",
                    "parent_locator": {
                        "kind": "frame",
                        "frame_id": str(frame_id) if frame_id is not None else "unknown",
                    },
                    "status": "success_output" if normalized_text or observations else "success_empty",
                    "raw_text": raw_text,
                    "normalized_text": normalized_text,
                    "observations": observations,
                    "preprocess": {
                        "crop": {
                            "coordinate_system": "source_image_pixels",
                            "x": 0,
                            "y": 0,
                            "width": width,
                            "height": crop_height,
                        }
                    },
                }
                return normalized_text, evidence

            step = max(1, num_batches // 50)
            for b in range(num_batches):
                batch_images = images[b * self._batch_size : (b + 1) * self._batch_size]
                futures = [executor.submit(process_one_image, image) for image in batch_images]

                for future in futures:
                    normalized_text, evidence = future.result()
                    image_features.append(np.array(normalized_text))
                    native_items.append(evidence)

                if callback and ((b + 1) % step == 0 or (b + 1) == num_batches):
                    callback(self, b + 1, num_batches, image_features)

        self._native_evidence = {
            "scope": "frame",
            "kind": "ocr_observation",
            "items": native_items,
        }
        return np.array(image_features)

    def get_native_evidence(self):
        return self._native_evidence

    def _normalize_text(self, text: str):
        res = text.strip().lower()
        return re.sub(r"\s+", " ", res)

    def get_text_features(self, texts: list[str] | str | np.ndarray, callback: Optional[Callable] = None) -> Any:
        return texts

    def to(self, device):
        pass
