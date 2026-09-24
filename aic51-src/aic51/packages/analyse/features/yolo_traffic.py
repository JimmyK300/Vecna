import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import numpy as np
import torch
from PIL import Image

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory

# Định nghĩa bảng màu nhận diện
COLOR_NAMES = [
    "trắng", "đen", "bạc/xám", "đỏ", "xanh dương", "vàng", "cam", "xanh lá", "tím"
]
COLOR_MAP = {c: i for i, c in enumerate(COLOR_NAMES)}
VEHICLE_CLASSES = {"bicycle", "car", "motorcycle", "bus", "truck"}


def extract_vehicle_color_traffic_cam(img_bgr, bbox):
    """
    Trích xuất màu sắc thân xe chuẩn xác cho Camera giao thông góc cao:
    - Tránh bẫy kính chắn gió phản chiếu bầu trời xanh (Windshield Sky Reflection).
    - Tránh bẫy vệt chói mặt trời trên nóc kính (Sun Glare).
    - Tránh bẫy lốp xe và bóng tối gầm xe (Undercarriage Shadow).
    """
    h_img, w_img = img_bgr.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w_img, x2), min(h_img, y2)

    bw = x2 - x1
    bh = y2 - y1
    if bw < 15 or bh < 15:
        return "không rõ"

    # Lấy mẫu vùng nắp capo / cốp / thân dưới (40% - 82% chiều cao, 15% - 85% chiều rộng)
    crop = img_bgr[y1:y2, x1:x2]
    paint_sample = crop[int(bh * 0.40):int(bh * 0.82), int(bw * 0.15):int(bw * 0.85)]
    if paint_sample.size == 0:
        paint_sample = crop

    hsv = cv2.cvtColor(paint_sample, cv2.COLOR_BGR2HSV)
    H = hsv[:, :, 0].flatten()
    S = hsv[:, :, 1].flatten()
    V = hsv[:, :, 2].flatten()

    B = paint_sample[:, :, 0].flatten()
    G = paint_sample[:, :, 1].flatten()
    R = paint_sample[:, :, 2].flatten()

    valid = (V >= 35) & ~((V > 250) & (S < 20))
    if np.sum(valid) < 20:
        return "đen" if np.mean(V < 35) > 0.5 else "không rõ"

    H_v = H[valid]
    S_v = S[valid]
    V_v = V[valid]
    B_v = B[valid]
    R_v = R[valid]

    mean_v = float(np.mean(V_v))
    median_v = float(np.median(V_v))
    mean_s = float(np.mean(S_v))
    p75_s = float(np.percentile(S_v, 75))

    b_minus_r = float(np.median(B_v) - np.median(R_v))
    r_minus_b = float(np.median(R_v) - np.median(B_v))

    # 1. Đỏ
    red_mask = ((H_v <= 12) | (H_v >= 155)) & (S_v >= 45) & (V_v >= 45)
    if np.sum(red_mask) / len(H_v) >= 0.22 or (r_minus_b >= 16 and np.sum(red_mask) / len(H_v) >= 0.14):
        return "đỏ"

    # 2. Vàng / Cam
    yellow_mask = (H_v >= 22) & (H_v <= 42) & (S_v >= 50) & (V_v >= 70)
    if np.sum(yellow_mask) / len(H_v) >= 0.25:
        return "vàng"
    orange_mask = (H_v >= 12) & (H_v < 22) & (S_v >= 50) & (V_v >= 65)
    if np.sum(orange_mask) / len(H_v) >= 0.25:
        return "cam"

    # 3. Xanh lá
    green_mask = (H_v >= 42) & (H_v <= 85) & (S_v >= 45) & (V_v >= 45)
    if np.sum(green_mask) / len(H_v) >= 0.25:
        return "xanh lá"

    # 4. Xanh dương
    blue_mask = (H_v >= 90) & (H_v <= 135) & (S_v >= 60) & (V_v >= 65)
    if (np.sum(blue_mask) / len(H_v) >= 0.30) and (b_minus_r >= 28) and (median_v >= 75):
        return "xanh dương"

    # 5. Trung tính: Đen, Trắng, Bạc/Xám
    if median_v < 78 or (mean_v < 82 and p75_s < 65):
        return "đen"
    if (median_v >= 125 and mean_s < 45) or mean_v >= 140:
        return "trắng"
    return "bạc/xám"


@FeatureExtractorFactory.register("yolo26x_seg")
@FeatureExtractorFactory.register("yolo_traffic")
class YoloTraffic(FeatureExtractor):
    """
    Feature Extractor chuẩn AIC51 tích hợp YOLO-seg cho Video Giao thông.
    Dùng chung output contract cho YOLO11-seg và YOLO26x-seg.
    - Phát hiện và phân đoạn: Xe ô tô, Xe buýt, Xe tải, Xe máy.
    - Trích xuất màu sắc sơn xe chính xác cao cho camera an ninh.
    - Xuất Vector đặc trưng 32-dim cho Milvus & Metadata JSON chi tiết.
    """

    @staticmethod
    def require_input() -> Any:
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(
        pretrained_model: str = "weights/yolo11m-seg.pt",
        *args,
        **kwargs,
    ) -> "YoloTraffic":
        return YoloTraffic(pretrained_model=pretrained_model, *args, **kwargs)

    def __init__(
        self,
        name: str = "yolo_traffic",
        pretrained_model: str = "weights/yolo11m-seg.pt",
        batch_size: int = 16,
        device: str | torch.device = "cuda:0",
        *args,
        **kwargs,
    ):
        from ultralytics import YOLO

        self.name = name
        self._batch_size = batch_size
        self._work_dir = Path(kwargs.get("work_dir", ".")).resolve()
        self._pretrained_model = str(pretrained_model)
        self._conf = float(kwargs.get("conf", 0.25))
        self._min_box_area = int(kwargs.get("min_box_area", 1800))

        # Tìm model weight: ưu tiên path chỉ định -> weights/ -> root -> auto download
        configured_path = Path(pretrained_model)
        candidates = [
            configured_path,
            self._work_dir / configured_path,
            self._work_dir / "weights" / configured_path.name,
            self._work_dir.parent / configured_path,
            self._work_dir.parent / "weights" / configured_path.name,
        ]
        model_path = next((path for path in candidates if path.exists()), None)
        if model_path is None:
            # A bare official model name lets Ultralytics download the weight.
            model_path = Path(configured_path.name)

        logger.info(f"YoloTraffic: Loading model from {model_path}...")
        self._model_path = str(model_path)
        self._model = YOLO(str(model_path))

        # Thiết lập device
        if isinstance(device, str):
            self._device = device
        elif isinstance(device, torch.device):
            self._device = f"cuda:{device.index}" if device.type == "cuda" and device.index is not None else device.type
        else:
            self._device = "0" if torch.cuda.is_available() else "cpu"

        super().__init__(name, batch_size, self._device)

    def runtime_semantics(self) -> dict[str, Any]:
        return {
            "pretrained_model": self._pretrained_model,
            "model_file": Path(self._model_path).name,
            "confidence": self._conf,
            "min_box_area": self._min_box_area,
            "vector_schema": "traffic-32-v1",
        }

    def to(self, device: str | torch.device):
        if isinstance(device, torch.device):
            self._device = f"cuda:{device.index}" if device.type == "cuda" and device.index is not None else device.type
        else:
            self._device = str(device)
        return self

    def get_features(
        self,
        images: list[Path | str] | np.ndarray | torch.Tensor | list[Image.Image],
        callback: Optional[Callable] = None,
    ) -> np.ndarray:
        if len(images) == 0:
            return np.zeros((0, 32), dtype=np.float32)

        # Chuyển đổi danh sách đường dẫn ảnh
        image_paths = [str(p) for p in images]
        total_images = len(image_paths)
        features_list = []

        for i in range(0, total_images, self._batch_size):
            batch_paths = image_paths[i : i + self._batch_size]
            results = self._model.predict(
                source=batch_paths,
                conf=self._conf,
                device=self._device,
                verbose=False,
            )

            for img_p, res in zip(batch_paths, results):
                p_obj = Path(img_p)
                video_id = p_obj.parent.name
                frame_id = p_obj.stem

                img_bgr = None

                car_count = 0
                bus_count = 0
                truck_count = 0
                motorcycle_count = 0
                van_count = 0
                suv_count = 0
                sedan_count = 0

                color_counts = Counter()
                detected_objects = []
                car_areas = []
                car_centers_x = []
                car_centers_y = []

                if res.boxes is not None and len(res.boxes) > 0:
                    boxes = res.boxes
                    masks = res.masks
                    has_masks = masks is not None and len(masks.xy) > 0

                    for b_idx, box in enumerate(boxes):
                        cls_id = int(box.cls[0])
                        cls_name = self._model.names[cls_id]
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = [round(float(v), 1) for v in box.xyxy[0].tolist()]
                        area = (x2 - x1) * (y2 - y1)

                        poly_pts = []
                        if has_masks and b_idx < len(masks.xy):
                            poly = masks.xy[b_idx]
                            if len(poly) >= 3:
                                poly_pts = [
                                    [round(float(pt[0]), 1), round(float(pt[1]), 1)]
                                    for pt in poly
                                ]

                        # Ước lượng màu cho phương tiện; object khác vẫn có
                        # trường color=null để mọi record cùng một schema.
                        obj_color = None
                        if cls_name in VEHICLE_CLASSES:
                            if img_bgr is None:
                                img_bgr = cv2.imread(img_p)
                            if img_bgr is not None:
                                obj_color = extract_vehicle_color_traffic_cam(
                                    img_bgr,
                                    [x1, y1, x2, y2],
                                )
                                if obj_color in COLOR_MAP:
                                    color_counts[obj_color] += 1

                        subtype = None

                        if cls_name == "motorcycle":
                            motorcycle_count += 1
                        elif cls_name in ["car", "bus", "truck"]:
                            # Bỏ qua xe kích thước quá bé ở đường chân trời
                            if area >= self._min_box_area:
                                if cls_name == "car":
                                    car_count += 1
                                elif cls_name == "bus":
                                    bus_count += 1
                                elif cls_name == "truck":
                                    truck_count += 1

                                # Ước lượng phân loại chi tiết (Subtype)
                                aspect_ratio = (y2 - y1) / max(1, (x2 - x1))
                                if area > 12000 or (aspect_ratio > 1.1 and area > 7000):
                                    subtype = "van"
                                    van_count += 1
                                elif aspect_ratio > 0.85:
                                    subtype = "suv"
                                    suv_count += 1
                                else:
                                    subtype = "sedan"
                                    sedan_count += 1

                                cx = (x1 + x2) / 2.0
                                cy = (y1 + y2) / 2.0
                                car_areas.append(area)
                                car_centers_x.append(cx)
                                car_centers_y.append(cy)

                        detected_object = {
                            "class_id": cls_id,
                            "class_name": cls_name,
                            "confidence": round(conf, 5),
                            "color": obj_color,
                            "bbox": {
                                "x1": x1,
                                "y1": y1,
                                "x2": x2,
                                "y2": y2,
                            },
                            "mask": {"polygon": poly_pts},
                        }
                        if subtype is not None:
                            detected_object["subtype"] = subtype
                        detected_objects.append(detected_object)

                # Xây dựng vector 32 chiều
                vec = np.zeros(32, dtype=np.float32)
                vec[0] = min(car_count / 10.0, 1.0)
                vec[1] = min(bus_count / 5.0, 1.0)
                vec[2] = min(truck_count / 5.0, 1.0)
                vec[3] = min(motorcycle_count / 25.0, 1.0)
                vec[4] = min((car_count + bus_count + truck_count) / 15.0, 1.0)

                # Dải màu (Dim 5-13)
                for c_name, c_idx in COLOR_MAP.items():
                    vec[5 + c_idx] = min(color_counts[c_name] / 5.0, 1.0)

                # Thuộc tính không gian (Dim 14-17)
                if car_areas:
                    vec[14] = min(float(np.mean(car_areas)) / 25000.0, 1.0)
                    vec[15] = min(float(np.max(car_areas)) / 50000.0, 1.0)
                    vec[16] = float(np.mean(car_centers_x)) / 1280.0
                    vec[17] = float(np.mean(car_centers_y)) / 720.0

                # Dòng xe (Dim 18-20)
                vec[18] = min(van_count / 5.0, 1.0)
                vec[19] = min(suv_count / 5.0, 1.0)
                vec[20] = min(sedan_count / 5.0, 1.0)

                # Chuẩn hóa L2 vector
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                features_list.append(vec)

                # Lưu đồng thời metadata JSON chi tiết vào thư mục features/<video_id>/<frame_id>/
                out_dir = self._work_dir / constant.FEATURE_DIR / video_id / frame_id
                out_dir.mkdir(parents=True, exist_ok=True)
                json_path = out_dir / f"{self.name}.json"
                meta_payload = {
                    "video_id": video_id,
                    "frame_id": frame_id,
                    "feature_name": self.name,
                    "model": Path(self._pretrained_model).name,
                    "car_count": car_count,
                    "bus_count": bus_count,
                    "truck_count": truck_count,
                    "motorcycle_count": motorcycle_count,
                    "total_cars": car_count + bus_count + truck_count,
                    "colors": list(color_counts.elements()),
                    "objects": detected_objects,
                }
                with open(json_path, "w", encoding="utf-8") as f_json:
                    json.dump(meta_payload, f_json, ensure_ascii=False, indent=2)

            if callback:
                callback(self, min(i + self._batch_size, total_images), total_images, features_list)

        return np.vstack(features_list) if features_list else np.zeros((0, 32), dtype=np.float32)

    def get_text_features(
        self,
        texts: list[str] | str | np.ndarray,
        callback: Optional[Callable] = None,
    ) -> Any:
        """Chuyển đổi câu truy vấn văn bản sang vector 32 chiều tương thích."""
        if isinstance(texts, str):
            texts = [texts]

        query_vectors = []
        for text in texts:
            vec = np.zeros(32, dtype=np.float32)
            t_clean = text.lower()

            # Phân tích số lượng
            m_count = re.search(r"\b(\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\b", t_clean)
            num_val = 1
            if m_count:
                c_map = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10}
                val_str = m_count.group(1)
                num_val = int(val_str) if val_str.isdigit() else c_map.get(val_str, 1)

            # Lớp xe
            if any(k in t_clean for k in ["ô tô", "oto", "car", "xe hơi"]):
                vec[0] = min(num_val / 10.0, 1.0)
                vec[4] = min(num_val / 15.0, 1.0)
            if any(k in t_clean for k in ["buýt", "bus"]):
                vec[1] = min(num_val / 5.0, 1.0)
            if any(k in t_clean for k in ["tải", "truck"]):
                vec[2] = min(num_val / 5.0, 1.0)
            if any(k in t_clean for k in ["xe máy", "mô tô", "motorcycle"]):
                vec[3] = min(num_val / 25.0, 1.0)

            # Phân loại chi tiết
            if any(k in t_clean for k in ["van", "carnival", "transit", "7 chỗ"]):
                vec[18] = min(num_val / 5.0, 1.0)
            if any(k in t_clean for k in ["suv", "gầm cao", "cx5", "fortuner"]):
                vec[19] = min(num_val / 5.0, 1.0)
            if any(k in t_clean for k in ["sedan", "4 chỗ"]):
                vec[20] = min(num_val / 5.0, 1.0)

            # Màu sắc
            for c_name, c_idx in COLOR_MAP.items():
                if c_name in t_clean:
                    vec[5 + c_idx] = 1.0

            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            query_vectors.append(vec)

        return np.vstack(query_vectors)
