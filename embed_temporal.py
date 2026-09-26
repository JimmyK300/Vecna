#!/usr/bin/env python3
"""Build resumable temporal video embeddings with Qwen3-VL-Embedding."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence

import numpy as np

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
DEFAULT_MODEL = "Qwen/Qwen3-VL-Embedding-2B"
DEFAULT_QWEN_COMMIT = "393e2978d27852b0d0230d6994f37f9c15bed73c"
DEFAULT_MODEL_REVISION = "9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_levels(value: str | None) -> set[str] | None:
    if not value:
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


def discover_videos(video_root: Path, levels: set[str] | None = None) -> list[Path]:
    if not video_root.exists():
        raise FileNotFoundError(f"Video root does not exist: {video_root}")
    videos = []
    for path in video_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        rel = path.relative_to(video_root)
        if levels and (not rel.parts or rel.parts[0] not in levels):
            continue
        videos.append(path)
    return sorted(videos)


def segment_bounds(duration_s: float, window_s: float, stride_s: float, min_tail_s: float) -> list[tuple[float, float]]:
    if duration_s <= 0 or window_s <= 0 or stride_s <= 0:
        return []
    out = []
    start = 0.0
    while start < duration_s:
        end = min(start + window_s, duration_s)
        if end - start >= min_tail_s:
            out.append((start, end))
        start += stride_s
    return out


def sample_frame_indices(start_s: float, end_s: float, fps: float, frame_count: int, samples: int) -> np.ndarray:
    if samples <= 0:
        raise ValueError("samples must be > 0")
    if frame_count <= 0 or fps <= 0:
        raise ValueError("invalid video metadata")
    width = max(0.0, end_s - start_s)
    times = start_s + (np.arange(samples, dtype=np.float64) + 0.5) * width / samples
    indices = np.rint(times * fps).astype(np.int64)
    return np.clip(indices, 0, frame_count - 1)


def stable_output_stem(video: Path, video_root: Path) -> Path:
    rel = video.relative_to(video_root)
    clean_parts = [re.sub(r"[^A-Za-z0-9_.-]+", "_", p) for p in rel.with_suffix("").parts]
    return Path(*clean_parts)


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez(f, **arrays)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def resolve_model(model: str, requested_revision: str, cache_root: Path) -> tuple[Path, str]:
    local = Path(model)
    if local.exists():
        return local.resolve(), "local"
    if "/" not in model:
        raise ValueError(f"Expected a local model path or Hugging Face repo id, got: {model}")
    from huggingface_hub import HfApi, snapshot_download

    resolved_revision = HfApi().model_info(model, revision=requested_revision).sha
    if not resolved_revision:
        raise RuntimeError(f"Could not resolve model revision for {model}@{requested_revision}")
    target = cache_root / model.replace("/", "--") / resolved_revision
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=model, revision=resolved_revision, local_dir=str(target))
    return target, resolved_revision


def load_embedder(model_path: Path, qwen_repo: Path, frames_per_window: int, frame_side: int, attention: str):
    if not qwen_repo.exists():
        raise FileNotFoundError(f"Pinned Qwen code checkout missing: {qwen_repo}. Run setup.sh first.")
    sys.path.insert(0, str(qwen_repo / "src"))
    import torch
    from models.qwen3_vl_embedding import Qwen3VLEmbedder

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available; this H100 runner requires an NVIDIA GPU.")
    if attention == "auto":
        try:
            import flash_attn  # noqa: F401
            attention = "flash_attention_2"
        except Exception:
            attention = "sdpa"

    model = Qwen3VLEmbedder(
        model_name_or_path=str(model_path),
        max_frames=frames_per_window,
        total_pixels=int(frames_per_window * frame_side * frame_side),
        torch_dtype=torch.bfloat16,
        attn_implementation=attention,
    )
    return model, torch, attention


def load_segment_frames(vr, start_s: float, end_s: float, fps: float, frame_count: int, samples: int, frame_side: int):
    from PIL import Image

    indices = sample_frame_indices(start_s, end_s, fps, frame_count, samples)
    batch = vr.get_batch(indices.tolist()).asnumpy()
    images = []
    for arr in batch:
        image = Image.fromarray(arr).convert("RGB")
        if max(image.size) > frame_side:
            image.thumbnail((frame_side, frame_side), Image.Resampling.LANCZOS)
        images.append(image)
    return images, indices


def embed_with_backoff(model, torch, inputs: Sequence[dict], batch_size: int) -> np.ndarray:
    rows = []
    pos = 0
    current = max(1, batch_size)
    while pos < len(inputs):
        take = min(current, len(inputs) - pos)
        try:
            emb = model.process(list(inputs[pos:pos + take]))
            rows.append(emb.detach().float().cpu().numpy())
            pos += take
            if current < batch_size:
                current = min(batch_size, current * 2)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            gc.collect()
            if take == 1:
                raise
            current = max(1, take // 2)
            print(f"[oom] reducing batch size to {current}", flush=True)
    return np.concatenate(rows, axis=0)


def process_video(video: Path, video_root: Path, output_root: Path, model, torch, args, run_meta: dict) -> tuple[int, bool]:
    from decord import VideoReader, cpu

    stem = stable_output_stem(video, video_root)
    vector_path = output_root / "vectors" / stem.with_suffix(".npz")
    meta_path = output_root / "vectors" / stem.with_suffix(".json")
    if vector_path.exists() and meta_path.exists() and not args.force:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("run_signature") == run_meta["run_signature"]:
                return int(meta.get("segment_count", 0)), True
        except Exception:
            pass

    vr = VideoReader(str(video), ctx=cpu(0), num_threads=args.decode_threads)
    frame_count = len(vr)
    fps = float(vr.get_avg_fps())
    duration_s = frame_count / fps if fps > 0 else 0.0
    bounds = segment_bounds(duration_s, args.window_seconds, args.stride_seconds, args.min_tail_seconds)
    if not bounds:
        print(f"[skip] no usable segments: {video}", flush=True)
        return 0, False

    embeddings = []
    starts = []
    ends = []
    all_indices = []
    pending_inputs = []
    pending_meta = []

    def flush() -> None:
        nonlocal pending_inputs, pending_meta
        if not pending_inputs:
            return
        batch_emb = embed_with_backoff(model, torch, pending_inputs, args.batch_size)
        embeddings.append(batch_emb.astype(np.float16, copy=False))
        for start, end, idx in pending_meta:
            starts.append(start)
            ends.append(end)
            all_indices.append(idx.astype(np.int32, copy=False))
        pending_inputs = []
        pending_meta = []

    for start, end in bounds:
        frames, indices = load_segment_frames(
            vr, start, end, fps, frame_count, args.frames_per_window, args.frame_side
        )
        pending_inputs.append({"video": frames})
        pending_meta.append((start, end, indices))
        if len(pending_inputs) >= args.batch_size:
            flush()
    flush()

    matrix = np.concatenate(embeddings, axis=0)
    atomic_npz(
        vector_path,
        embeddings=matrix,
        starts=np.asarray(starts, dtype=np.float32),
        ends=np.asarray(ends, dtype=np.float32),
        frame_indices=np.stack(all_indices).astype(np.int32, copy=False),
    )

    rel = video.relative_to(video_root).as_posix()
    meta = {
        **run_meta,
        "video_path": rel,
        "video_size_bytes": video.stat().st_size,
        "video_mtime_ns": video.stat().st_mtime_ns,
        "frame_count": frame_count,
        "fps": fps,
        "duration_s": duration_s,
        "segment_count": len(bounds),
        "vector_dim": int(matrix.shape[1]),
        "vector_dtype": str(matrix.dtype),
        "vector_file": vector_path.relative_to(output_root).as_posix(),
        "created_unix": time.time(),
    }
    if args.hash_videos:
        meta["video_sha256"] = sha256_file(video)
    atomic_json(meta_path, meta)

    del vr, matrix, embeddings
    gc.collect()
    torch.cuda.empty_cache()
    return len(bounds), False


def build_run_meta(args, model_revision: str, attention: str) -> dict:
    config = {
        "model": args.model,
        "model_revision": model_revision,
        "qwen_code_commit": DEFAULT_QWEN_COMMIT,
        "window_seconds": args.window_seconds,
        "stride_seconds": args.stride_seconds,
        "frames_per_window": args.frames_per_window,
        "frame_side": args.frame_side,
        "dtype": "bfloat16",
        "attention": attention,
    }
    signature = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    return {**config, "run_signature": signature}


def parse_args() -> argparse.Namespace:
    root = repo_root()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video-root", type=Path, default=Path(os.getenv("VIDEO_ROOT", root / "videos")))
    p.add_argument(
        "--output-root",
        type=Path,
        default=Path(os.getenv("OUTPUT_ROOT", root / "derived/embeddings/qwen3-vl-temporal-v1")),
    )
    p.add_argument("--model", default=os.getenv("MODEL", DEFAULT_MODEL))
    p.add_argument("--model-revision", default=os.getenv("MODEL_REVISION", DEFAULT_MODEL_REVISION))
    p.add_argument(
        "--qwen-repo",
        type=Path,
        default=Path(os.getenv("QWEN_REPO", root / ".cache/qwen3-vl-embedding")),
    )
    p.add_argument("--levels", default=os.getenv("LEVELS", ""), help="Comma-separated first-level dirs, e.g. L21,L22")
    p.add_argument("--window-seconds", type=float, default=float(os.getenv("WINDOW_SECONDS", "10")))
    p.add_argument("--stride-seconds", type=float, default=float(os.getenv("STRIDE_SECONDS", "10")))
    p.add_argument("--frames-per-window", type=int, default=int(os.getenv("FRAMES_PER_WINDOW", "8")))
    p.add_argument("--frame-side", type=int, default=int(os.getenv("FRAME_SIDE", "512")))
    p.add_argument("--batch-size", type=int, default=int(os.getenv("BATCH_SIZE", "2")))
    p.add_argument("--min-tail-seconds", type=float, default=float(os.getenv("MIN_TAIL_SECONDS", "2")))
    p.add_argument("--decode-threads", type=int, default=int(os.getenv("DECODE_THREADS", "2")))
    p.add_argument(
        "--attention",
        choices=["auto", "sdpa", "flash_attention_2"],
        default=os.getenv("ATTENTION", "auto"),
    )
    p.add_argument("--limit-videos", type=int, default=int(os.getenv("LIMIT_VIDEOS", "0")))
    p.add_argument("--hash-videos", action="store_true", default=os.getenv("HASH_VIDEOS", "0") == "1")
    p.add_argument("--force", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    levels = parse_levels(args.levels)
    videos = discover_videos(args.video_root, levels)
    if args.limit_videos > 0:
        videos = videos[:args.limit_videos]
    if not videos:
        raise SystemExit(
            f"No videos found under {args.video_root} (levels={sorted(levels) if levels else 'all'})."
        )

    cache_root = repo_root() / ".cache/hf-models"
    model_path, model_revision = resolve_model(args.model, args.model_revision, cache_root)
    model, torch, attention = load_embedder(
        model_path, args.qwen_repo, args.frames_per_window, args.frame_side, args.attention
    )
    run_meta = build_run_meta(args, model_revision, attention)
    args.output_root.mkdir(parents=True, exist_ok=True)
    atomic_json(
        args.output_root / "run_config.json",
        {**run_meta, "video_root": str(args.video_root.resolve())},
    )

    print(
        f"[run] {len(videos)} videos | {args.model}@{model_revision[:12]} | "
        f"{args.frames_per_window} frames/{args.window_seconds:g}s | batch={args.batch_size}"
    )
    done_segments = 0
    skipped = 0
    started = time.time()
    for i, video in enumerate(videos, start=1):
        rel = video.relative_to(args.video_root)
        before = time.time()
        count, was_skipped = process_video(
            video, args.video_root, args.output_root, model, torch, args, run_meta
        )
        done_segments += count
        skipped += int(was_skipped)
        elapsed = time.time() - before
        print(
            f"[{i}/{len(videos)}] {'resume' if was_skipped else 'done  '} "
            f"{rel} | segments={count} | {elapsed:.1f}s",
            flush=True,
        )

    total = time.time() - started
    print(
        f"[complete] segments={done_segments} resumed_videos={skipped} "
        f"elapsed={total / 3600:.2f}h"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
