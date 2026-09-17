# Qwen3-VL temporal embeddings

Vecna now exposes a temporal retrieval channel backed by the same
`Qwen/Qwen3-VL-Embedding-2B` checkpoint already used for keyframe embeddings.

## Why this model

Qwen3-VL-Embedding-2B is a 2B-parameter multimodal embedding model with a
2048-dimensional shared embedding space. The checkpoint natively supports video
inputs, so temporal clips are encoded jointly instead of embedding frames
independently and averaging them.

The temporal channel intentionally reuses the existing Qwen text encoder. Query
embeddings therefore search both `qwen_vl` (keyframes) and
`qwen_vl_temporal` (video clips) in the same space.

## Input

The analyser reads clips from:

`data/video_clips/<video_id>/<frame_id>.mp4`

Each clip is uniformly sampled to at most 16 RGB frames with OpenCV, preserving
frame order. The ordered frame tensor is passed to Sentence Transformers as the
native `video` modality.

## Run

To extract temporal video clip embeddings independently:

```bash
aic51-cli analyse --use-qwen-temporal
```

For keyframe static embeddings only:

```bash
aic51-cli analyse --use-qwen-vl
```

To extract both keyframe and temporal features together:

```bash
aic51-cli analyse --use-qwen-vl --use-qwen-temporal
```

For a CPU-only machine:

```bash
aic51-cli analyse --use-qwen-temporal --no-gpu
```

The current Qwen weights are about 4.3 GB and CPU inference is expected to be
slow. The checkpoint can still be cached once and reused across runs.

## Runtime requirements

- `sentence-transformers>=5.4.0`
- `transformers>=4.57.0`
- `qwen-vl-utils>=0.0.14`
- OpenCV

The OpenCV loader avoids requiring `torchcodec` for local MP4 clips.

## Video clip generation (GPU Acceleration)

Clips can be generated either from raw videos or directly from existing keyframes:

### Option 1: Standalone High-Speed GPU Extractor (Recommended when keyframes already exist)

When keyframes are already extracted in `data/keyframes/<video_id>/*.jpg`, use `scripts/extract_clips_gpu.py`. It uses NVIDIA NVDEC + NVENC hardware acceleration in parallel threads to cut 5-second clips in milliseconds per clip without modifying existing keyframe images:

```bash
# Process testing5vid workspace
python scripts/extract_clips_gpu.py --work-dir testing5vid

# Custom clip length (5.0s) and Min-Gap (4.0s)
python scripts/extract_clips_gpu.py --work-dir testing5vid --clip-length 5.0 --min-clip-gap 4.0 --workers 4
```

### Option 2: Via `aic51-cli add` with `--gpu`

The `add` command supports `--gpu` (`-g`) to leverage hardware acceleration:

```bash
# Add with keyframes and GPU-accelerated clips
aic51-cli add <video_path> -d -k -c --gpu

# Generate clips from existing keyframes without re-extracting frames
aic51-cli add <video_path> -d -c --gpu
```

## Output

The feature name is `qwen_vl_temporal`. Each clip produces one normalized
2048-dimensional vector stored as:

`features/<video_id>/<frame_id>/qwen_vl_temporal.npy`

This is stored alongside and distinct from the static keyframe embedding:

`features/<video_id>/<frame_id>/qwen_vl.npy`

Both channels are indexed with cosine similarity and can be queried jointly or separately.

