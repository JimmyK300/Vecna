#!/usr/bin/env python3
"""Issue #95: query-independent Gemini oracle-clip caption experiment.

Caption generation intentionally never reads or sends benchmark query text.
Ground truth is used only to select oracle video intervals before captioning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TRUTH_DEFAULT = ROOT.parent / "issue34-current-115" / "ground_truth_current_115.jsonl"
PILOT_DEFAULT = ROOT / "pilot_config.json"
PROMPTS_DIR = ROOT / "prompts"
MANIFEST_DEFAULT = ROOT / "oracle_manifest.jsonl"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mts", ".m2ts"}
PROMPTS = {
    "dense-natural": PROMPTS_DIR / "dense-natural.txt",
    "structured-evidence": PROMPTS_DIR / "structured-evidence.txt",
    "structured-temporal": PROMPTS_DIR / "structured-temporal.txt",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, block: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(block):
            digest.update(chunk)
    return digest.hexdigest()


def prompt_record(name: str) -> dict[str, str]:
    path = PROMPTS[name]
    text = path.read_text(encoding="utf-8").strip()
    return {"name": name, "text": text, "sha256": sha256_bytes(text.encode("utf-8"))}


def _range_seconds(item: dict[str, Any]) -> tuple[float | None, float | None]:
    start = item.get("start_s", item.get("start_time", item.get("start_seconds")))
    end = item.get("end_s", item.get("end_time", item.get("end_seconds")))
    try:
        return (float(start), float(end)) if start is not None and end is not None else (None, None)
    except (TypeError, ValueError):
        return None, None


def oracle_intervals(row: dict[str, Any]) -> list[dict[str, Any]]:
    intervals: list[dict[str, Any]] = []
    accepted_video = row.get("accepted_video_id")
    for item in row.get("accepted_ranges") or []:
        if not isinstance(item, dict):
            continue
        start_s, end_s = _range_seconds(item)
        intervals.append({
            "video_id": item.get("video_id") or accepted_video,
            "start_frame": item.get("start_frame", item.get("start")),
            "end_frame": item.get("end_frame", item.get("end")),
            "start_s": start_s,
            "end_s": end_s,
            "source": "accepted_ranges",
        })
    for group in row.get("accepted_groups") or []:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            start_s, end_s = _range_seconds(item)
            intervals.append({
                "video_id": item.get("video_id") or accepted_video,
                "start_frame": item.get("start_frame", item.get("start")),
                "end_frame": item.get("end_frame", item.get("end")),
                "start_s": start_s,
                "end_s": end_s,
                "source": "accepted_groups",
            })
    # De-duplicate identical intervals while preserving provenance.
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in intervals:
        key = (item["video_id"], item["start_frame"], item["end_frame"], item["start_s"], item["end_s"])
        unique.setdefault(key, item)
    return list(unique.values())


def build_manifest(args: argparse.Namespace) -> None:
    truth_rows = {row["query_id"]: row for row in read_jsonl(args.truth)}
    pilot = json.loads(args.pilot.read_text(encoding="utf-8"))
    tags = pilot.get("capability_tags", {})
    rows: list[dict[str, Any]] = []
    for qid in pilot["query_ids"]:
        truth = truth_rows.get(qid)
        out: dict[str, Any] = {
            "query_id": qid,
            "capability_tags": tags.get(qid, []),
            "eligible": False,
            "eligibility_reason": None,
        }
        if not truth:
            out["eligibility_reason"] = "missing_current_truth_row"
            rows.append(out)
            continue
        out.update({
            "task_type": truth.get("task_type"),
            "truth_tier": truth.get("truth_tier"),
            "truth_authority": truth.get("truth_authority"),
            "accepted_video_id": truth.get("accepted_video_id"),
            "scoreable": bool(truth.get("scoreable")),
        })
        if not truth.get("scoreable"):
            out["eligibility_reason"] = "not_scoreable"
            rows.append(out)
            continue
        intervals = oracle_intervals(truth)
        seconds = [item for item in intervals if item.get("start_s") is not None and item.get("end_s") is not None]
        videos = {item.get("video_id") for item in seconds if item.get("video_id")}
        if not seconds:
            out["eligibility_reason"] = "no_legitimate_interval_with_seconds"
            out["available_intervals"] = intervals
            rows.append(out)
            continue
        if len(videos) != 1:
            out["eligibility_reason"] = "oracle_intervals_span_multiple_videos"
            out["available_intervals"] = intervals
            rows.append(out)
            continue
        start_s = min(float(item["start_s"]) for item in seconds)
        end_s = max(float(item["end_s"]) for item in seconds)
        if not (end_s > start_s >= 0):
            out["eligibility_reason"] = "invalid_oracle_seconds"
            rows.append(out)
            continue
        video_id = next(iter(videos))
        out.update({
            "eligible": True,
            "eligibility_reason": "scoreable_single_video_oracle_interval_with_seconds",
            "video_id": video_id,
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": end_s - start_s,
            "interval_policy": "union_of_all_legitimate_accepted_intervals_with_seconds",
            "intervals": seconds,
        })
        rows.append(out)
    write_jsonl(args.output, rows)
    summary = {
        "schema": "shot-caption-oracle-manifest-v0",
        "pilot_count": len(rows),
        "eligible_count": sum(bool(row.get("eligible")) for row in rows),
        "ineligible": {row["query_id"]: row.get("eligibility_reason") for row in rows if not row.get("eligible")},
        "truth_path": str(args.truth),
        "truth_sha256": sha256_file(args.truth),
        "pilot_path": str(args.pilot),
        "pilot_sha256": sha256_file(args.pilot),
        "query_text_exposed_to_captioner": False,
    }
    (args.output.parent / "oracle_manifest.summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def index_videos(dataset_root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    pattern = re.compile(r"^(L\d+_V\d+)(?:\b|[_-])", re.I)
    for root, _, files in os.walk(dataset_root):
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            match = pattern.match(path.stem)
            if match:
                index.setdefault(match.group(1).upper(), []).append(path)
    return index


def resolve_video(index: dict[str, list[Path]], video_id: str) -> Path:
    matches = sorted(index.get(video_id.upper(), []), key=lambda p: (len(str(p)), str(p).lower()))
    if not matches:
        raise FileNotFoundError(f"no video file found for {video_id}")
    exact = [p for p in matches if p.stem.upper() == video_id.upper()]
    if len(exact) == 1:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    raise RuntimeError(f"ambiguous video files for {video_id}: {[str(p) for p in matches[:10]]}")


def ffmpeg_version(ffmpeg: str) -> str:
    proc = subprocess.run([ffmpeg, "-version"], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.stdout.splitlines()[0] if proc.stdout else "unknown"


def extract_clips(args: argparse.Namespace) -> None:
    if not shutil.which(args.ffmpeg):
        raise RuntimeError(f"ffmpeg not found: {args.ffmpeg}")
    manifest = read_jsonl(args.manifest)
    index = index_videos(args.dataset_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    source_hashes: dict[Path, str] = {}
    for row in manifest:
        if not row.get("eligible"):
            continue
        qid = row["query_id"]
        source = resolve_video(index, row["video_id"])
        if source not in source_hashes:
            source_hashes[source] = sha256_file(source)
        target = args.output_dir / f"{qid}__{row['video_id']}__{row['start_s']:.3f}-{row['end_s']:.3f}.mp4"
        if not target.exists() or args.force:
            cmd = [
                args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{row['start_s']:.6f}", "-to", f"{row['end_s']:.6f}", "-i", str(source),
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target),
            ]
            subprocess.run(cmd, check=True)
        results.append({
            "query_id": qid,
            "video_id": row["video_id"],
            "source_path": str(source),
            "source_size": source.stat().st_size,
            "source_sha256": source_hashes[source],
            "clip_path": str(target),
            "clip_size": target.stat().st_size,
            "clip_sha256": sha256_file(target),
            "start_s": row["start_s"],
            "end_s": row["end_s"],
            "duration_s": row["duration_s"],
            "ffmpeg": ffmpeg_version(args.ffmpeg),
        })
    write_jsonl(args.output_dir / "clips.jsonl", results)
    print(json.dumps({"clips": len(results), "output": str(args.output_dir)}, ensure_ascii=False))


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _jsonable(dump())
        except Exception:
            pass
    return str(value)


def wait_file_ready(client: Any, uploaded: Any, timeout_s: float = 900) -> Any:
    deadline = time.monotonic() + timeout_s
    current = uploaded
    while True:
        state = getattr(current, "state", None)
        state_name = str(getattr(state, "name", state or "")).upper()
        if state_name in {"", "ACTIVE", "READY", "SUCCEEDED"}:
            return current
        if state_name in {"FAILED", "ERROR", "CANCELLED"}:
            raise RuntimeError(f"uploaded Gemini file entered terminal state {state_name}: {current}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Gemini file processing timed out after {timeout_s}s")
        time.sleep(2)
        name = getattr(current, "name", None)
        if not name:
            return current
        current = client.files.get(name=name)


def parse_json_output(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def retryable_api_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in {429, 500, 502, 503, 504}:
        return True
    message = str(exc).lower()
    return isinstance(exc, (TimeoutError, ConnectionError)) or any(
        marker in message for marker in ("error code: 429", "error code: 500", "error code: 502", "error code: 503", "error code: 504", "timed out")
    )


def retry_wait_seconds(exc: Exception, attempt: int, base: float, maximum: float) -> float:
    match = re.search(r"retry in ([0-9.]+)s", str(exc), flags=re.I)
    server_wait = float(match.group(1)) + 1.0 if match else 0.0
    return min(max(server_wait, base * (2 ** (attempt - 1))), maximum)


def caption(args: argparse.Namespace) -> None:
    # Import only in the API stage so manifest/extraction work without the SDK.
    try:
        from google import genai
    except Exception as exc:
        raise RuntimeError("google-genai is required for caption stage: pip install google-genai") from exc
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY must be present in the process environment")

    clip_rows = read_jsonl(args.clips)
    prompt_names = list(PROMPTS) if args.prompt == "all" else [args.prompt]
    prompt_rows = {name: prompt_record(name) for name in prompt_names}
    client = genai.Client()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    uploaded_cache: dict[str, Any] = {}
    completed = 0
    failed = 0

    for clip in clip_rows:
        clip_path = Path(clip["clip_path"])
        clip_sha = clip.get("clip_sha256") or sha256_file(clip_path)
        for name in prompt_names:
            prompt = prompt_rows[name]
            config_identity = {
                "model": args.model,
                "processing": {"type": "static", "fps": args.fps, "resolution": args.resolution},
                "prompt_sha256": prompt["sha256"],
                "clip_sha256": clip_sha,
            }
            cache_key = sha256_bytes(json.dumps(config_identity, sort_keys=True).encode("utf-8"))
            stem = f"{clip['query_id']}__{name}__{cache_key[:16]}"
            target = args.output_dir / f"{stem}.json"
            if target.exists() and not args.force:
                try:
                    existing = json.loads(target.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
                if existing.get("status") == "ok":
                    completed += 1
                    continue
                retry = 1
                while (args.output_dir / f"{stem}__retry-{retry:02d}.json").exists():
                    retry += 1
                target = args.output_dir / f"{stem}__retry-{retry:02d}.json"
            started = time.time()
            record: dict[str, Any] = {
                "schema": "shot-caption-response-v0",
                "query_id": clip["query_id"],
                "caption_model_received_query_text": False,
                "prompt_family": name,
                "prompt_sha256": prompt["sha256"],
                "clip_sha256": clip_sha,
                "clip_path": str(clip_path),
                "model": args.model,
                "processing": {"type": "static", "fps": args.fps, "resolution": args.resolution},
                "cache_key": cache_key,
                "started_at_unix": started,
            }
            attempt_errors: list[dict[str, Any]] = []
            try:
                for attempt in range(1, args.max_attempts + 1):
                    try:
                        if clip_sha not in uploaded_cache:
                            uploaded = client.files.upload(file=str(clip_path))
                            uploaded_cache[clip_sha] = wait_file_ready(client, uploaded, timeout_s=args.upload_timeout)
                        uploaded = uploaded_cache[clip_sha]
                        mime = getattr(uploaded, "mime_type", None) or mimetypes.guess_type(clip_path.name)[0] or "video/mp4"
                        interaction = client.interactions.create(
                            model=args.model,
                            input=[
                                {
                                    "type": "video",
                                    "uri": getattr(uploaded, "uri"),
                                    "mime_type": mime,
                                    "processing": {"type": "static", "fps": args.fps},
                                    "resolution": args.resolution,
                                },
                                {"type": "text", "text": prompt["text"]},
                            ],
                        )
                        text = str(getattr(interaction, "output_text", "") or "")
                        record.update({
                            "status": "ok",
                            "output_text": text,
                            "parsed_json": parse_json_output(text) if name != "dense-natural" else None,
                            "interaction_id": getattr(interaction, "id", None),
                            "usage": _jsonable(getattr(interaction, "usage", None)),
                            "uploaded_file": {
                                "name": getattr(uploaded, "name", None),
                                "uri": getattr(uploaded, "uri", None),
                                "mime_type": mime,
                            },
                        })
                        completed += 1
                        break
                    except Exception as exc:
                        attempt_errors.append({"attempt": attempt, "error_type": type(exc).__name__, "error": str(exc), "at_unix": time.time()})
                        if attempt >= args.max_attempts or not retryable_api_error(exc):
                            raise
                        wait_s = retry_wait_seconds(exc, attempt, args.retry_base_wait, args.retry_max_wait)
                        print(json.dumps({"query_id": clip["query_id"], "prompt": name, "status": "retrying", "attempt": attempt, "wait_s": wait_s}, ensure_ascii=False), flush=True)
                        time.sleep(wait_s)
                if attempt_errors:
                    record["attempt_errors"] = attempt_errors
            except Exception as exc:
                record.update({"status": "error", "error_type": type(exc).__name__, "error": str(exc)})
                record["attempt_errors"] = attempt_errors
                failed += 1
            record["elapsed_s"] = time.time() - started
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps({"query_id": clip["query_id"], "prompt": name, "status": record["status"], "elapsed_s": record["elapsed_s"]}, ensure_ascii=False), flush=True)
            if failed and args.stop_on_error:
                raise RuntimeError(f"caption failure for {clip['query_id']} / {name}: {record.get('error')}")
    print(json.dumps({"completed_or_cached": completed, "failed": failed, "output_dir": str(args.output_dir)}, ensure_ascii=False))


def build_eval_packets(args: argparse.Namespace) -> None:
    """Freeze post-caption judge inputs. Query text appears only in this post-caption stage."""
    decompositions = {row["query_id"]: row for row in read_jsonl(args.decompositions)}
    manifest = {row["query_id"]: row for row in read_jsonl(args.manifest)}
    captions: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(args.caption_dir.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if row.get("status") == "ok":
            captions[(row.get("query_id"), row.get("prompt_family"))] = row
    packets: list[dict[str, Any]] = []
    for (qid, family), cap in sorted(captions.items()):
        decomp = decompositions.get(qid)
        if not decomp:
            continue
        packets.append({
            "query_id": qid,
            "prompt_family": family,
            "capability_tags": decomp.get("capability_tags", []),
            "task_type": manifest.get(qid, {}).get("task_type"),
            "query_text": decomp.get("query_text"),
            "requirements": decomp.get("events", []),
            "caption": cap.get("parsed_json") if cap.get("parsed_json") is not None else cap.get("output_text"),
            "caption_cache_key": cap.get("cache_key"),
            "caption_was_frozen_before_query_join": True,
            "decompositions_sha256": sha256_file(args.decompositions),
        })
    write_jsonl(args.output, packets)
    print(json.dumps({"packets": len(packets), "output": str(args.output)}, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="stage", required=True)

    m = sub.add_parser("build-manifest")
    m.add_argument("--truth", type=Path, default=TRUTH_DEFAULT)
    m.add_argument("--pilot", type=Path, default=PILOT_DEFAULT)
    m.add_argument("--output", type=Path, default=MANIFEST_DEFAULT)
    m.set_defaults(func=build_manifest)

    e = sub.add_parser("extract-clips")
    e.add_argument("--manifest", type=Path, default=MANIFEST_DEFAULT)
    e.add_argument("--dataset-root", type=Path, required=True)
    e.add_argument("--output-dir", type=Path, default=ROOT / "clips")
    e.add_argument("--ffmpeg", default="ffmpeg")
    e.add_argument("--force", action="store_true")
    e.set_defaults(func=extract_clips)

    c = sub.add_parser("caption")
    c.add_argument("--clips", type=Path, default=ROOT / "clips" / "clips.jsonl")
    c.add_argument("--output-dir", type=Path, default=ROOT / "captions")
    c.add_argument("--prompt", choices=["all", *PROMPTS], default="all")
    c.add_argument("--model", default="gemini-3.8-flash")
    c.add_argument("--fps", type=float, default=4.0)
    c.add_argument("--resolution", choices=["low", "medium", "high", "ultra_high"], default="high")
    c.add_argument("--upload-timeout", type=float, default=900)
    c.add_argument("--max-attempts", type=int, default=6)
    c.add_argument("--retry-base-wait", type=float, default=20.0)
    c.add_argument("--retry-max-wait", type=float, default=120.0)
    c.add_argument("--force", action="store_true")
    c.add_argument("--stop-on-error", action="store_true")
    c.set_defaults(func=caption)

    j = sub.add_parser("build-eval-packets")
    j.add_argument("--decompositions", type=Path, required=True)
    j.add_argument("--manifest", type=Path, default=MANIFEST_DEFAULT)
    j.add_argument("--caption-dir", type=Path, default=ROOT / "captions")
    j.add_argument("--output", type=Path, default=ROOT / "eval_packets.jsonl")
    j.set_defaults(func=build_eval_packets)
    return p


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
