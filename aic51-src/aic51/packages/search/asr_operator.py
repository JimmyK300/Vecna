"""Read-only ASR operator search for Vecna Issue #68.

This module promotes the accepted sentence-grouping experiment into an explicit
operator-only search path. It does not modify Searcher.search_multimodal or any
production fusion/index semantics.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .experimental_sentence_asr import group_frame_hits_by_sentence

DEFAULT_EXPOSURE_DEPTH = 1000
DEFAULT_LIMIT = 20
DEFAULT_NPROBE = 32


def _video_ids(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.replace(";", ",").replace(" ", ",").split(",")
    else:
        raw = list(value)
    return [str(item).strip() for item in raw if str(item).strip()]


def _asr_text_field(asr_field: str) -> str:
    return str(asr_field).removesuffix("_sparse").removesuffix("_dense")


def _raw_entity(hit: Any) -> dict[str, Any]:
    if isinstance(hit, dict):
        entity = hit.get("entity")
        return entity if isinstance(entity, dict) else hit
    entity = getattr(hit, "entity", None)
    return entity if isinstance(entity, dict) else {}


def _raw_score(hit: Any) -> float:
    if isinstance(hit, dict):
        value = hit.get("distance", hit.get("score", 0.0))
    else:
        value = getattr(hit, "distance", getattr(hit, "score", 0.0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _frame_record(hit: Any) -> dict[str, Any] | None:
    entity = _raw_entity(hit)
    frame_id = entity.get("frame_id")
    if not isinstance(frame_id, str) or "#" not in frame_id:
        return None
    score = _raw_score(hit)
    return {
        "entity": deepcopy(entity),
        "distance": score,
        "scores": {
            "final": round(score, 6),
            "asr": round(score, 6),
            "asr_raw": round(score, 6),
            "clip": 0.0,
            "ocr": 0.0,
            "clip_raw": 0.0,
            "ocr_raw": 0.0,
        },
    }


def _group_record(group: dict[str, Any], entity_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    members = list(group.get("member_frames") or [])
    if not members:
        return None
    best_score = max(float(member.get("score", 0.0)) for member in members)
    representative = next(
        member for member in members if float(member.get("score", 0.0)) == best_score
    )
    representative_id = representative.get("frame_id")
    entity = entity_by_id.get(str(representative_id))
    if not isinstance(entity, dict):
        return None

    score = float(group.get("score", best_score))
    member_frames = [str(int(member["frame"])) for member in members]
    member_scores = [
        {
            "final": round(float(member.get("score", 0.0)), 6),
            "asr": round(float(member.get("score", 0.0)), 6),
            "asr_raw": round(float(member.get("score", 0.0)), 6),
            "clip": 0.0,
            "ocr": 0.0,
            "clip_raw": 0.0,
            "ocr_raw": 0.0,
        }
        for member in members
    ]
    return {
        "entity": deepcopy(entity),
        "distance": score,
        "scores": {
            "final": round(score, 6),
            "asr": round(score, 6),
            "asr_raw": round(score, 6),
            "clip": 0.0,
            "ocr": 0.0,
            "clip_raw": 0.0,
            "ocr_raw": 0.0,
        },
        "time_line": member_frames,
        "time_line_scores": member_scores,
        "sentence_group": {
            "normalized_asr_text": group.get("normalized_asr_text", ""),
            "asr_text": group.get("asr_text", ""),
            "member_count": len(members),
            "member_frames": deepcopy(members),
        },
    }


def search_asr_operator(
    searcher,
    query_text: str,
    *,
    sentence_level: bool = False,
    offset: int = 0,
    limit: int = DEFAULT_LIMIT,
    exposure_depth: int = DEFAULT_EXPOSURE_DEPTH,
    nprobe: int = DEFAULT_NPROBE,
    include_videos: str | list[str] | None = None,
    exclude_videos: str | list[str] | None = None,
) -> dict[str, Any]:
    """Search existing ASR BM25 and optionally collapse frame hits by sentence.

    `sentence_level=False` is the default and returns the raw frame-level BM25
    order. `sentence_level=True` groups the *same* backend exposure by exact
    normalized ASR text within each video, preserving all member frames.
    """
    query_text = str(query_text or "").strip()
    if not query_text:
        return {"results": [], "total": 0, "offset": max(0, int(offset)), "mode": "sentence" if sentence_level else "raw"}

    asr_field = getattr(searcher, "_asr_name", None)
    if not asr_field:
        raise RuntimeError("ASR sparse search is not enabled on this Searcher")
    text_field = _asr_text_field(asr_field)
    include_ids = _video_ids(include_videos)
    exclude_ids = _video_ids(exclude_videos)
    offset = max(0, int(offset))
    limit = max(1, int(limit))
    exposure_depth = max(offset + limit, int(exposure_depth))

    video_filter = searcher._get_video_filter(include_ids)
    raw = searcher._database.search(
        data=[query_text],
        filter=video_filter,
        offset=0,
        limit=exposure_depth,
        anns_field=asr_field,
        search_params={"metric_type": "BM25", "nprobe": int(nprobe)},
    )
    hits = list(raw[0]) if raw else []
    if exclude_ids:
        hits = searcher._filter_exclude_videos(hits, exclude_ids)

    if not sentence_level:
        records = [record for record in (_frame_record(hit) for hit in hits) if record is not None]
        return {
            "results": records[offset : offset + limit],
            "total": len(records),
            "offset": offset,
            "mode": "raw",
            "asr_field": asr_field,
            "asr_text_field": text_field,
            "exposure_depth": exposure_depth,
        }

    entity_by_id = {
        str(entity.get("frame_id")): deepcopy(entity)
        for entity in (_raw_entity(hit) for hit in hits)
        if isinstance(entity.get("frame_id"), str)
    }
    groups = group_frame_hits_by_sentence(hits, text_field=text_field, limit=None)
    records = [
        record
        for record in (_group_record(group, entity_by_id) for group in groups)
        if record is not None
    ]
    return {
        "results": records[offset : offset + limit],
        "total": len(records),
        "offset": offset,
        "mode": "sentence",
        "asr_field": asr_field,
        "asr_text_field": text_field,
        "exposure_depth": exposure_depth,
    }
