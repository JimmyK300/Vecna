#!/usr/bin/env python3
"""Run the Issue #64 legacy arm against a repaired local Vecna checkout.

This is the control companion to ``run_issue64_opencubee_fusion.py``.  It uses
the primary checkout's existing P20/P21 quality runner without injecting or
importing any Issue #64 experimental Searcher.  Artifacts are written only to
this worktree, while the primary checkout is treated as read-only.

The wrapper records primary Git/config/query/runner identity before execution
and fails if the primary Git state changes, making it straightforward to run a
back-to-back identity-matched legacy/donor A/B.
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

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

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


def git_output(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), check=True, capture_output=True, text=True
    ).stdout


def primary_identity(root: Path) -> dict[str, object]:
    return {
        "head": git_output(root, "rev-parse", "HEAD").strip(),
        "branch": git_output(root, "branch", "--show-current").strip(),
        "status_porcelain_v1": git_output(root, "status", "--porcelain=v1"),
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    worktree_aic51 = here.parent
    worktree_root = worktree_aic51.parent

    parser = argparse.ArgumentParser(description="Issue #64 identity-matched legacy headless arm")
    parser.add_argument(
        "--primary-root",
        type=Path,
        default=Path(os.environ.get("VECNA_PRIMARY_ROOT", DEFAULT_PRIMARY_ROOT)),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=worktree_root / "benchmark-results" / "issue64-opencubee-fusion" / "legacy",
    )
    parser.add_argument("--cell", default=DEFAULT_CELL)
    parser.add_argument("--limit-queries", type=int, default=None, help="debug only")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    primary_root = args.primary_root.resolve()
    primary_aic51 = primary_root / "aic51-src"
    primary_scripts = primary_aic51 / "script"
    required = [
        primary_root / "config.yaml",
        primary_scripts / "headless_benchmark.py",
        primary_scripts / "run_p20_p21_measurement.py",
        primary_aic51 / "benchmark" / "issue34_headless_queries.csv",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Issue #64 required primary inputs missing: {missing}")

    before = primary_identity(primary_root)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "issue64-run.json"
    manifest: dict[str, object] = {
        "issue": 64,
        "arm": "legacy",
        "status": "running",
        "started_at": utc_now(),
        "primary_root": str(primary_root),
        "primary_before": before,
        "primary_inputs": {
            "config_yaml_sha256": sha256_file(primary_root / "config.yaml"),
            "runner_sha256": sha256_file(primary_scripts / "run_p20_p21_measurement.py"),
            "headless_benchmark_sha256": sha256_file(primary_scripts / "headless_benchmark.py"),
            "queries_sha256": sha256_file(primary_aic51 / "benchmark" / "issue34_headless_queries.csv"),
        },
        "cell": args.cell,
        "limit_queries": args.limit_queries,
        "output_dir": str(output_dir),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sys.path.insert(0, str(primary_aic51))
    sys.path.insert(0, str(primary_scripts))
    import run_p20_p21_measurement as runner  # noqa: E402

    if args.cell not in runner.CELLS_BY_NAME:
        raise ValueError(f"unknown quality cell {args.cell!r}; known={sorted(runner.CELLS_BY_NAME)}")

    started = time.perf_counter()
    try:
        rc = runner.run_quality(
            runner.CELLS_BY_NAME[args.cell],
            output_dir,
            overwrite=args.overwrite,
            limit_queries=args.limit_queries,
        )
    except Exception as exc:
        manifest.update(
            {
                "status": "failed",
                "ended_at": utc_now(),
                "failure": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise

    after = primary_identity(primary_root)
    primary_unchanged = before == after
    manifest.update(
        {
            "status": "complete" if rc == 0 and primary_unchanged else "failed_safety_gate",
            "returncode": rc,
            "ended_at": utc_now(),
            "elapsed_s": round(time.perf_counter() - started, 3),
            "primary_after": after,
            "primary_unchanged": primary_unchanged,
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not primary_unchanged:
        print("ERROR: primary Vecna checkout changed during Issue #64 legacy run", file=sys.stderr)
        return 3
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
