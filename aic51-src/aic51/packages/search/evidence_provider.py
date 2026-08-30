from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

THREAD3_PROVIDER_ID = "thread3_evidence"
THREAD3_PROVIDER_SCHEMA_VERSION = "vecna.thread3_evidence_provider.v1"


class EvidenceBundleError(ValueError):
    """Raised when an explicitly enabled Thread-3 evidence bundle is invalid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, *, required: bool) -> dict[str, Any] | None:
    if not path.is_file():
        if required:
            raise EvidenceBundleError(f"required evidence bundle file not found: {path}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceBundleError(f"cannot read evidence bundle file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceBundleError(f"evidence bundle file must contain a JSON object: {path}")
    return value


def _bundle_paths(bundle_path: str | Path) -> tuple[Path, Path, Path]:
    supplied = Path(bundle_path)
    if supplied.is_dir():
        root = supplied
        fused = root / "fused_candidates.json"
    else:
        fused = supplied
        root = supplied.parent
    return fused, root / "verification_queue.json", root / "manifest.json"


def _verification_index(document: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not document:
        return {}
    values = document.get("verification_queue") or []
    if not isinstance(values, list):
        raise EvidenceBundleError("verification_queue.json: verification_queue must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in values:
        if not isinstance(item, dict):
            continue
        media_id = str(item.get("media_id") or "").strip()
        if media_id:
            result[media_id] = item
    return result


def _time_range(timestamp_provenance: Any) -> dict[str, Any] | None:
    if not isinstance(timestamp_provenance, dict):
        return None
    for source_name in ("semantic_record", "asr_ocr_span"):
        source = timestamp_provenance.get(source_name)
        if not isinstance(source, dict):
            continue
        start = source.get("start_sec")
        end = source.get("end_sec")
        if start is None and end is None:
            continue
        return {"start_sec": start, "end_sec": end, "source": source_name}
    return None


def _verification_payload(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {"state": "unavailable"}
    return {
        "state": "available",
        "already_ruled_out": bool(item.get("already_ruled_out", False)),
        "verification_status": item.get("verification_status"),
        "needs_visual_inspection": bool(item.get("needs_visual_inspection", False)),
        "repeat_verification": bool(item.get("repeat_verification", False)),
        "priority_rank": item.get("priority_rank"),
        "ruling_source": item.get("ruling_source") or "",
        "ruling_conclusion": item.get("ruling_conclusion") or "",
        "ruling_observed_content": item.get("ruling_observed_content") or "",
        "verification_obligations": item.get("verification_obligations") or [],
        "calibration_notice": item.get("calibration_notice") or "",
    }


def load_thread3_evidence_bundle(bundle_path: str | Path) -> dict[str, Any]:
    """Read a Thread-3 evidence bundle without changing or re-ranking its candidates."""
    fused_path, verification_path, manifest_path = _bundle_paths(bundle_path)
    fused_document = _read_json(fused_path, required=True)
    verification_document = _read_json(verification_path, required=False)
    manifest_document = _read_json(manifest_path, required=False)
    assert fused_document is not None

    fused_candidates = fused_document.get("fused_candidates")
    if not isinstance(fused_candidates, list):
        raise EvidenceBundleError("fused_candidates.json: fused_candidates must be a list")

    verification_by_media = _verification_index(verification_document)
    candidates: list[dict[str, Any]] = []
    for candidate in fused_candidates:
        if not isinstance(candidate, dict):
            raise EvidenceBundleError("fused_candidates.json: every fused candidate must be an object")
        media_id = str(candidate.get("media_id") or "").strip()
        if not media_id:
            raise EvidenceBundleError("fused candidate is missing media_id")
        timestamp_provenance = candidate.get("timestamp_provenance") or {}
        semantic_record = (
            timestamp_provenance.get("semantic_record")
            if isinstance(timestamp_provenance, dict)
            else None
        )
        candidates.append(
            {
                "provider": THREAD3_PROVIDER_ID,
                "video_id": media_id,
                "frame_id": str(candidate.get("best_frame") or ""),
                "segment_id": (
                    semantic_record.get("segment_id")
                    if isinstance(semantic_record, dict)
                    else None
                ),
                "time_range": _time_range(timestamp_provenance),
                "upstream_rank": candidate.get("fused_rank"),
                "upstream_score": {
                    "name": "rrf_score",
                    "value": candidate.get("rrf_score"),
                    "semantics": "ranking_signal_not_calibrated_confidence",
                },
                "best_frame_fused_rank": candidate.get("best_frame_fused_rank"),
                "modalities_supporting": candidate.get("modalities_supporting") or [],
                "contributors": candidate.get("contributors") or [],
                "timestamp_provenance": timestamp_provenance,
                "verification": _verification_payload(verification_by_media.get(media_id)),
            }
        )

    source = {
        "bundle_path": str(Path(bundle_path)),
        "fused_candidates_path": str(fused_path),
        "fused_candidates_sha256": _sha256(fused_path),
        "verification_queue_path": str(verification_path) if verification_path.is_file() else None,
        "verification_queue_sha256": _sha256(verification_path) if verification_path.is_file() else None,
        "manifest_path": str(manifest_path) if manifest_path.is_file() else None,
        "manifest_sha256": _sha256(manifest_path) if manifest_path.is_file() else None,
        "upstream_manifest": manifest_document,
    }

    return {
        "schema_version": THREAD3_PROVIDER_SCHEMA_VERSION,
        "provider": THREAD3_PROVIDER_ID,
        "query_id": fused_document.get("query_id"),
        "task_type": fused_document.get("task_type"),
        "score_semantics": "upstream_ranking_metadata_not_calibrated_confidence",
        "source": source,
        "candidates": candidates,
    }


def attach_thread3_evidence_provider(searcher_cls):
    """Add an opt-in evidence_bundle_path keyword without changing disabled behavior."""
    if getattr(searcher_cls, "_thread3_evidence_provider_attached", False):
        return searcher_cls

    original_search_multimodal = searcher_cls.search_multimodal

    def search_multimodal_with_evidence(
        self,
        *args,
        evidence_bundle_path: str | Path | None = None,
        **kwargs,
    ):
        baseline = original_search_multimodal(self, *args, **kwargs)
        if evidence_bundle_path is None:
            return baseline
        if not isinstance(baseline, dict):
            raise EvidenceBundleError(
                "Searcher.search_multimodal must return a dict when the evidence provider is enabled"
            )
        result = dict(baseline)
        result["evidence_provider"] = load_thread3_evidence_bundle(evidence_bundle_path)
        return result

    search_multimodal_with_evidence.__name__ = getattr(
        original_search_multimodal, "__name__", "search_multimodal"
    )
    search_multimodal_with_evidence.__doc__ = getattr(original_search_multimodal, "__doc__", None)
    searcher_cls.search_multimodal = search_multimodal_with_evidence
    searcher_cls._thread3_evidence_provider_attached = True
    return searcher_cls
