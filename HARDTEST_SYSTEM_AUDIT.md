# 📑 TÀI LIỆU TOÀN DIỆN: ĐÁNH GIÁ HỆ THỐNG VECNA (AIC51) & MASTER PROMPT HARD-TEST
## (Bao gồm Giám sát CPU, RAM, VRAM & Test Lặp Lại Chu Trình Khởi Động - Tắt - Serve Hệ Thống)

Tài liệu này tổng hợp toàn bộ kết quả phân tích cấu trúc hệ thống, kiểm kê tính năng, đánh giá nguy cơ quá tải CPU & rò rỉ RAM/VRAM, phân tích rủi ro kẹt cổng khi tắt/bật server nhiều lần, đồng thời cung cấp **Master Prompt** chuẩn cùng 2 công cụ kiểm thử tự động để giao nhiệm vụ cho AI Coding Agent tiến hành Hard-test toàn diện hệ thống Vecna trước khi thi đấu thực tế.

---

## MỤC LỤC
1. [Tổng quan Kiến trúc Hệ thống Vecna](#1-tổng-quan-kiến-trúc-hệ-thống-vecna)
2. [Bảng kiểm kê Tính năng & Trạng thái hoạt động](#2-bảng-kiểm-kê-tính-năng--trạng-thái-hoạt-động)
3. [Phân tích Nguy cơ CPU Spike & Rò rỉ RAM/VRAM](#3-phân-tích-nguy-cơ-cpu-spike--rò-rỉ-ramvram)
   - 3.1. Điểm nghẽn CPU & Chặn Event Loop
   - 3.2. Rò rỉ RAM Hệ thống & Milvus Docker
   - 3.3. Tràn VRAM GPU (CUDA Out of Memory)
   - 3.4. Quá tải RAM Trình duyệt (Browser DOM)
4. [Phân tích Rủi ro Chu trình Khởi động - Tắt - Restart Nhiều Lần](#4-phân-tích-rủi-ro-chu-trình-khởi-động---tắt---restart-nhiều-lần)
   - 4.1. Lỗi kẹt cổng Windows Socket (`WinError 10048`)
   - 4.2. Tiến trình ma (Zombie Subprocess: `node.exe` & Uvicorn Workers)
   - 4.3. Rò rỉ dư lượng VRAM qua các lần Restart
   - 4.4. Phục hồi sau khi bị tắt đột ngột (Ungraceful Shutdown)
5. [Mã nguồn 2 Công cụ Kiểm thử Tự động](#5-mã-nguồn-2-công-cụ-kiểm-thử-tự-động)
   - 5.1. Công cụ Giám sát Tài nguyên: `scripts/system_resource_monitor.py`
   - 5.2. Công cụ Test Lặp lại Khởi động - Tắt - Serve: `scripts/test_lifecycle_restarts.py`
6. [Master Prompt Giao việc cho Agent Hard-Test (Đầy đủ 7 bước)](#6-master-prompt-giao-việc-cho-agent-hard-test)
7. [Hướng dẫn Vận hành & Cấu hình An toàn](#7-hướng-dẫn-vận-hành--cấu-hình-an-toàn)

---

## 1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG VECNA

Hệ thống **Vecna / AIC51** là công cụ tìm kiếm video đa phương thức phục vụ các kỳ thi AI Challenge (AIC / VBS / Video Retrieval). Kiến trúc phân tán gồm 3 tầng chính:

```
                          [ Người dùng / Trình duyệt ]
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   Core Proxy (:6900)      │
                        │ - Vite Static Frontend    │
                        │ - Reverse Proxy & Balance │
                        │ - DRES Evaluator Proxy    │
                        └─────────────┬─────────────┘
                                      │
                   ┌──────────────────┴──────────────────┐
                   ▼                                     ▼
        ┌───────────────────────┐             ┌─────────────────────┐
        │ Search Backend (:1337)│             │ File Backend (:4200)│
        │ - Milvus Vector DB    │             │ - Stream Video 206  │
        │ - SigLIP2 + Qwen3-VL  │             │ - Keyframes / Thumb │
        │ - BM25 (OCR & ASR)    │             │ - Map-keyframes CSV │
        │ - Temporal DP & YOLO  │             │ - Transcript Parser │
        └───────────────────────┘             └─────────────────────┘
```

1. **Core Gateway (`:6900`)** (`aic51.packages.webui.backend.core`):
   - Đóng vai trò Reverse Proxy tập trung.
   - Phục vụ ứng dụng React tĩnh (`.web/dist`).
   - Định tuyến DRES Proxy (`/api/dres-proxy/...`) giúp vượt lỗi CORS và đồng bộ trạng thái bài thi từ máy chủ DRES.
   - Tự động thăm dò và đồng bộ danh sách `target_features` từ Search Server.

2. **Search Backend (`:1337`)** (`aic51.packages.webui.backend.search`):
   - Nạp các mô hình nhúng Text/Image: SigLIP2 (`ViT-SO400M-14-SigLIP2-378`), Qwen3-VL Embedding (2B).
   - Truy vấn song song Vector Cosine và BM25 Sparse Search (OCR/ASR).
   - Khử trùng lặp ảnh liên tiếp (Visual Shot Clustering / Deduplication) bằng SigLIP2.
   - Định tuyến theo bộ sưu tập: `workspace` (Batch 1: L, S, M) và `workspace2` (Batch 2: N).
   - Bộ mở rộng truy vấn ngữ nghĩa Groq LLM (`openai/gpt-oss-120b`).
   - Tìm kiếm chuỗi hành động theo thời gian (Temporal Dynamic Programming).
   - Bộ lọc quan hệ không gian YOLO (`ARRAY_CONTAINS`) và bộ lọc Camera Metadata.

3. **File Backend (`:4200`)** (`aic51.packages.webui.backend.file`):
   - Streaming video tốc độ cao qua giao thức HTTP 206 Partial Content (kích thước chunk 4MB).
   - Phục vụ Keyframes gốc và Thumbnails đã nén.
   - Parse tệp ánh xạ thời gian PTS `map-keyframes/*.csv`.
   - Đọc dữ liệu OCR từng frame (`.npy`) và tổng hợp câu thoại ASR thành transcript hoàn chỉnh.

---

## 2. BẢNG KIỂM KÊ TÍNH NĂNG & TRẠNG THÁI HOẠT ĐỘNG

| STT | Nhóm tính năng | Mô tả kỹ thuật | Trạng thái Code | Trạng thái Cấu hình | Đã Unit Test? | Nhận định & Khuyến nghị |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **1** | **Multimodal Dense Search** | Nhúng text qua SigLIP2 (1152-dim) & Qwen3-VL (2048-dim) truy vấn Milvus SCANN index. | ✅ Hoàn chỉnh | **BẬT** | ✅ Đầy đủ | Tính năng cốt lõi, hoạt động ổn định. |
| **2** | **Sparse BM25 Search** | Tìm kiếm từ khóa OCR và ASR qua inverted index TAAT Naive. | ✅ Hoàn chỉnh | **BẬT** | ✅ Đầy đủ | Hỗ trợ tìm biển số xe, tên quán, chữ trên áo, lời thoại. |
| **3** | **Exact Phrase Match** | Tìm chính xác cụm từ trong dấu `""`, regex ranh giới từ `(?<!\w)...(?!\w)`, tự động chuẩn hóa dấu tiếng Việt. | ✅ Hoàn chỉnh | **BẬT** | ✅ Đầy đủ | Rất hữu ích cho các câu hỏi yêu cầu khớp chính xác từ ngữ. |
| **4** | **Temporal DP Search** | Tìm chuỗi hành động `A -> B -> C` tuân thủ thứ tự thời gian, áp dụng hàm mục tiêu DP và phạt `max_interval`. | ✅ Hoàn chỉnh | **BẬT** | ✅ `test_temporal_online_dp.py` | Cần kiểm tra kỹ các trường hợp ranh giới (stage rỗng, timeout). |
| **5** | **Single Search Clustering** | Loại bỏ các frame trùng lặp thị giác ($gap \le 150$, $sim \ge 0.95$) bằng vector SigLIP2. | ✅ Hoàn chỉnh | **BẬT** | ✅ `test_single_search_clustering.py` | Giúp kết quả tìm kiếm đa dạng, không bị lấp đầy bởi 1 cảnh quay. |
| **6** | **YOLO Spatial Relations** | Lọc quan hệ không gian (`car left_of person`) & boost điểm 1.1x qua `ARRAY_CONTAINS`. | ✅ Hoàn chỉnh | ⚠️ **TẮT** ở `config.yaml` (`enable: false`) | ✅ `test_yolo26x_feature.py` | Chỉ dùng cho Batch 2 (N). Cần bật lại nếu đề thi yêu cầu quan hệ vật thể. |
| **7** | **Camera Scene Filter** | Lọc theo loại đường (`highway`, `urban`, `tunnel`) và ánh sáng (`day`, `night`, `rain`). | ✅ Hoàn chỉnh | **BẬT** (cho Batch 2) | ✅ `test_camera_metadata.py` | Giảm mạnh không gian tìm kiếm cho camera giao thông. |
| **8** | **Multi-Collection Routing** | Tự động hoặc thủ công phân luồng Batch 1 (L, S, M) vs Batch 2 (N). | ✅ Hoàn chỉnh | **BẬT** | ⚠️ Thiếu test phân luồng đồng thời | Cần test tải khi chuyển đổi nhanh giữa 2 collection. |
| **9** | **Groq LLM Query Expander** | Tự động sinh 3 biến thể ngữ nghĩa (HyDE, Keywords, Paraphrase) bằng `gpt-oss-120b`. | ✅ Hoàn chỉnh | ⚠️ **TẮT** ở `config.yaml` (`enable: false`) | ❌ Chưa có test | Cần kiểm tra hạn ngạch API key trước khi bật lại. |
| **10** | **BGE CrossEncoder Reranker** | Chấm điểm chéo lại top candidates bằng `bge-reranker-v2-m3`. | ✅ Hoàn chỉnh | ⚠️ **TẮT** / Bị comment trong config | ❌ Chưa có test | Tốn thêm ~1.5GB VRAM. Khuyến nghị chỉ bật nếu GPU $\ge 12\text{GB}$. |
| **11** | **Multi-tier Translation** | Dịch VI $\leftrightarrow$ EN: Chrome API $\rightarrow$ MyMemory $\rightarrow$ Google Scraper $\rightarrow$ Disk Cache. | ✅ Hoàn chỉnh | **BẬT** | ⚠️ 1 test fail do nâng cấp Tier | Cần sửa unit test mock cho khớp với cấu trúc 3 tầng mới. |
| **12** | **Dynamic Search Cancel** | Hủy truy vấn Milvus ngay khi người dùng gõ câu mới hoặc ngắt kết nối trình duyệt. | ✅ Hoàn chỉnh | **BẬT** | ✅ Đầy đủ | Tránh nghẽn thread pool backend khi người dùng gõ phím nhanh. |
| **13** | **DRES Submitter & Timer** | Kết nối máy chủ DRES v2, chống giật đồng hồ (anti-jitter), dựng chuỗi TRAKE, nộp bài. | ✅ Hoàn chỉnh | **BẬT** | ❌ Thiếu test giả lập máy chủ DRES | Đã tối ưu giao diện Modal 3 tầng không bị tràn màn hình. |
| **14** | **Map-Keyframes PTS Scrubbing** | Đồng bộ chính xác giữa thanh trượt video, PTS thời gian thực và frame ID dự thi. | ✅ Hoàn chỉnh | **BẬT** | ✅ Đầy đủ | Đảm bảo nộp đúng frame ID theo chuẩn BTC yêu cầu. |

---

## 3. PHÂN TÍCH NGUY CƠ CPU SPIKE & RÒ RỈ RAM/VRAM

### 3.1. Điểm nghẽn CPU & Hiện tượng Chặn Event Loop (CPU Spikes)
1. **Chiếm dụng 100% CPU do cấu hình `max_workers_ratio: 1.0`**:
   - Trong `config.yaml`, tham số `max_workers_ratio: 1.0` cho phép hệ thống sử dụng toàn bộ số nhân CPU có sẵn. Khi các tác vụ xử lý ma trận (ONNX, PyTorch, Milvus SCANN indexing, FAISS) kích hoạt đa luồng OpenMP, CPU có thể nhảy vọt lên 100% trong nhiều giây.
   - Hậu quả: Tiến trình Core Gateway (`:6900`) không nhận được CPU slice để chuyển tiếp request, dẫn đến giao diện người dùng bị đơ và xuất hiện lỗi `Connection Timeout`.
2. **Nghẽn Event Loop do hàm đồng bộ nặng trong FastAPI**:
   - Trong [`file.py`](file:///e:/Projects/Vecna/aic51-src/aic51/packages/webui/backend/file.py), hàm `_load_map_keyframes_data` mở file `.csv` và đọc từng dòng bằng Python thuần. Khi frontend gọi liên tục để đồng bộ thanh tua video, tiến trình chạy hoàn toàn trên CPU của main thread, chặn đứng các request stream ảnh/video khác.
   - Thuật toán Temporal DP `_best_ordered_frame_sequence` trong [`searcher.py`](file:///e:/Projects/Vecna/aic51-src/aic51/packages/search/searcher.py#L1508): Khi số lượng ứng viên lớn (ví dụ $k=200$ trên 3 stage liên tiếp), vòng lặp lồng duyệt $O(N \times M)$ tính điểm phạt thời gian hoàn toàn trên CPU.

### 3.2. Rò rỉ RAM Hệ thống & Milvus Docker (System Memory Leaks)
1. **Bộ nhớ đệm Transcript vô hạn (`_TRANSCRIPT_CACHE`)**:
   - Vị trí: [`file.py` dòng 248](file:///e:/Projects/Vecna/aic51-src/aic51/packages/webui/backend/file.py#L248)
   - Hiện trạng: Khai báo `_TRANSCRIPT_CACHE: dict[str, list] = {}`.
   - Vấn đề: Đây là một từ điển Python **không giới hạn dung lượng**. Trong quá trình thi đấu kéo dài 4-8 tiếng, mỗi video được người dùng mở xem transcript sẽ được giữ vĩnh viễn trong RAM. Với hàng trăm video, dung lượng RAM của tiến trình File Backend sẽ tăng tịnh tiến không bao giờ giảm.
   - **Khắc phục**: Thay thế bằng `BoundedLRUCache(maxsize=64)` hoặc xóa bớt phần tử cũ khi vượt ngưỡng.
2. **Milvus Vector Index Out Of Memory**:
   - Milvus Docker container nạp toàn bộ vector index (SCANN/IVF) và BM25 inverted index vào RAM.
   - Với hơn 200,000 keyframes của 2 batch, Milvus tiêu tốn từ 6GB đến 10GB RAM.
   - Nếu Docker Desktop trên Windows không được cấu hình file `.wslconfig` với dung lượng RAM tối thiểu 12GB - 16GB, hệ điều hành sẽ kích hoạt WSL OOM Killer tắt đột ngột container Milvus.

### 3.3. Nguy cơ Tràn VRAM GPU (CUDA Out Of Memory)
1. **Xung đột dung lượng nạp nhiều mô hình đồng thời**:
   - `SigLIP2` (SO400M-378): $\approx 1.8\text{ GB}$ VRAM.
   - `Qwen3-VL-Embedding-2B`: $\approx 4.5 - 5.0\text{ GB}$ VRAM.
   - `BGE CrossEncoder Reranker` (nếu bật): $\approx 1.5\text{ GB}$ VRAM.
   - `YOLO traffic detector` (nếu bật): $\approx 0.8\text{ GB}$ VRAM.
   - Tổng VRAM yêu cầu: **$\approx 8.6\text{ GB}$**.
   - **Cảnh báo**: Trên các card đồ họa phổ thông 8GB VRAM (RTX 3070, RTX 4060, laptop GPU), nếu bật đồng thời Reranker hoặc chạy đa luồng, hệ thống sẽ **bị văng lỗi `CUDA Out of Memory`**.
2. **Nguy cơ Multiprocessing**:
   - Trong `config.yaml`, cấu hình `backends.search.workers` **bắt buộc phải là 1**. Nếu nâng lên $\ge 2$, Python multiprocessing trên Windows sẽ tạo thêm các tiến trình con độc lập, mỗi tiến trình lại nạp một bản sao model vào GPU $\rightarrow$ VRAM nhân đôi $\rightarrow$ Crash ngay khi khởi động.
3. **Tần suất giải phóng bộ nhớ**:
   - Tại [`searcher.py` dòng 381-386](file:///e:/Projects/Vecna/aic51-src/aic51/packages/search/searcher.py#L381-L386), backend gọi `torch.cuda.empty_cache()` và `gc.collect()` sau mỗi truy vấn. Điều này triệt tiêu phân mảnh VRAM nhưng có thể làm tăng độ trễ truy vấn khoảng 30-50ms.

### 3.4. Quá tải RAM Trình duyệt (Browser Frontend)
1. **DOM Node Explosion**:
   - Giao diện `Search.jsx` nạp `CHUNK_SIZE = 300` frames. Nếu người dùng liên tục cuộn trang mà không giải phóng các frame phía trước (không dùng virtualized list như `react-window`), số lượng thẻ `<img>` và listener tăng vọt, tab trình duyệt có thể ngốn 3GB - 4GB RAM và bị đơ (Page Unresponsive).
2. **Bộ đệm Media HTML5 Video**:
   - Mỗi video mở xem được stream theo chunk 4MB. Nếu người dùng mở đóng liên tục 50 video mà trình duyệt không kịp dọn dẹp các `HTMLMediaElement`, bộ đệm video sẽ chiếm dụng hàng gigabyte RAM máy trạm.

---

## 4. PHÂN TÍCH RỦI RO CHU TRÌNH KHỞI ĐỘNG - TẮT - RESTART NHIỀU LẦN

Trong quá trình thi đấu hoặc vận hành thực tế, việc phải khởi động lại hệ thống (`aic51-cli serve`) do đổi cấu hình, đổi collection hoặc sửa lỗi là điều thường xuyên xảy ra. Nếu hệ thống không được thiết kế dọn dẹp tài nguyên triệt để, các vấn đề nghiêm trọng sau sẽ xuất hiện:

### 4.1. Lỗi kẹt cổng Windows Socket (`WinError 10048`)
- Khi người dùng bấm `Ctrl+C` hoặc lệnh tắt gửi đến `serve.py`:
  ```python
  def _stop_backend(self):
      for p in self._backend_processes:
          p.terminate() # <-- Không có p.join() chờ giải phóng socket!
  ```
- Trên Windows OS, cơ chế giải phóng TCP socket qua `terminate()` có độ trễ `TIME_WAIT`. Nếu ngay lập tức gõ lại `aic51-cli serve`, Uvicorn sẽ ném lỗi:
  ```
  [Errno 10048] error while attempting to bind on address ('0.0.0.0', 6900): 
  Only one usage of each socket address (protocol/network address/port) is normally permitted
  ```
  Lỗi này làm máy chủ không thể bật lại được, buộc người dùng phải mở Task Manager hoặc PowerShell để dò PID và `kill` thủ công.

### 4.2. Tiến trình ma (Zombie Subprocess)
- Ở chế độ `dev_mode: True`, frontend được khởi động bằng:
  ```python
  subprocess.Popen("npm run dev", shell=True, ...)
  ```
- Lệnh `shell=True` trên Windows tạo ra một tiến trình trung gian `cmd.exe`, sau đó `cmd.exe` mới tạo ra `node.exe`.
- Khi gọi `_stop_frontend() -> terminate()`, Python chỉ tắt tiến trình `cmd.exe`, còn tiến trình con **`node.exe` vẫn tiếp tục chạy ngầm (Orphaned Zombie Process)** và giữ cổng `5173`. Lần restart kế tiếp sẽ bị xung đột port Vite!

### 4.3. Rò rỉ dư lượng VRAM qua các lần Restart
- Khi tiến trình `Search` bị tắt không sạch (ungraceful termination), CUDA context của PyTorch trên Windows đôi khi không được thu hồi về hệ điều hành ngay lập tức.
- Khi server khởi động lại lần thứ 2 hoặc thứ 3, VRAM cơ sở đã bị chiếm dụng một phần. Lúc nạp lại `SigLIP2` và `Qwen3-VL`, dung lượng VRAM mới cộng dồn với dư lượng cũ sẽ dẫn đến **`CUDA Out of Memory` ngay trong bước khởi động**.

### 4.4. Phục hồi sau khi bị tắt đột ngột (Ungraceful Shutdown)
- Nếu server bị tắt đột ngột giữa lúc đang ghi file cache (ví dụ: `translation_cache.json` hoặc `_transcript_cache.json`), tệp JSON có thể bị lỗi cú pháp nửa chừng (`Unexpected EOF`). Lần khởi động tiếp theo khi đọc lại cache sẽ bị crash (`JSONDecodeError`).

---

## 5. MÃ NGUỒN 2 CÔNG CỤ KIỂM THỬ TỰ ĐỘNG

### 5.1. Công cụ Giám sát Tài nguyên Tự động: `scripts/system_resource_monitor.py`
Giám sát liên tục CPU (%), RAM (MB/GB), VRAM GPU (MB) của từng tiến trình Vecna và xuất ra CSV:

```python
# scripts/system_resource_monitor.py
import time, os, psutil, csv, sys
from datetime import datetime

TARGET_PORTS = [6900, 1337, 4200]
LOG_FILE = "system_resource_benchmark.csv"

def find_vecna_processes():
    pids = {}
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == psutil.CONN_LISTEN and conn.laddr.port in TARGET_PORTS:
                try:
                    pids[conn.laddr.port] = psutil.Process(conn.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    except Exception:
        pass
    return pids

def get_vram_usage():
    try:
        import torch
        if torch.cuda.is_available():
            return round(torch.cuda.memory_allocated() / (1024 ** 2), 2), round(torch.cuda.memory_reserved() / (1024 ** 2), 2)
    except Exception:
        pass
    return 0.0, 0.0

def monitor(interval=1.0, duration=600):
    print(f"[*] Starting Vecna System Resource Monitor (Logging to {LOG_FILE})...")
    with open(LOG_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Total_CPU_Percent", "Total_RAM_Used_GB", "Total_RAM_Percent",
                         "Core_6900_CPU", "Core_6900_RAM_MB", "Search_1337_CPU", "Search_1337_RAM_MB",
                         "File_4200_CPU", "File_4200_RAM_MB", "GPU_VRAM_Alloc_MB", "GPU_VRAM_Res_MB"])
        start_time = time.time()
        while time.time() - start_time < duration:
            procs = find_vecna_processes()
            total_cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total_cpu, round(mem.used / (1024 ** 3), 2), mem.percent]
            for port in TARGET_PORTS:
                proc = procs.get(port)
                if proc and proc.is_running():
                    try:
                        row.extend([proc.cpu_percent(interval=None), round(proc.memory_info().rss / (1024 ** 2), 2)])
                    except Exception: row.extend([0.0, 0.0])
                else: row.extend([0.0, 0.0])
            vram_alloc, vram_res = get_vram_usage()
            row.extend([vram_alloc, vram_res])
            writer.writerow(row); f.flush()
            print(f"[{row[0]}] Total CPU: {total_cpu:>5}% | RAM: {row[2]:>5}GB ({row[3]}%) | Search (:1337): {row[6]:>5}% / {row[7]:>7}MB | VRAM: {vram_alloc:>7}MB")
            time.sleep(interval)

if __name__ == "__main__":
    monitor(interval=1.0, duration=600)
```

### 5.2. Công cụ Test Lặp lại Khởi động - Tắt - Serve: `scripts/test_lifecycle_restarts.py`
Tự động bật server `aic51-cli serve`, chờ healthcheck 3 cổng, chạy test query, tắt server, quét kiểm tra cổng kẹt và rò rỉ VRAM, sau đó lặp lại $N$ chu kỳ:

```python
# scripts/test_lifecycle_restarts.py
import subprocess, time, sys, os, psutil, requests

TARGET_PORTS = [6900, 1337, 4200]
FRONTEND_PORT = 5173
PYTHON_EXEC = sys.executable

def check_ports_free():
    return [(c.laddr.port, c.pid) for c in psutil.net_connections(kind='inet') 
            if c.status == psutil.CONN_LISTEN and c.laddr.port in TARGET_PORTS + [FRONTEND_PORT]]

def kill_zombie_vecna():
    for port, pid in check_ports_free():
        try:
            p = psutil.Process(pid)
            print(f"[!] Force killing zombie process {p.name()} (PID: {pid}) on port {port}")
            p.kill()
        except Exception: pass
    time.sleep(1)

def get_vram_mb():
    try:
        import torch
        if torch.cuda.is_available(): return round(torch.cuda.memory_allocated() / (1024 ** 2), 2)
    except Exception: pass
    return 0.0

def wait_for_healthy(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r1 = requests.get("http://127.0.0.1:6900/api/collections", timeout=1)
            r2 = requests.get("http://127.0.0.1:1337/api/health", timeout=1)
            r3 = requests.get("http://127.0.0.1:4200/api/health", timeout=1)
            if r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 200: return True
        except Exception: pass
        time.sleep(1)
    return False

def run_lifecycle_cycles(total_cycles=5):
    print("=" * 80)
    print(f"[*] BẮT ĐẦU KIỂM THỬ VÒNG ĐỜI: {total_cycles} CHU KỲ KHỞI ĐỘNG - TẮT - RESTART")
    print("=" * 80)
    kill_zombie_vecna()
    results = []
    
    for cycle in range(1, total_cycles + 1):
        print(f"\n--- [CHU KỲ {cycle}/{total_cycles}] ---")
        vram_start = get_vram_mb()
        t_start = time.time()
        
        proc = subprocess.Popen([PYTHON_EXEC, "-m", "aic51.cli", "serve"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=os.getcwd())
        
        is_healthy = wait_for_healthy(timeout=45)
        startup_time = round(time.time() - t_start, 2)
        if not is_healthy:
            print(f"[-] THẤT BẠI: Server không thể sẵn sàng sau 45s tại chu kỳ {cycle}!")
            proc.terminate(); kill_zombie_vecna()
            results.append({"cycle": cycle, "status": "FAIL_STARTUP", "startup_time": startup_time})
            continue
        print(f"[+] Server sẵn sàng sau {startup_time}s")
        
        # Test query
        try:
            t0 = time.time()
            resp = requests.get("http://127.0.0.1:6900/api/search_multimodal?q=xe+hoi&limit=10", timeout=15)
            q_time = round(time.time() - t0, 2)
            q_ok = resp.status_code == 200
        except Exception as e:
            q_time = 0.0; q_ok = False
        print(f"[*] Test query ('xe hoi'): {'SUCCESS' if q_ok else 'FAIL'} trong {q_time}s")
        
        # Tắt server
        t_stop = time.time()
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill()
        shutdown_time = round(time.time() - t_stop, 2)
        print(f"[+] Tiến trình chính đã tắt sau {shutdown_time}s")
        time.sleep(2)
        
        # Kiểm tra zombie
        busy = check_ports_free()
        vram_end = get_vram_mb()
        if busy:
            print(f"[-] CẢNH BÁO ZOMBIE: Các cổng vẫn bị kẹt sau khi tắt: {busy}")
            kill_zombie_vecna()
        else:
            print(f"[+] TẤT CẢ CỔNG ĐÃ ĐƯỢC GIẢI PHÓNG SẠCH SẼ")
            
        results.append({
            "cycle": cycle,
            "status": "PASS" if is_healthy and q_ok and not busy else "FAIL",
            "startup_time": startup_time, "query_time": q_time, "shutdown_time": shutdown_time,
            "zombies": len(busy), "vram_delta": round(vram_end - vram_start, 2)
        })
        time.sleep(2)
        
    print("\n" + "=" * 80)
    print(f"{'Chu kỳ':<8} | {'Trạng thái':<10} | {'Bật (s)':<8} | {'Query (s)':<10} | {'Tắt (s)':<8} | {'Zombie':<8} | {'VRAM Delta'}")
    print("-" * 80)
    for r in results:
        print(f"{r['cycle']:<8} | {r['status']:<10} | {r.get('startup_time', '-'):<8} | {r.get('query_time', '-'):<10} | {r.get('shutdown_time', '-'):<8} | {r.get('zombies', '-'):<8} | {r.get('vram_delta', '-')} MB")
    print("=" * 80)

if __name__ == "__main__":
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    run_lifecycle_cycles(cycles)
```

---

## 6. MASTER PROMPT GIAO VIỆC CHO AGENT HARD-TEST

> **Hướng dẫn**: Sao chép toàn bộ khối markdown bên dưới và dán vào cửa sổ chat với AI Agent để bắt đầu quá trình kiểm thử tự động.

````markdown
# MISSION: COMPREHENSIVE HARD-TEST, STRESS TEST & AUDIT FOR VECNA (AIC51)
## (Bao gồm Giám sát CPU/RAM/VRAM & Test Lặp Lại Chu Trình Khởi Động - Tắt - Serve Hệ Thống)

Bạn là Chuyên gia Đảm bảo Chất lượng Hệ thống AI & SRE Performance Engineer cấp cao.
Nhiệm vụ của bạn là tiến hành HARD-TEST toàn bộ hệ thống "Vecna / AIC51 - Multimodal Video Retrieval Engine" tại workspace này để xác minh độ ổn định, kiểm tra tính năng thực tế, phát hiện rò rỉ RAM, phát hiện CPU spikes, và ĐẶC BIỆT KIỂM THỬ KHẢ NĂNG TẮT RỒI SERVE LẠI HỆ THỐNG NHIỀU LẦN (Lifecycle Restart Resilience) để xử lý triệt để các lỗi tiềm ẩn trước khi đưa vào thi đấu thực tế.

---

## 1. PHẠM VI & THÔNG TIN HỆ THỐNG
- **Workspace**: `e:\Projects\Vecna`
- **Môi trường Python**: `.\.venv\Scripts\python.exe`
- **Các thành phần Backend**:
  - Core Gateway / Reverse Proxy: Cổng `6900` (`aic51.packages.webui.backend.core`)
  - Search Engine (Milvus + AI Models): Cổng `1337` (`aic51.packages.webui.backend.search`)
  - Media & File Streaming: Cổng `4200` (`aic51.packages.webui.backend.file`)
- **Frontend**: React 18 Vite tại `aic51-src/aic51/packages/webui/frontend` (Build tĩnh tại `.web/dist`)
- **Vector DB**: Milvus Standalone (Docker Container)
- **Tệp cấu hình**: `config.yaml` và `FINALCONFIG.yaml`

---

## 2. NHIỆM VỤ CHI TIẾT (BẮT BUỘC THỰC HIỆN ĐỦ 7 BƯỚC)

### BƯỚC 1: KIỂM TRA ĐỘ PHỦ VÀ SỬA TOÀN BỘ UNIT TESTS HIỆN CÓ
1. Chạy toàn bộ test suite bằng lệnh:
   ```powershell
   .\.venv\Scripts\python -m unittest discover -s aic51-src/tests -p "test_*.py"
   ```
2. Phân tích nguyên nhân test case bị FAIL trong `test_translation.py` (`test_error_response_not_cached_and_fallbacks` bị sai lệch giữa Tier Chrome API và DeepTranslator Google Scraper). Hãy điều chỉnh mock hoặc logic test để **đạt 100% tests PASSED**.
3. Bổ sung các unit test còn thiếu cho:
   - Cơ chế ngắt tìm kiếm (`SearchCancelledException` & `cancel_search_endpoint`).
   - Mock endpoint `/api/expand_query` của Groq LLM khi không có API key hoặc khi API key bị lỗi.
   - Bounded LRU Cache eviction khi đạt ngưỡng `maxsize=20`.

---

### BƯỚC 2: THEO DÕI & STRESS-TEST CHUYÊN SÂU CPU & RAM (BENCHMARK & LEAK AUDIT)
Khởi chạy script `scripts/system_resource_monitor.py` hoặc một background thread (`psutil`) để ghi log mỗi giây 1 lần về: CPU tổng, CPU từng tiến trình (6900, 1337, 4200), RAM RSS (MB) từng tiến trình, RAM hệ thống, và VRAM GPU:
1. **Unbounded Cache Audit (`file.py`)**:
   - Kiểm tra `_TRANSCRIPT_CACHE`: Thử truy vấn liên tục `/api/video/transcript/{video_id}` của 100 video khác nhau. Đo xem RAM của tiến trình File Backend có phình to liên tục không.
   - Thay thế bằng `BoundedLRUCache` hoặc `@lru_cache(maxsize=64)` có cơ chế tự dọn dẹp khi vượt quá 64 video.
2. **I/O Pressure & CPU Spikes Test (`map-keyframes` CSV)**:
   - Gửi dồn dập 500 requests vào `/api/video/map-keyframes-around/{video_id}/{frame_id}`.
   - Đo CPU % và RAM spike do hàm đọc và parse CSV từ đĩa liên tục mà không có LRU memory cache. Áp dụng `@lru_cache(maxsize=128)` cho hàm `_load_map_keyframes_data`.
3. **Continuous Search Concurrency Loop & CPU Saturation**:
   - Gửi vòng lặp 200 truy vấn tìm kiếm ngẫu nhiên (Text đơn, Ngoặc kép exact phrase, Temporal query `A -> B -> C`, Filter YOLO, Filter Camera) với cờ `asyncio` đồng thời 5-10 requests.
   - Ghi lại đồ thị/log: 
     - **CPU (%)**: Kiểm tra xem CPU có bị ghim 100% làm nghẽn tiến trình Core Proxy không.
     - **RAM (RSS MB)**: Đo độ dốc tăng trưởng RAM ($\Delta\text{RAM}/\Delta t$) để phát hiện rò rỉ bộ nhớ. Xác nhận `torch.cuda.empty_cache()` và `gc.collect()` có thực sự thu hồi bộ nhớ sau mỗi truy vấn hay không.
4. **VRAM Estimation & Safety Check**:
   - Đo đạc thực tế lượng VRAM khi nạp đồng thời: `SigLIP2` + `Qwen3-VL` + `BGE Reranker`.
   - Cảnh báo nếu cấu hình hiện tại vượt quá 8GB VRAM và đề xuất cấu hình an toàn cho máy trạm thi đấu.

---

### BƯỚC 3: KIỂM THỬ TẤT CẢ CÁC TÍNH NĂNG THEO CASE BIÊN (EDGE CASES)
Tạo script giả lập HTTP client kiểm thử các tình huống nguy hiểm:
1. **Exact Phrase Edge Cases & Regex CPU Spikes**:
   - Query chứa ký tự đặc biệt, regex injection: `*`, `+`, `?`, `(`, `)`, `[`, `]`, `\`, `.*`.
   - Query rỗng, query toàn khoảng trắng, query 500 từ (kiểm tra CPU timeout).
   - Ngoặc kép lồng nhau, ngoặc kép mở không đóng (`"cô gái áo đỏ`).
   - Tiếng Việt có dấu vs không dấu: `"câu 3"` vs `"cau 3"`, `"VTV1"` vs `"VTV 1"`.
2. **Temporal Query Edge Cases & DP CPU Load**:
   - Query 1 stage, 2 stages, 5 stages liên tiếp.
   - Query temporal không tìm thấy kết quả ở stage đầu hoặc stage giữa.
   - `max_interval` cực nhỏ (0) và cực lớn (100,000). Đảm bảo thuật toán Dynamic Programming (DP) không bị exception `IndexError` hoặc vòng lặp vô tận gây 100% CPU.
3. **YOLO & Camera Filter Safety**:
   - Truy vấn sai định dạng key YOLO: `car:person:invalid_relation`, `:::`, chuỗi SQL injection.
   - Truy vấn YOLO relation trên `workspace` (Batch 1) $\rightarrow$ Phải trả về mã lỗi 400 rõ ràng, không làm crash backend.
   - Giá trị `road_type` hoặc `lighting` không hợp lệ.
4. **Race Condition & Cancel Search**:
   - Bắn 1 query nặng (temporal 3 stage), sau đó 50ms bắn ngay request `/api/cancel_search` hoặc ngắt kết nối HTTP client giữa chừng.
   - Xác nhận backend hủy bỏ tính toán ngay tức thì, CPU hạ nhiệt ngay và không bị treo luồng worker.

---

### BƯỚC 4: STRESS-TEST CHU TRÌNH KHỞI ĐỘNG - TẮT - SERVE LẠI HỆ THỐNG NHIỀU LẦN (REPEATED RESTART TEST)
Sử dụng script `scripts/test_lifecycle_restarts.py` để chạy lặp đi lặp lại tối thiểu **5 đến 10 chu kỳ liên tiếp**:
1. **Quy trình mỗi chu kỳ**:
   - Khởi động server (`aic51-cli serve`).
   - Chờ Healthcheck 3 cổng (6900, 1337, 4200) trả về `200 OK`. Đo thời gian khởi động (Startup latency).
   - Bắn test search request ("xe hoi") để kiểm tra Warm-up.
   - Gửi lệnh tắt server (SIGTERM/Ctrl+C). Đo thời gian tắt (Shutdown latency).
   - **Quét rà soát cổng mạng & Zombie Process**: Sử dụng `psutil` kiểm tra xem các cổng `6900`, `1337`, `4200`, `5173` có được giải phóng hoàn toàn không. Có tiến trình ma nào (`node.exe` hoặc Uvicorn child process) kẹt lại không?
   - **Kiểm tra VRAM thu hồi**: Đo xem lượng VRAM sau khi tắt có quay về baseline không hay bị rò rỉ dư lượng qua các chu kỳ.
   - Bật lại ngay lập tức (sau 2 giây nghỉ) để phát hiện lỗi `[Errno 10048] Address already in use`.
2. **Kiểm thử Ungraceful Shutdown (Tắt đột ngột)**:
   - Trong lúc đang xử lý truy vấn tìm kiếm nặng, kích hoạt lệnh ngắt đột ngột (`kill -9` hoặc dừng tiến trình cưỡng bức).
   - Khởi động lại hệ thống ngay sau đó và xác nhận:
     - Tệp cache JSON (`translation_cache.json`, `_transcript_cache.json`) có bị hỏng dữ liệu không?
     - Kết nối Milvus Client có bị treo connection pool không?
     - Hệ thống có tự phục hồi (Self-healing) thành công không?
3. **Cải tiến mã nguồn nếu phát hiện lỗi kẹt cổng**:
   - Cập nhật `_stop_backend` trong `serve.py` thêm lệnh `p.join(timeout=5)` và cưỡng bức kill nếu timeout.
   - Xử lý tắt triệt để cây tiến trình con của `npm run dev` trên Windows (`taskkill /F /T /PID`).

---

### BƯỚC 5: RÀ SOÁT CẤU HÌNH & TÍNH NĂNG "NGỦ QUÊN" (DEAD CODE / ORPHANED CONFIG)
Đối chiếu giữa `config.yaml`, `FINALCONFIG.yaml` và mã nguồn:
1. Xác định những tính năng đã code nhưng đang bị tắt (`enable: false`) hoặc comment out:
   - LLM Expander (`llm.enable` đang tắt hay bật? API Key còn hạn không?).
   - YOLO Auto-crop / Relations (`yolo.enable`).
   - BGE Reranker (`searcher.reranker.enable`).
2. Kiểm tra `build_segment_map.py`: Model trong script đang dùng `image_clip_pe_l_14_336`, trong khi `config.yaml` dùng `image_siglip2_so400m-378`. Có bị lệch model không? Có cần cập nhật để đồng bộ với cơ sở dữ liệu Milvus hiện hành?
3. Xác minh tính năng định tuyến bộ sưu tập `testcol1` / `workspace` và `testcol2` / `workspace2`: Kiểm tra xem frontend gửi alias có khớp 100% với tên collection thực tế trong Milvus không.

---

### BƯỚC 6: FRONTEND UX & DRES COMPETITION CLIENT AUDIT
1. **Kiểm tra DRES Integration**:
   - Rà soát các hàm trong `dres.js` và `DresSubmitPanel.jsx`: Logic chống giật timer (anti-jitter), logic parse thời gian giây/milliseconds, logic gửi TRAKE item.
   - Kiểm tra xem nếu DRES Server trả về HTTP 401 (hết session), 429 (rate limit) hoặc 502 (máy chủ ban tổ chức sập), giao diện có thông báo lỗi mượt mà không hay bị trắng trang (crash React).
2. **Kiểm tra DOM Memory Leak & Browser CPU**:
   - Kiểm tra `Search.jsx`: Khi kết quả trả về 300 keyframes, việc render các thẻ ảnh và sự kiện hover có gây tăng vọt CPU và ngốn RAM trình duyệt không.
   - Kiểm tra `VideoPlayer.jsx`: Khi bấm đổi video liên tục, thẻ `<video>` cũ có được dọn dẹp bộ nhớ đệm (buffer) không.

---

### BƯỚC 7: BÁO CÁO TỔNG KẾT & DANH SÁCH BẢN VÁ (FINAL AUDIT REPORT)
Sau khi hoàn thành, hãy tạo tài liệu báo cáo chi tiết bao gồm:
1. **Bảng tổng kết trạng thái**: Tính năng nào hoạt động tốt (PASS), tính năng nào có nguy cơ (WARN), tính năng nào bị lỗi (FAIL).
2. **Kết quả đo đạc CPU & RAM / VRAM**:
   - Biểu đồ hoặc bảng số liệu CPU peak, RAM baseline vs peak, VRAM tiêu thụ.
   - Đánh giá kết luận: Hệ thống có bị tràn RAM hay CPU throttle khi thi đấu cường độ cao không.
3. **Kết quả kiểm thử Restart vòng đời**:
   - Bảng tổng kết thời gian khởi động, thời gian tắt, số tiến trình zombie và độ chênh lệch VRAM qua 5-10 chu kỳ.
4. **Danh sách các bản vá đã thực hiện**: Diff hoặc giải thích chi tiết các đoạn mã đã sửa để tối ưu hệ thống (đặc biệt là sửa unbounded cache, thêm LRU, và cơ chế dọn dẹp tiến trình con khi tắt).
5. **Khuyến nghị cấu hình tối ưu** cho ngày thi đấu chính thức (Recommended `config.yaml`).
````

---

## 7. HƯỚNG DẪN VẬN HÀNH & CẤU HÌNH AN TOÀN

1. **Trước khi bắt đầu Hard-test**:
   - Khởi động Docker Desktop để Milvus sẵn sàng nhận kết nối.
   - Đảm bảo môi trường ảo Python đã được cài đầy đủ thư viện:
     ```powershell
     .\.venv\Scripts\activate
     pip install -e ./aic51-src
     ```
2. **Chạy các công cụ kiểm thử**:
   - Chạy kiểm thử tài nguyên:
     ```powershell
     .\.venv\Scripts\python scripts/system_resource_monitor.py
     ```
   - Chạy kiểm thử chu trình Khởi động - Tắt - Restart (5 chu kỳ):
     ```powershell
     .\.venv\Scripts\python scripts/test_lifecycle_restarts.py 5
     ```
3. **Giám sát tài nguyên trong quá trình thi đấu**:
   - Sử dụng lệnh PowerShell sau để theo dõi CPU và RAM các tiến trình Python:
     ```powershell
     Get-Process python | Select-Object Id, ProcessName, CPU, @{Name="RAM (MB)";Expression={[math]::round($_.WS/1MB,2)}}
     ```
   - Sử dụng `nvidia-smi -l 1` để quan sát VRAM GPU.
4. **Quy tắc an toàn phần cứng**:
   - **CPU**: Đặt `max_workers_ratio: 0.75` thay vì `1.0` để chừa lại 25% nhân CPU cho hệ điều hành và tiến trình Core Proxy, tránh hiện tượng nghẽn mạng nội bộ.
   - **VRAM < 8GB**: Chỉ nên bật `SigLIP2` + `BM25`. Tắt `Qwen3-VL` và tắt `Reranker`.
   - **VRAM 8GB - 12GB**: Bật `SigLIP2` + `Qwen3-VL` + `BM25`. Giữ `Reranker` ở trạng thái tắt.
   - **VRAM $\ge$ 16GB**: Bật toàn bộ tính năng (SigLIP2, Qwen3-VL, BGE Reranker, YOLO relations, WhisperX).
