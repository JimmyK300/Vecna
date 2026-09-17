"""
GPU-Accelerated Video Clip Extractor for Vecna / Qwen Temporal.

Fast hardware-accelerated (NVIDIA NVDEC + NVENC) extraction of 5-second video clips
from existing keyframes in data/keyframes with Min-Gap temporal filtering.

Usage:
    python scripts/extract_clips_gpu.py --work-dir testing5vid
    python scripts/extract_clips_gpu.py --work-dir testing5vid --clip-length 5.0 --min-clip-gap 4.0
    python scripts/extract_clips_gpu.py --work-dir . --workers 4
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table

    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None


SUPPORTED_VIDEO_EXTS = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"]


def check_ffmpeg() -> bool:
    """Check if ffmpeg executable is available in PATH."""
    return shutil.which("ffmpeg") is not None


def check_nvenc_support() -> bool:
    """Check if NVIDIA NVENC hardware encoder is functional on this system."""
    if not check_ffmpeg():
        return False
    try:
        # Quick 1-frame probe with h264_nvenc
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "nullsrc=s=64x64:d=0.04",
            "-c:v",
            "h264_nvenc",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def get_video_fps(video_path: Path, video_info_dir: Optional[Path] = None) -> float:
    """Get video frame rate from video_info JSON or probe via OpenCV/ffprobe."""
    # 1. Try video_info JSON if available
    if video_info_dir and video_info_dir.exists():
        info_file = video_info_dir / f"{video_path.stem}.json"
        if info_file.exists():
            try:
                with open(info_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "frame_rate" in data and float(data["frame_rate"]) > 0:
                        return float(data["frame_rate"])
                    if "avg_frame_rate" in data:
                        parts = str(data["avg_frame_rate"]).split("/")
                        if len(parts) == 2 and float(parts[1]) > 0:
                            return float(parts[0]) / float(parts[1])
            except Exception:
                pass

    # 2. Try OpenCV
    try:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            if fps and fps > 0:
                return float(fps)
    except Exception:
        pass

    # 3. Fallback default
    return 30.0


def filter_keyframes_min_gap(
    frame_indices: list[int],
    fps: float,
    min_clip_gap_seconds: float,
) -> list[int]:
    """Filter sorted frame indices so consecutive clips are separated by at least min_clip_gap_seconds."""
    if not frame_indices:
        return []

    min_gap_frames = int(round(min_clip_gap_seconds * fps))
    selected = [frame_indices[0]]
    last_frame = frame_indices[0]

    for f in frame_indices[1:]:
        if (f - last_frame) >= min_gap_frames:
            selected.append(f)
            last_frame = f

    return selected


def cut_single_clip(
    video_path: Path,
    output_path: Path,
    start_sec: float,
    clip_length: float,
    use_nvenc: bool = True,
) -> bool:
    """
    Cut a single video clip using FFmpeg.
    Uses GPU NVDEC + NVENC if use_nvenc is True, falls back to CPU ultrafast.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if use_nvenc:
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-hwaccel",
            "cuda",
            "-ss",
            f"{max(0.0, start_sec):.3f}",
            "-t",
            f"{clip_length:.3f}",
            "-i",
            str(video_path),
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p1",
            "-b:v",
            "3M",
            "-maxrate",
            "4M",
            "-bufsize",
            "8M",
            "-an",
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1024:
            return True

    # Fallback to CPU ultrafast
    cmd_cpu = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, start_sec):.3f}",
        "-t",
        f"{clip_length:.3f}",
        "-i",
        str(video_path),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-an",
        str(output_path),
    ]
    res_cpu = subprocess.run(cmd_cpu, capture_output=True)
    return res_cpu.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1024


def process_video_clips(
    video_path: Path,
    keyframe_dir: Path,
    output_dir: Path,
    fps: float,
    clip_length: float = 5.0,
    min_clip_gap: float = 4.0,
    use_nvenc: bool = True,
    overwrite: bool = False,
    workers: int = 4,
    progress_callback=None,
) -> tuple[int, int, float]:
    """
    Process all clips for a single video.
    Returns (clips_created, clips_skipped, elapsed_seconds).
    """
    start_time = time.perf_counter()

    # 1. Collect all keyframes
    keyframe_files = sorted(
        [
            p
            for p in keyframe_dir.glob("*")
            if p.is_file() and p.suffix.lower() in [".jpg", ".png", ".jpeg"]
        ],
        key=lambda p: p.stem,
    )

    if not keyframe_files:
        return 0, 0, 0.0

    frame_indices = []
    for kf in keyframe_files:
        try:
            frame_indices.append(int(kf.stem))
        except ValueError:
            continue
    frame_indices.sort()

    # 2. Filter keyframes with Min-Gap
    selected_frames = filter_keyframes_min_gap(frame_indices, fps, min_clip_gap)

    # 3. Schedule clips
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    skipped = 0

    half_clip = clip_length / 2.0

    for f_idx in selected_frames:
        out_clip = output_dir / f"{f_idx:06d}.mp4"
        if out_clip.exists() and out_clip.stat().st_size > 1024 and not overwrite:
            skipped += 1
            if progress_callback:
                progress_callback(advance=1)
            continue

        center_sec = f_idx / fps
        clip_start_sec = max(0.0, center_sec - half_clip)
        tasks.append((out_clip, clip_start_sec))

    if not tasks:
        elapsed = time.perf_counter() - start_time
        return 0, skipped, elapsed

    # 4. Run FFmpeg in parallel
    created = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                cut_single_clip,
                video_path,
                out_clip,
                start_sec,
                clip_length,
                use_nvenc,
            ): out_clip
            for out_clip, start_sec in tasks
        }

        for fut in as_completed(futures):
            ok = fut.result()
            if ok:
                created += 1
            if progress_callback:
                progress_callback(advance=1)

    elapsed = time.perf_counter() - start_time
    return created, skipped, elapsed


def main():
    parser = argparse.ArgumentParser(
        description="GPU-Accelerated Video Clip Extractor for Qwen Temporal"
    )
    parser.add_argument(
        "-w",
        "--work-dir",
        type=str,
        default=".",
        help="Workspace directory containing data/ folder (default: current dir)",
    )
    parser.add_argument(
        "--video-id",
        type=str,
        default=None,
        help="Optional single video ID or comma-separated list of video IDs",
    )
    parser.add_argument(
        "--clip-length",
        type=float,
        default=5.0,
        help="Duration of each clip in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--min-clip-gap",
        type=float,
        default=4.0,
        help="Minimum gap between clips in seconds (default: 4.0)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel FFmpeg worker threads (default: 4)",
    )
    parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        help="Overwrite existing video clips",
    )
    parser.add_argument(
        "--no-gpu",
        action="store_true",
        help="Disable GPU NVENC hardware acceleration and force CPU encoding",
    )
    parser.add_argument(
        "--video-dir",
        type=str,
        default=None,
        help="Custom path to videos directory if not in work-dir/data/videos",
    )

    args = parser.parse_args()

    work_dir = Path(args.work_dir).resolve()
    # If data/keyframes does not exist in work_dir, check if testing5vid/data exists
    if not (work_dir / "data" / "keyframes").exists() and (work_dir / "testing5vid" / "data" / "keyframes").exists():
        work_dir = work_dir / "testing5vid"

    data_dir = work_dir / "data"
    videos_dir = Path(args.video_dir).resolve() if args.video_dir else (data_dir / "videos")
    keyframes_base = data_dir / "keyframes"
    clips_base = data_dir / "video_clips"
    video_info_base = data_dir / "video_info"

    if not check_ffmpeg():
        print("[ERROR] ffmpeg not found in PATH! Please install FFmpeg to use GPU clip extraction.")
        sys.exit(1)

    has_nvenc = False if args.no_gpu else check_nvenc_support()
    encoder_name = "NVIDIA NVENC (GPU)" if has_nvenc else "libx264 Ultrafast (CPU)"

    if HAS_RICH:
        console.rule("[bold cyan]Vecna GPU Video Clip Extractor[/bold cyan]")
        console.print(f"[bold]Workspace:[/bold] {work_dir}")
        console.print(f"[bold]Encoder:[/bold]   {encoder_name}")
        console.print(f"[bold]Params:[/bold]    Clip Length = {args.clip_length}s | Min Gap = {args.min_clip_gap}s | Workers = {args.workers}")
    else:
        print("=" * 60)
        print(f"Workspace: {work_dir}")
        print(f"Encoder:   {encoder_name}")
        print(f"Params:    Clip Length = {args.clip_length}s | Min Gap = {args.min_clip_gap}s | Workers = {args.workers}")
        print("=" * 60)

    if not keyframes_base.exists():
        print(f"[ERROR] Keyframe directory does not exist: {keyframes_base}")
        sys.exit(1)

    # Discover videos that have keyframes
    target_video_ids = (
        [v.strip() for v in args.video_id.split(",") if v.strip()]
        if args.video_id
        else None
    )

    candidate_dirs = [d for d in keyframes_base.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if target_video_ids:
        candidate_dirs = [d for d in candidate_dirs if d.name in target_video_ids]

    candidate_dirs.sort(key=lambda d: d.name)

    if not candidate_dirs:
        print("[WARNING] No keyframe folders found to process.")
        sys.exit(0)

    # Summary tracking
    results = []
    total_created = 0
    total_skipped = 0
    total_start = time.perf_counter()

    for kf_dir in candidate_dirs:
        vid_id = kf_dir.name

        # Locate raw video file
        video_path = None
        for ext in SUPPORTED_VIDEO_EXTS:
            cand = videos_dir / f"{vid_id}{ext}"
            if cand.exists():
                video_path = cand
                break

        if not video_path:
            if HAS_RICH:
                console.print(f"[yellow]Skipping {vid_id}: Raw video file not found in {videos_dir}[/yellow]")
            else:
                print(f"Skipping {vid_id}: Raw video file not found in {videos_dir}")
            continue

        fps = get_video_fps(video_path, video_info_base)
        out_clip_dir = clips_base / vid_id

        # Quick count of total selected keyframes for progress bar
        kf_files = sorted(
            [p for p in kf_dir.glob("*") if p.is_file() and p.suffix.lower() in [".jpg", ".png"]],
            key=lambda p: p.stem,
        )
        frame_indices = []
        for kf in kf_files:
            try:
                frame_indices.append(int(kf.stem))
            except ValueError:
                pass
        selected_frames = filter_keyframes_min_gap(frame_indices, fps, args.min_clip_gap)

        if HAS_RICH:
            with Progress(
                SpinnerColumn(),
                TextColumn(f"[bold green]{vid_id}[/bold green]"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=True,
            ) as prog:
                task_id = prog.add_task("Clipping", total=len(selected_frames))

                def update_cb(advance=1):
                    prog.update(task_id, advance=advance)

                created, skipped, elapsed = process_video_clips(
                    video_path=video_path,
                    keyframe_dir=kf_dir,
                    output_dir=out_clip_dir,
                    fps=fps,
                    clip_length=args.clip_length,
                    min_clip_gap=args.min_clip_gap,
                    use_nvenc=has_nvenc,
                    overwrite=args.overwrite,
                    workers=args.workers,
                    progress_callback=update_cb,
                )
        else:
            print(f"Processing {vid_id} ({len(selected_frames)} clips)...")
            created, skipped, elapsed = process_video_clips(
                video_path=video_path,
                keyframe_dir=kf_dir,
                output_dir=out_clip_dir,
                fps=fps,
                clip_length=args.clip_length,
                min_clip_gap=args.min_clip_gap,
                use_nvenc=has_nvenc,
                overwrite=args.overwrite,
                workers=args.workers,
            )

        total_created += created
        total_skipped += skipped
        results.append({
            "video_id": vid_id,
            "raw_keyframes": len(kf_files),
            "selected_clips": len(selected_frames),
            "created": created,
            "skipped": skipped,
            "fps": fps,
            "elapsed": elapsed,
        })

    total_elapsed = time.perf_counter() - total_start

    # Render summary table
    if HAS_RICH:
        table = Table(title="[bold green]Clip Generation Summary[/bold green]", show_header=True, header_style="bold magenta")
        table.add_column("Video ID", style="cyan")
        table.add_column("FPS", justify="right")
        table.add_column("Keyframes", justify="right")
        table.add_column("Selected Clips", justify="right")
        table.add_column("Created", justify="right", style="green")
        table.add_column("Skipped", justify="right", style="dim")
        table.add_column("Time", justify="right", style="yellow")
        table.add_column("Speed", justify="right")

        for r in results:
            speed = f"{r['created'] / max(r['elapsed'], 0.001):.1f} clips/s" if r['created'] > 0 else "-"
            table.add_row(
                r["video_id"],
                f"{r['fps']:.1f}",
                str(r["raw_keyframes"]),
                str(r["selected_clips"]),
                str(r["created"]),
                str(r["skipped"]),
                f"{r['elapsed']:.2f}s",
                speed,
            )

        console.print(table)
        console.print(
            f"[bold cyan]Total:[/bold cyan] {total_created} clips created, {total_skipped} skipped "
            f"across {len(results)} videos in [bold yellow]{total_elapsed:.2f}s[/bold yellow] "
            f"({total_created / max(total_elapsed, 0.001):.1f} clips/s)"
        )
    else:
        print("\n--- Summary ---")
        for r in results:
            print(f"Video {r['video_id']}: {r['created']} created, {r['skipped']} skipped in {r['elapsed']:.2f}s")
        print(f"Total: {total_created} clips created, {total_skipped} skipped in {total_elapsed:.2f}s")


if __name__ == "__main__":
    main()
