# ĐẶC TẢ YÊU CẦU: MỞ VIDEO BẰNG MPC-HC TRỰC TIẾP TỪ Ổ ĐĨA TẠI ĐÚNG FRAME TRÊN WEB UI AIC26

## 1. Mục tiêu & Bối cảnh
- **Vấn đề hiện tại:** Trình duyệt load video dài (2 - 3 tiếng) qua HTTP range chunks (1MB) bị trễ và giật lag khi tua đến frame bất kỳ, kể cả khi video đã được nén.
- **Mục tiêu:** Cho phép người dùng click trên giao diện Web UI để kích hoạt trực tiếp phần mềm xem video MPC-HC (`E:\Apps\MPC-HC\mpc-hc64.exe`) trên máy Windows. MPC-HC sẽ đọc file trực tiếp từ ổ cứng (NVMe/SSD) và lập tức nhảy đến đúng thời điểm (mili-giây/frame) tương ứng, độ trễ < 0.5s.

---

## 2. Đặc tả phía Backend (FastAPI)

### Vị trí file cần chỉnh sửa:
1. `aic51-src/aic51/packages/webui/backend/core.py` (Gateway chính cổng 6900 mà browser gọi tới)
2. `aic51-src/aic51/packages/webui/backend/file.py` (File service)

### API Endpoint:
- **Phương thức:** `POST /api/video/open-mpc`
- **Request Body (JSON):**
```json
{
  "video_id": "S01-V002",
  "frame_id": "000030"
}
```

### Logic xử lý chống bug:
1. **Định vị file thực thi MPC-HC:**
   - Danh sách đường dẫn ưu tiên:
     - `E:\Apps\MPC-HC\mpc-hc64.exe` (Đường dẫn chính xác trên máy hiện tại)
     - `C:\Program Files\MPC-HC\mpc-hc64.exe`
     - `C:\Program Files (x86)\K-Lite Codec Pack\MPC-HC64\mpc-hc64.exe`
   - Nếu không tìm thấy, trả về lỗi 404: `{"status": "error", "message": "Không tìm thấy MPC-HC"}`.

2. **Tìm đường dẫn file video thật trên đĩa:**
   - Dùng hàm `_get_candidate_roots(video_id)` từ `aic51.packages.webui.backend.utils` để duyệt qua các thư mục (`workspace`, `workspace_2`, `data`, v.v.).
   - Kiểm tra file video tồn tại tại: `root / constant.VIDEO_DIR / f"{video_id}.mp4"` hoặc `root / "data/videos" / f"{video_id}.mp4"`.
   - Nếu không tìm thấy, trả về lỗi 404.

3. **Tính toán thời gian mili-giây chính xác từ frame_id:**
   - Parse `frame_num = int(str(frame_id).strip())`.
   - Lấy FPS thực tế của video qua hàm `get_fps(video_id)` (mặc định 25.0 nếu không có info).
   - Tính: `time_ms = max(0, int((frame_num / fps) * 1000))`.

4. **Khởi chạy tiến trình MPC-HC bất đồng bộ (Non-blocking Subprocess):**
   - Trên Windows, bắt buộc dùng cờ `DETACHED_PROCESS` và `CREATE_NEW_PROCESS_GROUP` để tách tiến trình độc lập với tiến trình FastAPI:
```python
import subprocess
import sys

creation_flags = 0
if sys.platform.startswith("win"):
    creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

subprocess.Popen(
    [str(mpc_path), str(video_path), "/start", str(time_ms)],
    creationflags=creation_flags,
    close_fds=True
)
```
   - Trả về ngay lập tức: `{"status": "ok", "video_id": video_id, "frame_id": frame_id, "time_ms": time_ms}`.

---

## 3. Đặc tả phía Frontend (React)

### Vị trí file cần chỉnh sửa:
1. `aic51-src/aic51/packages/webui/frontend/src/services/search.js`:
   Thêm hàm gọi API:
```javascript
export async function openInMpcHc(videoId, frameId) {
  const res = await fetch("/api/video/open-mpc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId, frame_id: String(frameId) }),
  });
  return await res.json();
}
```

2. `aic51-src/aic51/packages/webui/frontend/src/components/Frame.jsx`:
   - Thêm nút icon MPC-HC (icon màn hình Desktop / màn hình có chân màu tím) đặt ngay bên cạnh nút Play hiện tại.
   - Khi bấm, gọi `e.stopPropagation()` để không trigger chọn card, sau đó gọi `openInMpcHc(video_id, frame_id)`.
   - Nếu backend trả về lỗi, hiển thị thông báo alert hoặc toast ngắn gọn.

3. `aic51-src/aic51/packages/webui/frontend/src/components/VideoPlayer.jsx`:
   - Thêm nút phụ "Mở bằng MPC-HC" trên thanh điều khiển của modal player web, giúp chuyển sang MPC-HC bất cứ lúc nào.

---

## 4. Quy trình Build & Triển khai

1. Chạy lệnh build frontend tại:
```bash
cd E:\Projects\Vecna\aic51-src\aic51\packages\webui\frontend
npm run build
```
2. Đảm bảo thư mục `.web/dist` được cập nhật bundle mới nhất.
3. Khởi động lại backend server `core.py` (cổng 6900) để nạp endpoint mới.

---

## 5. Danh sách Test Cases chống Bug
- [x] **Test 1:** Bấm nút MPC trên card bất kỳ (ví dụ `S01-V002 / # 000030`), cửa sổ MPC-HC mở ra ngay tại giây thứ 1.0 (frame 30 / 30fps).
- [x] **Test 2:** Bấm nút MPC trên frame ở phút thứ 60, MPC-HC mở ngay lập tức mà không cần tải mạng.
- [x] **Test 3:** Chuỗi `frame_id` có số 0 ở đầu (`"000120"`) được xử lý chính xác thành số nguyên, không lỗi.
- [x] **Test 4:** Việc mở MPC-HC không gây đứng luồng FastAPI backend, người dùng tiếp tục thao tác bình thường.
- [x] **Test 5:** Nhấn liên tục nhiều frame khác nhau không gây crash hay đơ hệ thống.
