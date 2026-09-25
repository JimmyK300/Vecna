# 📑 TÀI LIỆU KỸ THUẬT: ĐỒNG BỘ DRES API, SỬA LỖI TIMER & TỐI ƯU UX MODAL

Tài liệu này lưu lại chi tiết toàn bộ các thay đổi kiến trúc, mã nguồn, nguyên nhân lỗi và giải pháp kỹ thuật đã triển khai trong hệ thống tích hợp máy chủ thi DRES (Direct Retrieval Evaluation Server) của VECNA / AIC51.

---

## 1. Danh sách các tệp thay đổi

1. **[`dres.js`](file:///e:/AI_Challenge/Vecna/aic51-src/aic51/packages/webui/frontend/src/services/dres.js)**:
   * Sửa lỗi toán học hàm `parseSecondsFromDres`: Không chia nhầm số giây cho 1000.
   * Cung cấp hàm định dạng chuẩn DRES Viewer `formatDresTime`: Hiển thị `hh:mm:ss` khi $\ge 3600\text{s}$, và `mm:ss` khi $< 3600\text{s}$.
   * Mở rộng hàm `getLiveEvaluationContext`: Truy vấn đồng thời `/api/v2/evaluation/info/list` để nạp đầy đủ danh sách `taskTemplates`.

2. **[`DresSubmitPanel.jsx`](file:///e:/AI_Challenge/Vecna/aic51-src/aic51/packages/webui/frontend/src/components/DresSubmitPanel.jsx)**:
   * Tối ưu `setInterval` đếm lùi timer: Tách rời vòng lặp đếm lùi khỏi dependency re-render từng giây để chống giật/rách nhịp đếm.
   * Cơ chế chống nhảy số (Anti-jitter): Chỉ đồng bộ lại `taskRemainingSec` từ server poll khi độ lệch thời gian $> 2$ giây.
   * Chuẩn hóa hiển thị chuỗi TRAKE preview: Loại bỏ khoảng trắng thừa giữa các frame ID.
   * Phát sự kiện `dres_eval_changed` và lắng nghe sự kiện `storage` để đồng bộ 2 chiều với VideoPlayer.

3. **[`VideoPlayer.jsx`](file:///e:/AI_Challenge/Vecna/aic51-src/aic51/packages/webui/frontend/src/components/VideoPlayer.jsx)**:
   * Xử lý phím `ESC`: Khi popup DRES đang mở, nhấn ESC chỉ đóng popup DRES, không đóng VideoPlayer.
   * Xử lý click ra ngoài (Backdrop click): Bấm vào nền tối bên ngoài chỉ tắt popup DRES, không tắt VideoPlayer.
   * Tái cấu trúc giao diện Modal DRES thành 3 tầng: **Sticky Header - Scrollable Body - Sticky Footer**:
     * Header & Footer chứa nút `Nộp ngay` ghim cố định ở đáy, không bao giờ bị tràn hay khuất khỏi màn hình.
     * Thân modal có `max-h-[90vh]` và `overflow-y-auto` cuộn độc lập mượt mà.
   * Tự động tải thông tin Evaluation ngầm khi mount component (Silent Pre-fetch) để dữ liệu luôn sẵn sàng ngay trước khi mở modal.
   * Đồng bộ TRAKE format với `quickPayload.formattedText`, hỗ trợ nút `+ Thêm #{activeFrameNum}` và `📋 Lấy frame đã lưu`.

4. **Thư mục Build & Deploy**:
   * Thư mục nguồn build: `aic51-src/aic51/packages/webui/frontend/dist/`
   * Thư mục phục vụ FastAPI: `.web/dist/` (`index.html`, `assets/index-gkQMehFa.js`, `assets/index-BnUmYX3L.css`)

---

## 2. Chi tiết các vấn đề & Giải pháp kỹ thuật

### A. Lỗi hiển thị sai thời gian (4:14 thay vì 71:28:42) và liên tục bị reset về ~5 phút

#### 1. Phân tích nguyên nhân gốc rễ (Root Cause Analysis)
* **Thực tế trên DRES Server**: Bài thi thử nghiệm `trake-test` có thời lượng 72 giờ ($\approx 259.200\text{ giây}$). Tại thời điểm kiểm tra, thời gian còn lại là **71 giờ 28 phút 42 giây** = **257.322 giây**.
* **Chuẩn API DRES v2**:
  * Trường `timeLeft` trong `EvaluationState` trả về số nguyên biểu thị số giây còn lại của câu thi đang diễn ra.
  * Trường `duration` trong `TaskTemplate` cũng trả về số giây của câu thi.
* **Mã nguồn bị lỗi trước đó**:
  ```javascript
  // LỖI: Nhầm lẫn rằng số > 1000 là milliseconds và chia cho 1000
  export function parseSecondsFromDres(val) {
    if (val === null || val === undefined || isNaN(val)) return null;
    const num = Number(val);
    if (num < 0) return null;
    if (num === 0) return 0;
    return num > 1000 ? Math.round(num / 1000) : Math.round(num); // <-- BUG
  }
  ```
* **Hậu quả**:
  * Khi `val = 257322` ($> 1000$), hàm thực hiện chia:
    $$\frac{257.322}{1.000} = 257,322\text{ giây} \approx 257\text{ giây} = \mathbf{4\text{ phút } 17\text{ giây}}$$
  * Sau vài giây đếm lùi, thời gian hiển thị thành `4:14`.
  * Cứ sau mỗi 8 giây khi background sync tự động gọi API DRES, server trả về thời gian thực $\sim 257.314\text{s}$, hàm lại tiếp tục chia cho 1000 ra $\sim 257\text{s} \rightarrow$ khiến đồng hồ **bị reset liên tục về mốc ~4-5 phút**.

#### 2. Giải pháp khắc phục
* Cập nhật `parseSecondsFromDres`: Giữ nguyên giá trị giây từ DRES. Chỉ chia cho 1000 nếu là timestamp dạng epoch milliseconds ($> 100.000.000$):
  ```javascript
  export function parseSecondsFromDres(val) {
    if (val === null || val === undefined || isNaN(val)) return null;
    const num = Number(val);
    if (num < 0) return null; // -1: không có task chạy
    if (num === 0) return 0;
    if (num > 100000000) {
      return Math.round(num / 1000);
    }
    return Math.round(num);
  }
  ```
* Cập nhật hàm định dạng thời gian `formatDresTime`:
  ```javascript
  export function formatDresTime(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds)) return "--:--";
    const s = Math.max(0, Math.round(Number(seconds)));
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    if (hrs > 0) {
      return `${hrs}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  ```
* **Kết quả**: $257.322\text{ giây} \rightarrow \mathbf{71:28:42}$, khớp 100% từng giây với DRES Viewer.

---

### B. Cơ chế đếm lùi mượt mà & Chống giật nhịp (Anti-Jitter)

#### 1. Vấn đề
* Trước đây, `useEffect` đặt `[taskRemainingSec]` vào dependency array. Cứ sau mỗi 1 giây khi số giây giảm, React hủy interval cũ và tạo interval mới $\rightarrow$ gây tốn tài nguyên và có thể bị trôi nhịp (clock drift).
* Khi background sync chạy mỗi 8 giây, nếu server trả về số giây chênh lệch 1 giây do độ trễ mạng (latency), đồng hồ cục bộ sẽ bị nhảy giật.

#### 2. Giải pháp
* **Tách rời vòng lặp Interval**: Chỉ lắng nghe cờ boolean `taskRemainingSec > 0`. Bên trong interval sử dụng functional state update `prev => prev - 1`:
  ```javascript
  useEffect(() => {
    const isRunning = taskRemainingSec !== null && taskRemainingSec > 0;
    if (!isRunning) {
      if (countdownIntervalRef.current) {
        clearInterval(countdownIntervalRef.current);
        countdownIntervalRef.current = null;
      }
      return;
    }

    if (!countdownIntervalRef.current) {
      countdownIntervalRef.current = setInterval(() => {
        setTaskRemainingSec((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(countdownIntervalRef.current);
            countdownIntervalRef.current = null;
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
  }, [taskRemainingSec > 0]);
  ```
* **Kiểm tra ngưỡng giật (Threshold check)**: Chỉ cập nhật lại `taskRemainingSec` từ server nếu chênh lệch $> 2$ giây:
  ```javascript
  setTaskRemainingSec((prev) => {
    if (sec === null) return null;
    if (prev === null || Math.abs(prev - sec) > 2) {
      return Math.max(0, sec);
    }
    return prev;
  });
  ```

---

### C. Độc lập & Đồng bộ 2 chiều (Two-Way Evaluation Sync)

#### 1. Yêu cầu kiến trúc
* `DresSubmitPanel` và `VideoPlayer` phải hoạt động độc lập: Nếu một trong hai không mở, bên còn lại vẫn gọi API DRES bình thường.
* Khi người dùng thay đổi Evaluation ID ở giao diện này, giao diện kia phải tự động chuyển theo.

#### 2. Cơ chế triển khai
* Sử dụng kết hợp **`CustomEvent('dres_eval_changed')`** (đồng bộ tức thì trong cùng 1 tab) và **`storage` event** (đồng bộ xuyên tab trình duyệt):
  ```javascript
  // Khi người dùng chọn Evaluation mới:
  localStorage.setItem(DRES_EVAL_KEY, evalId);
  window.dispatchEvent(new CustomEvent("dres_eval_changed", { detail: { evalId } }));
  ```
* Trong `VideoPlayer.jsx`:
  * Lắng nghe sự kiện vô điều kiện (kể cả khi modal DRES đang đóng) để cập nhật state ngầm.
  * Khi component mount, tự động gọi `refreshLiveTaskInfo(true)` ngầm nếu đã có `DRES_SESSION_KEY`.

---

### D. Chuẩn hóa định dạng TRAKE

* **Cấu trúc chuỗi định dạng**:
  $$\text{TR-}<\text{VIDEO\_ID}>-<\text{FRAME}_1,\text{FRAME}_2,...>$$
* **Ví dụ**: `TR-M10_V027-14489,18827`
* **Payload JSON gửi đi**:
  ```json
  {
    "answerSets": [
      {
        "answers": [
          {
            "text": "TR-M10_V027-14489,18827"
          }
        ]
      }
    ]
  }
  ```
* Cả 2 giao diện đều hỗ trợ:
  * Nút `+ Thêm #{activeFrameNum}`: Thêm frame hiện tại đang phát vào chuỗi.
  * Nút `📋 Lấy {n} frame đã lưu`: Tự động nạp toàn bộ danh sách frame đã bookmark của video hiện tại từ VECNA.

---

### E. Tối ưu UX Modal DRES trong VideoPlayer

#### 1. Đóng modal bằng phím ESC và bấm ra ngoài nền tối
* **Vấn đề**: Trước đây bấm ESC hoặc click ra ngoài sẽ đóng luôn cả trình phát `VideoPlayer`.
* **Giải pháp**:
  * **Phím ESC**: Dùng `showDresModalRef` để bắt sự kiện phím tại `case 27 (Escape)`. Nếu modal DRES đang mở thì `setShowDresModal(false)`, `e.preventDefault()`, `e.stopPropagation()` và không gọi `onCancel()` của VideoPlayer.
  * **Bấm ra ngoài**: Lớp backdrop phủ tối (`fixed inset-0 z-[60]`) có bộ xử lý click gọi `setShowDresModal(false)` và `e.stopPropagation()`. Hộp thoại con màu trắng bên trong có `onClick={(e) => e.stopPropagation()}` để chặn nổi bọt.

#### 2. Bố cục 3 tầng giải quyết lỗi mất nút "Nộp ngay"
* **Vấn đề**: Hộp thoại DRES có nội dung dài (cảnh báo trừ điểm, video info, frame input, JSON preview) khiến phần chân trang bị tràn xuống dưới màn hình và không cuộn chuột tới được.
* **Giải pháp**:
  * **Sticky Header**: Tiêu đề và nút `✕` luôn ghim cố định ở đỉnh modal (`shrink-0`).
  * **Scrollable Body**: Thân modal được bao bọc trong `max-h-[90vh] overflow-y-auto flex-1 min-h-0`, cuộn độc lập và mượt mà.
  * **Sticky Footer**: Phần chân trang chứa nút `Đóng`, `🧪 Đổi sang Dry-Run`, và `🚀 Nộp ngay` được **ghim cố định ở đáy modal (`shrink-0 border-t bg-gray-50/90`)**. Nút nộp bài luôn luôn hiển thị trong tầm mắt trên mọi kích thước màn hình.

---

## 3. Quy trình Build & Deploy

* Lệnh build frontend:
  ```powershell
  cd e:\AI_Challenge\Vecna\aic51-src\aic51\packages\webui\frontend
  npm run build
  ```
* Lệnh copy sang thư mục phân phối FastAPI:
  ```powershell
  Remove-Item -Path "e:\AI_Challenge\Vecna\.web\dist\assets\*.js","e:\AI_Challenge\Vecna\.web\dist\assets\*.css" -Force
  Copy-Item -Path "e:\AI_Challenge\Vecna\aic51-src\aic51\packages\webui\frontend\dist\*" -Destination "e:\AI_Challenge\Vecna\.web\dist" -Recurse -Force
  ```
* Tệp bundle phân phối hiện tại:
  * JavaScript: `assets/index-gkQMehFa.js`
  * CSS: `assets/index-BnUmYX3L.css`
  * HTML: `.web/dist/index.html`
