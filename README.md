# 🚀 VECNA / AIC51 - MULTIMODAL VIDEO KEYFRAME SEARCH ENGINE

Hệ thống tìm kiếm khung hình video đa thức (Multimodal Video Keyframe Search Engine) phục vụ cuộc thi AIC (AI Challenge). Hệ thống tích hợp các mô hình tiên tiến nhất: **CLIP (PE-Core-L-14-336)**, **SigLIP (ViT-SO400M-14-SigLIP-384)**, **Groq LLM Query Expander (gpt-oss-120b)**, và cơ sở dữ liệu vector **Milvus Standalone**.

---

## 🛠️ HƯỚNG DẪN KHỞI ĐỘNG HỆ THỐNG (QUICK START)

### 1. Yêu cầu Tiền đề (Prerequisites)
- **Python 3.11+**
- **Docker Desktop** (Đang chạy để nạp Milvus Vector Database)
- **Node.js 18+** & **npm**

### 2. Kích hoạt Môi trường & Khởi chạy Server
Mở Cửa sổ **PowerShell** tại thư mục gốc dự án:

```powershell
# 1. Kích hoạt Virtual Environment Python
.\.venv\Scripts\activate

# 2. Khởi chạy hệ thống AIC51 (Tự động nâng Milvus Docker & Web UI)
aic51-cli --dev serve
```

👉 Sau khi khởi chạy thành công, truy cập giao diện Web tại: **`http://localhost:6900`**

---

## 🔑 HƯỚNG DẪN CẤU HÌNH API KEY (GROQ LLM API KEY)

Tính năng **Sửa lỗi chính tả tự động & Sinh biến thể truy vấn (Jina HyDE / Paraphrase)** sử dụng mô hình LLM thông qua **Groq Cloud API**.

### 🔹 Cách 1: Đặt biến môi trường PowerShell (Khuyên dùng)
Trước khi chạy lệnh `aic51-cli --dev serve`, gõ lệnh đặt biến môi trường trong PowerShell:

```powershell
$env:GROQ_API_KEY="gsk_YOUR_GROQ_API_KEY_HERE"   # Thay gsk_... bằng Groq API Key cá nhân của bạn
```

### 🔹 Cách 2: Cấu hình trong tệp `config.yaml`
Mở tệp `config.yaml` tại thư mục gốc dự án và cập nhật mục `llm`:

```yaml
llm:
  enable: true
  provider: "groq"                      # groq, gemini, hoặc openai
  model_name: "openai/gpt-oss-120b"     # Mô hình 120B tham số trên Groq Cloud
  api_key: "YOUR_GROQ_API_KEY_HERE"     # Điền Groq API Key cá nhân của bạn vào đây
```

> ⚠️ **LƯU Ý BẢO MẬT GITHUB**: 
> Khi đẩy code (push) lên GitHub Repository public/private, GitHub sẽ tự động chặn nếu thấy chuỗi API Key cá nhân thực tế trong tệp tin. Do đó, hãy sử dụng biến môi trường `$env:GROQ_API_KEY` hoặc giữ `api_key: ""` trước khi `git push`.

---

## 🔥 TÍNH NĂNG NỔI BẬT & HƯỚNG DẪN SỬ DỤNG

### 1. Gợi ý Sửa lỗi Chính tả kiểu Google (Google-Style Spellcheck)
- Khi gõ từ tiếng Việt không dấu (ví dụ: `"con cho"` hoặc `"cô gái nau an"`), ô gõ chính **giữ nguyên văn bản người dùng**.
- Ngay bên dưới xuất hiện **Banner gợi ý kiểu Google**:
  > *Showing results for* **`"con chó"`**  
  > *Search instead for* `<button> "con cho" </button>`
- Nhấp vào từ đã sửa dấu để tự động thay thế văn bản trong ô nhập.

### 2. Mở rộng Truy vấn bằng LLM (Jina AI Expansion Variants)
- Nhấp nút **`Expand Query`** màu tím trên thanh công cụ để thả xuống 3 thẻ biến thể:
  1. **CORRECTED**: Sửa chính tả & chuẩn hóa ngữ nghĩa tiếng Việt.
  2. **HYDE**: Tự động sinh mô tả bối cảnh thị giác chi tiết (Visual Scene Generation) phục vụ tìm kiếm CLIP.
  3. **PARAPHRASE**: Diễn đạt lại câu truy vấn dưới dạng ngắn gọn.
- **Cuộn chuột dọc**: Mỗi ô biến thể hỗ trợ cuộn chuột nội bộ (`max-h-16 overflow-y-auto`), không làm tràn viền giao diện.
- **Click to Search & Auto Snap-Back**: Nhấp vào bất kỳ thẻ nào để tìm kiếm ngay lập tức. Thanh trượt ngăn cách giữa ô Query và danh sách Frames sẽ **tự động co rút ôm sát nội dung**, loại bỏ hoàn toàn khoảng trống thừa.

### 3. Đóng mở Cửa sổ Bộ lọc (Collapsible Filter Side Panels)
- Các nút bật/tắt nhanh trên thanh header: **`OCR/ASR: ON/OFF`** và **`Video Filters: ON/OFF`**.
- Nhấp nút **`✕`** trên từng khung side panel để thu gọn. Khi đóng bộ lọc, ô nhập tìm kiếm chính tự động giãn tràn 100% độ rộng.

### 4. Tìm kiếm Đa thức (Multimodal Fusion)
- Hỗ trợ kết hợp trọng số giữa **CLIP/SigLIP Vector Search**, **OCR Text Search** (chữ hiển thị trên màn hình), và **ASR Speech Search** (lời nói trong video).
- Lọc danh sách Video theo ID bao gồm (`Include Video IDs`) hoặc loại trừ (`Exclude Video IDs`).

---

## ⌨️ BẢNG PHÍM TẮT THAO TÁC NHANH (KEYBOARD SHORTCUTS)

| Phím tắt | Chức năng |
| :--- | :--- |
| **`/`** | Nhảy nhanh con trỏ vào ô nhập câu hỏi tìm kiếm chính. |
| **`Shift + ?`** | Nhảy nhanh đến Sidebar Trả lời / Submit kết quả. |
| **`Tab` / `Shift + Tab`** | Chuyển đổi con trỏ qua lại giữa các ô nhập Search, OCR và ASR. |
| **`Enter`** | Chạy tìm kiếm ngay lập tức (khi đang ở trong ô text). |
| **`ArrowUp (↑)` / `ArrowDown (↓)`** | Chuyển trang Kết quả (Trang Trước / Trang Sau). |
| **`Shift + 1` .. `Shift + 0`** | Mở trình phát Video ngay tại Keyframe tương ứng từ vị trí 1 đến 10. |

---

## 🏗️ CẤU TRÚC THƯ MỤC DỰ ÁN (PROJECT STRUCTURE)

```text
Vecna/
├── aic51-src/                     # Mã nguồn chính của thư viện aic51
│   └── aic51/
│       ├── packages/
│       │   ├── search/            # Searcher, LLMQueryExpander, Multimodal Fusion
│       │   ├── index/             # Milvus Database Integration & Schema
│       │   ├── analyse/           # Feature Extractors (CLIP, SigLIP, OCR, ASR)
│       │   └── webui/             # FastAPI Backend & React Frontend (Vite)
│       └── resources/             # Cấu hình mặc định & Docker Compose files
├── config.yaml                    # Tệp cấu hình gốc hệ thống
└── README.md                      # Hướng dẫn sử dụng dự án
```
