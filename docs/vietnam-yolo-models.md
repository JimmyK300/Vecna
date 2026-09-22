# Danh Sách Các Model YOLO & Bộ Dữ Liệu Giao Thông Việt Nam

Tài liệu này tổng hợp các model YOLO đã được fine-tune chuyên biệt và các bộ dữ liệu chất lượng cao cho môi trường **Giao thông Việt Nam**, đặc biệt tối ưu cho dữ liệu camera đường phố, flycam, dashcam trong các bài toán **AI Challenge (AIC)** (tương tự tập dữ liệu trong `workspace_2`).

---

## 1. Model Nhận Diện Biển Báo Giao Thông Việt Nam (Traffic Signs)

Hệ thống biển báo Việt Nam tuân theo quy chuẩn **QCVN 41:2019/BGTVT**, khác biệt hoàn toàn với biển báo chuẩn phương Tây trong tập COCO.

| Model / Repository | Kiến trúc | Số lớp | Nguồn / Link | Đặc điểm & Đối tượng detect |
| :--- | :--- | :--- | :--- | :--- |
| **traffic-sign-detection-vietnam-yolo** | YOLO11s | 82 classes | [Hugging Face](https://huggingface.co/star092304/traffic-sign-detection-vietnam-yolo) | Đầy đủ 82 loại biển báo: cấm rẽ, cấm quay đầu, đường một chiều, giới hạn tốc độ, cấm dừng đỗ, biển hiệu lệnh, biển cảnh báo nguy hiểm... |
| **zalo_traffic_detection** | YOLOv5x / YOLOv8 | 7 nhóm chính | [GitHub (buiduchanh)](https://github.com/buiduchanh/zalo_traffic_detection) | Huấn luyện trên dataset Zalo AI Challenge Street View. Phân loại 7 nhóm biển: cấm, nguy hiểm, hiệu lệnh, tốc độ... |
| **VietNam_Traffic_sign_recognise** | YOLOv5s / YOLOv8s | 58 classes | [GitHub (Luantrannew)](https://github.com/Luantrannew/VietNam_Traffic_sign_recognise) | 58 loại biển báo phổ biến nhất trên đường phố đô thị Việt Nam. |
| **vietspeedyolo** | YOLOv8 | 2 classes (R420/R421) | [Hugging Face (NghiMe)](https://huggingface.co/datasets/NghiMe/vietspeedyolo) | Chuyên dụng nhận diện biển báo bắt đầu / hết khu đông dân cư (R.420 / R.421). |

#### Lệnh tải nhanh model từ Hugging Face:
```powershell
pip install huggingface_hub
huggingface-cli download star092304/traffic-sign-detection-vietnam-yolo best.pt --local-dir weights/traffic_signs_vn/
```

---

## 2. Model Nhận Diện Phương Tiện Giao Thông Việt Nam (Vehicles & Mixed Traffic)

Giao thông Việt Nam có đặc thù "hỗn hợp" (mixed traffic) với mật độ xe máy cực lớn, xe lôi, xe ba gác, xe ôm công nghệ, taxi nội địa.

| Model / Project | Kiến trúc | Nhãn đối tượng | Nguồn | Ứng dụng nổi bật |
| :--- | :--- | :--- | :--- | :--- |
| **highway-vehicle-detection** | YOLOv8m | 8 classes: `car`, `truck`, `bus`, `motorcycle`, `van`,... | [Hugging Face (vietnguyennn0705)](https://huggingface.co/vietnguyennn0705/highway-vehicle-detection) | Tối ưu cho phương tiện giao thông chạy tốc độ cao trên cao tốc & quốc lộ VN. |
| **Vehicle Vietnam - CanTho** | YOLOv8 | `motorbike`, `car`, `bus`, `truck` | [Roboflow Universe](https://universe.roboflow.com/vehicle/vehicle-vietnam-cantho-2gxc8) | Tối ưu mật độ xe máy dày đặc trong đô thị Việt Nam. |
| **CCTV Vietnam Traffic** | YOLOv8 / YOLOv11 | `motorcycle`, `car`, `heavy_truck`, `bus` | [Roboflow Universe](https://universe.roboflow.com/vehicle-qmmot/cctv-vietnam) | Huấn luyện trực tiếp từ camera giao thông ngã tư góc cao (rất tương đồng với camera trong AIC). |
| **AI-Traffic-Analysis** | YOLOv8 + ByteTrack + PP-OCR | Xe máy, ô tô, xe tải, người đi bộ | [GitHub (tungedng2710)](https://github.com/tungedng2710/AI-Traffic-Analysis) | Pipeline hoàn chỉnh cho bài toán camera giám sát giao thông Việt Nam. |

---

## 3. Model Nhận Diện Biển Số Xe Việt Nam (License Plate Recognition - ALPR)

Biển số xe Việt Nam gồm 2 dạng hình học (biển vuông 2 dòng và biển dài 1 dòng), cùng các màu sắc khác nhau (trắng: dân sự, vàng: dịch vụ, xanh: nhà nước).

| Model / Pipeline | Kiến trúc | Nguồn | Điểm mạnh |
| :--- | :--- | :--- | :--- |
| **Yolov8-Detect-VN-License-Plates** | YOLOv8 (detect biển) + EasyOCR | [GitHub (MagicXuanTung)](https://github.com/MagicXuanTung/Yolov8-Detect-Vietnamese-license-plates-and-characters) | Phát hiện chính xác vị trí biển số xe máy và ô tô, kèm module OCR đọc số. |
| **VNPlateRec** | YOLOv8 + PaddleOCR | [GitHub (NMThanh123)](https://github.com/NMThanh123/License-Plate-Recognition) | Độ chính xác cao với biển số bị mờ, chụp xiên góc từ camera ngã tư. |
| **Motorcycle License Plate** | YOLOv8 | [Roboflow](https://universe.roboflow.com/hanoi-university-of-industry/motorcycle-license-plate) | Tập trung phát hiện biển số xe máy Việt Nam. |

---

## 4. Model Open-Vocabulary (YOLO-World) - Sẵn Có Trong Dự Án

Trong thư mục gốc `e:\Projects\Vecna` đã có sẵn file checkpoint:
* **File:** `yolov8x-worldv2.pt` (hoặc `yolo11x-seg.pt`)
* **Khả năng:** Zero-shot Object Detection theo danh sách từ khóa văn bản tùy ý mà **không cần huấn luyện lại**.

### Mẫu mã code áp dụng cho giao thông Việt Nam:
```python
from ultralytics import YOLO

# Khởi tạo YOLO-World v2
model = YOLO("yolov8x-worldv2.pt")

# Đặt các lớp đặc thù cho giao thông Việt Nam
vietnam_traffic_classes = [
    "motorcycle",
    "delivery motorbike with cargo box",
    "scooter",
    "yellow bus",
    "green taxi",
    "pickup truck",
    "three-wheeler tricycle",
    "police motorbike",
    "ambulance",
    "vietnamese circular traffic sign",
    "vietnamese triangular traffic sign",
    "license plate"
]
model.set_classes(vietnam_traffic_classes)

# Dự đoán trên frame video của workspace_2
results = model("workspace_2/data/keyframes/N041-V001/0001.jpg")
results[0].show()
```

---

## 5. Danh Sách Bộ Dữ Liệu Giao Thông Việt Nam (YOLO Format)

| Bộ dữ liệu | Quy mô | Đối tượng | Nguồn tải |
| :--- | :--- | :--- | :--- |
| **Zalo AI Traffic Sign 2020** | >5.000 ảnh Street View | 7 phân nhóm biển báo | [Dataset Ninja](https://datasetninja.com/zalo-traffic-sign) / [Roboflow](https://universe.roboflow.com/zalo-ai/zalo-ai) |
| **UIT-ADrone** | 51 video flycam (~6.5h), 206k frames | Xe máy, ô tô, vi phạm làn, đi ngược chiều, chở hàng cồng kềnh | [UIT-Together Research](https://github.com/uit-together) |
| **UIT-VinaDeveS22** | Hàng ngàn frame ngã tư TP.HCM | Phương tiện hỗn hợp đô thị VN | UIT ĐHQG-HCM |
| **Da Nang Urban Traffic Dataset** | >23.000 ảnh | Xe máy, xe hơi, xe tải, xe buýt | SciOpen / IEEE Research (2024-2026) |
| **Vietnam Traffic Signs (VNTSD)** | ~4.500 ảnh | Biển cấm, biển hiệu lệnh, biển cảnh báo | [Hugging Face (thanhhiepvos)](https://huggingface.co/datasets/thanhhiepvos/vietnam_traffic_sign) |
| **Giao Thong Viet Nam (VKU)** | >1.000 ảnh | Biển báo & phương tiện | [Roboflow Universe](https://universe.roboflow.com/vku-jmcnd/giao-thong-viet-nam) |

---

## 6. Cấu Hình Tích Hợp Vào Vecna (`config.yaml`)

Để tích hợp model đã tải vào pipeline tìm kiếm và auto-crop của Vecna:

```yaml
# Trong config.yaml hoặc workspace_2/config.yaml
searcher:
  # YOLO Auto-Crop Processor
  yolo:
    enable: true
    # Trỏ đến model đã fine-tune (ví dụ biển báo hoặc vehicle):
    model_path: "weights/traffic_signs_vn/best.pt"
    # Hoặc sử dụng model open-vocabulary:
    # model_path: "yolov8x-worldv2.pt"
    conf_threshold: 0.25
    padding: 15
```
