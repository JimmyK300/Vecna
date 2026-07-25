# Consolidated Benchmark Module

Everything related to the Vecna (AIC51) benchmark suite is consolidated inside this single directory: **`benchmark/`**.

---

## 📁 Directory Structure

```
benchmark/
├── __init__.py         # Package exports
├── schema.py           # Data models, Categories, & Failure Taxonomy
├── evaluator.py        # Evaluation Engine (Recall@1/5/20, MRR, Latency)
├── validator.py        # Query integrity validator & candidate inspector
├── cli.py              # CLI logic runner
├── run.py              # Standalone executable entrypoint script
├── queries.json        # Benchmark query dataset
├── results.json        # Execution output log (JSON)
├── report.md           # Execution summary report (Markdown)
├── baseline.json       # System baseline metrics
└── README.md           # Documentation (this file)
```

---

## ⚡ How to Run

### Method 1: Standalone Python Script
```bash
python benchmark/run.py
```

Options:
- `--validate`: Validate query dataset schema & video paths without searching.
- `--validate-query q_001`: Inspect top 20 retrieval candidates for a single query.
- `--category ocr_dependent`: Filter benchmark to a single category.
- `--save-baseline`: Save execution results as `benchmark/baseline.json`.

### Method 2: CLI Command
```bash
aic51 benchmark
```
(Supported flags: `--queries`, `--output`, `--report`, `--collection`, `--device`, `--category`, `--save-baseline`, `--validate`, `--validate-query`).

---

## 🎯 Modality Scope

Evaluates strictly using:
- **ImageCLIP** (`image_clip_pe-l-14-336`)
- **OCR** (BM25 sparse keyframe text)
- **ASR** (BM25 sparse WhisperX transcripts)

> `video_clip` is deprecated and excluded.
