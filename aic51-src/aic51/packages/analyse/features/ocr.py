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
from aic51.packages.logger import logger
from aic51.packages.provenance import normalize_text, write_json_artifact

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
    def __init__(self, name: str = "ocr", batch_size: int = 1, work_dir: Path | str = ".", *args, **kwargs):
        self.name = name
        self._batch_size = batch_size
        self._work_dir = Path(work_dir)

    def get_features(
        self,
        images: list[Path | str] | np.ndarray | torch.Tensor | list[Image.Image],
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        image_features = []
        num_batches = ceil(len(images) / self._batch_size)
        if callback:
            callback(self, 0, num_batches, image_features)

        with ThreadPoolExecutor(self._batch_size) as executor:

            def process_one_image(image):
                image_path = Path(image)
                name = image_path.stem
                crop_box = None
                if isinstance(image, (str, Path)):
                    image = Image.open(image)
                    width, height = image.size
                    crop_box = (0, 0, width, round(height * 8 / 9))
                    image = image.crop(crop_box)

                observations = []
                raw_text = {}
                for language in ("eng", "vie"):
                    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, lang=language)
                    raw_text[language] = " ".join(data.get("text", []))
                    for index, text in enumerate(data.get("text", [])):
                        if not text or not text.strip():
                            continue
                        observations.append(
                            {
                                "text": text,
                                "language": language,
                                "confidence": data.get("conf", [""])[index],
                                "bbox": {
                                    "left": data["left"][index],
                                    "top": data["top"][index],
                                    "width": data["width"][index],
                                    "height": data["height"][index],
                                },
                            }
                        )

                res = normalize_text(raw_text["eng"] + " " + raw_text["vie"])

                return name, res, {
                    "frame_id": name,
                    "raw_text": raw_text,
                    "normalized_text": res,
                    "observations": observations,
                    "crop_box": crop_box,
                    "languages": ["eng", "vie"],
                }

            raw_records = []
            for b in range(num_batches):
                futures = []
                for image in images[b * self._batch_size : (b + 1) * self._batch_size]:
                    futures.append(executor.submit(process_one_image, image))

                for i, future in enumerate(futures):
                    name, data, raw_record = future.result()
                    image_features.append(np.array(data))
                    raw_records.append(raw_record)

                if callback:
                    callback(self, b + 1, num_batches, image_features)

        if len(images) > 0:
            video_id = Path(images[0]).parent.stem
            write_json_artifact(
                self._work_dir / constant.OCR_RAW_DIR / f"{video_id}.json",
                {
                    "artifact_version": "ocr-1",
                    "video_id": video_id,
                    "recognizer": "tesseract",
                    "languages": ["eng", "vie"],
                    "crop_rule": "top_eight_ninths",
                    "observations": sorted(raw_records, key=lambda item: int(item["frame_id"])),
                },
            )

        return np.array(image_features)

    def _normalize_text(self, text: str):
        return normalize_text(text)

    def get_text_features(self, texts: list[str] | str | np.ndarray, callback: Optional[Callable] = None) -> Any:
        return texts

    def to(self, device):
        pass
