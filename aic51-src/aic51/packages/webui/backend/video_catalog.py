"""Safe lookup of source videos exposed by the web UI.

The catalog deliberately accepts video IDs rather than filesystem paths.  A
workspace can point at a read-only external video tree with either the
``VECNA_VIDEO_ROOT`` environment variable or ``media.video_root`` in
``config.yaml``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VIDEO_ROOT_ENV = "VECNA_VIDEO_ROOT"


class AmbiguousVideoError(RuntimeError):
    """Raised when one video ID maps to more than one source file."""


def get_video_root() -> Path:
    """Return the configured source root, resolved to an absolute path."""

    configured_root = os.environ.get(VIDEO_ROOT_ENV)
    if not configured_root:
        configured_root = GlobalConfig.get("media", "video_root")

    if configured_root:
        return Path(configured_root).expanduser().resolve()

    return (Path.cwd() / constant.VIDEO_DIR).resolve()


def _is_valid_video_id(video_id: str) -> bool:
    return bool(VIDEO_ID_PATTERN.fullmatch(video_id or ""))


def _is_inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def resolve_video_path(video_id: str) -> Path | None:
    """Resolve an exact video ID to one file below the configured root.

    Both the legacy flat layout (``data/videos/V001.mp4``) and nested source
    layouts (``videos/L23/V23.mp4``) are supported.  Duplicate IDs are
    rejected instead of selecting an arbitrary file.
    """

    if not _is_valid_video_id(video_id):
        return None

    root = get_video_root()
    if not root.is_dir():
        return None

    exact_path = root / f"{video_id}{constant.VIDEO_EXTENSION}"
    if exact_path.is_file() and _is_inside_root(exact_path, root):
        return exact_path.resolve()

    normalized_id = video_id.casefold()
    matches = [
        path.resolve()
        for path in root.rglob(f"*{constant.VIDEO_EXTENSION}")
        if path.is_file()
        and path.stem.casefold() == normalized_id
        and _is_inside_root(path, root)
    ]

    if len(matches) > 1:
        raise AmbiguousVideoError(
            f"Video ID {video_id!r} has multiple files below {root}"
        )

    return matches[0] if matches else None


def list_video_ids() -> list[str]:
    """List unique source-video IDs below the configured root."""

    root = get_video_root()
    if not root.is_dir():
        return []

    ids: dict[str, str] = {}
    for path in root.rglob(f"*{constant.VIDEO_EXTENSION}"):
        if not path.is_file() or not _is_inside_root(path, root):
            continue
        video_id = path.stem
        if not _is_valid_video_id(video_id):
            continue
        ids.setdefault(video_id.casefold(), video_id)

    return sorted(ids.values(), key=str.casefold)
