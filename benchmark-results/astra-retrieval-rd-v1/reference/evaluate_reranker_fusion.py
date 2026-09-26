#!/usr/bin/env python3
"""Authoritative frozen-control scorer for reranker-fusion-v1.

This harness joins the current 115-query candidate exports to the historical
P0/P1/P2 manifest by (operational phase, numeric query number).  It keeps the
historical range and TRAKE contracts separate from the current P3 contract:
historical TRAKE success is *all* events covered by K, while P3 retains the
existing event-level fractional metrics.

The module is deliberately dependency-free so the scorer and its provenance
can be copied into experiment artifacts and rerun without model inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


KS = (1, 5, 10, 20)
EXCLUDED_QUERY_IDS = frozenset({"p0_q15", "p3_q09"})
DEFAULT_FPS = 25.0
DEFAULT_POINT_TOLERANCE_SECONDS = 2.0
EXPECTED_CONTROLS = {
    "baseline": {"recall_at_1": 41, "recall_at_5": 56, "recall_at_10": 65, "recall_at_20": 68, "mrr_at_20": 0.424340},
    "reranker": {"recall_at_1": 40, "recall_at_5": 61, "recall_at_10": 64, "recall_at_20": 76, "mrr_at_20": 0.432021},
}
EXPECTED_P3 = {
    "baseline": {"recall_at_1": 8, "recall_at_5": 15, "recall_at_10": 17, "recall_at_20": 18, "mrr_at_20": 0.3164625850340136},
    "reranker": {"recall_at_1": 8, "recall_at_5": 16, "recall_at_10": 17, "recall_at_20": 22, "mrr_at_20": 0.3356813028241599},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def norm_video(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    text = text.rsplit("/", 1)[-1]
    return text.rsplit(".", 1)[0].casefold()


def frame_id(item: dict[str, Any]) -> int:
    value = item.get("frame_id", item.get("frame"))
    if isinstance(value, str) and "#" in value:
        value = value.rsplit("#", 1)[1]
    return int(value)


def candidate_frames(item: dict[str, Any]) -> list[int]:
    """Match current headless_benchmark's empty-timeline fallback."""
    raw = item.get("time_line", item.get("timeline"))
    if raw:
        return [int(x) for x in raw]
    return [frame_id(item)]


def ranked(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for index, item in enumerate(items, start=1):
        copy = dict(item)
        copy["_rank"] = int(item.get("rank", index))
        out.append(copy)
    return sorted(out, key=lambda x: x["_rank"])


def first_rank(ranks: Iterable[int | None]) -> int | None:
    values = [x for x in ranks if x is not None]
    return min(values) if values else None


def reciprocal(rank: int | None) -> float:
    return 1.0 / rank if rank and rank <= 20 else 0.0


def hit_at(rank: int | None, k: int) -> bool:
    return rank is not None and rank <= k


def interval_hit(frame: int, start: int, end: int) -> bool:
    return int(start) <= frame <= int(end)


def video_frame_hit(item: dict[str, Any], video_id: str, start: int, end: int) -> bool:
    return norm_video(item.get("video_id")) == norm_video(video_id) and any(interval_hit(frame, start, end) for frame in candidate_frames(item))


def historical_range_rank(items: Iterable[dict[str, Any]], truth: dict[str, Any]) -> int | None:
    ranges = truth.get("accepted_ranges") or []
    for item in ranked(items):
        if any(video_frame_hit(item, truth["accepted_video_id"], r["start_frame"], r["end_frame"]) for r in ranges):
            return item["_rank"]
    return None


def historical_trake_score(items: Iterable[dict[str, Any]], truth: dict[str, Any]) -> dict[str, Any]:
    """Score historical TRAKE with strict all-events coverage.

    A query is successful at K only when every required event has a candidate
    rank <= K.  The first strict success rank is therefore the maximum of the
    per-event first-hit ranks, not the minimum.
    """
    events = truth.get("trake_event_truth") or []
    event_ranks: list[int | None] = []
    for event in events:
        rank = None
        for item in ranked(items):
            if norm_video(item.get("video_id")) != norm_video(truth["accepted_video_id"]):
                continue
            if any(interval_hit(frame, event["proxy_window"]["start_frame"], event["proxy_window"]["end_frame"]) for frame in candidate_frames(item)):
                rank = item["_rank"]
                break
        event_ranks.append(rank)
    all_events_rank = max(event_ranks) if event_ranks and all(x is not None for x in event_ranks) else None
    return {
        "event_first_ranks": event_ranks,
        "all_events_covered": {f"R@{k}": all(hit_at(rank, k) for rank in event_ranks) for k in KS},
        "first_all_events_rank": all_events_rank,
        "reciprocal_rank": reciprocal(all_events_rank),
    }


def historical_score(items: Iterable[dict[str, Any]], truth: dict[str, Any]) -> dict[str, Any]:
    if truth.get("task_type") == "trake":
        return {"family": "historical_trake", **historical_trake_score(items, truth)}
    rank = historical_range_rank(items, truth)
    return {
        "family": "historical_range",
        "first_correct_rank": rank,
        "reciprocal_rank": reciprocal(rank),
        "recall": {f"R@{k}": hit_at(rank, k) for k in KS},
    }


def p3_target_hit(item: dict[str, Any], target: dict[str, Any]) -> bool:
    if norm_video(item.get("video_id")) != norm_video(target.get("video_id")):
        return False
    frames = candidate_frames(item)
    if target.get("kind") == "interval":
        return any(interval_hit(frame, target["start"], target["end"]) for frame in frames)
    if target.get("kind") == "point":
        # This is the current retrieval contract: timestamp tolerance at the
        # configured FPS. P3's stored comparison uses the 25 FPS default.
        tolerance = DEFAULT_FPS * DEFAULT_POINT_TOLERANCE_SECONDS
        return any(abs(frame - int(target["frame"])) <= tolerance for frame in frames)
    raise ValueError(f"unsupported P3 target kind: {target.get('kind')!r}")


def p3_score(items: Iterable[dict[str, Any]], truth: dict[str, Any]) -> dict[str, Any]:
    """Reproduce current P3 event/target semantics, including fractional TRAKE."""
    groups = truth.get("accepted_groups") or []
    # The stored P3 comparison evaluates the exported top-20 result list. A
    # baseline candidate beyond rank 20 is therefore a no-hit at MRR@20, even
    # though the baseline export itself retains top-100 for other controls.
    p3_items = [item for item in ranked(items) if item["_rank"] <= 20]
    target_ranks: list[int | None] = []
    for group in groups:
        for target in group:
            rank = None
            for item in p3_items:
                if p3_target_hit(item, target):
                    rank = item["_rank"]
                    break
            target_ranks.append(rank)
    first = first_rank(target_ranks)
    return {
        "family": "p3",
        "target_ranks": target_ranks,
        "first_correct_rank": first,
        "reciprocal_rank": reciprocal(first),
        "recall": {f"R@{k}": sum(hit_at(rank, k) for rank in target_ranks) / len(target_ranks) if target_ranks else 0.0 for k in KS},
        "all_targets_hit_at_20": bool(target_ranks) and all(hit_at(rank, 20) for rank in target_ranks),
    }


def current_query_number(row: dict[str, Any]) -> int:
    match = re.search(r"query-p[012]-(\d+)(?:-|$)", str(row["canonical_source_key"]))
    if not match:
        raise ValueError(f"cannot derive numeric historical query number: {row['query_id']} / {row['canonical_source_key']}")
    return int(match.group(1))


def join_historical(row: dict[str, Any], records: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any] | None:
    phase_match = re.search(r"query-(p[012])-", str(row["canonical_source_key"]))
    if not phase_match:
        raise ValueError(f"cannot derive historical phase: {row['query_id']} / {row['canonical_source_key']}")
    phase = phase_match.group(1).upper()
    number = current_query_number(row)
    raw = f"p1-{number}" if phase in {"P0", "P1"} else str(row["canonical_source_key"])
    return records.get((phase, raw))


def aggregate(scores: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(scores),
        "recall_at_1": sum(float(s["recall"]["R@1"]) for s in scores),
        "recall_at_5": sum(float(s["recall"]["R@5"]) for s in scores),
        "recall_at_10": sum(float(s["recall"]["R@10"]) for s in scores),
        "recall_at_20": sum(float(s["recall"]["R@20"]) for s in scores),
        "mrr_at_20": sum(float(s["reciprocal_rank"]) for s in scores) / len(scores) if scores else 0.0,
    }


def score_query(items: list[dict[str, Any]], truth: dict[str, Any]) -> dict[str, Any]:
    raw = historical_score(items, truth) if truth.get("_source") == "historical" else p3_score(items, truth)
    if raw["family"] == "historical_trake":
        raw["recall"] = raw.pop("all_events_covered")
    return raw


def compare_expected(actual: dict[str, Any], expected: dict[str, Any], tolerance: float = 1e-9) -> dict[str, Any]:
    return {key: {"actual": actual.get(key), "expected": value, "match": abs(float(actual.get(key, 0)) - float(value)) <= tolerance} for key, value in expected.items()}


def run(args: argparse.Namespace) -> dict[str, Any]:
    baseline_path = Path(args.baseline)
    reranker_path = Path(args.reranker)
    truth_path = Path(args.truth)
    historical_path = Path(args.historical_manifest)
    comparison_path = Path(args.p3_comparison)

    baseline_rows = {row["query_id"]: row for row in read_jsonl(baseline_path)}
    reranker_doc = read_json(reranker_path)
    reranker_rows = {row["query_id"]: row for row in reranker_doc["per_query"]}
    truth_rows = {row["query_id"]: row for row in read_jsonl(truth_path)}
    historical_doc = read_json(historical_path)
    historical_records = {(row["operational_phase"], row["raw_query_id"]): row for row in historical_doc["records"]}
    comparison = read_json(comparison_path)
    stored_p3 = {row["query_id"]: row for row in comparison["per_query"]}

    joined: list[dict[str, Any]] = []
    for query_id, row in baseline_rows.items():
        if query_id in EXCLUDED_QUERY_IDS:
            continue
        if str(row.get("canonical_source_key", "")).startswith("query-p"):
            historical = join_historical(row, historical_records)
            if historical is None:
                raise AssertionError(f"historical join missing for {query_id}: {row['canonical_source_key']}")
            truth = dict(historical)
            truth["_source"] = "historical"
            family = "historical_trake" if truth.get("task_type") == "trake" else "historical_range"
        else:
            truth = dict(truth_rows[query_id])
            if not truth.get("scoreable"):
                continue
            truth["_source"] = "p3"
            family = "p3"
        if query_id not in reranker_rows:
            raise AssertionError(f"reranker row missing for {query_id}")
        base_items = row.get("candidates_top100") or []
        rerank_items = reranker_rows[query_id].get("reranked_candidates_top20") or []
        base_score = score_query(base_items, truth)
        rerank_score = score_query(rerank_items, truth)
        joined.append({"query_id": query_id, "family": family, "truth_key": truth.get("canonical_query_id", truth.get("canonical_source_key", query_id)), "baseline": base_score, "reranker": rerank_score})

    if len(joined) != 113:
        raise AssertionError(f"expected 113 joined queries, got {len(joined)}")
    historical_joined = [x for x in joined if x["family"].startswith("historical")]
    p3_joined = [x for x in joined if x["family"] == "p3"]
    counts = {
        "total": len(joined),
        "historical": len(historical_joined),
        "historical_non_trake": sum(x["family"] == "historical_range" for x in joined),
        "historical_trake": sum(x["family"] == "historical_trake" for x in joined),
        "p3": len(p3_joined),
        "p3_trake": sum(truth_rows[x["query_id"]].get("task_type") == "trake" for x in p3_joined),
        "all_trake_rows_in_113": sum(x["family"] == "historical_trake" for x in joined) + sum(truth_rows[x["query_id"]].get("task_type") == "trake" for x in p3_joined),
        "excluded": sorted(EXCLUDED_QUERY_IDS),
        "historical_manifest_records": len(historical_doc["records"]),
    }

    overall = {name: aggregate([x[name] for x in joined]) for name in ("baseline", "reranker")}
    p3_actual = {name: aggregate([x[name] for x in p3_joined]) for name in ("baseline", "reranker")}
    p3_stored = {
        "baseline": comparison["summary"]["provisional_scored"]["baseline"],
        "reranker": comparison["summary"]["provisional_scored"]["reranker"],
    }
    p3_normalized = {
        name: {
            "count": p3_actual[name]["count"],
            "recall_at_1": p3_actual[name]["recall_at_1"] / len(p3_joined),
            "recall_at_5": p3_actual[name]["recall_at_5"] / len(p3_joined),
            "recall_at_10": p3_actual[name]["recall_at_10"] / len(p3_joined),
            "recall_at_20": p3_actual[name]["recall_at_20"] / len(p3_joined),
            "mrr_at_20": p3_actual[name]["mrr_at_20"],
        }
        for name in ("baseline", "reranker")
    }
    p3_check = {
        name: compare_expected(p3_actual[name], EXPECTED_P3[name]) for name in ("baseline", "reranker")
    }
    p3_stored_check = {
        name: compare_expected(p3_normalized[name], {key: p3_stored[name][key] for key in ("recall_at_1", "recall_at_5", "recall_at_10", "recall_at_20", "mrr_at_20")})
        for name in ("baseline", "reranker")
    }

    # Compare every P3 first-rank/recall result to the stored per-query record.
    p3_disagreements = []
    for row in p3_joined:
        stored = stored_p3[row["query_id"]]
        for name, stored_key in (("baseline", "baseline_metrics_at_20"), ("reranker", "reranked_metrics_at_20")):
            actual = row[name]
            expected = stored[stored_key]
            fields = {"first_correct_rank": actual["first_correct_rank"], "reciprocal_rank": actual["reciprocal_rank"], "recall_at_1": actual["recall"]["R@1"], "recall_at_5": actual["recall"]["R@5"], "recall_at_10": actual["recall"]["R@10"], "recall_at_20": actual["recall"]["R@20"]}
            for field, value in fields.items():
                if value != expected.get(field) and not (isinstance(value, float) and isinstance(expected.get(field), float) and abs(value - expected[field]) < 1e-12):
                    p3_disagreements.append({"query_id": row["query_id"], "arm": name, "field": field, "actual": value, "stored": expected.get(field)})

    out = {
        "schema": "reranker-fusion-v1/authoritative-113-scorer-v1",
        "scoring_contract": {
            "historical_non_trake": "correct video AND inclusive overlap with accepted range",
            "historical_trake": "all required TRAKE events covered by K; strict query success",
            "p3": "current headless_benchmark retrieval semantics; P3 event recall remains fractional",
            "join": "operational phase + numeric query number for historical rows",
            "excluded": sorted(EXCLUDED_QUERY_IDS),
            "ks": list(KS),
        },
        "inputs": {key: {"path": str(path), "sha256": sha256_file(path)} for key, path in (("baseline", baseline_path), ("reranker", reranker_path), ("truth", truth_path), ("historical_manifest", historical_path), ("p3_comparison", comparison_path))},
        "counts": counts,
        "partition_reconciliation": {
            "requested": {"historical_non_trake": 70, "historical_trake": 8, "p3": 35, "total": 113},
            "observed_from_frozen_sources": {"historical_non_trake": counts["historical_non_trake"], "historical_trake": counts["historical_trake"], "p3": counts["p3"], "total": counts["total"]},
            "note": "The only frozen 78-row historical manifest contains 72 range rows and 6 historical TRAKE rows. The 113 metrics reproduce exactly under strict all-events scoring; no rows were reclassified or invented. The full 113 set contains 8 TRAKE rows only when the two P3 TRAKE rows are included.",
        },
        "controls": overall,
        "expected_controls": EXPECTED_CONTROLS,
        "control_check": {name: compare_expected(overall[name], EXPECTED_CONTROLS[name], tolerance=1e-6) for name in ("baseline", "reranker")},
        "p3_actual": p3_actual,
        "p3_normalized": p3_normalized,
        "p3_stored_summary": p3_stored,
        "p3_check": p3_check,
        "p3_stored_check": p3_stored_check,
        "p3_disagreement_count": len(p3_disagreements),
        "p3_disagreements": p3_disagreements,
        "verification": {
            "controls_match": all(check["match"] for arm in ("baseline", "reranker") for check in {k: v for k, v in compare_expected(overall[arm], EXPECTED_CONTROLS[arm], tolerance=1e-6).items()}.values()),
            "p3_stored_match": not p3_disagreements and all(check["match"] for arm in ("baseline", "reranker") for check in p3_stored_check[arm].values()),
        },
        "per_query": joined,
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scorer_config.json").write_text(json.dumps({k: out[k] for k in ("schema", "scoring_contract", "inputs", "expected_controls")}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "controls.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "per_query_scores.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in joined) + "\n", encoding="utf-8")
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--reranker", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--historical-manifest", required=True, type=Path)
    parser.add_argument("--p3-comparison", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({"counts": result["counts"], "controls": result["controls"], "p3_disagreement_count": result["p3_disagreement_count"]}, indent=2))
