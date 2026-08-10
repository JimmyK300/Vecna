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
from aic51.packages.utils.provenance import file_sha256, stable_id

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
        raise RuntimeError(f"OCR: source={source} is invalid")


class Tesseract(OCR):
    def __init__(
        self,
        name: str = "ocr",
        batch_size: int = 1,
        work_dir: Path | str = ".",
        *args,
        **kwargs,
    ):
        self.name = name
        self._batch_size = batch_size
        self._work_dir = Path(work_dir)
        self._last_evidence_payload = None

    @staticmethod
    def _observations(data: dict[str, list], language: str) -> list[dict[str, Any]]:
        observations = []
        texts = data.get("text", [])
        for i, raw_text in enumerate(texts):
            text = str(raw_text or "")
            if not text.strip():
                continue
            try:
                confidence = float(data.get("conf", [])[i])
            except (ValueError, TypeError, IndexError):
                confidence = None
            observations.append(
                {
                    "language": language,
                    "text": text,
                    "provider_native_confidence": confidence,
                    "region": {
                        "coordinate_system": "keyframe_pixels_top_left",
                        "left": int(data["left"][i]),
                        "top": int(data["top"][i]),
                        "width": int(data["width"][i]),
                        "height": int(data["height"][i]),
                    },
                    "tesseract_locator": {
                        "page_num": int(data["page_num"][i]),
                        "block_num": int(data["block_num"][i]),
                        "par_num": int(data["par_num"][i]),
                        "line_num": int(data["line_num"][i]),
                        "word_num": int(data["word_num"][i]),
                    },
                }
            )
        return observations

    def get_features(
        self,
        images: list[Path | str] | np.ndarray | torch.Tensor | list[Image.Image],
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        if len(images) == 0:
            self._last_evidence_payload = {
                "evidence_kind": "ocr",
                "provider_generation_id": getattr(
                    self,
                    "_vecna_provider_generation_id",
                    "unknown",
                ),
                "records": [],
            }
            return np.array([])

        image_features = []
        evidence_records = []
        num_batches = ceil(len(images) / self._batch_size)
        if callback:
            callback(self, 0, num_batches, image_features)

        source_context = getattr(self, "_vecna_source_context", {})
        provider_generation_id = getattr(
            self,
            "_vecna_provider_generation_id",
            "unknown",
        )

        with ThreadPoolExecutor(self._batch_size) as executor:

            def process_one_image(image_input):
                input_path = Path(image_input) if isinstance(image_input, (str, Path)) else None
                if input_path is not None:
                    image = Image.open(input_path)
                else:
                    image = image_input

                width, height = image.size
                crop_bottom = round(height * 8 / 9)
                cropped = image.crop((0, 0, width, crop_bottom))

                eng_data = pytesseract.image_to_data(
                    cropped,
                    output_type=pytesseract.Output.DICT,
                    lang="eng",
                )
                vie_data = pytesseract.image_to_data(
                    cropped,
                    output_type=pytesseract.Output.DICT,
                    lang="vie",
                )

                eng_observations = self._observations(eng_data, "eng")
                vie_observations = self._observations(vie_data, "vie")
                observations = eng_observations + vie_observations
                eng_raw = " ".join(x["text"] for x in eng_observations)
                vie_raw = " ".join(x["text"] for x in vie_observations)
                normalized = self._normalize_text(f"{eng_raw} {vie_raw}")

                frame_id = input_path.stem if input_path is not None else None
                input_sha256 = (
                    file_sha256(input_path)
                    if input_path is not None and input_path.exists()
                    else None
                )
                evidence_id = stable_id(
                    "ev_ocr",
                    {
                        "provider_generation_id": provider_generation_id,
                        "source_id": source_context.get("source_id"),
                        "rendition_id": source_context.get("rendition_id"),
                        "frame_id": frame_id,
                        "input_image_sha256": input_sha256,
                        "normalized_text": normalized,
                        "observations": observations,
                    },
                )
                evidence_record = {
                    "evidence_id": evidence_id,
                    "kind": "ocr",
                    "direct_or_generated": "direct",
                    "source_id": source_context.get("source_id"),
                    "rendition_id": source_context.get("rendition_id"),
                    "parent_frame_evidence_id": (
                        source_context.get("frame_evidence_map", {}).get(frame_id)
                        if frame_id is not None
                        else None
                    ),
                    "natural_locator": {
                        "kind": "frame_region_set",
                        "frame_id": frame_id,
                        "coordinate_system": "keyframe_pixels_top_left",
                    },
                    "input_image": str(input_path) if input_path is not None else None,
                    "input_image_sha256": input_sha256,
                    "image_size": {"width": width, "height": height},
                    "preprocessing": {
                        "crop": {
                            "left": 0,
                            "top": 0,
                            "right": width,
                            "bottom": crop_bottom,
                        },
                        "languages": ["eng", "vie"],
                        "normalization": "strip+lower+collapse_whitespace",
                    },
                    "raw_text_by_language": {"eng": eng_raw, "vie": vie_raw},
                    "normalized_text": normalized,
                    "observations": observations,
                }
                return normalized, evidence_record

            step = max(1, num_batches // 50)
            for b in range(num_batches):
                futures = [
                    executor.submit(process_one_image, image)
                    for image in images[b * self._batch_size : (b + 1) * self._batch_size]
                ]

                for future in futures:
                    normalized, record = future.result()
                    image_features.append(np.array(normalized))
                    evidence_records.append(record)

                if callback and ((b + 1) % step == 0 or (b + 1) == num_batches):
                    callback(self, b + 1, num_batches, image_features)

        self._last_evidence_payload = {
            "evidence_kind": "ocr",
            "provider_generation_id": provider_generation_id,
            "source_id": source_context.get("source_id"),
            "rendition_id": source_context.get("rendition_id"),
            "records": evidence_records,
            "legacy_projection": {
                "description": "normalized frame text remains in existing .npy output",
                "normalization": "strip+lower+collapse_whitespace",
            },
        }
        return np.array(image_features)

    def get_last_evidence_payload(self):
        return self._last_evidence_payload

    def _normalize_text(self, text: str):
        res = text.strip().lower()
        return re.sub(r"\s+", " ", res)

    def get_text_features(
        self,
        texts: list[str] | str | np.ndarray,
        callback: Optional[Callable] = None,
    ) -> Any:
        return texts

    def to(self, device):
        pass
