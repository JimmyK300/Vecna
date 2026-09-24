# Hướng dẫn Tích hợp & Sử dụng YOLO11-seg cho Video Giao thông (Traffic Videos)

Tài liệu này hướng dẫn chi tiết cách sử dụng mô hình **YOLO11-seg** (`yolo11m-seg.pt`) được tích hợp đồng bộ vào hệ thống CLI chuẩn của `aic51`, tương tự như các mô hình `image_siglip2` và `qwen_vl`.

---

## 1. Tổng quan Kiến trúc

- **Mục đích:** Chuyên biệt trích xuất thông tin xe cộ, phân loại (car, bus, truck, motorcycle, van, suv, sedan), đếm số lượng, phân đoạn biên dạng (mask/polygon), và nhận diện màu sắc sơn xe chính xác cao cho **Camera Giao thông góc cao (High-angle Traffic Cameras)**.
- **Vị trí Weight:** `weights/yolo11m-seg.pt` (Đã tải sẵn 45 MB).
- **Module Backend:** `aic51/packages/analyse/features/yolo_traffic.py` (Đăng ký trong Factory dưới định danh `@FeatureExtractorFactory.register("yolo_traffic")`).
- **Đặc trưng xuất ra (Dual Output):**
  1. `features/<video_id>/<frame_id>/yolo_traffic.npy`: Vector đặc trưng 32 chiều được chuẩn hóa L2, tối ưu cho Milvus Vector Search / SCANN.
  2. `features/<video_id>/<frame_id>/yolo_traffic.json`: Toàn bộ metadata chi tiết (tọa độ BBox, Mask polygon, màu sắc từng xe, số lượng xe từng loại).

---

## 2. Cấu hình hệ thống (`config.yaml` & `workspace/config.yaml`)

Module đã được tự động thêm vào cả `config.yaml` và `workspace/config.yaml`:

```yaml
features:
  ...
  yolo_traffic:
    model: "yolo_traffic"
    arch_name: "yolo11m-seg"
    pretrained_model: "weights/yolo11m-seg.pt"
    analyse:
      batch_size: 16
      conf: 0.25
      min_box_area: 1800
    index:
      datatype: "FLOAT_VECTOR"
      dim: 32
      metric_type: "COSINE"
      index_type: "SCANN"
      params:
        nlist: 64

searcher:
  language_models:
    ...
    language_yolo_traffic:
      model: "yolo_traffic"
      pretrained_model: "weights/yolo11m-seg.pt"
      target:
        - yolo_traffic
```

---

## 3. Các lệnh CLI chuẩn (Workflow cho Đồng đội / Partners)

Khi đồng đội pull code về, quy trình chạy tương tự 100% như các tính năng trước đây:

### Bước 1: Thêm Video Giao thông và Trích xuất Keyframes
Sử dụng lệnh `aic51-cli add` với cờ `-k` (extract keyframes):

```bash
# Thêm 1 video giao thông cụ thể
python -m aic51.cli add path/to/traffic_video.mp4 -k

# Hoặc thêm toàn bộ thư mục video giao thông
python -m aic51.cli add path/to/traffic_folder -d -k
```
*Keyframe sẽ được lưu tự động tại `data/keyframes/<video_id>/<frame_id>.jpg`.*

---

### Bước 2: Chạy Phân tích Trích xuất Đặc trưng (Analyse)

#### Trường hợp A: Chỉ chạy YOLO11-seg cho Video Giao thông (Khuyên dùng)
Vì YOLO chỉ áp dụng cho camera giao thông, bạn có thể truyền cờ `--use-yolo` kết hợp với lọc video `--video`:

```bash
# Phân tích YOLO cho 1 video giao thông cụ thể
python -m aic51.cli analyse --use-yolo --video L21_V001

# Phân tích YOLO cho nhiều video giao thông
python -m aic51.cli analyse --use-yolo --video L21_V001 --video L21_V002
```

#### Trường hợp B: Chạy đồng thời YOLO cùng các mô hình Multimodal khác
Hệ thống cho phép kết hợp các cờ `--use-*` cùng lúc trong một phiên chạy:

```bash
python -m aic51.cli analyse --use-image-siglip --use-qwen-vl --use-yolo --video L21_V001
```

#### Trường hợp C: Ghi đè (Overwrite) lại các frame đã phân tích
```bash
python -m aic51.cli analyse --use-yolo --video L21_V001 -o
```

---

## 4. Cấu trúc Output & Dữ liệu Trích xuất

Sau khi phân tích, thư mục `features/<video_id>/<frame_id>/` sẽ chứa:

```
features/
└── L21_V001/
    ├── 000001/
    │   ├── image_siglip2_so400m-378.npy   # (nếu chạy siglip2)
    │   ├── qwen_vl.npy                    # (nếu chạy qwen_vl)
    │   ├── yolo_traffic.npy               # Vector 32 chiều cho Milvus
    │   └── yolo_traffic.json              # Chi tiết phát hiện đối tượng
    └── 000002/
        ├── ...
```

### Chi tiết tệp `yolo_traffic.json` / `yolo26x_seg.json`:
```json
{
  "video_id": "L21_V001",
  "frame_id": "000001",
  "car_count": 3,
  "bus_count": 0,
  "truck_count": 1,
  "motorcycle_count": 12,
  "total_cars": 4,
  "colors": [
    "trắng",
    "đỏ",
    "đen",
    "bạc/xám"
  ],
  "objects": [
    {
      "class_id": 2,
      "class_name": "car",
      "confidence": 0.892,
      "color": "trắng",
      "bbox": {
        "x1": 210.5,
        "y1": 340.2,
        "x2": 380.0,
        "y2": 470.1
      },
      "mask": {
        "polygon": [[215.0, 345.0], [375.0, 345.0], [378.0, 465.0], [210.5, 460.0]]
      },
      "subtype": "sedan"
    }
  ]
}
```

`color` được ước lượng cho `bicycle`, `car`, `motorcycle`, `bus` và
`truck`. Các lớp khác vẫn có trường `color` với giá trị `null`.

---

## 5. Quy chuẩn Vector 32 chiều (`yolo_traffic.npy`)

| Chiều | Ý nghĩa đại diện | Thang chuẩn hóa |
|---|---|---|
| `0` | Số lượng Ô tô con (Car) | `min(count / 10.0, 1.0)` |
| `1` | Số lượng Xe buýt (Bus) | `min(count / 5.0, 1.0)` |
| `2` | Số lượng Xe tải (Truck) | `min(count / 5.0, 1.0)` |
| `3` | Số lượng Xe máy (Motorcycle) | `min(count / 25.0, 1.0)` |
| `4` | Tổng số xe cơ giới lớn | `min(sum / 15.0, 1.0)` |
| `5 - 13` | Tần suất xuất hiện 9 dải màu (trắng, đen, bạc/xám, đỏ, xanh dương, vàng, cam, xanh lá, tím) | `min(count / 5.0, 1.0)` |
| `14 - 17` | Thuộc tính không gian (diện tích trung bình, diện tích lớn nhất, tọa độ trung tâm X, Y) | Chuẩn hóa theo độ phân giải frame |
| `18 - 20` | Dòng xe chi tiết (Van, SUV, Sedan) | `min(count / 5.0, 1.0)` |
| `21 - 31` | Dự phòng mở rộng (Reserved) | `0.0` |

*Toàn bộ vector sau khi tính toán được chuẩn hóa L2 (`norm = 1.0`) để tương thích trực tiếp với chỉ mục `COSINE` của Milvus.*
