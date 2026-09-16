#!/usr/bin/env python3
"""Read exact selected-frame PTS and source metadata; no model or output media.

Input JSON: {"videos":{"L24_V011":[13821,13881,13941,...],...}}.
Only exact source video filenames in the root or one directory below are read.
Selected-frame PTS is preferred; frame/FPS estimates are explicitly separate.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

DEFAULT_FFMPEG = Path(r"C:\Users\minhc\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")


def execute(command, timeout):
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", timeout=max(timeout, 0.1), check=False)
    return completed.returncode, completed.stdout, completed.stderr


def candidates(root, video):
    matches = []
    for suffix in (".mp4", ".mkv", ".avi", ".webm"):
        direct = root / (video + suffix)
        if direct.is_file():
            matches.append(direct)
        matches.extend(path for path in root.glob("*/" + video + suffix) if path.is_file())
    return sorted(set(matches))


def collect(args, request):
    videos = request["videos"]
    if len(videos) > 24 or any(not re.fullmatch(r"L\d+_V\d+", video) for video in videos):
        raise ValueError("Probe is restricted to at most24 exact candidate video IDs")
    if sum(len(frames) for frames in videos.values()) > 72:
        raise ValueError("Probe exceeds the72 already sampled frame IDs")
    if any(not isinstance(frame, int) or frame < 0 for frames in videos.values() for frame in frames):
        raise ValueError("Expected nonnegative integer frame IDs")
    ffmpeg, ffprobe = args.ffmpeg, args.ffmpeg.with_name("ffprobe.exe" if args.ffmpeg.suffix == ".exe" else "ffprobe")
    code, version, error = execute([str(ffmpeg), "-version"], 10)
    if code:
        raise RuntimeError(error)
    started = time.perf_counter()
    rows = []
    for video, raw_frames in sorted(videos.items()):
        frames = sorted(set(raw_frames))
        row = {"video_id": video, "requested_frame_ids": frames, "frames": [], "status": "pending"}
        matches = candidates(args.video_root, video)
        if len(matches) != 1:
            row.update(status="missing_or_ambiguous_source", paths=[str(path) for path in matches])
            rows.append(row)
            continue
        path = matches[0]
        row["source_path"] = str(path)
        row["source_bytes"] = path.stat().st_size
        row["source_mtime_ns"] = path.stat().st_mtime_ns
        remaining = args.overall_seconds - (time.perf_counter() - started)
        if remaining <= 0:
            row["status"] = "overall_budget_exhausted"
            rows.append(row)
            continue
        try:
            code, output, error = execute([str(ffprobe), "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=index,codec_name,r_frame_rate,avg_frame_rate,time_base,start_time,duration,nb_frames,width,height",
                "-of", "json", str(path)], min(15, remaining))
            if code:
                raise RuntimeError(error[-2000:])
            streams = json.loads(output)["streams"]
            if len(streams) != 1:
                raise ValueError("Expected exactly one selected video stream")
            row["stream"] = streams[0]
            fps = Fraction(streams[0]["avg_frame_rate"])
            if fps <= 0:
                raise ValueError("Invalid average frame rate")
            row["frames"] = [{"frame_id": frame, "nominal_frame_over_avg_fps_s": float(Fraction(frame) / fps),
                "nominal_time_is_exact_pts": False, "pts": None, "pts_time_s": None} for frame in frames]
            remaining = args.overall_seconds - (time.perf_counter() - started)
            if remaining <= 0:
                row["status"] = "metadata_only_budget_exhausted"
                rows.append(row)
                continue
            selection = "+".join(f"eq(n\\,{frame})" for frame in frames)
            command = [str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "info", "-copyts", "-threads", str(args.decode_threads),
                "-i", str(path), "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", "select=" + selection + ",showinfo",
                "-frames:v", str(len(frames)), "-fps_mode", "passthrough", "-f", "null", "-"]
            decode_start = time.perf_counter()
            code, output, error = execute(command, min(args.timeout_per_video, remaining))
            row["decode_elapsed_s"] = time.perf_counter() - decode_start
            records = re.findall(r"\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:([0-9.eE+-]+)", error)
            row["selected_frame_pts_log"] = [{"selected_index": int(index), "pts": int(pts), "pts_time_s": float(seconds)} for index, pts, seconds in records]
            if code or len(records) != len(frames) or [int(item[0]) for item in records] != list(range(len(frames))):
                row["status"] = "metadata_only_incomplete_decode"
                row["decode_error"] = error[-3000:]
            else:
                for frame, (_, pts, seconds) in zip(row["frames"], records):
                    frame.update(pts=int(pts), pts_time_s=float(seconds))
                row["status"] = "exact_pts_complete"
        except subprocess.TimeoutExpired:
            row["status"] = "metadata_only_decode_timeout" if row.get("stream") else "source_probe_timeout"
        except Exception as exc:
            row["status"] = "probe_error"
            row["error"] = str(exc)
        rows.append(row)
    return {"schema_version": 1, "purpose": "vecna82-matched-frame-timestamps", "ffmpeg_version": version.splitlines()[0],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "request": request,
        "overall_elapsed_s": time.perf_counter() - started, "videos": rows,
        "exact_pts_video_count": sum(row["status"] == "exact_pts_complete" for row in rows),
        "method": "Decode original stream from start, select exact zero-based n values, showinfo PTS; map selected chronological output to sorted requested frame IDs.",
        "metadata_fallback": "frame_id / averageFPS is nominal derived time only and never labeled exactPTS",
        "model_loaded": False, "output_media_written": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--video-root", type=Path, default=Path(r"D:\Official-Dataset\videos"))
    parser.add_argument("--ffmpeg", type=Path, default=DEFAULT_FFMPEG)
    parser.add_argument("--timeout-per-video", type=float, default=45)
    parser.add_argument("--overall-seconds", type=float, default=180)
    parser.add_argument("--decode-threads", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(collect(args, json.loads(args.request.read_text(encoding="utf-8")))), flush=True)


if __name__ == "__main__":
    main()
