#!/usr/bin/env python3
"""Compare frozen legacy and real donor headless runs for Vecna Issue #64.

Fusion itself happens inside ``OpenCubeeFusionSearcher`` during the donor run.
This evaluator therefore compares two normal headless JSONL outputs rather than
trying to reconstruct fusion from truncated result files.

It fails closed on query/ground-truth mismatches and verifies that the donor
run actually contains the Issue #64 fusion marker while the legacy run does
not.  No weights or ranking policy are tuned here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

DONOR_STRATEGY = "opencubee_model_weighted"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def by_query(rows: list[dict[str, Any]], source: str) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        query_id = str(row.get("query_id") or "").strip()
        if not query_id:
            raise ValueError(f"{source}: row missing query_id")
        if query_id in mapped:
            raise ValueError(f"{source}: duplicate query_id {query_id}")
        mapped[query_id] = row
    return mapped


def truth_fingerprint(record: dict[str, Any]) -> str:
    payload = {
        "query_text": record.get("query_text"),
        "answers": record.get("answers") or [],
        "task_type": record.get("task_type"),
        "ground_truth_tier": record.get("ground_truth_tier"),
        "match_contract": record.get("match_contract"),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return float(ordered[index])


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scoreable = [row for row in rows if row.get("answers")]
    if not scoreable:
        return {"n": 0}
    latencies = [float(row["latency_ms"]) for row in scoreable if row.get("latency_ms") is not None]
    ranks = [int(row["first_correct_rank"]) for row in scoreable if row.get("first_correct_rank")]
    return {
        "n": len(scoreable),
        "recall_at_1": sum(float(row.get("recall_at_1", 0.0)) for row in scoreable) / len(scoreable),
        "recall_at_5": sum(float(row.get("recall_at_5", 0.0)) for row in scoreable) / len(scoreable),
        "recall_at_20": sum(float(row.get("recall_at_20", 0.0)) for row in scoreable) / len(scoreable),
        "mrr_at_20": sum(float(row.get("reciprocal_rank", 0.0)) for row in scoreable) / len(scoreable),
        "median_first_correct_rank_within_20": statistics.median(ranks) if ranks else None,
        "no_hit_within_20_count": sum(1 for row in scoreable if row.get("first_correct_rank") is None),
        "latency_ms": {
            "mean": (sum(latencies) / len(latencies)) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
        },
    }


def marker_count(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        for result in row.get("top_results") or []:
            scores = result.get("scores") or {}
            if scores.get("issue64_fusion_strategy") == DONOR_STRATEGY:
                count += 1
    return count


def task_slices(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("task_type") or "unknown"), []).append(row)
    return {name: aggregate(group) for name, group in sorted(grouped.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue #64 legacy vs donor A/B evaluator")
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    legacy_path = args.legacy.resolve()
    donor_path = args.donor.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    legacy_rows = load_jsonl(legacy_path)
    donor_rows = load_jsonl(donor_path)
    legacy = by_query(legacy_rows, "legacy")
    donor = by_query(donor_rows, "donor")

    if set(legacy) != set(donor):
        raise ValueError(
            f"query-id mismatch: legacy-only={sorted(set(legacy)-set(donor))} "
            f"donor-only={sorted(set(donor)-set(legacy))}"
        )
    query_ids = sorted(legacy)
    for query_id in query_ids:
        if truth_fingerprint(legacy[query_id]) != truth_fingerprint(donor[query_id]):
            raise ValueError(f"ground-truth/query mismatch for {query_id}")

    legacy_markers = marker_count(legacy_rows)
    donor_markers = marker_count(donor_rows)
    if legacy_markers:
        raise ValueError(f"legacy arm unexpectedly contains {legacy_markers} Issue #64 donor markers")
    if donor_markers == 0:
        raise ValueError("donor arm contains no Issue #64 fusion markers")

    legacy_summary = aggregate(legacy_rows)
    donor_summary = aggregate(donor_rows)
    metric_keys = ("recall_at_1", "recall_at_5", "recall_at_20", "mrr_at_20")
    delta = {
        key: float(donor_summary.get(key, 0.0)) - float(legacy_summary.get(key, 0.0))
        for key in metric_keys
    }

    per_query: list[dict[str, Any]] = []
    improved = worsened = gained20 = lost20 = 0
    for query_id in query_ids:
        lrank = legacy[query_id].get("first_correct_rank")
        drank = donor[query_id].get("first_correct_rank")
        if lrank is not None and drank is not None:
            improved += int(int(drank) < int(lrank))
            worsened += int(int(drank) > int(lrank))
        lhit = bool(lrank is not None and int(lrank) <= 20)
        dhit = bool(drank is not None and int(drank) <= 20)
        gained20 += int(not lhit and dhit)
        lost20 += int(lhit and not dhit)
        per_query.append(
            {
                "query_id": query_id,
                "task_type": legacy[query_id].get("task_type"),
                "legacy_rank": lrank,
                "donor_rank": drank,
                "legacy_hit20": lhit,
                "donor_hit20": dhit,
                "rank_delta_donor_minus_legacy": (
                    int(drank) - int(lrank) if lrank is not None and drank is not None else None
                ),
                "legacy_latency_ms": legacy[query_id].get("latency_ms"),
                "donor_latency_ms": donor[query_id].get("latency_ms"),
            }
        )

    summary = {
        "issue": 64,
        "strategy": DONOR_STRATEGY,
        "policy_frozen_before_scoring": True,
        "post_result_tuning_allowed": False,
        "legacy": legacy_summary,
        "donor": donor_summary,
        "delta": delta,
        "legacy_by_task_type": task_slices(legacy_rows),
        "donor_by_task_type": task_slices(donor_rows),
        "per_query_improved_rank": improved,
        "per_query_worsened_rank": worsened,
        "gained_top20": gained20,
        "lost_top20": lost20,
        "legacy_donor_marker_count": legacy_markers,
        "donor_marker_count": donor_markers,
        "per_query": per_query,
        "verdict": "PENDING_BROWSER_REVIEW",
    }
    summary_path = output_dir / "ab-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run = {
        "issue": 64,
        "legacy": {"path": str(legacy_path), "sha256": sha256_file(legacy_path)},
        "donor": {"path": str(donor_path), "sha256": sha256_file(donor_path)},
        "summary": {"path": str(summary_path), "sha256": sha256_file(summary_path)},
        "query_count": len(query_ids),
        "truth_identity_checked": True,
        "donor_marker_checked": True,
    }
    (output_dir / "ab-run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def fmt(value: Any) -> str:
        return "n/a" if value is None else f"{float(value):.6f}"

    lines = [
        "# Issue #64 OpenCubee donor A/B",
        "",
        "| metric | legacy | donor | delta |",
        "|---|---:|---:|---:|",
    ]
    for key in metric_keys:
        lines.append(
            f"| {key} | {fmt(legacy_summary.get(key))} | {fmt(donor_summary.get(key))} | {delta[key]:+.6f} |"
        )
    lines.extend(
        [
            "",
            f"- improved correct rank: **{improved}**",
            f"- worsened correct rank: **{worsened}**",
            f"- gained top-20 hits: **{gained20}**",
            f"- lost top-20 hits: **{lost20}**",
            f"- donor result markers: **{donor_markers}**",
            f"- legacy mean latency ms: **{fmt(legacy_summary['latency_ms']['mean'])}**",
            f"- donor mean latency ms: **{fmt(donor_summary['latency_ms']['mean'])}**",
            "",
            "Verdict: **PENDING_BROWSER_REVIEW**",
            "",
        ]
    )
    (output_dir / "AB_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
