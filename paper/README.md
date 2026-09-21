# Vecna LaTeX Paper Project (SOICT Submission)

Dự án bài báo khoa học cho framework **Vecna (AIC51)** sẵn sàng để tải lên **Overleaf** hoặc biên dịch trực tiếp trên máy tính.

---

## 📁 Cấu trúc thư mục

```
paper/
├── main.tex                 # File chính định dạng chuẩn ACM ICPS (Double-column sigconf - thường dùng cho SOICT)
├── main_lncs.tex            # File phụ định dạng Springer LNCS (Single-column - nếu SOICT năm nay yêu cầu LNCS)
├── references.bib           # Toàn bộ danh mục trích dẫn BibTeX (CLIP, SigLIP, Qwen-VL, BGE-M3, Milvus, etc.)
├── README.md                # Hướng dẫn này
├── sections/                # Các chương nội dung tách biệt (dễ dàng phân công nhóm viết song song)
│   ├── 00_abstract.tex      # Tóm tắt bài báo (150-200 từ)
│   ├── 01_introduction.tex  # Bối cảnh, thách thức thực tế và 4 đóng góp chính
│   ├── 02_related_work.tex  # Tổng quan nghiên cứu liên quan
│   ├── 03_system_architecture.tex # Kiến trúc Ingestion, Feature Extraction & ONNX DirectML Pipeline
│   ├── 04_methodology.tex   # Các điểm sáng kỹ thuật: HyDE, Fusion, Temporal DP, Diversify, Provenance
│   ├── 05_experiments.tex   # Bảng thực nghiệm chính, Ablation studies, Throughput benchmark
│   ├── 06_interactive_ui.tex# Hệ thống UI, phím tắt $1/\text{FPS}$, xuất CSV UTF-8 BOM
│   └── 07_conclusion.tex    # Kết luận và hướng phát triển tương lai
└── figures/                 # Thư mục chứa hình ảnh, sơ đồ kiến trúc (vector PDF/PNG)
```

---

## 🚀 Cách tải lên Overleaf nhanh nhất

1. Nén toàn bộ thư mục `paper` thành một file `.zip` (ví dụ: `vecna_paper.zip`).
2. Truy cập [Overleaf](https://www.overleaf.com), bấm **New Project** $\rightarrow$ **Upload Project**.
3. Kéo thả file `vecna_paper.zip` vào.
4. Chọn file biên dịch chính:
   - Mặc định là **`main.tex`** (ACM format).
   - Nếu hội nghị yêu cầu Springer LNCS: đổi sang biên dịch **`main_lncs.tex`**.

---

## 🛠 Biên dịch trên máy cục bộ (Local Compilation)

Nếu bạn có cài đặt TeX Live / MiKTeX:

```bash
cd paper
# Biên dịch ACM
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex

# Hoặc dùng latexmk (tự động xử lý bibtex):
latexmk -pdf main.tex
```

---

## 👥 Phân công nhóm chỉnh sửa nhanh (18/09 - 05/10)

| File | Nội dung cần cập nhật / rà soát | Người phụ trách |
|---|---|---|
| `sections/01_introduction.tex` | Cập nhật tên tác giả, email trường Bách Khoa HCM (HCMUT) | Lead (Hoàng / Kiệt) |
| `sections/04_methodology.tex` | Kiểm tra lại các công thức toán và Algorithm 1 | Member 3 |
| `sections/05_experiments.tex` | Cập nhật số liệu thực tế từ hệ thống của nhóm vào Table 1 & Table 2 | Member 2 |
| `figures/` | Vẽ sơ đồ kiến trúc và xuất file `architecture.pdf` bỏ vào đây | Member 4 |
| `references.bib` | Bổ sung thêm các trích dẫn nếu cần | Member 5 |
