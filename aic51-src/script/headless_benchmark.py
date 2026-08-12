#!/usr/bin/env python3
"""Vecna headless one-shot retrieval benchmark.

The benchmark calls the same Searcher used by the current UI backend, without
starting FastAPI or the frontend. Text cases are executed once per cumulative
hint level:

    query
    query + hint_1
    query + hint_1 + hint_2
    ...

The canonical Issue #34 dataset contains mixed task types. TKIS/QA rows may use
interval, point, or video-level ground truth. TRAKE rows may contain several
event points and are scored as event recall. VKIS rows are retained in the CSV,
but the current backend has no external-video-query API; they are reported as
unsupported rather than silently mis-scored.

Example:
    python script/headless_benchmark.py \
        --csv benchmark/issue34_headless_queries.csv \
        --top-k 10
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
ANSWER_ALT_RE = re.compile(r"^answer_alt_(\d+)$", re.I)
VIDEO_ID_RE = re.compile(r"(?i)(?:L\d+_)?V\d+")
INT_RE = re.compile(r"-?\d+")
VIDEO_SUFFIXES = (".mp4", ".mkv", ".avi", ".mov", ".webm")


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def as_bool(value: Any, default: bool = True) -> bool:
    text = clean(value).lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def normalize_video_id(value: Any) -> str:
    text = Path(clean(value)).name.lower()
    for suffix in VIDEO_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    matches = VIDEO_ID_RE.findall(text)
    return matches[-1].lower() if matches else text


def parse_answer_string(raw: str, task_type: str, query_id: str) -> list[dict[str, Any]]:
    raw = clean(raw)
    if not raw:
        return []

    matches = list(VIDEO_ID_RE.finditer(raw))
    if not matches:
        raise ValueError(f"{query_id}: cannot find video id in answer {raw!r}")
    vm = matches[-1]
    video_id = vm.group(0)
    suffix = raw[vm.end():].strip()

    m = re.match(r"^\s*-\s*(\d+)\s*(?:->|→|to|–|—)\s*(\d+)\s*$", suffix, re.I)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return [{"video_id": video_id, "kind": "interval", "start": min(a, b), "end": max(a, b)}]

    m = re.match(r"^\s*-\s*(\d+(?:\s*,\s*\d+)+)\s*$", suffix)
    if m:
        points = [int(x.strip()) for x in m.group(1).split(",")]
        return [{"video_id": video_id, "kind": "point", "frame": p} for p in points]

    m = re.match(r"^\s*-\s*(\d+)\s*-\s*(.+?)\s*$", suffix, re.S)
    if m:
        return [{
            "video_id": video_id,
            "kind": "point",
            "frame": int(m.group(1)),
            "answer_text": m.group(2).strip(),
        }]

    m = re.match(r"^\s*-\s*(\d+)\s*$", suffix)
    if m:
        return [{"video_id": video_id, "kind": "point", "frame": int(m.group(1))}]

    prefix = raw[:vm.start()].strip("- ")
    answer_text = ""
    if task_type == "qa":
        answer_text = re.sub(r"(?i)^QA[-\s]*", "", prefix).strip("- ")
    target = {"video_id": video_id, "kind": "video"}
    if answer_text:
        target["answer_text"] = answer_text
    return [target]


def load_cases(path: Path, expected_count: int, allow_incomplete: bool) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header")

        hint_cols = sorted(
            ((int(m.group(1)), name) for name in reader.fieldnames if (m := HINT_RE.match(name.strip()))),
            key=lambda x: x[0],
        )
        alt_cols = sorted(
            ((int(m.group(1)), name) for name in reader.fieldnames if (m := ANSWER_ALT_RE.match(name.strip()))),
            key=lambda x: x[0],
        )

        cases: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row_num, row in enumerate(reader, start=2):
            qid = clean(row.get("query_id") or row.get("id")) or f"q_{row_num - 1:03d}"
            if qid in seen:
                raise ValueError(f"duplicate query_id: {qid}")
            seen.add(qid)

            task_type = clean(row.get("task_type")).lower() or "tkis"
            query_mode = clean(row.get("query_mode")).lower() or "text"
            query = clean(row.get("query") or row.get("question"))
            media_file = clean(row.get("media_file") or row.get("media_path"))
            if query_mode == "text" and not query:
                raise ValueError(f"{qid}: missing text query")
            if query_mode == "media" and not media_file:
                raise ValueError(f"{qid}: media query requires media_file")

            hints = [clean(row.get(name)) for _, name in hint_cols if clean(row.get(name))]
            answer_strings = []
            main_answer = clean(row.get("answer") or row.get("key") or row.get("ground_truth"))
            if main_answer:
                answer_strings.append(main_answer)
            answer_strings.extend(clean(row.get(name)) for _, name in alt_cols if clean(row.get(name)))

            scoreable = as_bool(row.get("scoreable"), default=bool(answer_strings))
            if scoreable and not answer_strings:
                raise ValueError(f"{qid}: scoreable=true but no answer is present")

            accepted_groups: list[list[dict[str, Any]]] = []
            for answer in answer_strings:
                targets = parse_answer_string(answer, task_type, qid)
                if targets:
                    accepted_groups.append(targets)

            target_mode = "events" if task_type == "trake" and len(accepted_groups) == 1 else "any"

            cases.append({
                "query_id": qid,
                "source": clean(row.get("source")),
                "source_question_number": clean(row.get("source_question_number")),
                "task_type": task_type,
                "query_mode": query_mode,
                "query": query,
                "hints": hints,
                "media_file": media_file,
                "scoreable": scoreable,
                "answer_strings": answer_strings,
                "accepted_groups": accepted_groups,
                "target_mode": target_mode,
                "notes": clean(row.get("notes")),
            })

    if len(cases) != expected_count:
        msg = f"loaded {len(cases)} questions; expected {expected_count}"
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


def target_matches(record: Any, target: dict[str, Any], point_tolerance: int) -> bool:
    video, frame, timeline, _ = unpack_result(record)
    if normalize_video_id(video) != normalize_video_id(target["video_id"]):
        return False
    if target["kind"] == "video":
        return True
    frames = timeline or ([] if frame is None else [frame])
    if target["kind"] == "interval":
        return any(target["start"] <= f <= target["end"] for f in frames)
    if target["kind"] == "point":
        return any(abs(f - target["frame"]) <= point_tolerance for f in frames)
    raise ValueError(f"unknown target kind: {target['kind']}")


def group_match_ranks(results: list[Any], group: list[dict[str, Any]], point_tolerance: int) -> list[int | None]:
    return [
        next(
            (rank for rank, record in enumerate(results, 1) if target_matches(record, target, point_tolerance)),
            None,
        )
        for target in group
    ]


def metrics_for_results(results: list[Any], case: dict[str, Any], point_tolerance: int) -> dict[str, Any]:
    if not case["scoreable"]:
        return {
            "first_correct_rank": None,
            "recall_at_1": None,
            "recall_at_5": None,
            "recall_at_10": None,
            "all_targets_hit_at_10": None,
            "target_ranks": [],
        }

    group_ranks = [group_match_ranks(results, group, point_tolerance) for group in case["accepted_groups"]]
    if not group_ranks:
        raise ValueError(f"{case['query_id']}: no parsed ground-truth targets")

    if case["target_mode"] == "events":
        ranks = group_ranks[0]

        def recall(k: int) -> float:
            return sum(r is not None and r <= k for r in ranks) / len(ranks)

        first = min((r for r in ranks if r is not None), default=None)
        return {
            "first_correct_rank": first,
            "recall_at_1": recall(1),
            "recall_at_5": recall(5),
            "recall_at_10": recall(10),
            "all_targets_hit_at_10": all(r is not None and r <= 10 for r in ranks),
            "target_ranks": ranks,
        }

    flat = [r for ranks in group_ranks for r in ranks]
    first = min((r for r in flat if r is not None), default=None)

    def hit(k: int) -> float:
        return 1.0 if any(r is not None and r <= k for r in flat) else 0.0

    return {
        "first_correct_rank": first,
        "recall_at_1": hit(1),
        "recall_at_5": hit(5),
        "recall_at_10": hit(10),
        "all_targets_hit_at_10": hit(10) == 1.0,
        "target_ranks": group_ranks,
    }


def serialize_result(record: Any, rank: int, case: dict[str, Any], point_tolerance: int) -> dict[str, Any]:
    video, frame, timeline, entity = unpack_result(record)
    matches_any = any(
        target_matches(record, target, point_tolerance)
        for group in case["accepted_groups"]
        for target in group
    ) if case["scoreable"] else None
    return {
        "rank": rank,
        "video_id": video,
        "frame_id": frame,
        "time_line": timeline,
        "distance": get_field(record, "distance"),
        "scores": get_field(record, "scores"),
        "ocr": get_field(entity, "ocr", ""),
        "asr": get_field(entity, "asr", ""),
        "matches_ground_truth": matches_any,
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


def run_text_variant(searcher: Any, case: dict[str, Any], hint_count: int, args: argparse.Namespace, features: list[str]) -> dict[str, Any]:
    query = "\n".join([case["query"], *case["hints"][:hint_count]])
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
    metrics = metrics_for_results(results, case, args.point_tolerance_frames)
    return {
        "query_id": case["query_id"],
        "task_type": case["task_type"],
        "query_mode": "text",
        "status": "scored" if case["scoreable"] else "unscored_missing_ground_truth",
        "hint_count": hint_count,
        "query_text": query,
        "hints_used": case["hints"][:hint_count],
        "answers": case["answer_strings"],
        "target_mode": case["target_mode"],
        **metrics,
        "latency_ms": round(latency_ms, 3),
        "top_results": [serialize_result(r, i, case, args.point_tolerance_frames) for i, r in enumerate(results, 1)],
    }


def unsupported_record(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_id": case["query_id"],
        "task_type": case["task_type"],
        "query_mode": case["query_mode"],
        "status": "unsupported_external_media_query",
        "hint_count": 0,
        "query_text": "",
        "media_file": case["media_file"],
        "answers": case["answer_strings"],
        "first_correct_rank": None,
        "recall_at_1": None,
        "recall_at_5": None,
        "recall_at_10": None,
        "all_targets_hit_at_10": None,
        "target_ranks": [],
        "latency_ms": None,
        "top_results": [],
    }


def summarize(records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in records if r["status"] == "scored"]
    groups: dict[int, list[dict[str, Any]]] = {}
    for record in scored:
        groups.setdefault(record["hint_count"], []).append(record)

    by_hint = {}
    for hint_count, group in sorted(groups.items()):
        ranks = [r["first_correct_rank"] for r in group if r["first_correct_rank"] is not None]
        by_hint[str(hint_count)] = {
            "scored_variants": len(group),
            "mean_recall_at_1": round(sum(r["recall_at_1"] for r in group) / len(group), 6),
            "mean_recall_at_5": round(sum(r["recall_at_5"] for r in group) / len(group), 6),
            "mean_recall_at_10": round(sum(r["recall_at_10"] for r in group) / len(group), 6),
            "mrr_first_target": round(
                sum((1 / r["first_correct_rank"]) if r["first_correct_rank"] else 0 for r in group) / len(group),
                6,
            ),
            "median_first_correct_rank": median(ranks) if ranks else None,
            "mean_latency_ms": round(sum(r["latency_ms"] for r in group) / len(group), 3),
        }

    return {
        "dataset": {
            "questions_loaded": len(cases),
            "scoreable_questions": sum(c["scoreable"] for c in cases),
            "text_questions": sum(c["query_mode"] == "text" for c in cases),
            "scoreable_text_questions": sum(c["query_mode"] == "text" and c["scoreable"] for c in cases),
            "media_questions": sum(c["query_mode"] == "media" for c in cases),
            "unscoreable_questions": [c["query_id"] for c in cases if not c["scoreable"]],
            "unsupported_media_questions": [c["query_id"] for c in cases if c["query_mode"] == "media"],
        },
        "by_hint_count": by_hint,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Headless one-shot retrieval benchmark for Vecna")
    p.add_argument("--csv", required=True, type=Path)
    p.add_argument("--output", type=Path, default=Path("benchmark-results/headless_results.jsonl"))
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--expected-count", type=int, default=42)
    p.add_argument("--allow-incomplete", action="store_true")
    p.add_argument("--target-features", default="")
    p.add_argument("--nprobe", type=int, default=32)
    p.add_argument("--temporal-k", type=int, default=10000)
    p.add_argument("--ocr-weight", type=float, default=0.5)
    p.add_argument("--asr-weight", type=float, default=0.0)
    p.add_argument("--max-interval", type=int, default=1000)
    p.add_argument(
        "--point-tolerance-frames",
        type=int,
        default=0,
        help="Tolerance for point-labelled QA/TRAKE answers; default is exact-frame matching.",
    )
    p.add_argument("--auto-translate", action="store_true")
    p.add_argument("--en-to-vi-translate", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.top_k < 10:
        raise ValueError("--top-k must be >= 10 because this benchmark reports Recall@10")
    if args.point_tolerance_frames < 0:
        raise ValueError("--point-tolerance-frames must be >= 0")

    cases = load_cases(args.csv, args.expected_count, args.allow_incomplete)
    print(
        f"Loaded {len(cases)} questions: "
        f"{sum(c['query_mode'] == 'text' for c in cases)} text, "
        f"{sum(c['query_mode'] == 'media' for c in cases)} media, "
        f"{sum(c['scoreable'] for c in cases)} scoreable"
    )

    text_cases = [c for c in cases if c["query_mode"] == "text"]
    searcher = setup_searcher() if text_cases else None
    features = choose_features(searcher, args.target_features) if searcher else []
    print(f"Features: {features}")
    print(
        f"Params: top_k={args.top_k} nprobe={args.nprobe} temporal_k={args.temporal_k} "
        f"ocr={args.ocr_weight} asr={args.asr_weight} max_interval={args.max_interval} "
        f"point_tolerance_frames={args.point_tolerance_frames}"
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    with args.output.open("w", encoding="utf-8", newline="\n") as out:
        for index, case in enumerate(cases, 1):
            if case["query_mode"] != "text":
                record = unsupported_record(case)
                records.append(record)
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(
                    f"[{index:02d}/{len(cases):02d}] {case['query_id']} "
                    f"UNSUPPORTED external media query ({case['media_file']})"
                )
                continue

            for hint_count in range(len(case["hints"]) + 1):
                record = run_text_variant(searcher, case, hint_count, args, features)
                records.append(record)
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                rank = record["first_correct_rank"] or "-"
                recall10 = record["recall_at_10"]
                r10 = "-" if recall10 is None else f"{recall10:.3f}"
                print(
                    f"[{index:02d}/{len(cases):02d}] {case['query_id']} "
                    f"hints={hint_count} status={record['status']} "
                    f"rank={rank} R@10={r10} latency={record['latency_ms']:.1f}ms"
                )

    summary_data = summarize(records, cases)
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expected_question_count": args.expected_count,
        "top_k": args.top_k,
        "target_features": features,
        "params": {
            "nprobe": args.nprobe,
            "temporal_k": args.temporal_k,
            "ocr_weight": args.ocr_weight,
            "asr_weight": args.asr_weight,
            "max_interval": args.max_interval,
            "point_tolerance_frames": args.point_tolerance_frames,
            "auto_translate": args.auto_translate,
            "en_to_vi_translate": args.en_to_vi_translate,
        },
        **summary_data,
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.output}")
    print(f"Summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
