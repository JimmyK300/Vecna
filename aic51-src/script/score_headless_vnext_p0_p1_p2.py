#!/usr/bin/env python3
"""Wrapper around frozen Headless-vNext scorer for additive P0/P1/P2 packets.

Does not edit score_headless_vnext.py. Unscoreable rows (scoreability.video=false)
stay in the 30-query packet but are excluded from video/range/TRAKE denominators.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FROZEN_SCORER = ROOT / "aic51-src" / "script" / "score_headless_vnext.py"
DEFAULT_MANIFEST = ROOT / "benchmark-results" / "headless-vnext-p0-p1-p2-v1" / "manifest.json"
FROZEN_QWEN = ROOT / "benchmark-results" / "headless-vnext-rerun-20260831" / "qwen-only-v1.jsonl"
EXPECTED_FROZEN_QWEN_SHA = "0adf3b70edd75778c18c6f0429fd6a430880db62a2d115fd03c83c151162b4be"


def load_scorer():
    spec = importlib.util.spec_from_file_location("headless_vnext_scorer_frozen", FROZEN_SCORER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load frozen scorer: {FROZEN_SCORER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def concat_jsonl(paths: list[Path], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with dest.open("w", encoding="utf-8", newline="\n") as out:
        for path in paths:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                qid = row.get("canonical_query_id")
                if not qid:
                    raise SystemExit(f"ranking row missing canonical_query_id in {path}")
                if qid in seen:
                    raise SystemExit(f"duplicate ranking id while concatenating: {qid}")
                seen.add(qid)
                out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _counts_for(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "queries": len(rows),
        "video_scoreable": len(rows),
        "range_scoreable_non_trake": sum(r["range"].get("status") != "not_applicable_trake" for r in rows),
        "trake_rows": sum("trake" in r for r in rows),
        "trake_events": sum(r.get("trake", {}).get("event_count", 0) for r in rows),
        "p0_rows": sum(r["operational_phase"] == "P0" for r in rows),
        "p1_rows": sum(r["operational_phase"] == "P1" for r in rows),
        "p2_rows": sum(r["operational_phase"] == "P2" for r in rows),
    }


def score_packet(
    manifest: dict[str, Any],
    rankings: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    scorer = load_scorer()
    all_rows, _raw = scorer.score(manifest, rankings, allow_partial=False)
    by_id = {record["canonical_query_id"]: record for record in manifest["records"]}
    scoreable: list[dict[str, Any]] = []
    unscoreable: list[dict[str, Any]] = []
    for row in all_rows:
        record = by_id[row["canonical_query_id"]]
        row["scoreability"] = record["scoreability"]
        row["accepted_video_id"] = record.get("accepted_video_id") or ""
        row["classification"] = (record.get("provenance") or {}).get("classification")
        row["classification_note"] = (record.get("provenance") or {}).get("classification_note")
        if record["scoreability"]["video"]:
            scoreable.append(row)
        else:
            unscoreable.append(
                {
                    "canonical_query_id": row["canonical_query_id"],
                    "vecna_provenance_id": row["vecna_provenance_id"],
                    "task_type": row["task_type"],
                    "operational_phase": row["operational_phase"],
                    "classification": row["classification"],
                    "classification_note": row["classification_note"],
                }
            )
    fake_manifest = {"counts": _counts_for(scoreable)}
    summary = scorer.aggregate(scoreable, fake_manifest, partial=False)
    summary["scored_counts"]["p2_rows"] = sum(r["operational_phase"] == "P2" for r in scoreable)
    summary["scored_counts"]["p2_execution_rows"] = sum(r["operational_phase"] == "P2" for r in all_rows)
    summary["scored_counts"]["p2_unscoreable"] = sum(
        1 for item in unscoreable if item["operational_phase"] == "P2"
    )
    summary["scored_counts"]["execution_rows"] = len(all_rows)
    summary["unscoreable"] = unscoreable
    summary["by_task_type"] = {}
    for task in sorted({row["task_type"] for row in scoreable}):
        subset = [row for row in scoreable if row["task_type"] == task]
        summary["by_task_type"][task] = scorer.aggregate(subset, {"counts": _counts_for(subset)}, partial=False)
    summary["by_phase"] = {}
    for phase in ("P0", "P1", "P2"):
        subset = [row for row in scoreable if row["operational_phase"] == phase]
        if subset:
            summary["by_phase"][phase] = scorer.aggregate(
                subset, {"counts": _counts_for(subset)}, partial=False
            )
    return all_rows, summary, scoreable


def ledger_rows(all_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in all_rows:
        range_block = row.get("range") or {}
        item = {
            "canonical_query_id": row["canonical_query_id"],
            "vecna_provenance_id": row["vecna_provenance_id"],
            "operational_phase": row["operational_phase"],
            "task_type": row["task_type"],
            "scoreable_video": bool((row.get("scoreability") or {}).get("video")),
            "classification": row.get("classification"),
            "classification_note": row.get("classification_note"),
            "accepted_video_id": row.get("accepted_video_id") or "",
            "first_correct_video_rank": row.get("first_correct_video_rank"),
            "video_R@1": row.get("video", {}).get("R@1"),
            "video_R@5": row.get("video", {}).get("R@5"),
            "video_R@20": row.get("video", {}).get("R@20"),
            "video_MRR@20": row.get("video_reciprocal_rank_at_20"),
            "range_status": range_block.get("status"),
            "first_range_valid_rank": range_block.get("first_range_valid_rank"),
            "range_R@1": range_block.get("R@1"),
            "range_R@5": range_block.get("R@5"),
            "range_R@20": range_block.get("R@20"),
            "range_MRR@20": range_block.get("reciprocal_rank_at_20"),
        }
        if "trake" in row:
            item["trake_event_count"] = row["trake"].get("event_count")
            item["trake_all_events_covered@20"] = row["trake"].get("all_events_covered", {}).get("20")
            item["trake_event_coverage@20"] = row["trake"].get("event_coverage", {}).get("20")
        out.append(item)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rankings", type=Path)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--concat-frozen-qwen", type=Path, help="P2-only jsonl to concat with frozen P0/P1 qwen jsonl")
    ap.add_argument("--frozen-qwen", type=Path, default=FROZEN_QWEN)
    args = ap.parse_args()
    rankings_path = args.rankings
    if args.concat_frozen_qwen:
        import hashlib

        frozen_sha = hashlib.sha256(args.frozen_qwen.read_bytes()).hexdigest()
        if frozen_sha != EXPECTED_FROZEN_QWEN_SHA:
            raise SystemExit(f"frozen qwen jsonl SHA mismatch: {frozen_sha}")
        concat_jsonl([args.frozen_qwen, args.concat_frozen_qwen], rankings_path)
    scorer = load_scorer()
    manifest = load_json(args.manifest)
    rankings = scorer.load_rankings(rankings_path)
    all_rows, summary, _scoreable = score_packet(manifest, rankings)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "scored.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in all_rows),
        encoding="utf-8",
    )
    write_json(args.out_dir / "summary.json", summary)
    ledger = ledger_rows(all_rows)
    (args.out_dir / "ledger.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in ledger),
        encoding="utf-8",
    )
    p2_ledger = [row for row in ledger if row["operational_phase"] == "P2"]
    (args.out_dir / "p2-ledger.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in p2_ledger),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
