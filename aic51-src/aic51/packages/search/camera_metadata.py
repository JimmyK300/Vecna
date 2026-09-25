"""Batch 2 camera metadata filters backed by the OCR road-classification file."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path


METADATA_FILENAME = "camera_info_workspace2_road_classification.json"
ROAD_TYPES = {
    "three_way": "3-Way Intersection",
    "four_way": "4-Way Intersection",
    "roundabout": "Roundabout",
    "bridge": "Bridge Approach / Underpass",
}
LIGHTING_TYPES = {"day", "night", "unknown"}
VIDEO_ID_PATTERN = re.compile(r"N\d{3}-V\d{3}\Z")


def metadata_path() -> Path:
    override = os.environ.get("AIC51_CAMERA_METADATA_PATH")
    if override:
        return Path(override).expanduser().resolve()
    candidates = [Path.cwd() / METADATA_FILENAME, Path(__file__).resolve().parents[4] / METADATA_FILENAME]
    return next((path for path in candidates if path.is_file()), candidates[0])


def lighting_from_ocr(time_of_day: str) -> str:
    """A conservative time proxy, not a visual day/night annotation."""
    match = re.match(r"^\s*(\d{1,2})[:.\-]", str(time_of_day or ""))
    if not match:
        return "unknown"
    hour = int(match.group(1))
    if 6 <= hour <= 17:
        return "day"
    if 18 <= hour <= 23:
        return "night"
    # OCR in this corpus sometimes reads a daytime clock as 00:00.
    return "unknown"


@lru_cache(maxsize=4)
def load_camera_metadata(path: str) -> dict[str, dict]:
    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    metadata = {}
    for row in rows:
        video_id = row.get("video_id", "")
        if not VIDEO_ID_PATTERN.fullmatch(video_id):
            continue
        metadata[video_id] = {
            "road_type": row.get("intersection_type", ""),
            "lighting": row.get("lighting_label") or lighting_from_ocr(row.get("time_of_day", "")),
        }
    return metadata


def build_camera_filter(road_type: str = "", lighting: str = "", path: Path | None = None) -> str:
    if road_type not in ("", *ROAD_TYPES):
        raise ValueError("Invalid road type")
    if lighting not in ("", *LIGHTING_TYPES):
        raise ValueError("Invalid lighting filter")
    if not road_type and not lighting:
        return ""
    source = path or metadata_path()
    if not source.is_file():
        raise ValueError(f"Camera metadata file not found: {source}")
    metadata = load_camera_metadata(str(source))
    video_ids = sorted(
        video_id for video_id, item in metadata.items()
        if (not road_type or item["road_type"] == ROAD_TYPES[road_type])
        and (not lighting or item["lighting"] == lighting)
    )
    if not video_ids:
        return 'frame_id == "__no_camera_match__"'
    return " || ".join(f'frame_id like "{video_id}#%"' for video_id in video_ids)
