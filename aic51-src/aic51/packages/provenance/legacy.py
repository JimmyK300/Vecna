"""Inspection of the legacy feature-extraction layout."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _video_record(path: Path, root: Path, hash_content: bool) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": path.relative_to(root).as_posix(),
        "video_id": path.stem,
        "size_bytes": path.stat().st_size,
    }
    if hash_content:
        record["sha256"] = _sha256(path)
    return record


def _sample_contract(files: list[Path]) -> dict[str, Any] | None:
    if not files:
        return None
    value = np.load(files[0], allow_pickle=False)
    return {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "sample_path": files[0].name,
    }


def build_legacy_manifest(root: str | Path, *, hash_content: bool = False) -> dict[str, Any]:
    """Build a read-only manifest for the friend's ``temp-extraction`` data.

    The function intentionally does not classify the data as reusable. It
    records evidence needed by a later compatibility decision and marks OCR
    as excluded because its producer reported a problem.
    """

    base = Path(root).resolve()
    video_dir = base / "video"
    videos = []
    if video_dir.exists():
        videos = [
            _video_record(path, base, hash_content)
            for path in sorted(video_dir.glob("*.mp4"))
        ]

    feature_videos: dict[str, dict[str, Any]] = {}
    for video_path in sorted(path for path in base.iterdir() if path.is_dir() and path.name != "video"):
        frame_dirs = sorted(path for path in video_path.iterdir() if path.is_dir())
        by_name: dict[str, list[Path]] = {}
        frame_ids = []
        for frame_dir in frame_dirs:
            frame_ids.append(frame_dir.name)
            for feature_path in sorted(frame_dir.glob("*.npy")):
                by_name.setdefault(feature_path.name, []).append(feature_path)

        artifacts = {}
        for name, files in sorted(by_name.items()):
            artifacts[name] = {
                "count": len(files),
                "contract": _sample_contract(files),
            }

        feature_videos[video_path.name] = {
            "frame_count": len(frame_ids),
            "frame_ids": frame_ids,
            "artifacts": artifacts,
        }

    return {
        "manifest_version": "legacy-1",
        "layout": "video-and-feature-roots",
        "producer_commit": None,
        "producer_config": None,
        "ocr_status": "excluded-suspect",
        "videos": {"count": len(videos), "files": videos},
        "features": {
            "video_count": len(feature_videos),
            "videos": feature_videos,
        },
    }
