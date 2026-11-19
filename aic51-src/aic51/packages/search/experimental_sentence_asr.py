"""Experimental OpenCubee-derived sentence-level ASR grouping for Vecna Issue #68.

This module is intentionally unreachable from production search code. It adapts
OpenCubee's sentence-level ASR result unit to Vecna's existing frame-projected
WhisperX text without rebuilding or writing any index.

Frozen donor source:
- k19tvan/Opencubee2@0412b55a0f9a3c9642805a669efd871fddf3e970
- src/tools/extract_asr.py
- src/tools/build_scene_frame_mapping.py
- backend/services/search.py::search_semantic_asr_*

The experimental unit is exact normalized ASR-text identity within one video.
This is deliberately an approximation for evaluation, not a production claim
that repeated identical text necessarily came from one physical utterance.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

DONOR_REPOSITORY = "k19tvan/Opencubee2"
DONOR_COMMIT = "0412b55a0f9a3c9642805a669efd871fddf3e970"
DONOR_SOURCE = (
    "src/tools/extract_asr.py + src/tools/build_scene_frame_mapping.py + "
    "backend/services/search.py::search_semantic_asr_*"
)

DEFAULT_EXPOSURE_DEPTH = 1000
DEFAULT_TOP_K = 20


def normalize_asr_text(value: Any) -> str:
    """Normalize only whitespace/case; do not rewrite linguistic content."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def parse_frame_id(value: Any) -> tuple[str, int] | None:
    if not isinstance(value, str) or "#" not in value:
        return None
    video_id, frame_text = value.rsplit("#", 1)
    video_id = video_id.strip()
    try:
        frame = int(frame_text)
    except (TypeError, ValueError):
        return None
    if not video_id or frame < 0:
        return None
    return video_id, frame


def _entity(hit: Any) -> dict[str, Any]:
    if isinstance(hit, dict):
        entity = hit.get("entity")
        if isinstance(entity, dict):
            return entity
        return hit
    entity = getattr(hit, "entity", None)
    return entity if isinstance(entity, dict) else {}


def _score(hit: Any) -> float:
    if isinstance(hit, dict):
        value = hit.get("distance", hit.get("score", 0.0))
    else:
        value = getattr(hit, "distance", getattr(hit, "score", 0.0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def canonicalize_frame_hit(hit: Any, *, text_field: str = "asr") -> dict[str, Any] | None:
    entity = _entity(hit)
    frame_id = entity.get("frame_id")
    parsed = parse_frame_id(frame_id)
    text = entity.get(text_field, "")
    normalized = normalize_asr_text(text)
    if parsed is None or not normalized:
        return None
    video_id, frame = parsed
    return {
        "frame_id": frame_id,
        "video_id": video_id,
        "frame": frame,
        "score": _score(hit),
        "asr_text": str(text),
        "normalized_asr_text": normalized,
    }


def sentence_group_key(frame_hit: dict[str, Any]) -> tuple[str, str]:
    return frame_hit["video_id"], frame_hit["normalized_asr_text"]


def group_frame_hits_by_sentence(
    hits: list[Any],
    *,
    text_field: str = "asr",
    limit: int | None = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    """Collapse identical same-video ASR text into deterministic result groups.

    Group score is the maximum member BM25 score. All member frames are retained
    for event-exposure analysis. Inputs are never mutated.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_hit in hits:
        item = canonicalize_frame_hit(raw_hit, text_field=text_field)
        if item is None:
            continue
        key = sentence_group_key(item)
        group = groups.get(key)
        if group is None:
            group = {
                "video_id": item["video_id"],
                "normalized_asr_text": item["normalized_asr_text"],
                "asr_text": item["asr_text"],
                "score": item["score"],
                "member_frames": [],
            }
            groups[key] = group
        elif item["score"] > group["score"]:
            group["score"] = item["score"]
            group["asr_text"] = item["asr_text"]
        group["member_frames"].append(
            {
                "frame_id": item["frame_id"],
                "frame": item["frame"],
                "score": item["score"],
            }
        )

    result = []
    for group in groups.values():
        group = deepcopy(group)
        group["member_frames"].sort(key=lambda item: (item["frame"], item["frame_id"]))
        group["member_count"] = len(group["member_frames"])
        result.append(group)

    result.sort(
        key=lambda group: (
            -float(group["score"]),
            group["video_id"],
            group["normalized_asr_text"],
        )
    )
    if limit is None:
        return result
    return result[: max(0, int(limit))]


def raw_top_frame_hits(
    hits: list[Any],
    *,
    text_field: str = "asr",
    limit: int = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    """Canonical raw frame arm from the same backend exposure."""
    result = []
    for hit in hits:
        item = canonicalize_frame_hit(hit, text_field=text_field)
        if item is not None:
            result.append(item)
        if len(result) >= max(0, int(limit)):
            break
    return result


def raw_flooding_stats(raw_hits: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[tuple[str, str], int] = {}
    for hit in raw_hits:
        key = sentence_group_key(hit)
        counts[key] = counts.get(key, 0) + 1
    return {
        "raw_slots": len(raw_hits),
        "unique_sentence_groups": len(counts),
        "largest_identical_sentence_slot_count": max(counts.values(), default=0),
    }
