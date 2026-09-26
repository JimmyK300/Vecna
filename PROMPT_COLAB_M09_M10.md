# Prompt Cho Claude: Tạo Colab Pro+ Pipeline Chạy Lại M09 & M10 Cho Vecna / AIC51

Dưới đây là toàn bộ nội dung prompt hoàn chỉnh để bạn copy và gửi cho Claude:

---

```markdown
Bạn là chuyên gia AI / MLOps cấp cao hỗ trợ dự án thi đấu AI Challenge (AIC 2026).
Tôi cần bạn phân tích repository công khai của tôi trên GitHub:
👉 GitHub Repo: https://github.com/JimmyK300/Vecna (nhánh main)

### BỐI CẢNH & MỤC TIÊU:
Tôi cần chạy lại toàn bộ quy trình tiền xử lý dữ liệu và trích xuất đặc trưng (feature extraction) cho 2 batch video tin tức:
- M09: https://aic-data.ledo.io.vn/Videos_M09.zip
- M10: https://aic-data.ledo.io.vn/Videos_M10.zip

Hãy viết một script Jupyter Notebook hoàn chỉnh (.ipynb) được tối ưu riêng cho môi trường **Google Colab Pro+ (GPU A100 / L4 / High-RAM)** để thực hiện toàn bộ pipeline từ tải video thô đến xuất kết quả lên Google Drive.

---

### YÊU CẦU QUY TRÌNH (PIPELINE CHI TIẾT):

#### 1. Khởi tạo môi trường & Dependencies:
- Mount Google Drive để lưu kết quả cuối cùng (`/content/drive/MyDrive/...`).
- Cài đặt hệ thống: `aria2` (để tải đa luồng cực nhanh), `ffmpeg`, `unzip`.
- Clone repo `https://github.com/JimmyK300/Vecna.git` và cài đặt CLI nội bộ từ source:
  ```bash
  cd /content/Vecna/aic51-src && pip install -e .
  ```
- Cài đặt đầy đủ các thư viện mô hình cần thiết:
  - OpenCLIP / SigLIP 2: `open_clip_torch`, `timm`, `sentence-transformers`
  - Qwen-VL: `transformers`, `accelerate`
  - OCR tiếng Việt: `paddlepaddle-gpu` (hoặc bản tương thích CUDA), `paddleocr`, `vietocr`
  - ASR âm thanh: `whisperx`, `faster-whisper`, `ctranslate2`, `pyannote.audio`
- Khởi tạo thư mục làm việc `/content/workspace` bằng `aic51-cli init` và copy file `config.yaml` từ repo sang.

#### 2. Tải và giải nén Video:
- Sử dụng `aria2c -x 16 -s 16` tải song song 2 file:
  - `https://aic-data.ledo.io.vn/Videos_M09.zip`
  - `https://aic-data.ledo.io.vn/Videos_M10.zip`
- Giải nén video ra thư mục tạm `/content/raw_videos/`.
- Xóa ngay file `.zip` sau khi giải nén để giải phóng dung lượng đĩa Colab.

#### 3. Trích xuất Keyframes, Thumbnails và Audio bằng `aic51-cli add`:
- Chạy lệnh `aic51-cli add <thư_mục_video> -d -k -a` để:
  - Trích xuất keyframe (`-k`) vào `data/keyframes/` (dựa trên I-frame và `max_scene_length` trong `config.yaml`).
  - Tự động sinh `data/thumbnails/` đồng bộ 100% với keyframes.
  - Tách audio (`-a`) sang `data/audio/*.wav` để phục vụ ASR.
  - Sinh metadata `data/video_info/*.json`.
- Sau khi add xong, xóa các video thô nặng trong `/content/raw_videos/` để tiết kiệm SSD.

#### 4. Trích xuất Đa phương thái (Feature Extraction) theo đúng thứ tự:
Chạy trích xuất tuần tự qua `aic51-cli analyse -m <tên_feature>` (chuẩn theo cấu hình trong `config.yaml`):
1. **Qwen-VL Embedding**: `aic51-cli analyse -m qwen_vl`
2. **SigLIP 2**: `aic51-cli analyse -m image_siglip2_so400m-378`
3. **OCR**: `aic51-cli analyse -m ocr`
4. **ASR (WhisperX)**: `aic51-cli analyse -m asr`

#### 5. Kiểm tra Đối soát tính toàn vẹn (Verification):
- Viết 1 đoạn script Python tự động kiểm tra:
  - Đảm bảo toàn bộ frame của M09 và M10 đều có đủ **4/4 file**: `qwen_vl.npy`, `image_siglip2_so400m-378.npy`, `ocr.npy`, `asr.npy`.
  - Đảm bảo danh sách ảnh trong `data/thumbnails/` khớp chính xác 1-1 với các folder frame trong `features/`.

#### 6. Nén và Xuất lên Google Drive:
- Nén ra đúng **2 file ZIP duy nhất** đưa thẳng vào Google Drive:
  1. `features_M09_M10.zip`: Chứa toàn bộ thư mục `features/` của các video M09 và M10.
  2. `thumbnails_M09_M10.zip`: Chứa toàn bộ thư mục `data/thumbnails/` của các video M09 và M10.
- **LƯU Ý QUAN TRỌNG**: **KHÔNG NÉN** thư mục `data/keyframes/` (để tránh lãng phí dung lượng Drive và thời gian nén).

---

### YÊU CẦU ĐẶC BIỆT VỀ LOGGING & THEO DÕI TIẾN TRÌNH:
- Toàn bộ các bước (Tải video, Giải nén, Add keyframes/audio, Từng model trích xuất, Nén zip, Upload Drive) đều phải được bọc trong một hàm đo thời gian rõ ràng:
  - In ra timestamp bắt đầu và kết thúc theo định dạng: `[YYYY-MM-DD HH:MM:SS]`.
  - In thời gian thực thi (Elapsed time: ... phút ... giây).
  - In dung lượng RAM, dung lượng đĩa trống (`shutil.disk_usage`), và VRAM GPU (`nvidia-smi`) trước và sau mỗi bước nặng.
- Có cơ chế flush log liên tục (`flush=True`) để không bị nuốt log trên Colab.
- Code phải sạch, có chú thích rõ ràng từng Cell để người dùng chỉ cần nhấn "Run All" là hoàn thành từ đầu đến cuối mà không bị lỗi thiếu dependencies hay tràn ổ đĩa.
```
