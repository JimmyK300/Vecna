"""
YOLOProcessor — Bộ tiền xử lý tự động phát hiện và crop vật thể chính bằng YOLOv8.

Dựa trên logic auto-crop từ dự án caube (D:\\AIC_2026\\caube\\app.py, dòng 746-800)
nhưng sử dụng mô hình YOLO mạnh hơn (yolov8x hoặc yolov8x-worldv2) thay vì yolov8n.

Tham khảo khoa học:
  - Region-CLIP (Zhong et al., CVPR 2022): ROI cropping cải thiện 10-15% mAP/Recall
    cho Object-level Alignment với CLIP.
  - DenseCLIP (Rao et al., CVPR 2022): Spatial Isolation giúp Vision-Language models
    tập trung vào đối tượng thay vì bối cảnh.

Thuật toán Best Box Selection:
  Score(B) = 0.5 * Confidence + 0.3 * AreaNormalized + 0.2 * CenterScore
"""

from pathlib import Path
from typing import Optional, Tuple

import torch
from PIL import Image

from aic51.packages.logger import logger


class YOLOProcessor:
    """Processor tự động phát hiện và crop vật thể chính bằng YOLOv8/YOLO-World.

    Sử dụng trong pipeline tìm kiếm ảnh tương tự (Similar Search / Image Upload):
    ảnh query upload → YOLO detect → crop ROI → SigLIP/CLIP encode → Milvus search.

    YOLO chỉ chạy trên 1 ảnh query upload (không chạy trên kho dữ liệu),
    nếu có GPU có thể dùng model mạnh (yolov8x) mà không ảnh hưởng tốc độ đáng kể.
    """

    def __init__(
        self,
        model_path: str = "yolov8x.pt",
        device: torch.device = torch.device("cpu"),
        conf_threshold: float = 0.25,
        padding: int = 15,
        # Trọng số cho thuật toán chấm điểm Best Box Selection
        # (theo dự án caube: 0.5 * conf + 0.3 * area + 0.2 * center)
        weight_conf: float = 0.5,
        weight_area: float = 0.3,
        weight_center: float = 0.2,
    ):
        self._device = device
        self._conf_threshold = conf_threshold
        self._padding = padding
        self._weight_conf = weight_conf
        self._weight_area = weight_area
        self._weight_center = weight_center
        self._model = None

        # Resolve đường dẫn model
        abs_path = Path(model_path)
        if not abs_path.is_absolute():
            abs_path = Path.cwd() / model_path

        if abs_path.exists():
            try:
                from ultralytics import YOLO

                self._model = YOLO(str(abs_path))
                self._model.to(device)
                logger.info(
                    f"YOLOProcessor: Loaded model from {abs_path} on {device}"
                )
            except Exception as e:
                logger.error(f"YOLOProcessor: Failed to load model: {e}")
        else:
            logger.warning(f"YOLOProcessor: Model file not found at {abs_path}")

    @property
    def is_available(self) -> bool:
        """Kiểm tra xem YOLO model đã được tải thành công chưa."""
        return self._model is not None

    def auto_crop(
        self, image: Image.Image
    ) -> Tuple[Image.Image, Optional[dict]]:
        """Nhận PIL.Image, tự động detect và crop vật thể tối ưu nhất.

        Thuật toán Best Box Selection (theo dự án caube):
          Score(B) = w_conf * Confidence(B)
                   + w_area * AreaNormalized(B)
                   + w_center * CenterScore(B)

        Args:
            image: Ảnh PIL đầu vào (RGB).

        Returns:
            Tuple (cropped_image, metadata_dict).
        """
        if self._model is None:
            return image, None

        img_w, img_h = image.size
        img_cx, img_cy = img_w / 2.0, img_h / 2.0
        max_dist = ((img_w / 2) ** 2 + (img_h / 2) ** 2) ** 0.5

        try:
            with torch.no_grad():
                results = self._model(image, verbose=False, conf=self._conf_threshold)

            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                logger.info(
                    "YOLOProcessor: No objects detected, returning original image."
                )
                del results
                if self._device.type == "cuda":
                    torch.cuda.empty_cache()
                return image, None

            # --- Chiến lược chọn box: ưu tiên diện tích lớn gần trung tâm ---
            best_box = None
            best_score = -1.0

            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                area = (x2 - x1) * (y2 - y1)
                box_cx, box_cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0

                dist_to_center = (
                    (box_cx - img_cx) ** 2 + (box_cy - img_cy) ** 2
                ) ** 0.5
                center_score = (
                    1.0 - (dist_to_center / max_dist) if max_dist > 0 else 1.0
                )
                area_normalized = (
                    area / (img_w * img_h) if (img_w * img_h) > 0 else 0.0
                )

                combined_score = (
                    self._weight_conf * conf
                    + self._weight_area * area_normalized
                    + self._weight_center * center_score
                )

                if combined_score > best_score:
                    best_score = combined_score
                    best_box = box

            if best_box is not None:
                x1, y1, x2, y2 = best_box.xyxy[0].tolist()
                cls_id = int(best_box.cls[0])
                conf = float(best_box.conf[0])
                class_name = results[0].names.get(cls_id, f"class_{cls_id}")

                x1_crop = max(0, int(x1) - self._padding)
                y1_crop = max(0, int(y1) - self._padding)
                x2_crop = min(img_w, int(x2) + self._padding)
                y2_crop = min(img_h, int(y2) + self._padding)

                cropped_img = image.crop((x1_crop, y1_crop, x2_crop, y2_crop))

                meta = {
                    "class_name": class_name,
                    "confidence": round(conf, 4),
                    "bbox": [x1_crop, y1_crop, x2_crop, y2_crop],
                    "best_score": round(best_score, 4),
                }
                logger.info(
                    f"YOLOProcessor: Auto-cropped '{class_name}' "
                    f"(conf: {conf:.2f}, score: {best_score:.3f}) "
                    f"box: [{x1_crop},{y1_crop},{x2_crop},{y2_crop}]"
                )

                del results
                if self._device.type == "cuda":
                    torch.cuda.empty_cache()

                return cropped_img, meta
            else:
                logger.info(
                    "YOLOProcessor: No suitable box found, returning original image."
                )

            del results
            if self._device.type == "cuda":
                torch.cuda.empty_cache()

        except Exception as e:
            logger.error(f"YOLOProcessor: Error during auto_crop: {e}")

        return image, None

    def detect_all(self, image: Image.Image) -> list[dict]:
        """Detect tất cả vật thể trong ảnh, trả về danh sách metadata."""
        if self._model is None:
            return []

        try:
            with torch.no_grad():
                results = self._model(image, verbose=False, conf=self._conf_threshold)

            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                del results
                if self._device.type == "cuda":
                    torch.cuda.empty_cache()
                return []

            detections = []
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                class_name = results[0].names.get(cls_id, f"class_{cls_id}")

                detections.append(
                    {
                        "class_name": class_name,
                        "confidence": round(conf, 4),
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    }
                )

            del results
            if self._device.type == "cuda":
                torch.cuda.empty_cache()

            return detections

        except Exception as e:
            logger.error(f"YOLOProcessor: Error during detect_all: {e}")
            return []

    def to(self, device: str | torch.device):
        self._device = torch.device(device)
        if self._model is not None:
            self._model.to(self._device)
