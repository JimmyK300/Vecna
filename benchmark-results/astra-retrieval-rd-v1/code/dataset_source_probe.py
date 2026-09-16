#!/usr/bin/env python3
"""Read-only, query-bounded host parity/native-evidence probe; JSON to stdout.

Example:
  python dataset_source_probe.py --dataset-root D:/Official-Dataset \
      --requests host_probe_requests.json --query-ids p0_q19,p0_q21,p1_q17

The request file is generated from the frozen sample by dataset_text_audit.py.
No corpus traversal, feature generation, index query, or data mutation occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(root, relative):
    rel = PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts or ":" in relative:
        raise ValueError("Expected a safe dataset-relative path")
    return root.joinpath(*rel.parts)


def native_listing(directory):
    if not directory.is_dir():
        return {"path": str(directory), "exists": False}
    paths = sorted(directory.glob("*.json"))
    return {"path": str(directory), "exists": True, "json_count": len(paths),
            "first_five": [{"path": str(p), "bytes": p.stat().st_size} for p in paths[:5]]}


def probe(packet, dataset_root, query_ids=None, do_ffprobe=False):
    root = Path(dataset_root)
    original = packet["requests"]
    counts = {c: len({r["query_id"] for r in original if r["channel"] == c}) for c in ("ocr", "asr")}
    if counts != {"ocr": 20, "asr": 18}:
        raise ValueError("Expected the unchanged 20-OCR / 18-ASR frozen sample")
    if query_ids is not None and not set(query_ids) <= {r["query_id"] for r in original}:
        raise ValueError("Requested query is outside the frozen sample")
    requests = [r for r in original if query_ids is None or r["query_id"] in query_ids]
    results = []
    feature_dirs = {}
    video_probes = {}
    try:
        import numpy as np
    except ImportError:
        np = None
    for request in requests:
        if request["channel"] not in {"ocr", "asr"}:
            raise ValueError("Only OCR/ASR is permitted")
        metadata = safe_path(root, request["metadata_relative_path"])
        video = safe_path(root, request["video_relative_path"])
        features = safe_path(root, request["feature_relative_dir"])
        row = {"query_id": request["query_id"], "channel": request["channel"], "video_id": request["video_id"],
               "metadata_path": str(metadata), "metadata_exists": metadata.is_file(),
               "metadata_sha256": file_sha(metadata) if metadata.is_file() else None,
               "expected_metadata_sha256": request["expected_metadata_sha256"],
               "video_path": str(video), "video_exists": video.is_file(),
               "video_bytes": video.stat().st_size if video.is_file() else None,
               "feature_dir": str(features), "feature_dir_exists": features.is_dir(),
               "source_fps_from_archived_probe": request["known_fps"],
               "native_evidence": native_listing(safe_path(root, request["native_evidence_relative_dir"])),
               "native_analysis": native_listing(safe_path(root, request["native_analysis_relative_dir"])),
               "feature_reads": []}
        row["metadata_matches_pinned_archive"] = row["metadata_sha256"] == request["expected_metadata_sha256"]
        if features.is_dir():
            if str(features) not in feature_dirs:
                numbered = sorted((int(p.name), p) for p in features.iterdir() if p.is_dir() and p.name.isdigit())
                if len(numbered) > 10000:
                    raise ValueError("Per-video frame-directory bound exceeded")
                feature_dirs[str(features)] = numbered
            numbered = feature_dirs[str(features)]
            row["observed_feature_frame_count"] = len(numbered)
            selected = set()
            for anchor in request["probe_anchor_frames"][:2]:
                if not numbered:
                    break
                frame_idx, frame_dir = min(numbered, key=lambda pair: (abs(pair[0] - anchor), pair[0]))
                if frame_idx in selected:
                    continue
                selected.add(frame_idx)
                path = frame_dir / (request["channel"] + ".npy")
                frame = {"requested_anchor": anchor, "actual_feature_frame": frame_idx,
                         "frame_offset": frame_idx - anchor, "path": str(path), "exists": path.is_file()}
                if path.is_file():
                    frame["sha256"] = file_sha(path)
                    if np is None:
                        frame["text_read_status"] = "numpy_unavailable"
                    else:
                        try:
                            array = np.load(path, allow_pickle=False)
                            text = str(array.reshape(-1)[0]) if array.size else ""
                            frame.update({"dtype": str(array.dtype), "shape": list(array.shape),
                                          "text": text[:500], "text_chars": len(text),
                                          "text_truncated": len(text) > 500, "text_read_status": "read"})
                        except (ValueError, OSError) as exc:
                            frame["text_read_status"] = type(exc).__name__ + ": " + str(exc)[:200]
                row["feature_reads"].append(frame)
        if do_ffprobe and video.is_file():
            if str(video) not in video_probes:
                try:
                    process = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                              "stream=r_frame_rate,avg_frame_rate,time_base,start_time,nb_frames,width,height",
                                              "-of", "json", str(video)], capture_output=True, text=True, timeout=15, check=False)
                    video_probes[str(video)] = json.loads(process.stdout) if process.returncode == 0 else {"error": process.stderr[:300]}
                except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                    video_probes[str(video)] = {"error": str(exc)[:300]}
            row["fresh_ffprobe"] = video_probes[str(video)]
        results.append(row)
    return {"frozen_sample_sha256": packet["frozen_sample_sha256"], "scope": "readonly exact per-query paths; at most two feature files per channel/query",
            "source_media_semantics_reviewed": False, "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--requests", required=True, help="Request JSON path, or - for stdin")
    parser.add_argument("--query-ids", default=None)
    parser.add_argument("--ffprobe", action="store_true")
    args = parser.parse_args()
    packet = json.load(sys.stdin) if args.requests == "-" else json.loads(Path(args.requests).read_text(encoding="utf-8"))
    query_ids = set(args.query_ids.split(",")) if args.query_ids else None
    print(json.dumps(probe(packet, args.dataset_root, query_ids, args.ffprobe), ensure_ascii=False))


if __name__ == "__main__":
    main()
