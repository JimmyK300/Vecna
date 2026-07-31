"""Inspect an AIC51 workspace without changing its data.

The report is intentionally filesystem-only.  It describes the inputs and
derived artifacts that determine whether a later ``add``/``analyse``/``index``
run can safely reuse existing data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def read_image_dimensions(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
        return {"width": width, "height": height}
    except Exception as error:  # noqa: BLE001 - report malformed external output
        return {"error": str(error)}


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


def summarize_keyframes(
    workspace: Path,
    include_content: bool,
    inspect_images: bool,
) -> dict[str, Any]:
    root = workspace / "data" / "keyframes"
    videos: dict[str, Any] = {}
    if root.is_dir():
        for video_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            files = collect_files(video_dir, "*.jpg")
            image_dimensions = []
            image_errors = []
            if inspect_images:
                for path in files:
                    dimensions = read_image_dimensions(path)
                    if "error" in dimensions:
                        image_errors.append(
                            {"path": str(path), "error": dimensions["error"]}
                        )
                    else:
                        image_dimensions.append(dimensions)
            videos[video_dir.name] = {
                "count": len(files),
                "frame_ids": [path.stem for path in files],
                "manifest_sha256": hash_manifest(files, video_dir, include_content),
                "file_sizes": sorted(
                    {f"{path.stat().st_size} bytes" for path in files}
                ),
                "image_dimensions": sorted(
                    {
                        f"{item['width']}x{item['height']}"
                        for item in image_dimensions
                    }
                ),
                "image_errors": image_errors,
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


def summarize_features(
    workspace: Path,
    configured_features: set[str],
    include_content: bool,
) -> dict[str, Any]:
    root = workspace / "features"
    videos: dict[str, Any] = {}
    if root.is_dir():
        for video_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            frame_dirs = sorted(path for path in video_dir.iterdir() if path.is_dir())
            counts: Counter[str] = Counter()
            headers: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
            frame_ids_by_feature: defaultdict[str, list[str]] = defaultdict(list)
            paths_by_feature: defaultdict[str, list[Path]] = defaultdict(list)

            for frame_dir in frame_dirs:
                for feature_path in sorted(frame_dir.glob("*.npy")):
                    feature_name = feature_path.stem
                    counts[feature_name] += 1
                    frame_ids_by_feature[feature_name].append(frame_dir.name)
                    paths_by_feature[feature_name].append(feature_path)
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
                "feature_manifests": {
                    feature: hash_manifest(
                        paths_by_feature[feature], video_dir, include_content
                    )
                    for feature in sorted(paths_by_feature)
                },
                "samples": dict(sorted(headers.items())),
            }

    return {
        "root": str(root),
        "exists": root.is_dir(),
        "videos": videos,
    }


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return repr(value)


def inspect_milvus(
    uri: str,
    collection_name: str,
    token: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "enabled": True,
        "uri": uri,
        "collection": collection_name,
    }
    try:
        from pymilvus import MilvusClient
    except ImportError as error:
        result["error"] = f"pymilvus unavailable: {error}"
        return result

    client = None
    try:
        client = MilvusClient(uri=uri, token=token or "")
        result["exists"] = bool(client.has_collection(collection_name))
        if not result["exists"]:
            return result

        result["schema"] = json_safe(client.describe_collection(collection_name))

        indexes: list[dict[str, Any]] = []
        for index_name in client.list_indexes(collection_name):
            try:
                description = client.describe_index(collection_name, index_name)
                indexes.append(
                    {
                        "name": index_name,
                        "description": json_safe(description),
                    }
                )
            except Exception as error:  # noqa: BLE001 - report external state
                indexes.append({"name": index_name, "error": str(error)})
        result["indexes"] = indexes

        try:
            result["stats"] = json_safe(client.get_collection_stats(collection_name))
        except Exception as error:  # noqa: BLE001 - report external state
            result["stats_error"] = str(error)
    except Exception as error:  # noqa: BLE001 - report external connection state
        result["error"] = str(error)
    finally:
        if client is not None:
            close = getattr(client, "close", None)
            if close is not None:
                close()
    return result


def build_report(
    workspace: Path,
    repo_root: Path | None,
    include_content: bool,
    inspect_images: bool,
    milvus_uri: str | None = None,
    milvus_collection: str | None = None,
    milvus_token: str | None = None,
) -> dict[str, Any]:
    config = load_config(workspace)
    configured_features = set(config.get("features", {}))
    return {
        "report_version": REPORT_VERSION,
        "workspace": str(workspace),
        "content_hashing": include_content,
        "image_inspection": inspect_images,
        "producer": git_info(repo_root),
        "config": config,
        "videos": summarize_videos(workspace, include_content),
        "keyframes": summarize_keyframes(workspace, include_content, inspect_images),
        "features": summarize_features(workspace, configured_features, include_content),
        "milvus": (
            inspect_milvus(milvus_uri, milvus_collection, milvus_token)
            if milvus_collection
            else {
                "enabled": False,
                "reason": "Pass --milvus-collection to inspect Milvus.",
            }
        ),
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
        "--inspect-images",
        action="store_true",
        help="Read image headers to report keyframe dimensions.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this path instead of stdout.",
    )
    parser.add_argument(
        "--milvus-uri",
        default="http://localhost:19530",
        help="Milvus URI used with --milvus-collection.",
    )
    parser.add_argument(
        "--milvus-collection",
        help="Inspect this Milvus collection using read-only metadata calls.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = args.workspace.resolve()
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(workspace)
    report = build_report(
        workspace,
        repo_root,
        args.hash_content,
        args.inspect_images,
        milvus_uri=args.milvus_uri,
        milvus_collection=args.milvus_collection,
        milvus_token=os.environ.get("MILVUS_TOKEN"),
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
