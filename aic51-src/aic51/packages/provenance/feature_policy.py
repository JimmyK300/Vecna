"""Shared feature activation policy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def is_feature_enabled(features: Mapping[str, Any] | None, feature_name: str) -> bool:
    """Return whether a feature participates in the active Vecna pipeline.

    Missing ``enabled`` keeps legacy configurations working as before.
    """

    if not features or feature_name not in features:
        return False
    return features[feature_name].get("enabled", True) is not False


def enabled_feature_names(features: Mapping[str, Any] | None) -> list[str]:
    if not features:
        return []
    return [name for name in features if is_feature_enabled(features, name)]
