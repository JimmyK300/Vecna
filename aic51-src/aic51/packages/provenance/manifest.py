"""Read-only workspace manifest generation.

The manifest records the inputs and derived artifacts that define a Vecna
data contract. It does not run extraction, analysis, indexing, or migration.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any


def _git_commit(work_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(work_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path, root: Path, hash_content: bool) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
    }
    if hash_content:
        record["sha256"] = _sha256(path)
    return record


def build_manifest(work_dir: str | Path, *, hash_content: bool = False) -> dict[str, Any]:
    """Build a JSON-serializable manifest without changing ``work_dir``.

    ``work_dir`` is a normal Vecna workspace containing ``data/videos`` and
    ``features``. Missing directories are represented as empty inventories so
    partial legacy datasets can be inspected safely.
    """

    root = Path(work_dir).resolve()
    video_dir = root / "data" / "videos"
    feature_dir = root / "features"

    videos = []
    if video_dir.exists():
        videos = [
            _file_record(path, root, hash_content)
            for path in sorted(video_dir.iterdir())
            if path.is_file()
        ]

    features: dict[str, dict[str, Any]] = {}
    if feature_dir.exists():
        for video_path in sorted(path for path in feature_dir.iterdir() if path.is_dir()):
            files = [
                _file_record(path, root, hash_content)
                for path in sorted(video_path.glob("*/*"))
                if path.is_file()
            ]
            features[video_path.name] = {
                "file_count": len(files),
                "files": files,
            }

    config_path = root / "config.yaml"
    config: dict[str, Any] = {"path": config_path.relative_to(root).as_posix(), "present": config_path.exists()}
    if config_path.exists():
        config["size_bytes"] = config_path.stat().st_size
        if hash_content:
            config["sha256"] = _sha256(config_path)

    return {
        "manifest_version": "1",
        "repo_commit": _git_commit(root),
        "config": config,
        "videos": {"count": len(videos), "files": videos},
        "features": {
            "video_count": len(features),
            "videos": features,
        },
    }
