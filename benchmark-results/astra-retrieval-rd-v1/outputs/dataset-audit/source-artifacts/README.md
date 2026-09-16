# ASR / OCR text metadata v1

This package decodes the official keyframe-owned `asr.npy` and `ocr.npy` strings into readable derived metadata. The `.npy` files remain the original feature store. Dense embeddings (`asr_dense.npy`, `ocr_dense.npy`) are not decoded here.

## Result

| Item | Count |
|---|---:|
| Videos | 873 |
| Keyframe folders | 322924 |
| ASR `.npy` present | 322924 |
| ASR grouped segments | 17875 |
| OCR `.npy` present | 322924 |
| OCR nonempty frames | 117754 |
| OCR grouped spans | 104994 |
| FPS probes ok | 873/873 |

### Coverage by corpus

| Corpus | Videos | Frames | ASR segments | OCR nonempty frames |
|---|---:|---:|---:|---:|
| `L21` | 29 | 19592 | 1328 | 5879 |
| `L22` | 31 | 22569 | 1535 | 7094 |
| `L23` | 25 | 6012 | 340 | 1025 |
| `L24` | 43 | 14588 | 324 | 1842 |
| `L25` | 88 | 80470 | 4964 | 61100 |
| `L26` | 498 | 120178 | 6294 | 26882 |
| `L27` | 16 | 7542 | 355 | 1525 |
| `L28` | 24 | 19542 | 991 | 5358 |
| `L29` | 23 | 18391 | 962 | 3598 |
| `L30` | 96 | 14040 | 782 | 3451 |
| **TOTAL** | **873** | **322924** | **17875** | **117754** |

## Evidence files

- `coverage.csv`: one row per video, with frame counts, nonempty rates, segment/span counts, and FPS probe status.
- `asr/by-video/<video_id>.json`: grouped ASR segments plus every nonempty keyframe projection.
- `asr/by-video/<video_id>.txt`: human-readable `[start -> end] text` transcript.
- `asr/segments.jsonl`: corpus-wide ASR segments.
- `ocr/by-video/<video_id>.json`: grouped OCR spans plus every nonempty keyframe string.
- `ocr/by-video/<video_id>.txt`: human-readable OCR spans.
- `ocr/spans.jsonl`: corpus-wide grouped OCR spans.
- `ocr/frames.jsonl`: corpus-wide nonempty OCR frames.
- `manifest.json`: source roots, method, counts, and SHA-256 hashes of the inventory files.
- `../../../tools/extract_asr_ocr_metadata.py`: reproducible generator.

## Method

- Observed at UTC: `2026-08-18T05:46:02Z`.
- Feature root: `D:\Official-Dataset\features_L21-L30_branch-feats-siglip\features` (portable relative root: `features_L21-L30_branch-feats-siglip/features`).
- Video root: `D:\Official-Dataset\videos` (portable relative root: `videos/`).
- Output root: `D:\Official-Dataset\derived\metadata\asr-ocr-text-v1`.
- Text decode matches Vecna: `np.load(..., allow_pickle=True)` then `str(array.reshape(-1)[0])`.
- Consecutive identical nonempty strings are collapsed into one span. Empty frames are skipped and do not break a run of identical text. This matches Vecna `/api/video/transcript`.
- Timestamps use `frame_idx / rounded_fps`, where `rounded_fps` is `round(r_frame_rate)` from `ffprobe`. This matches the FPS rounding used when Vecna projected WhisperX onto keyframes.
- Interval endpoints are inclusive keyframe times, not native WhisperX word boundaries.
- ASR source is WhisperX text already projected onto keyframes. OCR source is Tesseract normalized frame text (`strip + lower + collapse whitespace`). Bounding boxes and native confidences are not present in the `.npy` files.
- These texts are evidence, not ground truth. OCR is noisy.

## Non-goals

- Does not re-run WhisperX or Tesseract.
- Does not decode `asr_dense.npy` / `ocr_dense.npy` (BGE-M3 vectors).
- Does not sentence-split ASR (Vecna's UI does that as a display convenience and fabricates sub-span times).
