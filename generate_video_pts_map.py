"""Build frame-index to playback-PTS maps for videos already in a workspace.

The map must be generated from the exact MP4 served by the player.  In
particular, a MOV's frame numbers and timestamps cannot be reused after an
encode that drops or duplicates frames.

Example: python generate_video_pts_map.py --workspace workspace2
"""

import argparse
import csv
import math
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path


def video_fps(video: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        check=True, capture_output=True, text=True,
    )
    fps = float(Fraction(result.stdout.strip()))
    if fps <= 0:
        raise ValueError(f"Invalid frame rate: {video}")
    return fps


def build_map(
    video: Path, frames_dir: Path, output: Path, overwrite: bool,
    allow_trailing_missing: bool = False,
) -> tuple[int, int, int]:
    if output.exists() and not overwrite:
        raise FileExistsError(f"{output} exists; use --overwrite to replace it")
    selected = {int(p.stem) for p in frames_dir.glob("*.jpg") if p.stem.isdigit()}
    if not selected:
        raise ValueError(f"No numbered keyframe JPEGs found: {frames_dir}")

    fps = video_fps(video)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f".{os.getpid()}.{threading.get_ident()}.csv.tmp")
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "frame=best_effort_timestamp_time", "-of", "csv=p=0", str(video),
    ]
    count = 0
    mapped = 0
    try:
        with temporary.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(("n", "pts_time", "fps", "frame_idx"))
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, bufsize=1) as process:
                missing_timestamp = False
                for line in process.stdout:
                    value = line.strip().rstrip(",")
                    if not value or value == "N/A":
                        missing_timestamp = True
                    else:
                        try:
                            valid = math.isfinite(float(value))
                        except ValueError:
                            valid = False
                        if not valid:
                            missing_timestamp = True
                        elif count in selected:
                            writer.writerow((mapped + 1, value, fps, count))
                            mapped += 1
                    count += 1
                if process.wait() != 0:
                    raise RuntimeError(f"ffprobe failed for {video}")
                if missing_timestamp:
                    raise ValueError(f"Missing frame timestamps: {video}")
        missing = sum(index >= count for index in selected)
        if mapped != len(selected) and not (allow_trailing_missing and mapped + missing == len(selected)):
            raise ValueError(
                f"{video.name}: mapped {mapped}/{len(selected)} keyframes; "
                "the images may come from a different video encode"
            )
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return mapped, count, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("workspace2"))
    parser.add_argument("--pattern", default="N*.mp4", help="Video filename glob")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--allow-trailing-missing", action="store_true",
                        help="Map valid frames even if images beyond the MP4's final frame exist")
    args = parser.parse_args()
    work = args.workspace.resolve()
    videos = sorted((work / "data" / "videos").glob(args.pattern))
    if not videos:
        parser.error(f"No videos match {args.pattern!r} in {work / 'data' / 'videos'}")

    if args.workers < 1:
        parser.error("--workers must be positive")

    def process(video: Path) -> str:
        output = work / "map-keyframes" / f"{video.stem}.csv"
        frames_dir = work / "data" / "keyframes" / video.stem
        source_mtime = max(video.stat().st_mtime, frames_dir.stat().st_mtime if frames_dir.exists() else 0)
        if output.exists() and not args.overwrite and output.stat().st_mtime >= source_mtime:
            with output.open(newline="", encoding="utf-8") as file:
                mapped_count = sum(1 for _ in csv.DictReader(file))
            image_count = sum(1 for p in frames_dir.glob("*.jpg") if p.stem.isdigit())
            warning = f"; map/image count differs ({mapped_count}/{image_count})" if image_count != mapped_count else ""
            return f"{video.name}: existing map is current{warning}"
        mapped, total, missing = build_map(
            video, frames_dir, output, True, args.allow_trailing_missing
        )
        warning = f"; {missing} trailing images have no MP4 frame" if missing else ""
        return f"{video.name}: {mapped} keyframes / {total} decoded frames{warning} -> {output}"

    failures = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process, video): video for video in videos}
        for future in as_completed(futures):
            try:
                print(future.result(), flush=True)
            except Exception as exc:
                failures += 1
                print(f"{futures[future].name}: {exc}", file=sys.stderr, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
