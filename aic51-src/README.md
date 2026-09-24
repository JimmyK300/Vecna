# Vecna - HCMC AI Challenge (`aic51`)

Multimodal Video Retrieval & Traffic Analysis Engine built for the Ho Chi Minh City AI Challenge (HCMC AIC).

## Contributors

- Lê Tuấn Kiệt ([@ProfK602170](https://github.com/ProfK602170))
- Nguyễn Lê Minh Hoàng ([@nlmhoagn](https://github.com/nlmhoagn))
- Cao Chí Minh ([@JimmyK300](https://github.com/JimmyK300))
- Ngô Đắc Minh ([@kinus-is-coding](https://github.com/kinus-is-coding))
- Phan Hiếu Minh ([@PhanHieuMinh](https://github.com/PhanHieuMinh))

---

## Dependencies & Prerequisites

1. **Python 3.10+ / 3.11** with CUDA support.
2. **[ffmpeg](https://ffmpeg.org/)** (Required for video decoding and clip generation).
3. **[tesseract](https://github.com/tesseract-ocr/tesseract)** (Optional, for OCR).
4. **[Docker Desktop](https://www.docker.com/)** (Running for Milvus Vector Database).
5. **Model Weights:**
   - YOLO11-seg: `weights/yolo11m-seg.pt` (Auto-downloaded or pre-placed in `weights/`).
   - YOLO26x-seg: `yolo26x-seg.pt` (Auto-downloaded or placed in the workspace/repository root).
   - SigLIP 2: OpenCLIP `ViT-SO400M-14-SigLIP2-378` (`webli`).
   - Qwen VL: `Qwen/Qwen3-VL-Embedding-2B`.

---

## Installation

### Clone & Install Editable Package

```bash
git clone https://github.com/JimmyK300/Vecna.git
cd Vecna/aic51-src
pip install -e .
```

Or install directly with dependencies:

```bash
pip install "ultralytics>=8.4.160"
```

---

## Standard CLI Workflow

### 1. Initialize Workspace

```bash
aic51-cli init
```
*(Workspace configuration is managed via `config.yaml` or `workspace/config.yaml`)*

### 2. Add Videos to Workspace

Extract keyframes and prepare metadata:

```bash
# Add a single video with keyframes (-k)
aic51-cli add path/to/video.mp4 -k

# Add a directory of videos (-d) with keyframes (-k)
aic51-cli add path/to/videos_folder -d -k
```

### 3. Analyse & Extract Features

The analysis pipeline supports modular execution with individual `--use-*` flags:

```bash
# A. Multimodal Search (SigLIP 2 & Qwen-VL)
aic51-cli analyse --use-image-siglip --use-qwen-vl

# B. Traffic Camera Analysis (YOLO11-seg)
# Run specifically for traffic videos (extracts counts, colors, masks, 32-dim vector & JSON)
aic51-cli analyse --use-yolo --video <traffic_video_id>

# YOLO26x-seg for every video folder under data/keyframes
aic51-cli analyse --use-yolo26x-seg

# Split work across machines with repeatable video filters
aic51-cli analyse --use-yolo26x-seg --video L21_V001 --video L21_V002

# C. Combined Multimodal + Traffic Analysis
aic51-cli analyse --use-image-siglip --use-qwen-vl --use-yolo --video <video_id>

# D. Re-analyse with Overwrite (-o)
aic51-cli analyse --use-yolo --video <video_id> -o
```

#### Available Feature Extractors:

| Flag | Feature Extractor | Output Target |
|---|---|---|
| `--use-image-siglip` | SigLIP 2 (`ViT-SO400M-14-SigLIP2-378`) | `features/<video>/<frame>/image_siglip2_so400m-378.npy` |
| `--use-qwen-vl` | Qwen3 VL Embedding (2B) | `features/<video>/<frame>/qwen_vl.npy` |
| `--use-yolo` | YOLO11-seg (`yolo11m-seg.pt`) | `features/<video>/<frame>/yolo_traffic.npy` + `.json` |
| `--use-yolo26x` / `--use-yolo26x-seg` | YOLO26x-seg (`yolo26x-seg.pt`) | `features/<video>/<frame>/yolo26x_seg.npy` + `.json` |
| `--use-ocr` | PaddleOCR / Tesseract | `features/<video>/<frame>/ocr.npy` |
| `--use-asr` | WhisperX ASR | `features/<video>/<frame>/asr.npy` |
| `--use-text-embedding`| BGE-M3 Dense Text Embedding | `features/<video>/<frame>/ocr_dense.npy` |

For a distributed run, give each teammate a disjoint set of
`data/keyframes/<video_id>/` folders. They can run `aic51-cli analyse
--use-yolo26x-seg` without a filter, or use repeatable `--video` flags when the
shared keyframe tree contains more videos. Merge the resulting `features/`
trees afterward; outputs are partitioned by video ID and frame ID. Existing
`.npy` files are skipped, so the command is safe to resume without `-o`.

> 📖 **Detailed YOLO Traffic Guide:** See [`docs/YOLO_TRAFFIC_GUIDE.md`](../docs/YOLO_TRAFFIC_GUIDE.md) for vector dimensions, color calibration details, and schema definitions.

### 4. Build Milvus Vector Index

```bash
aic51-cli index
```

### 5. Launch Search Engine & Web UI

```bash
aic51-cli serve
```
Access the web search interface at `http://localhost:6900`.
