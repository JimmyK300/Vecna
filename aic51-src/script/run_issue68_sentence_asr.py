#!/usr/bin/env python3
"""Read-only local evidence runner for Vecna Issue #68.

Uses exactly one depth-1000 ASR BM25 exposure per frozen TRAKE query and derives
both the raw frame arm and experimental sentence-group arm from those same hits.
The repaired primary checkout supplies config + Milvus only and is never edited.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

DEFAULT_PRIMARY_ROOT = Path(r"C:\Users\minhc\Code\Vecna")
QUERY_IDS = ("p1_q02", "p1_q14", "p1_q16")
EXPOSURE_DEPTH = 1000
TOP_K = 20
NPROBE = 32

ISSUE59_GROUND_TRUTH = {
    "p1_q02": {"gold_video": "L26_V194", "fps": 25.0, "gold_points_frames": [4707, 5142, 5430, 5527]},
    "p1_q14": {"gold_video": "L24_V033", "fps": 30.0, "gold_points_frames": [15945, 16009, 16355, 16900]},
    "p1_q16": {"gold_video": "L26_V072", "fps": 25.0, "gold_points_frames": [2471, 3136, 3427, 3800]},
}
ISSUE59_SOURCE = {
    "commit": "6f81433a437c9aef1fbc86efb8c655199662dcf6",
    "path": "benchmark-results/issue59-trake-audit/trake-audit.jsonl",
    "blob_sha": "df52e74211b71e766d79a74f94959aa76c8eeb88",
    "tolerance_seconds": 2.0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_output(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), check=True, capture_output=True, text=True
    ).stdout


def git_state(root: Path) -> dict[str, Any]:
    return {
        "head": git_output(root, "rev-parse", "HEAD").strip(),
        "branch": git_output(root, "branch", "--show-current").strip(),
        "porcelain": git_output(root, "status", "--porcelain=v1"),
    }


def load_experiment(module_path: Path):
    spec = importlib.util.spec_from_file_location("vecna_issue68_sentence_asr", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load experiment module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def resolve_queries(path: Path) -> dict[str, str]:
    id_keys = ("query_id", "id", "qid", "queryId")
    text_keys = (
        "query", "query_text", "text", "description", "query_description",
        "question", "query_blob", "query_content",
    )
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"canonical query CSV is empty: {path}")
    headers = list(rows[0].keys())
    id_key = next((key for key in id_keys if key in headers), None)
    text_key = next((key for key in text_keys if key in headers), None)
    if id_key is None or text_key is None:
        raise ValueError(
            "cannot mechanically resolve canonical query columns; "
            f"headers={headers!r}, expected id in {id_keys!r}, text in {text_keys!r}"
        )
    resolved = {}
    for row in rows:
        qid = str(row.get(id_key, "")).strip()
        if qid in QUERY_IDS:
            text = str(row.get(text_key, "")).strip()
            if not text:
                raise ValueError(f"empty canonical query text for {qid}")
            resolved[qid] = text
    missing = [qid for qid in QUERY_IDS if qid not in resolved]
    if missing:
        raise ValueError(f"canonical query CSV missing frozen Issue #68 IDs: {missing}")
    return resolved


def list_indexes(database) -> list[str]:
    return sorted(str(value) for value in database._client.list_indexes(database._collection_name))


def database_identity(database) -> dict[str, Any]:
    return {
        "collection": database._collection_name,
        "row_count": int(database.get_size()),
        "indexes": list_indexes(database),
    }


def event_ranks_for_raw(raw_hits: list[dict[str, Any]], gt: dict[str, Any]) -> list[int | None]:
    tolerance = round(float(gt["fps"]) * float(ISSUE59_SOURCE["tolerance_seconds"]))
    ranks = []
    for gold in gt["gold_points_frames"]:
        rank = next(
            (
                index
                for index, item in enumerate(raw_hits, 1)
                if item["video_id"] == gt["gold_video"]
                and abs(int(item["frame"]) - int(gold)) <= tolerance
            ),
            None,
        )
        ranks.append(rank)
    return ranks


def event_ranks_for_groups(groups: list[dict[str, Any]], gt: dict[str, Any]) -> list[int | None]:
    tolerance = round(float(gt["fps"]) * float(ISSUE59_SOURCE["tolerance_seconds"]))
    ranks = []
    for gold in gt["gold_points_frames"]:
        rank = None
        for group_rank, group in enumerate(groups, 1):
            if group["video_id"] != gt["gold_video"]:
                continue
            if any(abs(int(member["frame"]) - int(gold)) <= tolerance for member in group["member_frames"]):
                rank = group_rank
                break
        ranks.append(rank)
    return ranks


def first_video_rank(items: list[dict[str, Any]], gold_video: str) -> int | None:
    return next((index for index, item in enumerate(items, 1) if item["video_id"] == gold_video), None)


def summarize_query(experiment, qid: str, query_text: str, hits: list[Any], text_field: str) -> dict[str, Any]:
    gt = ISSUE59_GROUND_TRUTH[qid]
    raw = experiment.raw_top_frame_hits(hits, text_field=text_field, limit=TOP_K)
    groups = experiment.group_frame_hits_by_sentence(hits, text_field=text_field, limit=TOP_K)
    raw_stats = experiment.raw_flooding_stats(raw)
    raw_event_ranks = event_ranks_for_raw(raw, gt)
    donor_event_ranks = event_ranks_for_groups(groups, gt)

    raw_video_rank = first_video_rank(raw, gt["gold_video"])
    donor_video_rank = first_video_rank(groups, gt["gold_video"])
    return {
        "query_id": qid,
        "query_text": query_text,
        "ground_truth": gt,
        "raw_frame_arm": {
            "top_k": TOP_K,
            **raw_stats,
            "unique_video_count": len({item["video_id"] for item in raw}),
            "correct_video_first_rank": raw_video_rank,
            "event_first_ranks_within_2s": raw_event_ranks,
            "events_exposed": sum(rank is not None for rank in raw_event_ranks),
            "frames": raw,
        },
        "sentence_group_arm": {
            "top_k": TOP_K,
            "group_count": len(groups),
            "unique_video_count": len({item["video_id"] for item in groups}),
            "correct_video_first_rank": donor_video_rank,
            "event_first_group_ranks_within_2s": donor_event_ranks,
            "events_exposed": sum(rank is not None for rank in donor_event_ranks),
            "largest_member_count": max((group["member_count"] for group in groups), default=0),
            "groups": groups,
        },
        "delta": {
            "unique_top_level_results": len(groups) - raw_stats["unique_sentence_groups"],
            "correct_video_rank_change": (
                None if raw_video_rank is None or donor_video_rank is None else donor_video_rank - raw_video_rank
            ),
            "event_exposure_change": sum(rank is not None for rank in donor_event_ranks)
            - sum(rank is not None for rank in raw_event_ranks),
        },
    }


def aggregate(per_query: list[dict[str, Any]]) -> dict[str, Any]:
    raw_slots = sum(item["raw_frame_arm"]["raw_slots"] for item in per_query)
    raw_unique = sum(item["raw_frame_arm"]["unique_sentence_groups"] for item in per_query)
    donor_groups = sum(item["sentence_group_arm"]["group_count"] for item in per_query)
    return {
        "query_count": len(per_query),
        "raw_top20_slots": raw_slots,
        "raw_unique_sentence_groups_in_top20": raw_unique,
        "raw_duplicate_slots": raw_slots - raw_unique,
        "donor_top20_groups": donor_groups,
        "raw_events_exposed": sum(item["raw_frame_arm"]["events_exposed"] for item in per_query),
        "donor_events_exposed": sum(item["sentence_group_arm"]["events_exposed"] for item in per_query),
        "raw_queries_with_correct_video_top20": sum(item["raw_frame_arm"]["correct_video_first_rank"] is not None for item in per_query),
        "donor_queries_with_correct_video_top20": sum(item["sentence_group_arm"]["correct_video_first_rank"] is not None for item in per_query),
        "max_raw_identical_sentence_slots": max(
            (item["raw_frame_arm"]["largest_identical_sentence_slot_count"] for item in per_query), default=0
        ),
        "max_donor_group_member_count": max(
            (item["sentence_group_arm"]["largest_member_count"] for item in per_query), default=0
        ),
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    worktree_aic51 = here.parent
    worktree_root = worktree_aic51.parent
    parser = argparse.ArgumentParser(description="Issue #68 sentence-level ASR read-only A/B")
    parser.add_argument("--primary-root", type=Path, default=DEFAULT_PRIMARY_ROOT)
    parser.add_argument("--query-csv", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=worktree_root / "benchmark-results" / "issue68-sentence-asr" / "ab.json",
    )
    args = parser.parse_args()

    primary_root = args.primary_root.resolve()
    primary_aic51 = primary_root / "aic51-src"
    query_csv = (args.query_csv or (primary_aic51 / "benchmark" / "issue34_headless_queries.csv")).resolve()
    experiment_path = worktree_aic51 / "aic51" / "packages" / "search" / "experimental_sentence_asr.py"
    for required in (primary_root / "config.yaml", query_csv, experiment_path):
        if not required.is_file():
            raise FileNotFoundError(required)

    before_git = git_state(primary_root)
    input_hashes = {
        "config_yaml_sha256": sha256_file(primary_root / "config.yaml"),
        "query_csv_sha256": sha256_file(query_csv),
        "experiment_sha256": sha256_file(experiment_path),
    }
    queries = resolve_queries(query_csv)
    experiment = load_experiment(experiment_path)

    old_cwd = Path.cwd()
    os.chdir(primary_root)
    sys.path.insert(0, str(primary_aic51))
    try:
        from aic51.packages.config import GlobalConfig
        from aic51.packages.index import MilvusDatabase

        collection = GlobalConfig.get("backends", "search", "collection") or "milvus"
        asr_field = GlobalConfig.get("searcher", "asr", "asr_field") or "asr_sparse"
        text_field = asr_field.removesuffix("_sparse").removesuffix("_dense")
        database = MilvusDatabase(collection)
        before_db = database_identity(database)

        per_query = []
        for qid in QUERY_IDS:
            search_results = database.search(
                data=[queries[qid]],
                filter="",
                offset=0,
                limit=EXPOSURE_DEPTH,
                anns_field=asr_field,
                search_params={"metric_type": "BM25", "nprobe": NPROBE},
            )
            hits = search_results[0] if search_results else []
            per_query.append(summarize_query(experiment, qid, queries[qid], hits, text_field))

        after_db = database_identity(database)
    finally:
        os.chdir(old_cwd)

    after_git = git_state(primary_root)
    primary_unchanged = before_git == after_git and before_db == after_db
    payload = {
        "schema_version": "vecna.issue68.sentence_asr_ab.v1",
        "generated_at": utc_now(),
        "status": "complete" if primary_unchanged else "failed_safety_gate",
        "issue": 68,
        "policy_frozen_before_scoring": True,
        "post_result_tuning_allowed": False,
        "donor": {
            "repository": experiment.DONOR_REPOSITORY,
            "commit": experiment.DONOR_COMMIT,
            "source": experiment.DONOR_SOURCE,
            "adaptation": "same-video exact-normalized-ASR-text groups over one existing Vecna ASR BM25 exposure",
        },
        "experiment": {
            "query_ids": list(QUERY_IDS),
            "exposure_depth": EXPOSURE_DEPTH,
            "top_k": TOP_K,
            "asr_mode": "BM25 sparse only",
            "group_key": ["video_id", "normalized_asr_text"],
            "group_score": "max member BM25 score",
            "normalization": "lowercase + whitespace collapse only",
            "nprobe_ignored_for_bm25_but_recorded": NPROBE,
        },
        "issue59_ground_truth_source": ISSUE59_SOURCE,
        "query_source": {"path": str(query_csv), "sha256": input_hashes["query_csv_sha256"]},
        "primary": {
            "root": str(primary_root),
            "before_git": before_git,
            "after_git": after_git,
            "before_database": before_db,
            "after_database": after_db,
            "primary_unchanged": primary_unchanged,
            "input_hashes": input_hashes,
            "asr_field": asr_field,
            "asr_text_field": text_field,
        },
        "aggregate": aggregate(per_query),
        "queries": per_query,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "aggregate": payload["aggregate"], "output": str(args.output)}, indent=2))
    return 0 if primary_unchanged else 3


if __name__ == "__main__":
    raise SystemExit(main())
