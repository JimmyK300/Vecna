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

The existing Qwen flag selects both Qwen channels because the temporal
extractor is registered as `qwen_vl_embedding_temporal`:

```bash
aic51-cli analyse --use-qwen-vl
```

For a CPU-only machine:

```bash
aic51-cli analyse --use-qwen-vl --no-gpu
```

The current Qwen weights are about 4.3 GB and CPU inference is expected to be
slow. The checkpoint can still be cached once and reused across runs.

## Runtime requirements

- `sentence-transformers>=5.4.0`
- `transformers>=4.57.0`
- `qwen-vl-utils>=0.0.14`
- OpenCV

The OpenCV loader avoids requiring `torchcodec` for local MP4 clips.

## Output

The feature name is `qwen_vl_temporal`. Each clip produces one normalized
2048-dimensional vector stored alongside the other per-frame feature arrays and
indexed with cosine similarity.
