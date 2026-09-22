import os
import re

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from pathlib import Path
from queue import Queue
from threading import Thread
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
    def from_pretrained(source: str = "paddle_vietocr", *args, **kwargs) -> "OCR":
        source_lower = source.lower()
        if source_lower == "tesseract":
            return Tesseract(*args, **kwargs)
        elif source_lower in (
            "paddle_vietocr",
            "paddleocr_vietocr",
            "vietocr",
            "paddle_det_vietocr",
            "paddle_rec_vietocr",
            "paddleocr_vl",
            "paddleocr-vl",
            "paddleocr",
            "paddle",
            "hf",
            "huggingface",
            "paddlepaddle/paddleocr-vl-1.6",
        ):
            return PaddleVietOCR(*args, **kwargs)
        raise RuntimeError(f"OCR: source={source} is invalid")





class PaddleVietOCR(OCR):
    """Hybrid OCR combining PaddleOCR (Text Detection) and VietOCR (Text Recognition) with top-to-bottom sorting and padding."""

    def __init__(
        self,
        name: str = "ocr",
        pretrained_model: str = "vgg_transformer",
        det_lang: str = "vi",
        use_angle_cls: bool = False,
        pad_y: int = 6,
        pad_x: int = 4,
        min_box_size: int = 5,
        device: Optional[str] = None,
        batch_size: int = 1,
        work_dir: Path | str = ".",
        *args,
        **kwargs,
    ):
        self.name = name
        self.pretrained_model = pretrained_model
        self.det_lang = det_lang
        self.use_angle_cls = use_angle_cls
        self.pad_y = int(pad_y)
        self.pad_x = int(pad_x)
        self.min_box_size = int(min_box_size)
        self._batch_size = batch_size
        self.work_dir = Path(work_dir)
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self._last_evidence_payload = None

        import os
        import logging
        os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
        for log_name in ("ppocr", "paddle", "paddleocr"):
            l = logging.getLogger(log_name)
            l.setLevel(logging.ERROR)
            l.disabled = True
            l.propagate = False

        try:
            from paddleocr import PaddleOCR
            for log_name in ("ppocr", "paddle", "paddleocr"):
                l = logging.getLogger(log_name)
                l.setLevel(logging.ERROR)
                l.disabled = True
                l.propagate = False
        except ImportError as e:
            raise ImportError(
                "PaddleOCR is required for PaddleVietOCR. Please install paddleocr."
            ) from e

        try:
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor
        except ImportError as e:
            raise ImportError(
                "VietOCR is required for PaddleVietOCR. Please install vietocr."
            ) from e

        # 1. Khß╗ƒi tß║ío PaddleOCR (T├¼m khung - chß║íy CPU nhß║╣ nh├áng, chß╗æng lß╗ùi driver Windows GPU)
        self.det_model = PaddleOCR(
            use_angle_cls=self.use_angle_cls,
            lang=self.det_lang,
            show_log=False,
            use_gpu=False,
        )
        for log_name in ("ppocr", "paddle", "paddleocr"):
            l = logging.getLogger(log_name)
            l.setLevel(logging.ERROR)
            l.disabled = True
            l.propagate = False

        # 2. Khß╗ƒi tß║ío VietOCR (─Éß╗ìc chß╗» - chß║íy tr├¬n GPU cuda:0)
        config = Cfg.load_config_from_name(self.pretrained_model)
        config["cnn"]["pretrained"] = False
        config["device"] = self.device

        weights_path = self._ensure_vietocr_weights(self.pretrained_model, config.get("weights"))
        config["weights"] = str(weights_path)
        self.rec_model = Predictor(config)

    @staticmethod
    def _ensure_vietocr_weights(model_name: str, config_weights_url: Optional[str] = None) -> Path:
        import os
        import tempfile
        import requests

        filename = f"{model_name}.pth"
        if config_weights_url and config_weights_url.endswith(".pth"):
            filename = config_weights_url.split("/")[-1]

        target_file = Path(tempfile.gettempdir()) / filename

        def is_valid_torch_file(path: Path) -> bool:
            if not path.exists() or path.stat().st_size < 1_000_000:
                return False
            try:
                torch.load(str(path), map_location="cpu")
                return True
            except Exception:
                return False

        if is_valid_torch_file(target_file):
            return target_file

        if target_file.exists():
            try:
                target_file.unlink(missing_ok=True)
            except Exception:
                pass

        candidate_urls = []
        if config_weights_url and config_weights_url.startswith("http"):
            candidate_urls.append(config_weights_url)
        candidate_urls.extend([
            f"https://huggingface.co/bmd1905/vietocr/resolve/main/{filename}",
            f"https://vocr.vn/data/vietocr/{filename}",
        ])

        download_success = False
        for url in candidate_urls:
            try:
                with requests.get(url, stream=True, timeout=120) as r:
                    if r.status_code == 200:
                        temp_dest = target_file.with_suffix(".tmp")
                        with open(temp_dest, "wb") as f:
                            for chunk in r.iter_content(chunk_size=65536):
                                if chunk:
                                    f.write(chunk)
                        if is_valid_torch_file(temp_dest):
                            if target_file.exists():
                                target_file.unlink(missing_ok=True)
                            temp_dest.rename(target_file)
                            download_success = True
                            break
                        else:
                            temp_dest.unlink(missing_ok=True)
            except Exception:
                continue

        if not download_success or not is_valid_torch_file(target_file):
            raise RuntimeError(
                f"Failed to download or verify VietOCR weights for {model_name}. "
                f"Please check your internet connection or manually place {filename} at {target_file}"
            )
        return target_file

    def get_features(
        self,
        images: list[Path | str] | list[np.ndarray] | list[Image.Image],
        callback: Optional[Callable] = None,
        source_context: Optional[dict[str, Any]] = None,
    ) -> Any:
        import cv2

        source_context = getattr(self, "_vecna_source_context", source_context or {})
        provider_generation_id = getattr(
            self,
            "_vecna_provider_generation_id",
            stable_id(
                "prv",
                {
                    "extractor": self.name,
                    "source": "paddle_vietocr",
                    "pretrained_model": self.pretrained_model,
                    "det_lang": self.det_lang,
                    "pad_y": self.pad_y,
                    "pad_x": self.pad_x,
                },
            ),
        )

        num_batches = ceil(len(images) / self._batch_size)
        image_features = []
        evidence_records = []
        step = max(1, num_batches // 50)
        max_workers = min(8, max(1, os.cpu_count() or 4))

        for b in range(num_batches):
            batch_images = images[b * self._batch_size : (b + 1) * self._batch_size]

            def process_detection(item_tuple):
                img_idx, img_item = item_tuple
                input_path = None
                input_sha256 = None
                if isinstance(img_item, (Path, str)):
                    input_path = Path(img_item)
                    input_sha256 = (
                        file_sha256(input_path)
                        if input_path.exists()
                        else None
                    )
                    cv_img = cv2.imread(str(input_path))
                    if cv_img is None:
                        pil_open = Image.open(input_path).convert("RGB")
                        cv_img = cv2.cvtColor(np.array(pil_open), cv2.COLOR_RGB2BGR)
                elif isinstance(img_item, Image.Image):
                    cv_img = cv2.cvtColor(np.array(img_item.convert("RGB")), cv2.COLOR_RGB2BGR)
                elif isinstance(img_item, np.ndarray):
                    if img_item.ndim == 3 and img_item.shape[2] == 3:
                        cv_img = cv2.cvtColor(img_item, cv2.COLOR_RGB2BGR)
                    else:
                        cv_img = img_item
                else:
                    raise ValueError(f"Unsupported image type: {type(img_item)}")

                img_height, img_width = cv_img.shape[:2]
                crop_bottom = round(img_height * 9 / 10)
                cropped_img = cv_img[:crop_bottom, :]
                boxes_result = self.det_model.ocr(cropped_img, rec=False, cls=False)

                img_crops = []
                if boxes_result and boxes_result[0]:
                    sorted_boxes = sorted(
                        boxes_result[0],
                        key=lambda box: np.min(np.array(box), axis=0)[1],
                    )

                    for box_idx, box in enumerate(sorted_boxes):
                        pts = np.array(box, dtype=np.int32)
                        x_min, y_min = np.min(pts, axis=0)
                        x_max, y_max = np.max(pts, axis=0)

                        x_min_padded = max(0, int(x_min - self.pad_x))
                        y_min_padded = max(0, int(y_min - self.pad_y))
                        x_max_padded = min(img_width, int(x_max + self.pad_x))
                        y_max_padded = min(crop_bottom, int(y_max + self.pad_y))

                        cropped = cv_img[y_min_padded:y_max_padded, x_min_padded:x_max_padded]
                        if (
                            cropped.size == 0
                            or cropped.shape[0] < self.min_box_size
                            or cropped.shape[1] < self.min_box_size
                        ):
                            continue

                        pil_crop = Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
                        img_crops.append((box_idx, pts, [x_min_padded, y_min_padded, x_max_padded, y_max_padded], pil_crop))

                return (img_idx, input_path, input_sha256, img_width, img_height, crop_bottom, img_crops)

            # 1. Multi-threaded CPU detection pass across the batch
            if len(batch_images) > 1:
                with ThreadPoolExecutor(max_workers=min(max_workers, len(batch_images))) as executor:
                    det_results = list(executor.map(process_detection, enumerate(batch_images)))
            else:
                det_results = [process_detection((0, batch_images[0]))]

            # Sort back by original image index
            det_results.sort(key=lambda x: x[0])

            batch_meta = []
            all_crops = []
            crop_mapping = []

            for (img_idx, input_path, input_sha256, img_width, img_height, crop_bottom, img_crops) in det_results:
                batch_meta.append({
                    "input_path": input_path,
                    "input_sha256": input_sha256,
                    "img_width": img_width,
                    "img_height": img_height,
                    "crop_bottom": crop_bottom,
                    "observations": [],
                    "recognized_lines": [],
                })
                for (box_idx, pts, padded_box, pil_crop) in img_crops:
                    all_crops.append(pil_crop)
                    crop_mapping.append((img_idx, box_idx, pts, padded_box))

            # 2. Second pass: Batched VietOCR GPU recognition with torch.inference_mode()
            if all_crops:
                with torch.inference_mode():
                    if len(all_crops) == 1:
                        batch_texts = [self.rec_model.predict(all_crops[0])]
                    else:
                        batch_texts = self.rec_model.predict_batch(all_crops)
                for (img_idx, box_idx, pts, padded_box), text in zip(crop_mapping, batch_texts):
                    if text and text.strip():
                        clean_line = text.strip()
                        batch_meta[img_idx]["recognized_lines"].append(clean_line)
                        batch_meta[img_idx]["observations"].append(
                            {
                                "box_index": box_idx,
                                "box": [
                                    [int(p[0]), int(p[1])] for p in pts
                                ],
                                "padded_box": padded_box,
                                "text": clean_line,
                            }
                        )

            # 3. Third pass: Build normalized text and evidence records
            for meta in batch_meta:
                raw_text = " ".join(meta["recognized_lines"])
                normalized = self._normalize_text(raw_text)

                input_path = meta["input_path"]
                frame_id = (
                    input_path.stem
                    if input_path is not None
                    else f"frame_{len(image_features):06d}"
                )
                evidence_id = stable_id(
                    "ev_ocr_paddle_vietocr",
                    {
                        "provider_generation_id": provider_generation_id,
                        "source_id": source_context.get("source_id"),
                        "rendition_id": source_context.get("rendition_id"),
                        "frame_id": frame_id,
                        "input_image_sha256": meta["input_sha256"],
                        "normalized_text": normalized,
                        "raw_text": raw_text,
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
                    "input_image_sha256": meta["input_sha256"],
                    "image_size": {"width": meta["img_width"], "height": meta["img_height"]},
                    "preprocessing": {
                        "crop": {
                            "left": 0,
                            "top": 0,
                            "right": meta["img_width"],
                            "bottom": meta["crop_bottom"],
                        },
                        "model": self.pretrained_model,
                        "det_lang": self.det_lang,
                        "pad_y": self.pad_y,
                        "pad_x": self.pad_x,
                        "normalization": "strip+lower+collapse_whitespace",
                    },
                    "raw_text": raw_text,
                    "normalized_text": normalized,
                    "observations": meta["observations"],
                }
                image_features.append(np.array(normalized))
                evidence_records.append(evidence_record)

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
        self.device = device
        if hasattr(self, "rec_model") and self.rec_model is not None:
            self.rec_model.device = device
        return self


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
                crop_bottom = round(height * 9 / 10)
                cropped = image.crop((0, 0, width, crop_bottom))

                try:
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
                except pytesseract.TesseractNotFoundError as err:
                    raise RuntimeError(
                        "Tesseract OCR executable not found on system PATH.\n"
                        "To fix this, install Tesseract OCR on Windows (e.g. `winget install UB-Mannheim.TesseractOCR` "
                        "with Vietnamese traineddata), ensure 'tesseract.exe' is added to PATH, "
                        "or switch to `source: paddle_vietocr` in config.yaml."
                    ) from err

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
