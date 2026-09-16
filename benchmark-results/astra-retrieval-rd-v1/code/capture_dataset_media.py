#!/usr/bin/env python3
"""Capture declared bounded source-evidence assets into a new disposable directory.

Reads only the explicitly named dataset videos. Requires ffmpeg/ffprobe, no
models or numpy. Images use decoded-frame selection, not timestamp rounding.
Usage: py -3.12 capture_dataset_media.py --dataset-root D:/Official-Dataset \
    --output-dir <disposable>/vecna82-source-media-<unique-id>
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time


REQUESTS = [
    {"query_id": "p0_q21", "kind": "image", "video": "videos/L30/L30_V078.mp4", "frame": 1788,
     "channel": "ocr", "reason": "Check whether the requested recipe title/200g ingredient text is visible where the stored OCR window is empty."},
    {"query_id": "p0_q19", "kind": "image", "video": "videos/L30/L30_V072.mp4", "frame": 1745,
     "channel": "ocr", "reason": "Check whether location/club writing is visible at the preserved anchor despite no OCR text in the accepted window."},
    {"query_id": "p1_q17", "kind": "image", "video": "videos/L25/L25_V041.mp4", "frame": 17152,
     "channel": "ocr", "reason": "Positive artifact control: compare source remember-lesson text with stored OCR."},
    {"query_id": "p0_q20", "kind": "audio", "video": "videos/L27/L27_V010.mp4", "start_s": 215, "end_s": 233,
     "channel": "asr", "reason": "Judge the query-critical two-line poem against the projected ASR wording; no wider transcription requested."},
    {"query_id": "p3_q24", "kind": "audio", "video": "videos/L26E/L26_V448.mp4", "start_s": 98, "end_s": 126,
     "channel": "asr", "reason": "Confirm the query-critical soy-sauce quantity already present in stored ASR; current truth remains provisional."},
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--request-manifest", type=Path, help="Optional predeclared frozen-sample request packet; default is the original five assets.")
    args = parser.parse_args()
    root = args.dataset_root.resolve()
    out = args.output_dir.resolve()
    if out.exists() or not out.name.startswith("vecna82-source-media-") or out.is_relative_to(root):
        raise ValueError("Output must be a new vecna82-source-media-* disposable directory outside the dataset")
    out.mkdir(parents=True, exist_ok=False)
    request_packet = None
    requests = REQUESTS
    if args.request_manifest:
        request_packet = json.loads(args.request_manifest.read_text(encoding="utf-8"))
        requests = request_packet["requests"]
        if not requests or len(requests) > 38:
            raise ValueError("Capture packet must contain one to 38 bounded query/channel requests")
        if len({(r["query_id"], r["channel"]) for r in requests}) != len(requests):
            raise ValueError("Duplicate query/channel capture request")
        for request in requests:
            source = (root / request["video"]).resolve()
            if not source.is_relative_to(root / "videos") or source.suffix.lower() != ".mp4":
                raise ValueError("Source must be an exact MP4 path under dataset videos")
            if request["kind"] == "image":
                if request["channel"] != "ocr" or not isinstance(request["frame"], int) or request["frame"] < 0:
                    raise ValueError("Invalid bounded OCR frame request")
            elif request["kind"] == "audio":
                if request["channel"] != "asr" or not 0 <= request["start_s"] < request["end_s"] <= request["start_s"] + 32:
                    raise ValueError("ASR request must be a positive source interval of at most 32 seconds")
            else:
                raise ValueError("Only declared image/audio source requests are supported")
    manifest = {
        "schema": "vecna82-bounded-source-media-v1", "started_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_sample_sha256": "d3727ab99ce98b708c835c8e8b0f8d5688af47e9d25e65ce55a8e5ca839e7714",
        "truth_source": {"repository": "JimmyK300/Vecna", "commit": "f0b0f4707ceab91ba7e266f72fa982dce3ae1c4b",
                         "path": "benchmark-results/issue34-current-115/ground_truth_current_115.jsonl",
                         "sha256": "63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f"},
        "text_source": {"repository": "JimmyK300/official-dataset-control", "commit": "1f1ad1baef1e1d31817f6c5a12d4d94133611038",
                        "path_pattern": "derived/metadata/asr-ocr-text-v1/{channel}/by-video/{video_id}.json"},
        "code_sha256": sha(Path(__file__)), "source_full_video_hashes": "not_computed_bounded_read_cost",
        "writes": "new disposable output directory only", "source_semantics_reviewed": False, "assets": [],
    }
    if request_packet:
        for field in ("frozen_sample_sha256", "truth_source", "text_source"):
            manifest[field] = request_packet[field]
        manifest["request_manifest_sha256"] = sha(args.request_manifest)
        manifest["selection_rule"] = request_packet["selection_rule"]
        manifest["request_scope"] = request_packet["scope"]
    started = time.monotonic()
    for request in requests:
        source = root / request["video"]
        record = dict(request, source_path=str(source))
        manifest["assets"].append(record)
        try:
            before = source.stat()
            record["source_file"] = {"bytes": before.st_size, "mtime_ns": before.st_mtime_ns}
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries",
                         "stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,time_base,start_time,duration,nb_frames,sample_rate,channels:format=duration,start_time",
                         "-of", "json", str(source)]
            probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=15, check=True)
            record["ffprobe"] = json.loads(probe.stdout)
            if "expected_fps" in request:
                from fractions import Fraction
                actual_fps = float(Fraction(next(s for s in record["ffprobe"]["streams"] if s["codec_type"] == "video")["avg_frame_rate"]))
                if abs(actual_fps - request["expected_fps"]) > 1e-6:
                    raise ValueError("Fresh source FPS differs from the predeclared source timing; do not silently retime the request")
            if request["kind"] == "image":
                filename = f"{request['query_id']}_{source.stem}_frame{request['frame']}.jpg"
                command = ["ffmpeg", "-v", "error", "-nostdin", "-threads", "4", "-i", str(source),
                           "-map", "0:v:0", "-vf", f"select=eq(n\\,{request['frame']})", "-frames:v", "1",
                           "-fps_mode", "vfr", "-q:v", "2", "-an", str(out / filename)]
                record["frame_identity_method"] = "zero-based decoded frame index via ffmpeg select(n); no source timestamp rounding"
                timeout = 85
            else:
                filename = f"{request['query_id']}_{source.stem}_{request['start_s']}-{request['end_s']}s.wav"
                command = ["ffmpeg", "-v", "error", "-nostdin", "-ss", str(request["start_s"]), "-i", str(source),
                           "-map", "0:a:0", "-t", str(request["end_s"] - request["start_s"]), "-vn",
                           "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out / filename)]
                record["audio_rendition"] = "bounded source interval, mono 16kHz PCM WAV; no ASR model"
                timeout = 25
            record["command"] = command
            run = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
            record["returncode"] = run.returncode
            record["stderr"] = run.stderr[-1200:]
            artifact = out / filename
            if run.returncode == 0 and artifact.is_file() and artifact.stat().st_size:
                record.update({"status": "CAPTURED", "artifact": filename, "artifact_sha256": sha(artifact), "artifact_bytes": artifact.stat().st_size})
            else:
                record["status"] = "CAPTURE_FAILED"
            after = source.stat()
            record["source_size_mtime_unchanged"] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
            record.update({"status": "CAPTURE_FAILED", "error": str(exc)[:1200]})
        write_manifest(out / "manifest.json", manifest)
    manifest["elapsed_seconds"] = round(time.monotonic() - started, 3)
    manifest["captured"] = sum(r.get("status") == "CAPTURED" for r in manifest["assets"])
    write_manifest(out / "manifest.json", manifest)
    print(json.dumps({"output_dir": str(out), "captured": manifest["captured"], "requested": len(requests), "elapsed_seconds": manifest["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
