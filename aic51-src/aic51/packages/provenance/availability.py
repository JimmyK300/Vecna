"""Feature-artifact availability and activation checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np


def inspect_feature_availability(
    frame_dir: str | Path,
    feature_names: Iterable[str],
    *,
    enabled_features: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Classify configured feature artifacts for one frame.

    Presence and readability are independent from activation. This lets a
    caller preserve a valid artifact while deliberately excluding it from an
    index or search configuration.
    """

    frame_path = Path(frame_dir)
    enabled = set(enabled_features) if enabled_features is not None else set(feature_names)
    result: dict[str, dict[str, Any]] = {}

    for feature_name in feature_names:
        artifact_path = frame_path / f"{feature_name}.npy"
        item: dict[str, Any] = {
            "path": artifact_path.name,
            "enabled": feature_name in enabled,
            "present": artifact_path.is_file(),
        }

        if not item["present"]:
            item["status"] = "missing"
        elif feature_name not in enabled:
            item["status"] = "disabled"
        else:
            try:
                value = np.load(artifact_path, allow_pickle=False)
                item["shape"] = list(value.shape)
                item["dtype"] = str(value.dtype)
                item["status"] = "ready"
            except (OSError, ValueError):
                item["status"] = "invalid"

        result[feature_name] = item

    return result
