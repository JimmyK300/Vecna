"""Canonical raw evidence and deterministic compatibility projections."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def project_timed_segments(
    segments: list[dict[str, Any]],
    frame_ids: list[str],
    fps: float,
    *,
    nearest_tolerance_s: float = 2.0,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Project timed ASR segments onto frames deterministically."""

    texts: list[str] = []
    projections: list[dict[str, Any]] = []
    for frame_id in frame_ids:
        timestamp = int(frame_id) / fps if fps else 0.0
        selected = None
        selected_index = None
        rule = "containing_segment"
        for index, segment in enumerate(segments):
            if segment.get("start", 0) <= timestamp <= segment.get("end", 0):
                selected = segment
                selected_index = index
                break

        if selected is None:
            nearest = []
            for index, segment in enumerate(segments):
                distance = min(
                    abs(segment.get("start", 0) - timestamp),
                    abs(segment.get("end", 0) - timestamp),
                )
                nearest.append((distance, index, segment))
            if nearest:
                distance, selected_index, selected = min(nearest)
                if distance > nearest_tolerance_s:
                    selected = None
                    selected_index = None
                else:
                    rule = "nearest_segment"

        text = normalize_text(selected.get("text", "")) if selected else ""
        texts.append(text)
        projection: dict[str, Any] = {
            "frame_id": frame_id,
            "timestamp_ms": round(timestamp * 1000),
            "text": text,
            "projection_rule": rule if selected else "no_segment",
        }
        if selected is not None:
            projection.update(
                {
                    "source_segment_index": selected_index,
                    "source_start_ms": round(float(selected.get("start", 0)) * 1000),
                    "source_end_ms": round(float(selected.get("end", 0)) * 1000),
                }
            )
        projections.append(projection)

    return texts, projections


def write_json_artifact(path: str | Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
