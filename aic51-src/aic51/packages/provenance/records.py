"""Pure frame-record construction for index compatibility checks."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .availability import inspect_feature_availability


def build_frame_record(
    frame_features_path: Path,
    video_id: str,
    feature_fields: list[str],
    *,
    enabled_features: list[str] | None = None,
) -> tuple[dict, dict]:
    """Build a partial frame record and its availability report.

    Whether a backing Milvus schema accepts missing fields is intentionally
    left to the collection contract; this helper only makes the data decision
    explicit and testable.
    """

    availability = inspect_feature_availability(
        frame_features_path,
        feature_fields,
        enabled_features=enabled_features,
    )
    data = {"frame_id": f"{video_id}#{frame_features_path.stem}"}

    for feature_name, status in availability.items():
        if status["status"] != "ready":
            continue

        feature = np.load(frame_features_path / status["path"], allow_pickle=False)
        if feature.dtype.kind == "U":
            feature = feature.tolist()
        data[feature_name] = feature

    return data, availability
