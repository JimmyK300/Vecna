from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from aic51.packages.config import GlobalConfig
from aic51.packages.utils.provenance import (
    atomic_write_json,
    file_sha256,
    implementation_fingerprint,
    new_id,
    read_json,
    stable_id,
    utc_now,
)

SEARCH_SCHEMA_VERSION = "vecna.search.v2"
INDEX_SCHEMA_VERSION = "vecna.index.v1"
CHANNEL_STATES = {
    "disabled",
    "unavailable",
    "failed",
    "success_empty",
    "success_output",
}


def channel_state(state: str, *, reason: str | None = None) -> dict[str, Any]:
    if state not in CHANNEL_STATES:
        raise ValueError(f"invalid channel state: {state}")
    value: dict[str, Any] = {"state": state}
    if reason:
        value["reason"] = reason
    return value


def _index_registry_path(work_dir: Path | str, collection_name: str) -> Path:
    return Path(work_dir) / "provenance" / "indexes" / f"{collection_name}.json"


def load_current_index_generation(work_dir: Path | str, collection_name: str) -> dict[str, Any]:
    registry = read_json(_index_registry_path(work_dir, collection_name))
    if not registry:
        return {
            "state": "unavailable",
            "collection_name": collection_name,
            "index_generation_id": None,
            "reason": "legacy_or_unmanifested_index",
        }

    if registry.get("index_state") == "mutating":
        return {
            "state": "unavailable",
            "collection_name": collection_name,
            "index_generation_id": None,
            "reason": "index_generation_mutating",
        }

    current_id = registry.get("current_index_generation_id")
    for generation in registry.get("generations", []):
        if generation.get("index_generation_id") == current_id:
            return {"state": "resolved", **generation}

    return {
        "state": "unavailable",
        "collection_name": collection_name,
        "index_generation_id": None,
        "reason": "index_manifest_has_no_current_generation",
    }


def invalidate_current_index_generation(
    work_dir: Path | str,
    collection_name: str,
) -> dict[str, Any]:
    """Make attribution unavailable before mutating an indexed collection."""
    path = _index_registry_path(work_dir, collection_name)
    registry = read_json(path) or {
        "schema_version": INDEX_SCHEMA_VERSION,
        "collection_name": collection_name,
        "generations": [],
    }
    previous_id = registry.get("current_index_generation_id")
    if previous_id:
        registry["previous_index_generation_id"] = previous_id
    registry["current_index_generation_id"] = None
    registry["index_state"] = "mutating"
    registry["updated_at"] = utc_now()
    atomic_write_json(path, registry)
    return registry


def record_index_generation(
    work_dir: Path | str,
    *,
    collection_name: str,
    feature_fields: list[str],
    feature_configs: dict[str, Any],
    provider_generations: dict[str, dict[str, Any]],
    video_lineage: dict[str, dict[str, Any]],
    inserted_entities: int,
    do_overwrite: bool,
    do_update: bool,
    failed_videos: list[str] | None = None,
) -> dict[str, Any]:
    """Record an immutable indexing generation without changing Milvus schema/data semantics."""
    path = _index_registry_path(work_dir, collection_name)
    registry = read_json(path) or {
        "schema_version": INDEX_SCHEMA_VERSION,
        "collection_name": collection_name,
        "generations": [],
    }

    generation = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "index_generation_id": new_id("idx"),
        "collection_name": collection_name,
        "created_at": utc_now(),
        "feature_fields": sorted(feature_fields),
        "feature_configs": feature_configs,
        "provider_generations": provider_generations,
        "video_lineage": video_lineage,
        "inserted_entities": int(inserted_entities),
        "status": "partial" if failed_videos else "success",
        "failed_videos": sorted(failed_videos or []),
        "operation": {
            "overwrite_collection": bool(do_overwrite),
            "update_existing": bool(do_update),
        },
    }
    registry.setdefault("generations", []).append(generation)
    registry["current_index_generation_id"] = generation["index_generation_id"]
    registry["index_state"] = "ready"
    registry["updated_at"] = utc_now()
    atomic_write_json(path, registry)
    return generation


def load_analysis_artifact_provenance(work_dir: Path | str) -> dict[str, list[dict[str, str]]]:
    """Map current-compatible artifact paths to provenance claims; callers still verify content hash."""
    root = Path(work_dir) / "provenance" / "analysis"
    result: dict[str, list[dict[str, str]]] = {}
    if not root.exists():
        return result

    for manifest_path in root.glob("*/*/*.json"):
        record = read_json(manifest_path)
        if not record:
            continue
        provider_id = (
            record.get("provider_generation", {}).get("provider_generation_id")
            if isinstance(record.get("provider_generation"), dict)
            else None
        )
        if not provider_id:
            continue
        for output in record.get("outputs", []):
            if not isinstance(output, dict):
                continue
            artifact_path = output.get("path")
            content_sha256 = output.get("content_sha256")
            if not artifact_path or not content_sha256:
                continue
            key = Path(str(artifact_path)).as_posix()
            result.setdefault(key, []).append(
                {
                    "content_sha256": str(content_sha256),
                    "provider_generation_id": str(provider_id),
                    "analysis_run_id": str(record.get("analysis_run_id") or ""),
                    "source_id": str(record.get("source_id") or ""),
                    "rendition_id": str(record.get("rendition_id") or ""),
                    "selection_generation_id": str(record.get("selection_generation_id") or ""),
                    "frame_evidence_id": str(output.get("frame_evidence_id") or ""),
                    "artifact_id": str(output.get("artifact_id") or ""),
                    "representation_id": str(output.get("representation_id") or ""),
                    "evidence_manifest": str(record.get("evidence_manifest") or ""),
                }
            )
    return result


def artifact_provenance_claims(
    work_dir: Path | str,
    feature_path: Path,
    artifact_provenance: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    try:
        relative = feature_path.resolve().relative_to(Path(work_dir).resolve()).as_posix()
    except (OSError, ValueError):
        return []

    candidates = artifact_provenance.get(relative, [])
    if not candidates:
        return []

    current_sha = file_sha256(feature_path)
    return [
        dict(item)
        for item in candidates
        if item.get("content_sha256") == current_sha
    ]


def artifact_provider_generation_ids(
    work_dir: Path | str,
    feature_path: Path,
    artifact_provenance: dict[str, list[dict[str, str]]],
) -> set[str]:
    return {
        item["provider_generation_id"]
        for item in artifact_provenance_claims(work_dir, feature_path, artifact_provenance)
        if item.get("provider_generation_id")
    }


def summarize_video_lineage(
    feature_fields: list[str],
    observed: dict[str, list[dict[str, str]]],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for feature_name in sorted(feature_fields):
        claims = observed.get(feature_name, [])
        unique: dict[str, dict[str, str]] = {}
        for claim in claims:
            descriptor = {
                "source_id": claim.get("source_id") or None,
                "rendition_id": claim.get("rendition_id") or None,
                "selection_generation_id": claim.get("selection_generation_id") or None,
                "provider_generation_id": claim.get("provider_generation_id") or None,
            }
            if not all(descriptor.values()):
                continue
            unique[stable_id("lin", descriptor)] = descriptor
        descriptors = [unique[key] for key in sorted(unique)]
        if not descriptors:
            summary[feature_name] = {
                "state": "unavailable",
                "lineages": [],
                "reason": "no_hash_matching_lineage_for_indexed_artifact",
            }
        elif len(descriptors) == 1:
            summary[feature_name] = {"state": "resolved", "lineages": descriptors}
        else:
            summary[feature_name] = {"state": "mixed", "lineages": descriptors}
    return summary


def summarize_provider_generations(
    feature_fields: list[str],
    observed: dict[str, set[str]],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for feature_name in sorted(feature_fields):
        generation_ids = sorted(observed.get(feature_name, set()))
        if not generation_ids:
            summary[feature_name] = {
                "state": "unavailable",
                "provider_generation_ids": [],
                "reason": "no_hash_matching_provenance_for_indexed_artifact",
            }
        elif len(generation_ids) == 1:
            summary[feature_name] = {
                "state": "resolved",
                "provider_generation_ids": generation_ids,
            }
        else:
            summary[feature_name] = {
                "state": "mixed",
                "provider_generation_ids": generation_ids,
            }
    return summary


@lru_cache(maxsize=1)
def _serving_implementation() -> dict[str, Any]:
    packages_dir = Path(__file__).resolve().parent.parent
    files = {
        "searcher": Path(__file__).resolve().with_name("searcher.py"),
        "query_parser": Path(__file__).resolve().with_name("utils.py"),
        "index_backend": packages_dir / "index" / "milvus.py",
    }
    result: dict[str, Any] = {}
    for name, path in files.items():
        try:
            digest = file_sha256(path)
        except OSError:
            digest = None
        result[name] = {
            "source_path": path.name,
            "source_sha256": digest,
            "state": "resolved" if digest else "unavailable",
        }
    return result


@lru_cache(maxsize=64)
def _query_encoder_implementation(model_name: str | None) -> dict[str, Any]:
    if not model_name:
        return {"state": "unavailable", "reason": "model_name_missing"}
    try:
        from aic51.packages.analyse import FeatureExtractorFactory

        extractor_cls = FeatureExtractorFactory.get(model_name)
    except Exception:
        extractor_cls = None
    if extractor_cls is None:
        return {"state": "unavailable", "reason": "extractor_class_unavailable"}
    return {"state": "resolved", **implementation_fingerprint(extractor_cls)}


def _query_encoder_configuration(active_target_features: list[str]) -> dict[str, Any]:
    configured = GlobalConfig.get("searcher", "language_models") or {}
    result: dict[str, Any] = {}
    for name, value in configured.items():
        if not isinstance(value, dict):
            continue
        targets = value.get("target") or []
        if any(target in active_target_features for target in targets):
            result[name] = {
                "source": value.get("source"),
                "model": value.get("model"),
                "arch_name": value.get("arch_name"),
                "pretrained_model": value.get("pretrained_model"),
                "target": sorted(targets),
                "implementation": _query_encoder_implementation(value.get("model")),
            }
    return result


def _channel_configuration(
    *,
    query_mode: str,
    active_target_features: list[str],
    ocr_weight: float,
    asr_weight: float,
    ocr_alpha: float = 0.5,
    asr_alpha: float = 0.5,
    support_ocr: bool,
    support_asr: bool,
) -> dict[str, Any]:
    if query_mode == "browse":
        return {
            "visual": {"enabled": False, "reason": "browse_mode"},
            "ocr": {"enabled": False, "reason": "browse_mode"},
            "asr": {"enabled": False, "reason": "browse_mode"},
        }

    ocr_weight = max(0.0, min(1.0, float(ocr_weight)))
    asr_weight = max(0.0, min(1.0 - ocr_weight, float(asr_weight)))
    visual_weight = 1.0 - ocr_weight - asr_weight
    return {
        "visual": {
            "enabled": bool(active_target_features) and visual_weight > 0,
            "weight": visual_weight,
            "target_features": active_target_features,
        },
        "ocr": {
            "enabled": bool(support_ocr) and ocr_weight > 0,
            "weight": ocr_weight,
            "alpha": ocr_alpha,
            "field": GlobalConfig.get("searcher", "ocr", "ocr_field") or "ocr",
        },
        "asr": {
            "enabled": bool(support_asr) and asr_weight > 0,
            "weight": asr_weight,
            "alpha": asr_alpha,
            "field": GlobalConfig.get("searcher", "asr", "asr_field") or "asr",
        },
    }


def build_channel_states(
    *,
    query_mode: str,
    channel_configuration: dict[str, Any],
    observed_channel_states: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    observed_channel_states = observed_channel_states or {}
    states: dict[str, dict[str, Any]] = {}
    for name in ("visual", "ocr", "asr"):
        observed = observed_channel_states.get(name)
        if isinstance(observed, dict) and observed.get("state") in CHANNEL_STATES:
            states[name] = dict(observed)
            continue

        config = channel_configuration[name]
        if query_mode == "browse" or not config.get("enabled"):
            states[name] = channel_state("disabled", reason=config.get("reason") or "channel_not_active")
        else:
            states[name] = channel_state(
                "unavailable",
                reason="legacy_searcher_does_not_expose_channel_outcome",
            )
    return states


def build_serving_composition(
    work_dir: Path | str,
    *,
    collection_name: str,
    query_mode: str,
    target_features: list[str],
    available_target_features: list[str],
    nprobe: int,
    temporal_k: int,
    ocr_weight: float,
    asr_weight: float,
    ocr_alpha: float = 0.5,
    asr_alpha: float = 0.5,
    max_interval: int,
    auto_translate: bool,
    en_to_vi_translate: bool,
    support_ocr: bool,
    support_asr: bool,
) -> dict[str, Any]:
    requested = [value for value in target_features if value]
    available = set(available_target_features)
    active_target_features = sorted({value for value in requested if value in available})
    index_generation = load_current_index_generation(work_dir, collection_name)
    channel_configuration = _channel_configuration(
        query_mode=query_mode,
        active_target_features=active_target_features,
        ocr_weight=ocr_weight,
        asr_weight=asr_weight,
        ocr_alpha=ocr_alpha,
        asr_alpha=asr_alpha,
        support_ocr=support_ocr,
        support_asr=support_asr,
    )

    descriptor: dict[str, Any] = {
        "schema_version": SEARCH_SCHEMA_VERSION,
        "collection": {
            "name": collection_name,
            "index_generation_state": index_generation.get("state"),
            "index_generation_id": index_generation.get("index_generation_id"),
        },
        "query_mode": query_mode,
        "channels": channel_configuration,
        "query_encoders": _query_encoder_configuration(
            active_target_features if channel_configuration["visual"].get("enabled") else []
        ),
        "serving_implementation": _serving_implementation(),
        "score_semantics": "ranking_diagnostics_not_calibrated_probabilities",
    }

    if query_mode != "browse":
        descriptor["search_parameters"] = {}
        if channel_configuration["visual"].get("enabled"):
            descriptor["search_parameters"]["nprobe"] = int(nprobe)
        descriptor["translation"] = {
            "vi_to_en_for_visual": (
                bool(auto_translate) if channel_configuration["visual"].get("enabled") else False
            ),
            "en_to_vi_for_ocr_asr": (
                bool(en_to_vi_translate)
                if channel_configuration["ocr"].get("enabled")
                or channel_configuration["asr"].get("enabled")
                else False
            ),
        }
    if query_mode == "temporal":
        descriptor["search_parameters"].update(
            {
                "temporal_k": int(temporal_k),
                "max_interval": int(max_interval),
            }
        )

    identity_state = "partial"
    if (
        index_generation.get("state") == "resolved"
        and index_generation.get("status") == "success"
    ):
        provider_states = [
            value.get("state")
            for value in index_generation.get("provider_generations", {}).values()
            if isinstance(value, dict)
        ]
        encoder_states = [
            value.get("implementation", {}).get("state")
            for value in descriptor["query_encoders"].values()
            if isinstance(value, dict)
        ]
        serving_states = [
            value.get("state")
            for value in descriptor["serving_implementation"].values()
            if isinstance(value, dict)
        ]
        if (
            provider_states
            and all(state in {"resolved", "mixed"} for state in provider_states)
            and all(state == "resolved" for state in encoder_states)
            and all(state == "resolved" for state in serving_states)
        ):
            identity_state = "resolved"

    return {
        "serving_composition_id": stable_id("cmp", descriptor),
        "identity_state": identity_state,
        **descriptor,
        "index_generation": index_generation,
    }


def build_search_trace(
    work_dir: Path | str,
    *,
    collection_name: str,
    query_mode: str,
    target_features: list[str],
    available_target_features: list[str],
    nprobe: int,
    temporal_k: int,
    ocr_weight: float,
    asr_weight: float,
    ocr_alpha: float = 0.5,
    asr_alpha: float = 0.5,
    max_interval: int,
    auto_translate: bool,
    en_to_vi_translate: bool,
    support_ocr: bool,
    support_asr: bool,
    observed_channel_states: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    composition = build_serving_composition(
        work_dir,
        collection_name=collection_name,
        query_mode=query_mode,
        target_features=target_features,
        available_target_features=available_target_features,
        nprobe=nprobe,
        temporal_k=temporal_k,
        ocr_weight=ocr_weight,
        asr_weight=asr_weight,
        ocr_alpha=ocr_alpha,
        asr_alpha=asr_alpha,
        max_interval=max_interval,
        auto_translate=auto_translate,
        en_to_vi_translate=en_to_vi_translate,
        support_ocr=support_ocr,
        support_asr=support_asr,
    )
    states = build_channel_states(
        query_mode=query_mode,
        channel_configuration=composition["channels"],
        observed_channel_states=observed_channel_states,
    )
    return {
        "schema_version": SEARCH_SCHEMA_VERSION,
        "query_run_id": new_id("qry"),
        "serving_composition": composition,
        "channel_states": states,
    }


def resolve_frame_provenance(
    work_dir: Path | str,
    video_id: str,
    frame_id: str,
    *,
    collection_name: str | None = None,
    feature_names: list[str] | None = None,
    index_generation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve provenance bound to the indexed generation; never rebind to current analysis state."""
    if index_generation is None:
        if not collection_name:
            return {"state": "unavailable", "reason": "index_collection_not_supplied"}
        generation = load_current_index_generation(work_dir, collection_name)
    else:
        generation = index_generation

    if generation.get("state") != "resolved":
        return {
            "state": "unavailable",
            "reason": "index_generation_unavailable",
            "index_generation_id": generation.get("index_generation_id"),
        }

    per_video = generation.get("video_lineage", {}).get(video_id, {})
    selected = [name for name in (feature_names or []) if name]
    missing_features = [name for name in selected if name not in per_video]
    entries = [per_video.get(name) for name in selected if per_video.get(name)]
    if not selected or not entries:
        return {
            "state": "unavailable",
            "reason": "index_generation_has_no_lineage_for_result_features",
            "index_generation_id": generation.get("index_generation_id"),
        }

    lineages: dict[str, dict[str, Any]] = {}
    unresolved = bool(missing_features)
    for entry in entries:
        if entry.get("state") != "resolved" or len(entry.get("lineages", [])) != 1:
            unresolved = True
            continue
        lineage = entry["lineages"][0]
        lineages[stable_id("lin", lineage)] = lineage

    if unresolved or len(lineages) != 1:
        return {
            "state": "mixed" if lineages or unresolved else "unavailable",
            "reason": "indexed_features_do_not_resolve_to_one_lineage",
            "index_generation_id": generation.get("index_generation_id"),
            "lineages": [lineages[key] for key in sorted(lineages)],
        }

    lineage = next(iter(lineages.values()))
    frame_evidence_id = stable_id(
        "ev_frame",
        {
            "source_id": lineage["source_id"],
            "rendition_id": lineage["rendition_id"],
            "selection_generation_id": lineage["selection_generation_id"],
            "frame_id": str(frame_id),
        },
    )
    return {
        "state": "resolved",
        "index_generation_id": generation.get("index_generation_id"),
        **lineage,
        "frame_evidence_id": frame_evidence_id,
    }


def build_result_traceability(
    work_dir: Path | str,
    *,
    video_id: str,
    frame_id: str,
    fps: float | int | None,
    collection_name: str | None = None,
    feature_names: list[str] | None = None,
    index_generation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seconds = None
    if fps:
        try:
            seconds = int(frame_id) / float(fps)
        except (TypeError, ValueError, ZeroDivisionError):
            seconds = None

    return {
        "natural_locator": {
            "kind": "source_frame",
            "video_id": video_id,
            "frame_id": str(frame_id),
        },
        "timing": {
            "seconds": seconds,
            "fps": fps,
            "quality": "reconstructed_from_rounded_fps" if seconds is not None else "unknown",
        },
        "provenance": resolve_frame_provenance(
            work_dir,
            video_id,
            str(frame_id),
            collection_name=collection_name,
            feature_names=feature_names,
            index_generation=index_generation,
        ),
        "score_semantics": "ranking_diagnostics_not_calibrated_probabilities",
    }
