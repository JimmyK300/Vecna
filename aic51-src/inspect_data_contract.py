"""Inspect an AIC51 workspace without changing its data.

The report is intentionally filesystem-only.  It describes the inputs and
derived artifacts that determine whether a later ``add``/``analyse``/``index``
run can safely reuse existing data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


REPORT_VERSION = 1
HASH_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def hash_manifest(paths: Iterable[Path], root: Path, include_content: bool) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(b"\0")
        if include_content:
            digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def git_info(repo_root: Path | None) -> dict[str, Any] | None:
    if repo_root is None:
        return None

    def run(*args: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    commit = run("rev-parse", "HEAD")
    if commit is None:
        return None
    return {
        "root": str(repo_root),
        "commit": commit,
        "branch": run("symbolic-ref", "--short", "-q", "HEAD"),
        "dirty": run("status", "--porcelain") != "",
    }


def find_repo_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def load_config(workspace: Path) -> dict[str, Any]:
    config_path = workspace / "config.yaml"
    result: dict[str, Any] = {
        "path": str(config_path),
        "exists": config_path.is_file(),
    }
    if not config_path.is_file():
        return result

    result["sha256"] = sha256_file(config_path)
    try:
        import yaml
    except ImportError as error:
        result["parse_error"] = f"PyYAML unavailable: {error}"
        return result

    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as error:  # noqa: BLE001 - report malformed external config
        result["parse_error"] = str(error)
        return result

    features = config.get("features") or {}
    result["features"] = {
        name: {
            "model": details.get("model"),
            "source": details.get("source"),
            "arch_name": details.get("arch_name"),
            "pretrained_model": details.get("pretrained_model"),
            "dimension": (details.get("index") or {}).get("dim"),
            "datatype": (details.get("index") or {}).get("datatype"),
        }
        for name, details in features.items()
        if isinstance(details, dict)
    }
    result["add"] = config.get("add") or {}
    result["milvus"] = {
        "fields": config.get("milvus", {}).get("fields", [])
        if isinstance(config.get("milvus"), dict)
        else []
    }
    return result


def collect_files(root: Path, pattern: str = "*") -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob(pattern) if path.is_file())


def summarize_videos(workspace: Path, include_content: bool) -> dict[str, Any]:
    root = workspace / "data" / "videos"
    files = collect_files(root, "*.mp4")
    return {
        "root": str(root),
        "exists": root.is_dir(),
        "count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "manifest_sha256": hash_manifest(files, root, include_content) if root.is_dir() else None,
        "videos": [
            {
                "id": path.stem,
                "relative_path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path) if include_content else None,
            }
            for path in files
        ],
    }


def summarize_keyframes(workspace: Path, include_content: bool) -> dict[str, Any]:
    root = workspace / "data" / "keyframes"
    videos: dict[str, Any] = {}
    if root.is_dir():
        for video_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            files = collect_files(video_dir, "*.jpg")
            videos[video_dir.name] = {
                "count": len(files),
                "frame_ids": [path.stem for path in files],
                "manifest_sha256": hash_manifest(files, video_dir, include_content),
                "dimensions": sorted(
                    {f"{path.stat().st_size} bytes" for path in files}
                ),
            }
    return {
        "root": str(root),
        "exists": root.is_dir(),
        "videos": videos,
    }


def read_npy_header(path: Path) -> dict[str, Any]:
    try:
        import numpy as np

        array = np.load(path, mmap_mode="r", allow_pickle=False)
        return {
            "shape": list(array.shape),
            "dtype": str(array.dtype),
        }
    except Exception as error:  # noqa: BLE001 - report malformed external output
        return {"error": str(error)}


def summarize_features(workspace: Path, configured_features: set[str]) -> dict[str, Any]:
    root = workspace / "features"
    videos: dict[str, Any] = {}
    if root.is_dir():
        for video_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            frame_dirs = sorted(path for path in video_dir.iterdir() if path.is_dir())
            counts: Counter[str] = Counter()
            headers: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
            frame_ids_by_feature: defaultdict[str, list[str]] = defaultdict(list)

            for frame_dir in frame_dirs:
                for feature_path in sorted(frame_dir.glob("*.npy")):
                    feature_name = feature_path.stem
                    counts[feature_name] += 1
                    frame_ids_by_feature[feature_name].append(frame_dir.name)
                    if len(headers[feature_name]) < 3:
                        headers[feature_name].append(
                            {"path": str(feature_path), **read_npy_header(feature_path)}
                        )

            expected = configured_features or set(counts)
            videos[video_dir.name] = {
                "frame_count": len(frame_dirs),
                "feature_counts": dict(sorted(counts.items())),
                "missing_counts": {
                    feature: len(frame_dirs) - counts.get(feature, 0)
                    for feature in sorted(expected)
                },
                "feature_frame_ids": {
                    feature: frame_ids_by_feature[feature]
                    for feature in sorted(frame_ids_by_feature)
                },
                "samples": dict(sorted(headers.items())),
            }

    return {
        "root": str(root),
        "exists": root.is_dir(),
        "videos": videos,
    }


def build_report(
    workspace: Path,
    repo_root: Path | None,
    include_content: bool,
) -> dict[str, Any]:
    config = load_config(workspace)
    configured_features = set(config.get("features", {}))
    return {
        "report_version": REPORT_VERSION,
        "workspace": str(workspace),
        "content_hashing": include_content,
        "producer": git_info(repo_root),
        "config": config,
        "videos": summarize_videos(workspace, include_content),
        "keyframes": summarize_keyframes(workspace, include_content),
        "features": summarize_features(workspace, configured_features),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "workspace",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="AIC51 workspace containing config.yaml, data/, and features/.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root to record as the producer source.",
    )
    parser.add_argument(
        "--hash-content",
        action="store_true",
        help="Hash video and keyframe contents; this can be expensive.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this path instead of stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = args.workspace.resolve()
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(workspace)
    report = build_report(workspace, repo_root, args.hash_content)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
