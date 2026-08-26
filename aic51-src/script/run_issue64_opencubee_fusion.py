#!/usr/bin/env python3
"""Run the Issue #64 donor arm against a repaired local Vecna checkout.

The primary checkout is treated as a read-only runtime.  This worktree supplies
only the two experimental Issue #64 modules.  They are loaded into the primary
``aic51.packages.search`` package namespace, then the primary Searcher symbol
is replaced in-memory with ``OpenCubeeFusionSearcher`` *before* the primary
P20/P21 runner is imported.

No file under the primary checkout is intentionally written.  The wrapper
captures primary Git status before/after and fails if it changes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def install_experimental_searcher(primary_aic51: Path, worktree_aic51: Path):
    # Primary package must win for every normal Vecna module.
    sys.path.insert(0, str(primary_aic51))

    import aic51.packages.search as search_package
    import aic51.packages.search.searcher as searcher_module

    fusion_path = worktree_aic51 / "aic51" / "packages" / "search" / "experimental_fusion.py"
    searcher_path = worktree_aic51 / "aic51" / "packages" / "search" / "experimental_searcher.py"
    fusion_module = load_module("aic51.packages.search.experimental_fusion", fusion_path)
    experimental_module = load_module("aic51.packages.search.experimental_searcher", searcher_path)

    donor_class = experimental_module.OpenCubeeFusionSearcher
    # Cover both import styles used by Vecna code: package export and direct
    # searcher-module import.  This is process-local only.
    search_package.Searcher = donor_class
    searcher_module.Searcher = donor_class
    return fusion_module, experimental_module


def main() -> int:
    here = Path(__file__).resolve().parent
    worktree_aic51 = here.parent
    worktree_root = worktree_aic51.parent

    parser = argparse.ArgumentParser(description="Issue #64 OpenCubee donor headless arm")
    parser.add_argument(
        "--primary-root",
        type=Path,
        default=Path(os.environ.get("VECNA_PRIMARY_ROOT", DEFAULT_PRIMARY_ROOT)),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=worktree_root / "benchmark-results" / "issue64-opencubee-fusion" / "donor",
    )
    parser.add_argument("--cell", default=DEFAULT_CELL)
    parser.add_argument("--limit-queries", type=int, default=None, help="debug only")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    primary_root = args.primary_root.resolve()
    primary_aic51 = primary_root / "aic51-src"
    primary_scripts = primary_aic51 / "script"
    worktree_fusion = worktree_aic51 / "aic51" / "packages" / "search" / "experimental_fusion.py"
    worktree_searcher = worktree_aic51 / "aic51" / "packages" / "search" / "experimental_searcher.py"

    required = [
        primary_root / "config.yaml",
        primary_scripts / "headless_benchmark.py",
        primary_scripts / "run_p20_p21_measurement.py",
        primary_aic51 / "benchmark" / "issue34_headless_queries.csv",
        worktree_fusion,
        worktree_searcher,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Issue #64 required inputs missing: {missing}")

    before = primary_identity(primary_root)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "issue64-run.json"

    manifest: dict[str, object] = {
        "issue": 64,
        "status": "running",
        "started_at": utc_now(),
        "strategy": "opencubee_model_weighted",
        "donor": {
            "repository": "k19tvan/Opencubee2",
            "commit": "f8045a6961de65b38436824606b493a12e73f89a",
            "source": "backend/services/search.py::fuse_results",
            "adaptation": (
                "equal-weight late fusion over each visual model's existing Vecna-normalized "
                "visual score, then unchanged Vecna outer visual/OCR/ASR weighting"
            ),
        },
        "primary_root": str(primary_root),
        "primary_before": before,
        "primary_inputs": {
            "config_yaml_sha256": sha256_file(primary_root / "config.yaml"),
            "runner_sha256": sha256_file(primary_scripts / "run_p20_p21_measurement.py"),
            "headless_benchmark_sha256": sha256_file(primary_scripts / "headless_benchmark.py"),
            "queries_sha256": sha256_file(primary_aic51 / "benchmark" / "issue34_headless_queries.csv"),
        },
        "experimental_inputs": {
            "fusion_sha256": sha256_file(worktree_fusion),
            "searcher_sha256": sha256_file(worktree_searcher),
        },
        "cell": args.cell,
        "limit_queries": args.limit_queries,
        "policy_frozen_before_scoring": True,
        "visual_model_weights": "equal across active selected visual target features",
        "post_result_tuning_allowed": False,
        "output_dir": str(output_dir),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    install_experimental_searcher(primary_aic51, worktree_aic51)
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
        print("ERROR: primary Vecna checkout changed during Issue #64 donor run", file=sys.stderr)
        return 3
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
