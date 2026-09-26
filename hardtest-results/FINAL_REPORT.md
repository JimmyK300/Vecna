# Báo cáo hard-test Vecna — 2026-09-26

## Kết quả chính

| Hạng mục | Kết quả | Bằng chứng |
| --- | --- | --- |
| Python unit tests | PASS — 82/82 | `python -m unittest discover -s aic51-src/tests -v` |
| JavaScript DRES tests | PASS — 4/4 | `node --test test/dres.test.mjs` |
| Frontend build | PASS | `npm run build` |
| API tìm kiếm thực tế | PASS | Batch 1, Batch 2, exact phrase, temporal, camera four-way, YOLO relation đều HTTP 200 |
| Đầu vào biên | PASS | 30 trường hợp: 24 HTTP 200, 6 đầu vào sai bị từ chối HTTP 400; không có lỗi 500 |
| Tìm kiếm đồng thời | PASS | 200/200 HTTP 200; 178 truy vấn cũ được báo hủy khi truy vấn mới thay thế; không có lỗi server |
| Tải map-keyframes | PASS | 500/500 HTTP 200, p95 0,293 giây |
| Tải transcript | PASS | 100/100 HTTP 200, p95 0,049 giây |
| Khởi động lại | PASS | Ít nhất 5 lần khởi động/tắt, cổng được giải phóng và VRAM về 0 sau mỗi lần tắt |
| Dừng cưỡng bức và phục hồi | PASS | Dừng đúng tiến trình search đang phục vụ request; khởi động lại, tìm kiếm Batch 2/camera trả HTTP 200; 112 cache transcript JSON đọc được |
| Giao diện | PASS trong smoke test | Chọn Batch 2 và bộ lọc “Ngã tư”, thấy 213 kết quả trên UI SigLIP; mở video và dải ảnh thời gian |
| Frontend lint | WARN — lỗi có sẵn | `npm run lint`: 273 errors, 26 warnings |
| Phụ thuộc npm | WARN | `npm install` báo 25 vulnerabilities: 2 low, 6 moderate, 16 high, 1 critical |

## Các thay đổi đã thực hiện

- Đồng bộ `origin/main` đến `7fd26df`: `N019-V001`, `N019-V002`, `N019-V003` chuyển từ `three_way` sang `four_way` trong `camera_info_workspace2_road_classification.json`. Bộ nạp metadata camera nay làm mới cache theo thời gian sửa và kích thước tệp, nên cập nhật JSON có hiệu lực khi chạy.
- Sửa thiếu `import json` trong YOLO relation filter; trước sửa yêu cầu live trả HTTP 500, sau sửa trả HTTP 200.
- Giới hạn cache transcript trong RAM ở 64 video theo LRU; cache CSV map-keyframes tối đa 128 bản và tự làm mới khi tệp thay đổi.
- Sửa test dịch thuật để không phụ thuộc cache đĩa hay API dịch bên ngoài; thêm test cho camera, backend endpoint, YOLO relation và DRES frontend.

## Số đo tài nguyên

Trong lượt tải ngắn ở `live-20260926-013748.json`: Core RSS 633,5 → 634,3 MiB; Search RSS 6.339,7 → đỉnh 7.404,6 → 6.341,5 MiB; GPU 7.909 → đỉnh 7.931 → 7.909 MiB. GPU RTX 4060 8 GiB còn rất ít dung lượng khi chạy; cấu hình hiện tại dùng một search worker. Dữ liệu 20 mẫu, mỗi giây một mẫu, không đủ để kết luận về rò rỉ sau nhiều giờ.

## Giới hạn và việc nên làm tiếp

- LLM expander và YOLO model tự động đang tắt trong cấu hình. YOLO relation trên metadata có sẵn đã kiểm thử; không kiểm thử gọi Groq thật hoặc nạp thêm reranker/model vì VRAM hiện tại sát giới hạn.
- DRES đã được kiểm thử bằng giả lập trạng thái 401/429/502, thời gian và TRAKE; không gửi bài thật đến máy chủ cuộc thi.
- Chưa có phép đo browser memory kéo dài hoặc soak nhiều giờ. Smoke test xác nhận luồng tìm kiếm và mở video, chưa chứng minh không rò rỉ bộ nhớ trình duyệt.
- Nên xử lý lỗi lint theo từng nhóm và rà soát `npm audit` trước khi phát hành. `config.yaml` đang chứa khóa Groq dạng văn bản; nên xoay khóa và chuyển sang biến môi trường. Không chỉnh sửa cấu hình người dùng trong lượt test này.

## Tệp bằng chứng

- `live-20260926-013748.json`: health, tìm kiếm, tải map/transcript, RSS và VRAM.
- `edge-20260926-020631.json`: 30 đầu vào biên và 200 truy vấn đồng thời.
- `../scripts/live_hardtest.py`, `../scripts/edge_hardtest.py`: kịch bản thử API chỉ đọc, có thể chạy lại khi server đang bật.

Kết thúc: server Vecna và ba container Milvus do lượt test này khởi động đã dừng; các cổng 6900, 1337, 4200, 5173, 19530 đều trống; không còn tiến trình dùng GPU từ lượt test.
