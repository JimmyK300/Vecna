"""Pure scoring helpers for Issue #63 reconstructed semantic intervals."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


def normalize_video_id(value: Any) -> str:
    return Path(str(value or "").strip()).stem.upper()


def result_frames(item: dict[str, Any]) -> list[int]:
    raw = item.get("time_line") or item.get("timeline")
    if raw is None:
        raw = [item.get("frame_id", item.get("frame"))]
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    frames: list[int] = []
    for value in raw:
        if value is None or isinstance(value, bool):
            continue
        try:
            frames.append(int(value))
        except (TypeError, ValueError):
            continue
    return frames


def result_matches_interval(record: dict[str, Any], item: dict[str, Any]) -> bool:
    if normalize_video_id(item.get("video_id") or item.get("video")) != normalize_video_id(record.get("video_id")):
        return False
    ranges = record.get("reviewed_ranges") or []
    if item.get("start_frame") is not None and item.get("end_frame") is not None:
        result_start = int(item["start_frame"])
        result_end = int(item["end_frame"])
        return any(
            result_start <= int(rng["end_frame"]) and result_end >= int(rng["start_frame"])
            for rng in ranges
        )
    return any(
        int(rng["start_frame"]) <= frame <= int(rng["end_frame"])
        for frame in result_frames(item)
        for rng in ranges
    )


def score_reconstructed(record: dict[str, Any], results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    first = next(
        (rank for rank, item in enumerate(results, 1) if result_matches_interval(record, item)),
        None,
    )
    return {
        "hit": first is not None,
        "first_correct_rank": first,
        "reciprocal_rank": 0.0 if first is None or first > 20 else 1.0 / first,
        **{f"recall_at_{k}": float(first is not None and first <= k) for k in (1, 5, 10, 20)},
        "no_hit_within_20": first is None or first > 20,
    }


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(records)
    if not count:
        return {"scoreable_count": 0}
    first_ranks = [record.get("first_correct_rank") for record in records]
    return {
        "scoreable_count": count,
        # Preserve legacy TRAKE fractional event coverage. Reconstructed cases use
        # target_mode=any, so their stored recall values remain binary.
        "recall_at_1": round(sum(float(record.get("recall_at_1") or 0.0) for record in records) / count, 6),
        "recall_at_5": round(sum(float(record.get("recall_at_5") or 0.0) for record in records) / count, 6),
        "recall_at_10": round(sum(float(record.get("recall_at_10") or 0.0) for record in records) / count, 6),
        "recall_at_20": round(sum(float(record.get("recall_at_20") or 0.0) for record in records) / count, 6),
        "mrr_at_20": round(sum(0.0 if rank is None or rank > 20 else 1.0 / rank for rank in first_ranks) / count, 6),
        "no_hit_within_20_count": sum(rank is None or rank > 20 for rank in first_ranks),
        "failed_search_count": sum(record.get("status") == "failed_search" for record in records),
    }
