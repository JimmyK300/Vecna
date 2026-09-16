"""Experimental OpenCubee-derived late fusion for Vecna Issue #64.

This module is deliberately NOT wired into the production Searcher.  It exists
as a default-off experimental seam so the donor behavior can be benchmarked on
the repaired local Vecna stack before any production ranking semantics change.

Donor evidence (frozen 2026-08-26):
- repository: k19tvan/Opencubee2
- commit: f8045a6961de65b38436824606b493a12e73f89a
- source: backend/services/search.py::fuse_results
- live caller: backend/api/search.py::_vector_stage

The donor pattern keeps each visual model's result list separate, normalizes
weights across the models that actually returned results, unions candidates by
frame identity, assigns zero contribution for a model that did not return a
candidate, and computes a weighted late-fusion score.

Vecna currently collapses visual-model scores into one aggregate CLIP bucket
inside Searcher._similarity_search.  Keeping this adapter separate allows an
A/B test without changing that default path.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


LEGACY_STRATEGY = "legacy"
OPENCUBEE_MODEL_WEIGHTED_STRATEGY = "opencubee_model_weighted"
DONOR_REPOSITORY = "k19tvan/Opencubee2"
DONOR_COMMIT = "f8045a6961de65b38436824606b493a12e73f89a"
DONOR_SOURCE = "backend/services/search.py::fuse_results"


def _frame_identity(result: Mapping[str, Any]) -> str:
    """Return a stable frame identity for Vecna- or OpenCubee-shaped hits."""
    entity = result.get("entity")
    if isinstance(entity, Mapping):
        frame_id = entity.get("frame_id")
        if frame_id:
            return str(frame_id)
    for key in ("frame_id", "frame_name", "id"):
        value = result.get(key)
        if value:
            return str(value)
    raise ValueError("fusion result has no stable frame identity")


def _score(result: Mapping[str, Any]) -> float:
    value = result.get("distance", result.get("score"))
    if value is None:
        raise ValueError(f"fusion result {_frame_identity(result)!r} has no score/distance")
    return float(value)


def _normalized_active_weights(
    results_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
    weights: Mapping[str, float],
) -> dict[str, float]:
    active = {
        model: float(weight)
        for model, weight in weights.items()
        if model in results_by_model and results_by_model[model] and float(weight) > 0.0
    }
    total = sum(active.values())
    if total <= 0.0:
        return {}
    return {model: weight / total for model, weight in active.items()}


def fuse_model_results(
    results_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
    weights: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Apply the bounded OpenCubee model-weighted late-fusion pattern.

    Candidates are unioned by stable frame identity.  Each active model
    contributes ``normalized_model_weight * result_score`` when the frame is
    present in that model's ranking and zero otherwise.  Model weights are
    renormalized over models that actually returned at least one result.

    The function deep-copies result payloads and never mutates input rankings.
    A deterministic frame-identity tie-break makes reruns stable.
    """
    normalized_weights = _normalized_active_weights(results_by_model, weights)
    if not normalized_weights:
        return []

    merged: dict[str, dict[str, Any]] = {}
    per_model_scores: dict[str, dict[str, float]] = {}

    for model in normalized_weights:
        for result in results_by_model[model]:
            frame_id = _frame_identity(result)
            if frame_id not in merged:
                merged[frame_id] = deepcopy(dict(result))
            per_model_scores.setdefault(frame_id, {})[model] = _score(result)

    fused: list[dict[str, Any]] = []
    for frame_id, result in merged.items():
        model_scores = per_model_scores.get(frame_id, {})
        fused_score = sum(
            normalized_weights[model] * model_scores.get(model, 0.0)
            for model in normalized_weights
        )
        result["distance"] = fused_score
        result["score"] = fused_score
        result["experimental_fusion"] = {
            "strategy": OPENCUBEE_MODEL_WEIGHTED_STRATEGY,
            "donor_repository": DONOR_REPOSITORY,
            "donor_commit": DONOR_COMMIT,
            "donor_source": DONOR_SOURCE,
            "normalized_model_weights": dict(sorted(normalized_weights.items())),
            "model_scores": dict(sorted(model_scores.items())),
        }
        fused.append(result)

    fused.sort(key=lambda item: (-_score(item), _frame_identity(item)))
    return fused


def select_visual_fusion(
    strategy: str = LEGACY_STRATEGY,
    *,
    legacy_results: Sequence[dict[str, Any]],
    results_by_model: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    weights: Mapping[str, float] | None = None,
) -> Sequence[dict[str, Any]]:
    """Narrow experimental switch used by benchmark/review code.

    ``legacy`` deliberately returns the original result sequence unchanged.
    Production code need not import this module at all; this switch exists so
    an A/B harness can prove disabled/default compatibility mechanically.
    """
    if strategy == LEGACY_STRATEGY:
        return legacy_results
    if strategy != OPENCUBEE_MODEL_WEIGHTED_STRATEGY:
        raise ValueError(f"unknown visual fusion strategy: {strategy}")
    if results_by_model is None or weights is None:
        raise ValueError("OpenCubee model-weighted fusion requires per-model results and weights")
    return fuse_model_results(results_by_model, weights)
