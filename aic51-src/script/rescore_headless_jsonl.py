#!/usr/bin/env python3
"""Re-judge stored headless JSONL with the timestamp retrieval matcher.

Does not re-run search. Canonical answers are unchanged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import headless_benchmark as hb  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rescore stored headless JSONL with ±2s timestamp matching")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fps-csv", type=Path, default=hb.DEFAULT_FPS_TABLE)
    parser.add_argument("--point-tolerance-seconds", type=float, default=hb.DEFAULT_RETRIEVAL_POINT_TOLERANCE_SECONDS)
    parser.add_argument("--official-point-tolerance-frames", type=int, default=hb.DEFAULT_OFFICIAL_POINT_TOLERANCE_FRAMES)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--answers-from",
        type=Path,
        default=None,
        help="JSONL with official answers if the input rows omit them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"missing input {args.input}")
    if args.output.exists() and not args.overwrite:
        raise SystemExit(f"refusing to overwrite {args.output}")
    config = hb.MatchConfig(
        fps_by_video=hb.load_fps_table(args.fps_csv),
        retrieval_point_tolerance_seconds=args.point_tolerance_seconds,
        official_point_tolerance_frames=args.official_point_tolerance_frames,
    )
    answers_by_id: dict[str, list] = {}
    if args.answers_from and args.answers_from.exists():
        with args.answers_from.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                src = json.loads(line)
                if src.get("answers"):
                    answers_by_id[src["query_id"]] = src["answers"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with args.input.open(encoding="utf-8") as fh, args.output.open("w", encoding="utf-8", newline="\n") as out:
        for line in fh:
            if not line.strip():
                continue
            raw = json.loads(line)
            if not raw.get("answers") and raw.get("query_id") in answers_by_id:
                raw["answers"] = answers_by_id[raw["query_id"]]
            rec = hb.rescore_stored_record(raw, config)
            records.append(rec)
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Rebuild a lightweight summary from the stored records (no CSV inventory required).
    official_ids = [f"p1_q{i:02d}" for i in range(2, 21)]
    primary = [
        rec
        for rec in records
        if rec.get("recall_at_20") is not None
        and rec.get("is_primary_baseline", True)
        and rec.get("query_mode", "text") in ("text", None)
        and not str(rec.get("status") or "").startswith("unsupported")
    ]
    # Prefer Q0 when the file contains hint variants
    q0 = [rec for rec in primary if rec.get("condition") in (None, "Q0")]
    if q0:
        primary = q0
    n19 = [rec for rec in primary if rec.get("query_id") in official_ids]

    def agg(group: list[dict]) -> dict:
        n = len(group)
        if not n:
            return {"n": 0}
        return {
            "n": n,
            "recall_at_1": sum(float(r["recall_at_1"] or 0) for r in group) / n,
            "recall_at_5": sum(float(r["recall_at_5"] or 0) for r in group) / n,
            "recall_at_10": sum(float(r["recall_at_10"] or 0) for r in group) / n,
            "recall_at_20": sum(float(r["recall_at_20"] or 0) for r in group) / n,
            "mrr": sum(float(r["reciprocal_rank"] or 0) for r in group) / n,
            "no_hit_within_20": sum(1 for r in group if r.get("no_hit_within_20")),
            "official_r20": sum(1 for r in group if r.get("official_tolerance_hit")) / n,
        }

    per_query = []
    for rec in n19 or primary:
        per_query.append({
            "query_id": rec.get("query_id"),
            "task_type": rec.get("task_type"),
            "first_correct_rank": rec.get("first_correct_rank"),
            "official_first_correct_rank": rec.get("official_first_correct_rank"),
            "retrieval_hit_2s": rec.get("retrieval_hit_2s"),
            "official_tolerance_hit": rec.get("official_tolerance_hit"),
            "nearest_gold_delta_frames": rec.get("nearest_gold_delta_frames"),
            "nearest_gold_delta_seconds": rec.get("nearest_gold_delta_seconds"),
            "recall_at_20": rec.get("recall_at_20"),
            "reciprocal_rank": rec.get("reciprocal_rank"),
            "target_ranks": rec.get("target_ranks"),
            "no_hit_within_20": rec.get("no_hit_within_20"),
        })

    summary = {
        "source_jsonl": str(args.input.resolve()),
        "output_jsonl": str(args.output.resolve()),
        "match_contract": {
            "retrieval_point_tolerance_seconds": config.retrieval_point_tolerance_seconds,
            "official_point_tolerance_frames": config.official_point_tolerance_frames,
            "fps_csv": str(args.fps_csv),
            "fps_rows": len(config.fps_by_video),
            "tkis": "inclusive interval membership",
            "trake_qa_points": "abs(delta_t) <= 2.0s using per-video rounded FPS",
        },
        "all_primary_scored": agg(primary),
        "official_p1_q02_q20": agg(n19),
        "per_query": per_query,
    }
    summary_path = args.output.with_suffix(".summary.json")
    if str(args.output).endswith(".jsonl"):
        summary_path = Path(str(args.output)[:-6] + ".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"all_primary": summary["all_primary_scored"], "n19": summary["official_p1_q02_q20"]}, indent=2))
    print("wrote", args.output)
    print("wrote", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
