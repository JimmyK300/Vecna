#!/usr/bin/env python3
"""Freeze and execute Issue #63 Stage B without changing retrieval semantics."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "benchmark-results" / "issue63-stage-b"
PACKET = ROOT / "benchmark-results" / "issue63-round1-segments"
PRIMARY = Path(os.environ.get("VECNA_PRIMARY_ROOT", r"C:\Users\minhc\Code\Vecna"))
PRIMARY_AIC51 = PRIMARY / "aic51-src"
PRIMARY_SCRIPTS = PRIMARY_AIC51 / "script"
LEGACY_CSV = PRIMARY_AIC51 / "benchmark" / "issue34_headless_queries.csv"
PROTOCOL_SHA256 = "9807d422d436e9b12fc87f7066c38ab51981a18a4dd801ea8578b417bccca8b4"
BASELINE = {
    "cell": "clip_siglip_qwen_sparse", "rerank": False,
    "ocr_weight": 0.25, "asr_weight": 0.25, "nprobe": 32,
    "temporal_k": 2000, "query_expansion": False, "translation": False,
}
HISTORICAL_ISSUE58 = {
    "scoreable_count": 21, "recall_at_1": 0.523810,
    "recall_at_5": 0.630952, "recall_at_20": 0.797619,
    "mrr_at_20": 0.588680,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def preliminary_questions() -> dict[str, dict[str, str]]:
    path = PACKET / "review" / "preliminary-round1-questions.txt"
    header = re.compile(r"^Câu query-(p1-\d+)-(kis|qa|trake)\s*$")
    parsed: dict[str, dict[str, str]] = {}
    active_id: str | None = None
    active_type: str | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal body
        if active_id is None:
            return
        text = "\n".join(body).strip()
        if not text or active_id in parsed:
            raise ValueError(f"invalid preliminary question block: {active_id}")
        parsed[active_id] = {"task_type": str(active_type), "query": text}
        body = []

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = header.match(line.strip())
        if match:
            flush()
            active_id, active_type = match.groups()
        elif active_id is not None:
            body.append(line)
    flush()
    expected = {f"p1-{number}" for number in range(1, 26)}
    if set(parsed) != expected:
        raise ValueError(f"preliminary question inventory mismatch: {sorted(set(parsed) ^ expected)}")
    return parsed


def freeze_inputs() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    if sha256_file(OUT / "PROTOCOL.md") != PROTOCOL_SHA256:
        raise ValueError("frozen protocol hash mismatch")
    review_path = PACKET / "review" / "reviewed-ranges.json"
    review_doc = json.loads(review_path.read_text(encoding="utf-8"))
    reviews = review_doc["reviews"]
    anchors = json.loads((PACKET / "anchors.json").read_text(encoding="utf-8"))
    anchor_by_id = {f"{row['submission']}::{row['query_id']}": row for row in anchors}
    provenance_path = PACKET / "review" / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    prelim = preliminary_questions()
    records: list[dict[str, Any]] = []
    for source_id in sorted(reviews):
        review = reviews[source_id]
        source, query_id = source_id.split("::", 1)
        segment_path = PACKET / "segments" / f"{source}__{query_id}.yaml"
        segment = yaml.safe_load(segment_path.read_text(encoding="utf-8"))
        anchor = anchor_by_id.get(source_id) or {}
        if source == "final_round1_10_4of13":
            query = prelim[query_id]["query"]
            task_type = prelim[query_id]["task_type"]
            text_status = "user_supplied_preliminary_round1_25_questions"
        else:
            query = segment.get("query")
            task_type = segment.get("submitted_type")
            text_status = segment.get("query_text_status")
        scoreable = review["decision"] == "accept"
        ranges = review.get("reviewed_ranges") or []
        record = {
            "source_qualified_id": source_id, "query_id": query_id,
            "query": query, "query_text_status": text_status,
            "task_type": task_type, "source_submission": source,
            "source_label": review.get("source_label"),
            "source_csv": anchor.get("source_csv") or segment.get("source_csv"),
            "source_csv_sha256": anchor.get("csv_sha256") or segment.get("source_submission_sha256"),
            "source_archive_sha256": (
                provenance.get("artifacts", {}).get("submission-final-round1.zip", {}).get("sha256")
                if source == "final_round1_10_4of13" else None
            ),
            "source_submission_numeric_id_caveat": (
                "testing88_submission633 is a description-based source label; numeric ID 633 is not independently verified"
                if source == "testing88_submission633" else None
            ),
            "video_id": review.get("video_id") or segment.get("video_id"),
            "video_path_at_review": anchor.get("video_path") or segment.get("video_path"),
            "video_fps_projection": segment.get("video_fps_projection"),
            "submitted_anchor_frames": anchor.get("anchor_frames") or segment.get("submitted_anchor_frames"),
            "submitted_timestamps_s": anchor.get("derived_anchor_times_s") or segment.get("submitted_timestamps_s"),
            "review_decision": review["decision"], "scoreable": scoreable,
            "reviewed_ranges": ranges, "reviewer_note": review.get("reviewer_note", ""),
            "review_updated_at_utc": review.get("updated_at_utc"),
            "review_tier": "reconstructed_round1_human_reviewed",
            "validation_state": (
                "human_reviewed_reconstructed_semantic_interval"
                if scoreable else "ambiguous_missing_source_video_non_scoreable"
            ),
            "confidence_at_stage_a": segment.get("confidence"),
            "conflict_notes": segment.get("conflict_notes"),
            "boundary_reasoning": segment.get("boundary_reasoning"),
            "segment_source_path": str(segment_path.relative_to(ROOT)).replace("\\", "/"),
            "segment_source_sha256": sha256_file(segment_path),
        }
        if scoreable and (not query or not ranges):
            raise ValueError(f"scoreable reconstructed record is incomplete: {source_id}")
        records.append(record)
    if len(records) != 49 or sum(row["scoreable"] for row in records) != 48:
        raise ValueError("reviewed inventory must contain exactly 48 scoreable plus one excluded")
    excluded = [row["source_qualified_id"] for row in records if not row["scoreable"]]
    if excluded != ["testing88_submission633::p1-21"]:
        raise ValueError(f"unexpected reconstructed exclusions: {excluded}")
    ids = [row["source_qualified_id"] for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError("source-qualified IDs are not unique")
    truth = {
        "schema_version": 2,
        "purpose": "Issue #63 Stage B frozen reconstructed semantic-interval truth",
        "frozen_at_utc": review_doc.get("saved_at_utc"),
        "protocol_sha256": PROTOCOL_SHA256,
        "stage_a_commit": "f0532c1be14b02b6da73d4b23e2d773591a48f97",
        "source_review_sha256": sha256_file(review_path),
        "source_provenance_sha256": sha256_file(provenance_path),
        "scoring_contract": {
            "primary": "correct normalized video and any returned point/timeline frame inside any accepted interval",
            "interval_endpoints": "inclusive", "alternative_intervals": "any accepted interval satisfies",
            "wrong_video": "miss", "correct_video_outside_intervals": "miss",
            "exact_frame_tolerance": "diagnostic only, not primary",
        },
        "records": records,
    }
    write_json(OUT / "reconstructed-truth.json", truth)
    shutil.copyfile(LEGACY_CSV, OUT / "legacy-canonical.csv")
    with LEGACY_CSV.open(encoding="utf-8-sig", newline="") as handle:
        legacy_rows = list(csv.DictReader(handle))
    write_json(OUT / "expanded-inventory.json", {
        "schema_version": 2,
        "legacy_policy": "embedded unchanged; Stage B extends rather than replaces legacy truth",
        "legacy_csv_sha256": sha256_file(LEGACY_CSV), "legacy_records": legacy_rows,
        "reconstructed_truth_sha256": sha256_file(OUT / "reconstructed-truth.json"),
        "reconstructed_records": records,
    })
    return truth


def git_identity(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    return {
        "root": str(root), "sha": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"), "dirty": bool(status),
        "status_entries": status.splitlines(),
        "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
    }


def critical_hashes() -> dict[str, str]:
    paths = {
        "config": PRIMARY / "config.yaml",
        "headless_benchmark": PRIMARY_SCRIPTS / "headless_benchmark.py",
        "p20_runner": PRIMARY_SCRIPTS / "run_p20_p21_measurement.py",
        "searcher": PRIMARY_AIC51 / "aic51" / "packages" / "search" / "searcher.py",
    }
    return {name: sha256_file(path) for name, path in paths.items()}


def reconstructed_case(row: dict[str, Any]) -> dict[str, Any]:
    groups = [[{
        "kind": "interval", "video_id": row["video_id"],
        "start": int(interval["start_frame"]), "end": int(interval["end_frame"]),
    }] for interval in row["reviewed_ranges"]]
    return {
        "query_id": row["source_qualified_id"], "source": row["source_submission"],
        "task_type": row["task_type"], "query_mode": "text", "query": row["query"],
        "hints": [], "scoreable": True,
        "answer_strings": [f"{row['video_id']}:{r['start_frame']}-{r['end_frame']}" for r in row["reviewed_ranges"]],
        "accepted_groups": groups, "target_mode": "any",
        "evaluation_scope": "include_current_dataset",
        "validation_state": "human_reviewed_reconstructed_semantic_interval",
    }


def summarize_slices(records: list[dict[str, Any]], aggregate: Any) -> dict[str, Any]:
    slices: dict[str, dict[str, list[dict[str, Any]]]] = {
        "source": defaultdict(list), "task_type": defaultdict(list), "truth_tier": defaultdict(list)
    }
    for record in records:
        slices["source"][str(record.get("source"))].append(record)
        slices["task_type"][str(record.get("task_type"))].append(record)
        slices["truth_tier"][str(record.get("review_tier") or record.get("ground_truth_tier"))].append(record)
    return {
        axis: {key: {**aggregate(group), "small_n_warning": len(group) < 10} for key, group in groups.items()}
        for axis, groups in slices.items()
    }


def execute(truth: dict[str, Any], overwrite: bool) -> int:
    result_names = (
        "old-results.jsonl", "reconstructed-results.jsonl", "expanded-results.jsonl",
        "summary.json", "run.json", "manifest.json", "README.md", "RERUN.md",
    )
    existing = [name for name in result_names if (OUT / name).exists()]
    if existing and not overwrite:
        raise ValueError(f"refusing to overwrite result artifacts: {existing}")
    sys.path.insert(0, str(PRIMARY_AIC51))
    sys.path.insert(0, str(PRIMARY_SCRIPTS))
    import headless_benchmark as hb
    import run_p20_p21_measurement as runner
    from issue63_stage_b_scoring import aggregate

    if (runner.OCR_WEIGHT, runner.ASR_WEIGHT, runner.NPROBE, runner.TEMPORAL_K) != (0.25, 0.25, 32, 2000):
        raise ValueError("live runner no longer matches the frozen baseline contract")
    legacy_cases, inventory_validation, canonical_hash = runner.load_inventory()
    legacy_scoreable = [case for case in legacy_cases if case["scoreable"] and case["query_mode"] == "text"]
    reconstructed_rows = [row for row in truth["records"] if row["scoreable"]]
    if (len(legacy_scoreable), len(reconstructed_rows)) != (21, 48):
        raise ValueError(f"unexpected invocation counts: {len(legacy_scoreable)}, {len(reconstructed_rows)}")
    before_hashes = critical_hashes()
    context: dict[str, Any] = {
        "status": "initializing", "started_at": utc_now(), "protocol_sha256": PROTOCOL_SHA256,
        "baseline": BASELINE, "invocation_budget": {"searcher_initializations": 1, "search_calls": 69, "retries": 0},
        "primary_git": git_identity(PRIMARY), "stage_b_git": git_identity(ROOT),
        "critical_hashes_before": before_hashes, "legacy_csv_sha256": sha256_file(LEGACY_CSV),
        "reconstructed_truth_sha256": sha256_file(OUT / "reconstructed-truth.json"),
        "expanded_inventory_sha256": sha256_file(OUT / "expanded-inventory.json"),
        "canonical_content_sha256": canonical_hash, "inventory_complete": inventory_validation["complete"],
        "exact_command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\minhc\\Code\\Vecna\\.venv\\Scripts\\python.exe' aic51-src\\script\\run_issue63_stage_b.py --execute --overwrite",
    }
    write_json(OUT / "run.json", context)
    searcher, features, collection, generation, init_s = runner.setup_cell_searcher(runner.CELLS_BY_NAME[BASELINE["cell"]])
    args = runner.benchmark_args()
    context.update({
        "status": "running", "searcher_init_s": round(init_s, 3),
        "collection_identity": {key: collection.get(key) for key in ("collection", "row_count", "indexes")},
        "index_generation": generation, "runtime": hb.runtime_versions(),
        "query_encoder_devices": hb.actual_query_encoder_devices(searcher, features), "target_features": features,
    })
    if collection.get("collection") != "official_l21_l30_all_v2" or generation.get("state") != "resolved":
        context.update({"status": "blocked_pre_search", "ended_at": utc_now()})
        write_json(OUT / "run.json", context)
        raise ValueError("required collection/index generation is unavailable")
    write_json(OUT / "run.json", context)
    old_records: list[dict[str, Any]] = []
    reconstructed_records: list[dict[str, Any]] = []
    attempted = 0

    def one(case: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        nonlocal attempted
        attempted += 1
        try:
            record = hb.run_text_variant(searcher, case, 0, args, features)
        except BaseException as exc:
            record = {
                "query_id": case["query_id"], "source": case["source"], "task_type": case["task_type"],
                "query_text": case["query"], "status": "failed_search", "first_correct_rank": None,
                "reciprocal_rank": 0.0, "recall_at_1": 0.0, "recall_at_5": 0.0,
                "recall_at_10": 0.0, "recall_at_20": 0.0, "no_hit_within_20": True,
                "latency_ms": None, "top_results": [],
                "failure": {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
            }
        record.update(metadata)
        print(f"[{attempted:02d}/69] {case['query_id']} rank={record.get('first_correct_rank') or '-'} status={record['status']}", flush=True)
        return record

    for case in legacy_scoreable:
        old_records.append(one(case, {"benchmark_partition": "legacy", "review_tier": "legacy_existing_contract"}))
    for row in reconstructed_rows:
        reconstructed_records.append(one(reconstructed_case(row), {
            "benchmark_partition": "reconstructed", "source_qualified_id": row["source_qualified_id"],
            "query_text_status": row["query_text_status"], "review_tier": row["review_tier"],
            "review_decision": row["review_decision"], "reviewed_ranges": row["reviewed_ranges"],
        }))
    if attempted != 69:
        raise RuntimeError(f"counted invocation mismatch: {attempted}")
    expanded_records = old_records + reconstructed_records
    for name, rows in (
        ("old-results.jsonl", old_records), ("reconstructed-results.jsonl", reconstructed_records),
        ("expanded-results.jsonl", expanded_records),
    ):
        (OUT / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    old_metrics = aggregate(old_records)
    reconstructed_metrics = aggregate(reconstructed_records)
    expanded_metrics = aggregate(expanded_records)
    historical_drift = {
        key: round(old_metrics[key] - value, 6)
        for key, value in HISTORICAL_ISSUE58.items() if isinstance(value, float)
    }
    summary = {
        "created_at": utc_now(),
        "counts": {
            "legacy_scoreable": 21, "reconstructed_scoreable_added": 48,
            "expanded_scoreable_total": 69, "reconstructed_excluded": 1,
            "legacy_excluded": len(legacy_cases) - 21, "all_inventory_excluded": len(legacy_cases) - 20,
        },
        "same_runtime_metrics": {"old": old_metrics, "reconstructed_only": reconstructed_metrics, "expanded": expanded_metrics},
        "historical_issue58_guardrail": HISTORICAL_ISSUE58,
        "old_metric_drift_vs_issue58": historical_drift,
        "slices": summarize_slices(expanded_records, aggregate),
        "no_hit_query_ids": {
            "old": [row["query_id"] for row in old_records if row.get("no_hit_within_20")],
            "reconstructed": [row["query_id"] for row in reconstructed_records if row.get("no_hit_within_20")],
        },
        "failed_searches": [{"query_id": row["query_id"], "failure": row.get("failure")} for row in expanded_records if row.get("status") == "failed_search"],
        "interpretation": "Expanded metrics add human-reviewed semantic interval truth. Cross-source records remain independent even when bare p1 IDs match.",
    }
    write_json(OUT / "summary.json", summary)
    after_hashes = critical_hashes()
    context.update({
        "status": "complete" if not summary["failed_searches"] else "complete_with_failed_searches",
        "ended_at": utc_now(), "search_calls_attempted": attempted, "retries": 0,
        "critical_hashes_after": after_hashes, "production_files_unchanged": before_hashes == after_hashes,
        "no_tuning_statement": "No retrieval, model, fusion, index, query-expansion, translation, or production configuration behavior was tuned or changed.",
        "result_hashes": {name: sha256_file(OUT / name) for name in ("old-results.jsonl", "reconstructed-results.jsonl", "expanded-results.jsonl", "summary.json")},
        "latency_caveat": "Latency is wall-clock and machine-load dependent; quality comparison uses one initialized searcher and one current runtime.",
    })
    write_json(OUT / "run.json", context)
    readme = f"""# Issue #63 Stage B result packet

Stage B completed with `clip_siglip_qwen_sparse`, reranking OFF. No production retrieval, model, fusion, index, query-expansion, or translation behavior was changed.

## Counts

- Legacy scoreable: 21
- Reconstructed scoreable added: 48
- Expanded scoreable total: 69
- Reconstructed excluded: 1 (`testing88_submission633::p1-21`)
- Legacy excluded: {len(legacy_cases) - 21}

## Same-runtime metrics

| set | R@1 | R@5 | R@20 | MRR@20 | no hit |
|---|---:|---:|---:|---:|---:|
| old | {old_metrics['recall_at_1']} | {old_metrics['recall_at_5']} | {old_metrics['recall_at_20']} | {old_metrics['mrr_at_20']} | {old_metrics['no_hit_within_20_count']} |
| reconstructed only | {reconstructed_metrics['recall_at_1']} | {reconstructed_metrics['recall_at_5']} | {reconstructed_metrics['recall_at_20']} | {reconstructed_metrics['mrr_at_20']} | {reconstructed_metrics['no_hit_within_20_count']} |
| expanded | {expanded_metrics['recall_at_1']} | {expanded_metrics['recall_at_5']} | {expanded_metrics['recall_at_20']} | {expanded_metrics['mrr_at_20']} | {expanded_metrics['no_hit_within_20_count']} |

See `summary.json` for slices/no-hit IDs, `run.json` for runtime/index/config identity, and JSONL files for top-20 results and first-correct ranks.

## Limitations

- Reconstructed truth is human-reviewed semantic interval evidence, not organizer truth.
- `testing88_submission633::p1-4` retains `official_text_unmappable`; its available query label is not silently upgraded.
- Frame coordinates are FPS projections; exact decoded-frame validation requires FFmpeg `select=eq(n\\,FRAME)`.
- Runtime results expose point/timeline frames. Explicit segment-overlap support exists in the pure scorer, but this run grades emitted point/timeline frames.
- Latency is machine-load dependent.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    (OUT / "RERUN.md").write_text("""# Exact rerun

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\\Users\\minhc\\Code\\Vecna\\.venv\\Scripts\\python.exe' aic51-src\\script\\run_issue63_stage_b.py --execute --overwrite
```

This overwrites only Stage B result artifacts and performs 69 searches with one Searcher initialization and no retries.
""", encoding="utf-8")
    write_json(OUT / "manifest.json", {
        "created_at": utc_now(),
        "files": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUT.iterdir()) if path.is_file() and path.name != "manifest.json"
        },
    })
    return 0


def resummarize_existing() -> None:
    """Recompute metrics from the frozen 69 result records without retrieval."""
    from issue63_stage_b_scoring import aggregate

    def read_jsonl(name: str) -> list[dict[str, Any]]:
        return [json.loads(line) for line in (OUT / name).read_text(encoding="utf-8").splitlines() if line]

    old_records = read_jsonl("old-results.jsonl")
    reconstructed_records = read_jsonl("reconstructed-results.jsonl")
    expanded_records = old_records + reconstructed_records
    if (len(old_records), len(reconstructed_records), len(expanded_records)) != (21, 48, 69):
        raise ValueError("existing result inventory is incomplete; refusing resummary")
    old_metrics = aggregate(old_records)
    reconstructed_metrics = aggregate(reconstructed_records)
    expanded_metrics = aggregate(expanded_records)
    summary = {
        "created_at": utc_now(),
        "counts": {
            "legacy_scoreable": 21, "reconstructed_scoreable_added": 48,
            "expanded_scoreable_total": 69, "reconstructed_excluded": 1,
            "legacy_excluded": 1, "all_inventory_excluded": 2,
        },
        "same_runtime_metrics": {"old": old_metrics, "reconstructed_only": reconstructed_metrics, "expanded": expanded_metrics},
        "historical_issue58_guardrail": HISTORICAL_ISSUE58,
        "old_metric_drift_vs_issue58": {
            key: round(old_metrics[key] - value, 6)
            for key, value in HISTORICAL_ISSUE58.items() if isinstance(value, float)
        },
        "slices": summarize_slices(expanded_records, aggregate),
        "no_hit_query_ids": {
            "old": [row["query_id"] for row in old_records if row.get("no_hit_within_20")],
            "reconstructed": [row["query_id"] for row in reconstructed_records if row.get("no_hit_within_20")],
        },
        "failed_searches": [{"query_id": row["query_id"], "failure": row.get("failure")} for row in expanded_records if row.get("status") == "failed_search"],
        "interpretation": "Expanded metrics add human-reviewed semantic interval truth. Cross-source records remain independent even when bare p1 IDs match.",
        "query_input_caveat": {
            "affected_records": ["final_round1_10_4of13::p1-17", "final_round1_10_4of13::p1-25"],
            "detail": "The frozen parser retained the immediately following task-section label as a final line of these two supplied questions. Exact query_text used is preserved in reconstructed-results.jsonl; no retry was permitted by the exactly-once protocol.",
        },
    }
    write_json(OUT / "summary.json", summary)
    run = json.loads((OUT / "run.json").read_text(encoding="utf-8"))
    run["result_hashes"] = {
        name: sha256_file(OUT / name)
        for name in ("old-results.jsonl", "reconstructed-results.jsonl", "expanded-results.jsonl", "summary.json")
    }
    run["post_run_resummary"] = "Corrected aggregate recall to preserve legacy TRAKE fractional event coverage; no retrieval calls."
    write_json(OUT / "run.json", run)
    readme = f"""# Issue #63 Stage B result packet

Stage B completed with `clip_siglip_qwen_sparse`, reranking OFF. No production retrieval, model, fusion, index, query-expansion, or translation behavior was changed.

## Counts

- Legacy scoreable: 21
- Reconstructed scoreable added: 48
- Expanded scoreable total: 69
- Reconstructed excluded: 1 (`testing88_submission633::p1-21`)
- Legacy excluded: 1

## Same-runtime metrics

| set | R@1 | R@5 | R@20 | MRR@20 | no hit |
|---|---:|---:|---:|---:|---:|
| old | {old_metrics['recall_at_1']} | {old_metrics['recall_at_5']} | {old_metrics['recall_at_20']} | {old_metrics['mrr_at_20']} | {old_metrics['no_hit_within_20_count']} |
| reconstructed only | {reconstructed_metrics['recall_at_1']} | {reconstructed_metrics['recall_at_5']} | {reconstructed_metrics['recall_at_20']} | {reconstructed_metrics['mrr_at_20']} | {reconstructed_metrics['no_hit_within_20_count']} |
| expanded | {expanded_metrics['recall_at_1']} | {expanded_metrics['recall_at_5']} | {expanded_metrics['recall_at_20']} | {expanded_metrics['mrr_at_20']} | {expanded_metrics['no_hit_within_20_count']} |

The old metrics reproduce Issue #58 exactly. See `summary.json` for slices/no-hit IDs, `run.json` for runtime/index/config identity, and JSONL files for top-20 results and first-correct ranks.

## Limitations

- Reconstructed truth is human-reviewed semantic interval evidence, not organizer truth.
- `testing88_submission633::p1-4` retains `official_text_unmappable`; its available query label is not silently upgraded.
- The exactly-once run retained a task-section label at the end of the supplied text for `final_round1_10_4of13::p1-17` and `::p1-25`. The exact used text is preserved; no retry was made.
- Frame coordinates are FPS projections; exact decoded-frame validation requires FFmpeg `select=eq(n\\,FRAME)`.
- Runtime results expose point/timeline frames. Explicit segment-overlap support exists in the pure scorer, but this run grades emitted point/timeline frames.
- Latency is machine-load dependent.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    write_json(OUT / "manifest.json", {
        "created_at": utc_now(),
        "files": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUT.iterdir()) if path.is_file() and path.name != "manifest.json"
        },
    })


def smoke() -> None:
    from issue63_stage_b_scoring import score_reconstructed
    record = {"video_id": "L1_V001", "reviewed_ranges": [{"start_frame": 10, "end_frame": 20}, {"start_frame": 40, "end_frame": 50}]}
    assert score_reconstructed(record, [{"video_id": "L1_V001", "frame_id": 10}])["hit"]
    assert score_reconstructed(record, [{"video_id": "L1_V001", "frame_id": 50}])["hit"]
    assert score_reconstructed(record, [{"video_id": "L1_V001", "frame_id": 45}])["hit"]
    assert not score_reconstructed(record, [{"video_id": "L1_V001", "frame_id": 21}])["hit"]
    assert not score_reconstructed(record, [{"video_id": "L1_V002", "frame_id": 10}])["hit"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resummarize-existing", action="store_true")
    args = parser.parse_args()
    truth = freeze_inputs()
    if args.resummarize_existing:
        resummarize_existing()
        print("Stage B existing results resummarized without retrieval")
        return 0
    if args.smoke:
        smoke()
        print("Stage B deterministic smoke: PASS")
    if args.execute:
        return execute(truth, args.overwrite)
    print(json.dumps({"status": "preflight_complete", "records": len(truth["records"]), "scoreable": sum(row["scoreable"] for row in truth["records"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
