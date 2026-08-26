#!/usr/bin/env python3
"""Read-only live-collection runner for Vecna Issue #66.

The repaired primary checkout supplies config + Milvus runtime.  The donor
classifier is loaded from this isolated worktree by file path, so the primary
checkout is never modified or imported from the experiment branch.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PRIMARY_ROOT = Path(r"C:\Users\minhc\Code\Vecna")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_state(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    return {
        "head": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current"),
        "porcelain": run("status", "--porcelain=v1"),
    }


def load_experiment(module_path: Path):
    spec = importlib.util.spec_from_file_location("vecna_issue66_similarity_labels", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load experiment module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def list_indexes(database) -> list[str]:
    try:
        raw = database._client.list_indexes(database._collection_name)
        return sorted(str(item) for item in raw)
    except Exception as exc:
        return [f"unavailable:{type(exc).__name__}:{exc}"]


def sample_ids(database, prefixes: list[str], per_prefix: int) -> list[str]:
    samples: list[str] = []
    for prefix in prefixes:
        rows = database.query(filter=f'frame_id like "{prefix}#%"', offset=0, limit=max(3, per_prefix * 8))
        ids = sorted(
            str(row.get("frame_id"))
            for row in rows
            if isinstance(row, dict) and row.get("frame_id")
        )
        if not ids:
            continue
        picks = [ids[0]]
        if per_prefix >= 2 and len(ids) > 2:
            picks.append(ids[len(ids) // 2])
        if per_prefix >= 3 and len(ids) > 1:
            picks.append(ids[-1])
        for frame_id in picks[:per_prefix]:
            if frame_id not in samples:
                samples.append(frame_id)
    return samples


def main() -> int:
    script_path = Path(__file__).resolve()
    worktree_root = script_path.parents[2]
    module_path = worktree_root / "aic51-src" / "aic51" / "packages" / "search" / "experimental_similarity_labels.py"

    parser = argparse.ArgumentParser(description="Issue #66 read-only similarity-label smoke")
    parser.add_argument("--primary-root", type=Path, default=Path(os.environ.get("VECNA_PRIMARY_ROOT", DEFAULT_PRIMARY_ROOT)))
    parser.add_argument("--source-id", action="append", default=[], help="Exact canonical Milvus frame_id; may repeat")
    parser.add_argument("--sample-prefix", action="append", default=[], help="Video prefix such as L21_V001; may repeat")
    parser.add_argument("--per-prefix", type=int, default=3)
    parser.add_argument("--feature", default="image_siglip_so400m-384")
    parser.add_argument("--threshold", type=float, default=0.985)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--nprobe", type=int, default=32)
    parser.add_argument("--intro-min-frame-gap", type=int, default=100)
    parser.add_argument("--intro-start-window-frames", type=int, default=300)
    parser.add_argument("--output", type=Path, default=worktree_root / "benchmark-results" / "issue66-similarity-labels" / "smoke.json")
    args = parser.parse_args()

    primary_root = args.primary_root.resolve()
    primary_aic51 = primary_root / "aic51-src"
    config_path = primary_root / "config.yaml"
    if not config_path.is_file() or not module_path.is_file():
        print("ERROR: required primary config or experiment module is missing", file=sys.stderr)
        return 2

    before_git = git_state(primary_root)
    before_hash = sha256_file(config_path)

    old_cwd = Path.cwd()
    try:
        os.chdir(primary_root)
        sys.path.insert(0, str(primary_aic51))
        from aic51.packages.config import GlobalConfig
        from aic51.packages.index import MilvusDatabase

        collection = GlobalConfig.get("backends", "search", "collection") or "milvus"
        database = MilvusDatabase(collection)

        before_collection = {
            "collection": collection,
            "row_count": database.get_size(),
            "indexes": list_indexes(database),
        }

        experiment = load_experiment(module_path)

        class ReadOnlySearcherAdapter:
            def __init__(self, db):
                self._database = db

            def get(self, frame_id):
                return self._database.get(frame_id)

        adapter = ReadOnlySearcherAdapter(database)
        source_ids = list(dict.fromkeys(str(item).strip() for item in args.source_id if str(item).strip()))
        if args.sample_prefix:
            for frame_id in sample_ids(database, args.sample_prefix, max(1, args.per_prefix)):
                if frame_id not in source_ids:
                    source_ids.append(frame_id)
        if not source_ids:
            raise ValueError("provide --source-id and/or --sample-prefix")

        runs = []
        for source_id in source_ids:
            try:
                result = experiment.find_similar_frames(
                    adapter,
                    source_id,
                    feature=args.feature,
                    threshold=args.threshold,
                    limit=args.limit,
                    nprobe=args.nprobe,
                    intro_min_frame_gap=args.intro_min_frame_gap,
                    intro_start_window_frames=args.intro_start_window_frames,
                )
                runs.append({"status": "ok", **result})
            except Exception as exc:
                runs.append({
                    "status": "error",
                    "source_frame_id": source_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })

        after_collection = {
            "collection": collection,
            "row_count": database.get_size(),
            "indexes": list_indexes(database),
        }
    finally:
        os.chdir(old_cwd)

    after_git = git_state(primary_root)
    after_hash = sha256_file(config_path)
    primary_unchanged = before_git == after_git and before_hash == after_hash and before_collection == after_collection

    counts = {"DUP": 0, "INTRO": 0, "REUSE": 0}
    for run in runs:
        for item in run.get("results", []):
            relation = item.get("relation")
            if relation in counts:
                counts[relation] += 1

    packet = {
        "schema_version": "vecna.issue66.smoke.v1",
        "started_at": utc_now(),
        "experiment_worktree": str(worktree_root),
        "experiment_module": str(module_path),
        "experiment_module_sha256": sha256_file(module_path),
        "primary_root": str(primary_root),
        "primary_git_before": before_git,
        "primary_git_after": after_git,
        "config_sha256_before": before_hash,
        "config_sha256_after": after_hash,
        "collection_before": before_collection,
        "collection_after": after_collection,
        "primary_unchanged": primary_unchanged,
        "parameters": {
            "feature": args.feature,
            "threshold": args.threshold,
            "limit": args.limit,
            "nprobe": args.nprobe,
            "intro_min_frame_gap": args.intro_min_frame_gap,
            "intro_start_window_frames": args.intro_start_window_frames,
        },
        "relation_counts": counts,
        "runs": runs,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS" if primary_unchanged else "FAIL_PRIMARY_MUTATED",
        "output": str(args.output),
        "sources": len(runs),
        "relation_counts": counts,
        "primary_unchanged": primary_unchanged,
    }, indent=2))
    return 0 if primary_unchanged else 3


if __name__ == "__main__":
    raise SystemExit(main())
