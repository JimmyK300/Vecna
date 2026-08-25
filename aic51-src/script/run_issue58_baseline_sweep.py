#!/usr/bin/env python3
"""Issue #58 baseline-sweep launcher (evaluation harness only; no retrieval changes).

Runs ONE quality cell -- the published current-system baseline-v1 default
``clip_siglip_qwen_sparse`` (CLIP+SigLIP+Qwen visual, OCR/ASR BM25 sparse,
rerank OFF, OCR/ASR weights 0.25/0.25, nprobe=32, temporal_k=2000) -- through
the OFFICIAL headless path ``run_p20_p21_measurement.run_quality`` exactly as
published in docs/baseline-v1.md.

The live runtime (code, config.yaml, provenance index registry, canonical
query CSV, Milvus collection ``official_l21_l30_all_v2``) is read from the
PRIMARY checkout (default C:/Users/minhc/Code/Vecna), which is treated as a
read-only reference environment:

  * nothing under PRIMARY_ROOT is written;
  * bytecode writing is disabled so no __pycache__ entries appear there;
  * every artifact is written under THIS worktree's
    benchmark-results/issue58-baseline-sweep/.

Deterministic rerun: see RERUN.md generated next to the artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # never drop .pyc into the primary checkout

DEFAULT_PRIMARY_ROOT = Path(r"C:\Users\minhc\Code\Vecna")
DEFAULT_CELL = "clip_siglip_qwen_sparse"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def worktree_git_identity(worktree_root: Path) -> dict[str, object]:
    def git(*argv: str) -> str:
        return subprocess.run(
            ["git", *argv], cwd=str(worktree_root), check=True, capture_output=True, text=True
        ).stdout.strip()

    return {
        "worktree_root": str(worktree_root),
        "sha": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty": bool(git("status", "--porcelain=v1").strip()),
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    worktree_aic51 = here.parent
    worktree_root = worktree_aic51.parent

    parser = argparse.ArgumentParser(description="Issue #58 baseline sweep via official P20 runner")
    parser.add_argument("--primary-root", type=Path, default=Path(os.environ.get("VECNA_PRIMARY_ROOT", DEFAULT_PRIMARY_ROOT)))
    parser.add_argument("--output-dir", type=Path, default=worktree_root / "benchmark-results" / "issue58-baseline-sweep")
    parser.add_argument("--cell", default=DEFAULT_CELL, help="P20 quality cell (baseline-v1 default: clip_siglip_qwen_sparse)")
    parser.add_argument("--limit-queries", type=int, default=None, help="Debug only: cap number of queries")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    primary_root = args.primary_root.resolve()
    primary_scripts = primary_root / "aic51-src" / "script"
    primary_aic51 = primary_root / "aic51-src"
    csv_path = primary_aic51 / "benchmark" / "issue34_headless_queries.csv"
    fps_csv = primary_aic51 / "benchmark" / "video_rounded_fps.csv"

    missing = [
        str(path)
        for path in (
            primary_root / "config.yaml",
            primary_scripts / "headless_benchmark.py",
            primary_scripts / "run_p20_p21_measurement.py",
            csv_path,
            fps_csv,
        )
        if not path.is_file()
    ]
    if missing:
        print(f"ERROR: primary checkout runtime inputs missing: {missing}", file=sys.stderr)
        return 2

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    launch_metadata: dict[str, object] = {
        "packet": "issue58-baseline-sweep",
        "purpose": "Reproducible current-system baseline sweep for GitHub issue JimmyK300/Vecna#58",
        "started_at": utc_now(),
        "launcher_path": str(Path(__file__).resolve()),
        "launcher_sha256": sha256_file(Path(__file__).resolve()),
        "python": sys.executable,
        "pythondontwritebytecode": True,
        "primary_root": str(primary_root),
        "primary_runtime_inputs": {
            "config_yaml_sha256": sha256_file(primary_root / "config.yaml"),
            "headless_benchmark_sha256": sha256_file(primary_scripts / "headless_benchmark.py"),
            "runner_sha256": sha256_file(primary_scripts / "run_p20_p21_measurement.py"),
            "queries_csv_sha256": sha256_file(csv_path),
            "fps_csv_sha256": sha256_file(fps_csv),
        },
        "output_dir": str(output_dir),
        "cell": args.cell,
        "limit_queries": args.limit_queries,
        "overwrite": args.overwrite,
        "worktree_git": worktree_git_identity(worktree_root),
    }
    metadata_path = output_dir / "sweep.launcher.json"
    metadata_path.write_text(json.dumps(launch_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sys.path.insert(0, str(primary_aic51))
    sys.path.insert(0, str(primary_scripts))
    import run_p20_p21_measurement as runner  # noqa: E402  (chdirs to primary root)

    if args.cell not in runner.CELLS_BY_NAME:
        print(f"ERROR: unknown cell {args.cell!r}; known: {sorted(runner.CELLS_BY_NAME)}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    try:
        rc = runner.run_quality(
            runner.CELLS_BY_NAME[args.cell],
            output_dir,
            overwrite=args.overwrite,
            limit_queries=args.limit_queries,
        )
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
        launch_metadata.update({"status": "failed", "ended_at": utc_now(), "failure": failure})
        metadata_path.write_text(json.dumps(launch_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise

    launch_metadata.update(
        {
            "status": "complete" if rc == 0 else f"nonzero_exit_{rc}",
            "ended_at": utc_now(),
            "elapsed_s": round(time.perf_counter() - started, 3),
            "returncode": rc,
        }
    )
    metadata_path.write_text(json.dumps(launch_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
