"""Migration decisions for legacy Vecna extraction artifacts."""

from __future__ import annotations

from typing import Any


def _artifact_contracts(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for video in (report.get("features", {}).get("videos", {}).values()):
        for name, details in (video.get("artifacts", {}).items()):
            contracts.setdefault(name.removesuffix(".npy"), details.get("contract") or {})
    return contracts


def assess_legacy_migration(
    legacy_report: dict[str, Any],
    *,
    target_features: dict[str, dict[str, Any]],
    legacy_keyframe_policy: str | None,
    target_keyframe_policy: str | None,
) -> dict[str, Any]:
    """Return conservative reuse/reprocess decisions without changing data."""

    legacy_contracts = _artifact_contracts(legacy_report)
    keyframes_match = legacy_keyframe_policy == target_keyframe_policy and legacy_keyframe_policy is not None
    feature_decisions = {}
    for name, details in target_features.items():
        legacy_name = f"{name}.npy"
        contract = legacy_contracts.get(name)
        expected_dim = (details.get("index") or {}).get("dim")
        observed_shape = (contract or {}).get("shape")
        dimension_matches = not expected_dim or observed_shape in ([expected_dim], (expected_dim,))

        if not contract:
            decision = "analyse_required"
        elif not dimension_matches:
            decision = "reanalyse_required"
        elif not keyframes_match:
            decision = "reuse_after_frame_verification"
        else:
            decision = "reuse_candidate"
        feature_decisions[name] = {
            "artifact": legacy_name,
            "decision": decision,
            "observed_contract": contract,
            "expected_dim": expected_dim,
        }

    return {
        "source": "verify_video_identity",
        "keyframes": "reuse_candidate" if keyframes_match else "reextract_required",
        "legacy_keyframe_policy": legacy_keyframe_policy,
        "target_keyframe_policy": target_keyframe_policy,
        "features": feature_decisions,
        "ocr_quality": "unverified" if "ocr" in legacy_contracts else "not_present",
        "milvus": "new_collection_required_for_schema_changes",
    }
