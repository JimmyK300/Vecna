#!/usr/bin/env python3
"""Vecna headless retrieval benchmark.

Uses the same Searcher initialization as the UI backend, but does not start FastAPI
or the frontend. For every CSV row it runs independent one-shot retrieval for:
question only, question+hint_1, ..., question+hint_1+...+hint_N.

Example:
  python script/headless_benchmark.py --csv benchmark/questions.csv --top-k 10
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aic51.packages.webui.backend.search import setup_searcher  # noqa: E402

HINT_RE = re.compile(r"^hint_(\d+)$", re.I)
ANSWER_RE = re.compile(
    r"^\s*(?P<video>.+?)-(?P<start>\d+)\s*(?:->|→|to|–|—)\s*(?P<end>\d+)\s*$",
    re.I,
)
INT_RE = re.compile(r"-?\d+")
VIDEO_SUFFIXES = (".mp4", ".mkv", ".avi", ".mov", ".webm")


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_answer(row: dict[str, str], query_id: str) -> tuple[str, int, int]:
    video = clean(row.get("answer_video_id") or row.get("correct_video_id"))
    start = clean(row.get("answer_start_frame") or row.get("correct_start_frame"))
    end = clean(row.get("answer_end_frame") or row.get("correct_end_frame"))
    if video and start and end:
        try:
            a, b = int(float(start)), int(float(end))
        except ValueError as exc:
            raise ValueError(f"{query_id}: invalid answer frame range") from exc
        return video, min(a, b), max(a, b)

    raw = clean(row.get("answer") or row.get("key") or row.get("ground_truth"))
    match = ANSWER_RE.match(raw)
    if match:
        a, b = int(match.group("start")), int(match.group("end"))
        return match.group("video").strip(), min(a, b), max(a, b)

    raise ValueError(
        f"{query_id}: need answer_video_id + answer_start_frame + answer_end_frame, "
        "or answer like 'TKIS-V003-10090 -> 12029'"
    )


def load_cases(path: Path, expected_count: int, allow_incomplete: bool) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header")
        hints = sorted(
            ((int(m.group(1)), name) for name in reader.fieldnames if (m := HINT_RE.match(name.strip()))),
            key=lambda x: x[0],
        )
        cases, seen = [], set()
        for row_num, row in enumerate(reader, start=2):
            qid = clean(row.get("query_id") or row.get("id")) or f"q_{row_num - 1:03d}"
            if qid in seen:
                raise ValueError(f"duplicate query_id: {qid}")
            seen.add(qid)
            question = clean(row.get("question") or row.get("query"))
            if not question:
                raise ValueError(f"{qid}: missing question/query")
            video, start, end = parse_answer(row, qid)
            cases.append(
                {
                    "query_id": qid,
                    "question": question,
                    "hints": [clean(row.get(name)) for _, name in hints if clean(row.get(name))],
                    "answer_video_id": video,
                    "answer_start_frame": start,
                    "answer_end_frame": end,
                    "answer_text": clean(row.get("answer_text")),
                }
            )

    if len(cases) != expected_count:
        msg = f"loaded {len(cases)} questions; expected {expected_count} (Issue #34 has 20 + 20 = 40)"
        if not allow_incomplete:
            raise ValueError(msg + ". Use --allow-incomplete only for intentional partial runs.")
        print(f"WARNING: {msg}", file=sys.stderr)
    return cases


def get_field(obj: Any, key: str, default: Any = None) -> Any:
    try:
        getter = getattr(obj, "get", None)
        if getter is not None:
            return getter(key, default)
    except Exception:
        pass
    try:
        return obj[key]
    except Exception:
        return default


def frame_number(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    matches = INT_RE.findall(clean(value))
    return int(matches[-1]) if matches else None


def normalize_video_id(value: Any) -> str:
    text = Path(clean(value)).name.lower()
    for suffix in VIDEO_SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def unpack_result(record: Any) -> tuple[str, int | None, list[int], Any]:
    entity = get_field(record, "entity", {}) or {}
    raw_id = clean(get_field(entity, "frame_id", ""))
    video, raw_frame = "", raw_id
    if "#" in raw_id:
        video, raw_frame = raw_id.split("#", 1)
    else:
        video = clean(get_field(entity, "video_id", ""))
    frame = frame_number(raw_frame)
    timeline = [
        n for n in (frame_number(v) for v in (get_field(record, "time_line", []) or [])) if n is not None
    ]
    if not timeline and frame is not None:
        timeline = [frame]
    return video, frame, timeline, entity


def is_correct(record: Any, case: dict[str, Any]) -> bool:
    video, frame, timeline, _ = unpack_result(record)
    if normalize_video_id(video) != normalize_video_id(case["answer_video_id"]):
        return False
    frames = timeline or ([] if frame is None else [frame])
    return any(case["answer_start_frame"] <= f <= case["answer_end_frame"] for f in frames)


def serialize_result(record: Any, rank: int, case: dict[str, Any]) -> dict[str, Any]:
    video, frame, timeline, entity = unpack_result(record)
    return {
        "rank": rank,
        "video_id": video,
        "frame_id": frame,
        "time_line": timeline,
        "distance": get_field(record, "distance"),
        "scores": get_field(record, "scores"),
        "ocr": get_field(entity, "ocr", ""),
        "asr": get_field(entity, "asr", ""),
        "correct": is_correct(record, case),
    }


def choose_features(searcher: Any, requested: str) -> list[str]:
    available = list(searcher.target_features)
    if requested.strip():
        selected = [x.strip() for x in requested.split(",") if x.strip()]
        unknown = [x for x in selected if x not in available]
        if unknown:
            raise ValueError(f"unknown target features {unknown}; available={available}")
        return selected
    selected = [f for f in available if "clip" in f.lower() or "siglip" in f.lower()]
    return selected or available


def run_variant(searcher: Any, case: dict[str, Any], hint_count: int, args: argparse.Namespace, features: list[str]) -> dict[str, Any]:
    query = "\n".join([case["question"], *case["hints"][:hint_count]])
    started = time.perf_counter()
    raw = searcher.search_multimodal(
        query,
        0,
        args.top_k,
        features,
        nprobe=args.nprobe,
        temporal_k=args.temporal_k,
        ocr_weight=args.ocr_weight,
        asr_weight=args.asr_weight,
        max_interval=args.max_interval,
        selected=None,
        auto_translate=args.auto_translate,
        en_to_vi_translate=args.en_to_vi_translate,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    results = list(raw.get("results", []))[: args.top_k]
    rank = next((i for i, r in enumerate(results, 1) if is_correct(r, case)), None)
    return {
        "query_id": case["query_id"],
        "hint_count": hint_count,
        "query_text": query,
        "hints_used": case["hints"][:hint_count],
        "answer": {
            "video_id": case["answer_video_id"],
            "start_frame": case["answer_start_frame"],
            "end_frame": case["answer_end_frame"],
            "answer_text": case["answer_text"],
        },
        "first_correct_rank": rank,
        "hit_at_1": rank is not None and rank <= 1,
        "hit_at_5": rank is not None and rank <= 5,
        "hit_at_10": rank is not None and rank <= 10,
        "latency_ms": round(latency_ms, 3),
        "top_results": [serialize_result(r, i, case) for i, r in enumerate(results, 1)],
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(record["hint_count"], []).append(record)
    out = {}
    for hint_count, group in sorted(groups.items()):
        ranks = [r["first_correct_rank"] for r in group if r["first_correct_rank"] is not None]
        out[str(hint_count)] = {
            "queries": len(group),
            "hit_at_1": round(sum(r["hit_at_1"] for r in group) / len(group), 6),
            "hit_at_5": round(sum(r["hit_at_5"] for r in group) / len(group), 6),
            "hit_at_10": round(sum(r["hit_at_10"] for r in group) / len(group), 6),
            "mrr": round(sum((1 / r["first_correct_rank"]) if r["first_correct_rank"] else 0 for r in group) / len(group), 6),
            "median_correct_rank": median(ranks) if ranks else None,
            "mean_latency_ms": round(sum(r["latency_ms"] for r in group) / len(group), 3),
        }
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Headless one-shot retrieval benchmark for Vecna")
    p.add_argument("--csv", required=True, type=Path)
    p.add_argument("--output", type=Path, default=Path("benchmark-results/headless_results.jsonl"))
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--expected-count", type=int, default=40)
    p.add_argument("--allow-incomplete", action="store_true")
    p.add_argument("--target-features", default="")
    p.add_argument("--nprobe", type=int, default=32)
    p.add_argument("--temporal-k", type=int, default=10000)
    p.add_argument("--ocr-weight", type=float, default=0.5)
    p.add_argument("--asr-weight", type=float, default=0.0)
    p.add_argument("--max-interval", type=int, default=1000)
    p.add_argument("--auto-translate", action="store_true")
    p.add_argument("--en-to-vi-translate", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.top_k < 10:
        raise ValueError("--top-k must be >= 10 because this benchmark reports Hit@10")
    cases = load_cases(args.csv, args.expected_count, args.allow_incomplete)
    print(f"Loaded {len(cases)} questions")
    print("Hint distribution:", {n: sum(len(c["hints"]) == n for c in cases) for n in sorted({len(c["hints"]) for c in cases})})

    searcher = setup_searcher()
    features = choose_features(searcher, args.target_features)
    print(f"Features: {features}")
    print(f"Params: top_k={args.top_k} nprobe={args.nprobe} temporal_k={args.temporal_k} ocr={args.ocr_weight} asr={args.asr_weight} max_interval={args.max_interval}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    with args.output.open("w", encoding="utf-8", newline="\n") as out:
        for index, case in enumerate(cases, 1):
            for hint_count in range(len(case["hints"]) + 1):
                record = run_variant(searcher, case, hint_count, args, features)
                records.append(record)
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                rank = record["first_correct_rank"] or "-"
                print(f"[{index:02d}/{len(cases):02d}] {case['query_id']} hints={hint_count} rank={rank} latency={record['latency_ms']:.1f}ms")

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question_count": len(cases),
        "expected_question_count": args.expected_count,
        "top_k": args.top_k,
        "target_features": features,
        "params": {
            "nprobe": args.nprobe,
            "temporal_k": args.temporal_k,
            "ocr_weight": args.ocr_weight,
            "asr_weight": args.asr_weight,
            "max_interval": args.max_interval,
            "auto_translate": args.auto_translate,
            "en_to_vi_translate": args.en_to_vi_translate,
        },
        "by_hint_count": summarize(records),
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.output}")
    print(f"Summary: {summary_path}")
    print(json.dumps(summary["by_hint_count"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
