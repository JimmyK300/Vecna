from __future__ import annotations

import hashlib
import inspect
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import aic51.packages.constant as constant


SCHEMA_VERSION = "vecna.provenance.v1"
PROVENANCE_DIR = "provenance"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_id(prefix: str, value: Any, length: int = 24) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def file_sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


ONNX_IDENTITY_KEYS = (
    "backend",
    "execution_framework",
    "execution_provider",
    "onnx_artifact_sha256",
    "onnx_model_id",
    "pretrained_model",
    "max_length",
    "precision",
    "hidden_size",
)


def _onnx_identity(semantics: dict[str, Any]) -> tuple:
    return tuple(semantics.get(key) for key in ONNX_IDENTITY_KEYS)


def implementation_fingerprint(obj: Any) -> dict[str, Any]:
    target = obj if inspect.isclass(obj) else obj.__class__
    source_file = inspect.getsourcefile(target)
    digest = None
    if source_file:
        try:
            digest = file_sha256(Path(source_file))
        except OSError:
            digest = None
    return {
        "module": target.__module__,
        "class": target.__name__,
        "source_sha256": digest,
    }


def atomic_save_npy(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with open(tmp_path, "wb") as f:
        np.save(f, array)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def preserve_artifact(path: Path, reason: str) -> Path | None:
    """Rename a foreign artifact so a newer generation can occupy the canonical name."""
    path = Path(path)
    if not path.exists():
        return None
    stamp = utc_now().replace(":", "").replace("+", "")
    safe_reason = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in reason)[:80]
    preserved = path.with_name(f"{path.stem}.preserved.{safe_reason}.{stamp}{path.suffix}")
    os.replace(path, preserved)
    return preserved


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_jsonable(value), f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


class ProvenanceStore:
    """Compatibility sidecars for the legacy Vecna ingestion/analysis pipeline."""

    def __init__(self, work_dir: Path | str):
        self.work_dir = Path(work_dir)
        self.root = self.work_dir / PROVENANCE_DIR

    def _relative(self, path: Path | str | None) -> str | None:
        if path is None:
            return None
        path = Path(path)
        try:
            return path.resolve().relative_to(self.work_dir.resolve()).as_posix()
        except (OSError, ValueError):
            return path.as_posix()

    def source_path(self, video_id: str) -> Path:
        return self.root / "sources" / f"{video_id}.json"

    def keyframe_path(self, video_id: str) -> Path:
        return self.root / "keyframes" / f"{video_id}.json"

    def analysis_path(self, video_id: str, feature_name: str, run_id: str) -> Path:
        return self.root / "analysis" / video_id / feature_name / f"{run_id}.json"

    def evidence_path(self, video_id: str, feature_name: str, run_id: str) -> Path:
        return self.root / "evidence" / video_id / feature_name / f"{run_id}.json"

    def ensure_source(self, video_id: str, *, refresh: bool = False) -> dict[str, Any]:
        path = self.source_path(video_id)
        existing = read_json(path)
        if existing and not refresh:
            return existing

        video_path = self.work_dir / constant.VIDEO_DIR / f"{video_id}{constant.VIDEO_EXTENSION}"
        info_path = self.work_dir / constant.VIDEO_INFO_DIR / f"{video_id}.json"
        info = read_json(info_path) or {}
        raw_fps = info.get(constant.FPS_KEY)
        fps_fraction = info.get(constant.FPS_FRACTION_KEY)
        rounded_fps = round(raw_fps) if isinstance(raw_fps, (int, float)) else None
        exact_fps = float(raw_fps) if isinstance(raw_fps, (int, float)) else None

        # Legacy video IDs are the only stable pre-v1 source handles available.
        # Use them as an explicit migration identity without claiming recovered
        # content-level source provenance.
        source_id = (
            existing.get("logical_source", {}).get("source_id")
            if existing
            else stable_id(
                "src",
                {
                    "migration_basis": "legacy_video_id",
                    "legacy_video_id": video_id,
                },
            )
        )

        asset_sha256 = file_sha256(video_path) if video_path.exists() else None
        rendition_descriptor = {
            "source_id": source_id,
            "asset_sha256": asset_sha256,
            "container": video_path.suffix.lower() if video_path.exists() else None,
        }
        rendition_id = stable_id("rnd", rendition_descriptor)
        rendition = {
            "rendition_id": rendition_id,
            "identity_basis": "exact_asset_sha256" if asset_sha256 else "missing_asset",
            "asset_sha256": asset_sha256,
            "registered_at": utc_now(),
            "registration_origin": "observed_at_ingest_or_analysis",
            "physical_asset": self._relative(video_path) if video_path.exists() else None,
            "container": video_path.suffix.lower() if video_path.exists() else None,
            "file_size_bytes": video_path.stat().st_size if video_path.exists() else None,
            "native_timing": "unknown",
            "exact_fps": exact_fps,
            "fps_fraction": fps_fraction,
            "legacy_rounded_fps": rounded_fps,
            "legacy_time_projection_quality": (
                "reconstructed_from_exact_fps"
                if (fps_fraction is not None or (exact_fps is not None and not isinstance(raw_fps, int)))
                else ("reconstructed_from_rounded_fps" if rounded_fps is not None else "unknown")
            ),
            "historical_rendition_derivation": "unknown",
        }

        if existing:
            record = dict(existing)
            record.setdefault("schema_version", SCHEMA_VERSION)
            record.setdefault("renditions", [])
            if not any(r.get("rendition_id") == rendition_id for r in record["renditions"]):
                record["renditions"].append(rendition)
            record["current_rendition_id"] = rendition_id
            record["updated_at"] = utc_now()
        else:
            record = {
                "schema_version": SCHEMA_VERSION,
                "logical_source": {
                    "source_id": source_id,
                    "legacy_video_id": video_id,
                    "identity_basis": "legacy_video_id_migration",
                    "logical_content_identity_status": "unknown_historical",
                    "registered_at": utc_now(),
                    "registration_origin": "observed_at_ingest_or_analysis",
                    "historical_import_provenance": "unknown",
                },
                "current_rendition_id": rendition_id,
                "renditions": [rendition],
            }
        atomic_write_json(path, record)
        return record

    def _build_keyframe_generation(
        self,
        *,
        source_id: str,
        rendition_id: str,
        frame_ids: list[str],
        producer_configuration: dict[str, Any] | str,
        producer_identity: dict[str, Any] | str,
        registration_origin: str,
    ) -> dict[str, Any]:
        descriptor = {
            "source_id": source_id,
            "rendition_id": rendition_id,
            "observed_frame_ids": frame_ids,
            "producer_configuration": producer_configuration,
            "producer_identity": producer_identity,
        }
        generation_id = stable_id("sel", descriptor)
        frames = [
            {
                "frame_id": frame_id,
                "evidence_id": stable_id(
                    "ev_frame",
                    {
                        "source_id": source_id,
                        "rendition_id": rendition_id,
                        "selection_generation_id": generation_id,
                        "frame_id": frame_id,
                    },
                ),
                "natural_locator": {
                    "kind": "source_frame",
                    "frame_id": frame_id,
                },
            }
            for frame_id in frame_ids
        ]
        return {
            "selection_generation_id": generation_id,
            "source_id": source_id,
            "rendition_id": rendition_id,
            "registered_at": utc_now(),
            "registration_origin": registration_origin,
            "producer_family": "frame_selection",
            "producer_identity": producer_identity,
            "producer_configuration": producer_configuration,
            "frames": frames,
        }

    def record_keyframe_generation(
        self,
        video_id: str,
        frame_ids: list[str],
        *,
        producer_configuration: dict[str, Any] | str,
        producer_identity: dict[str, Any] | str,
        registration_origin: str = "generated_by_current_pipeline",
    ) -> dict[str, Any]:
        source = self.ensure_source(video_id)
        source_id = source["logical_source"]["source_id"]
        rendition_id = source["current_rendition_id"]
        frame_ids = sorted(str(frame_id) for frame_id in frame_ids)
        generation = self._build_keyframe_generation(
            source_id=source_id,
            rendition_id=rendition_id,
            frame_ids=frame_ids,
            producer_configuration=producer_configuration,
            producer_identity=producer_identity,
            registration_origin=registration_origin,
        )

        path = self.keyframe_path(video_id)
        registry = read_json(path) or {
            "schema_version": SCHEMA_VERSION,
            "video_id": video_id,
            "generations": [],
        }
        # Transitional support if an early v1 single-generation sidecar exists.
        if "generations" not in registry and "selection_generation_id" in registry:
            old = dict(registry)
            registry = {
                "schema_version": SCHEMA_VERSION,
                "video_id": video_id,
                "current_selection_generation_id": old["selection_generation_id"],
                "generations": [old],
            }

        registry.setdefault("generations", [])
        if not any(
            item.get("selection_generation_id") == generation["selection_generation_id"]
            for item in registry["generations"]
        ):
            registry["generations"].append(generation)
        registry["current_selection_generation_id"] = generation["selection_generation_id"]
        registry["updated_at"] = utc_now()
        atomic_write_json(path, registry)
        return generation

    def ensure_keyframe_generation(self, video_id: str) -> dict[str, Any]:
        path = self.keyframe_path(video_id)
        existing = read_json(path)
        if existing:
            if "generations" in existing:
                current_id = existing.get("current_selection_generation_id")
                for generation in existing["generations"]:
                    if generation.get("selection_generation_id") == current_id:
                        return generation
                if existing["generations"]:
                    return existing["generations"][-1]
            if "selection_generation_id" in existing:
                return existing

        keyframe_dir = self.work_dir / constant.KEYFRAME_DIR / video_id
        frame_ids = sorted(
            p.stem
            for p in keyframe_dir.glob("*")
            if p.is_file() and not p.stem.startswith(".")
        )
        return self.record_keyframe_generation(
            video_id,
            frame_ids,
            producer_configuration="unknown",
            producer_identity="unknown",
            registration_origin="observed_at_analysis",
        )

    def latest_frame_provider_generations(
        self,
        video_id: str,
        feature_name: str,
    ) -> dict[str, str]:
        """Map frame_id -> provider_generation_id from the newest successful run."""
        analysis_dir = self.root / "analysis" / video_id / feature_name
        if not analysis_dir.is_dir():
            return {}
        latest: dict[str, tuple[str, str]] = {}
        for path in analysis_dir.glob("*.json"):
            record = read_json(path)
            if not record or record.get("status") != "success":
                continue
            provider = record.get("provider_generation") or {}
            provider_id = provider.get("provider_generation_id")
            if not provider_id:
                continue
            finished_at = str(record.get("finished_at") or record.get("started_at") or "")
            for output in record.get("outputs") or []:
                frame_id = output.get("frame_id")
                if not frame_id:
                    continue
                previous = latest.get(frame_id)
                if previous is None or finished_at >= previous[0]:
                    latest[frame_id] = (finished_at, str(provider_id))
        return {frame_id: provider_id for frame_id, (_, provider_id) in latest.items()}

    def unfinished_frame_provider_generations(
        self,
        video_id: str,
        feature_name: str,
    ) -> dict[str, str]:
        """frame_id -> provider_generation_id for runs that crashed before finish.

        A crash after atomic .npy writes leaves status=running and outputs=[].
        Resume must still treat those files as this generation when the frame
        was in requested_frame_ids.
        """
        analysis_dir = self.root / "analysis" / video_id / feature_name
        if not analysis_dir.is_dir():
            return {}
        claimed: dict[str, str] = {}
        for path in analysis_dir.glob("*.json"):
            record = read_json(path)
            if not record or record.get("status") == "success":
                continue
            provider = record.get("provider_generation") or {}
            provider_id = provider.get("provider_generation_id")
            if not provider_id:
                continue
            provider_id = str(provider_id)
            for frame_id in record.get("requested_frame_ids") or []:
                claimed[str(frame_id)] = provider_id
            for output in record.get("outputs") or []:
                frame_id = output.get("frame_id")
                if frame_id:
                    claimed[str(frame_id)] = provider_id
        return claimed

    def compatible_provider_generation_ids(
        self,
        feature_name: str,
        runtime_semantics: dict[str, Any] | None,
    ) -> set[str]:
        """IDs that share ONNX/model identity, ignoring implementation source hash.

        Pipeline or extractor-file edits must not force a rewrite of an already
        valid BGE-M3 ONNX generation (same artifact SHA + provider + model).
        """
        wanted = _onnx_identity(runtime_semantics or {})
        if not wanted[0]:
            return set()
        found: set[str] = set()
        root = self.root / "analysis"
        if not root.is_dir():
            return found
        for video_dir in root.iterdir():
            folder = video_dir / feature_name
            if not folder.is_dir():
                continue
            for path in folder.glob("*.json"):
                data = read_json(path)
                if not data or data.get("status") != "success":
                    continue
                generation = data.get("provider_generation") or {}
                descriptor = generation.get("descriptor") or {}
                if _onnx_identity(descriptor.get("runtime_semantics") or {}) != wanted:
                    continue
                provider_id = generation.get("provider_generation_id")
                if provider_id:
                    found.add(str(provider_id))
        return found

    def provider_generation(
        self,
        *,
        feature_name: str,
        model_name: str,
        source: str | None,
        arch_name: str | None,
        pretrained_model: str | None,
        batch_size: int,
        extractor: Any,
    ) -> dict[str, Any]:
        descriptor = {
            "provider_family": model_name,
            "feature_name": feature_name,
            "source": source,
            "arch_name": arch_name,
            "pretrained_model": pretrained_model,
            "analyse": {"batch_size": batch_size},
            "implementation": implementation_fingerprint(extractor),
        }
        return {
            "provider_generation_id": stable_id("prv", descriptor),
            "descriptor": descriptor,
        }

    def begin_analysis_run(
        self,
        *,
        video_id: str,
        feature_name: str,
        provider_generation: dict[str, Any],
        requested_frame_ids: list[str],
    ) -> dict[str, Any]:
        source = self.ensure_source(video_id)
        selection = self.ensure_keyframe_generation(video_id)
        run_id = new_id("run")
        record = {
            "schema_version": SCHEMA_VERSION,
            "analysis_run_id": run_id,
            "status": "running",
            "started_at": utc_now(),
            "video_id": video_id,
            "source_id": source["logical_source"]["source_id"],
            "rendition_id": source["current_rendition_id"],
            "selection_generation_id": selection["selection_generation_id"],
            "feature_name": feature_name,
            "provider_generation": provider_generation,
            "requested_frame_ids": requested_frame_ids,
            "outputs": [],
            "evidence_manifest": None,
        }
        atomic_write_json(self.analysis_path(video_id, feature_name, run_id), record)
        return record

    def frame_evidence_map(self, video_id: str) -> dict[str, str]:
        selection = self.ensure_keyframe_generation(video_id)
        return {
            entry["frame_id"]: entry["evidence_id"]
            for entry in selection["frames"]
        }

    def write_evidence(
        self,
        *,
        video_id: str,
        feature_name: str,
        run_id: str,
        payload: dict[str, Any],
    ) -> str:
        path = self.evidence_path(video_id, feature_name, run_id)
        value = {
            "schema_version": SCHEMA_VERSION,
            "analysis_run_id": run_id,
            **payload,
        }
        atomic_write_json(path, value)
        return self._relative(path) or str(path)

    def finish_analysis_run(
        self,
        record: dict[str, Any],
        *,
        status: str,
        outputs: list[dict[str, Any]] | None = None,
        evidence_manifest: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        record = dict(record)
        record["status"] = status
        record["finished_at"] = utc_now()
        if outputs is not None:
            record["outputs"] = outputs
        if evidence_manifest is not None:
            record["evidence_manifest"] = evidence_manifest
        if error is not None:
            record["error"] = {
                "type": error.__class__.__name__,
                "message": str(error),
            }
        atomic_write_json(
            self.analysis_path(
                record["video_id"],
                record["feature_name"],
                record["analysis_run_id"],
            ),
            record,
        )

    def output_record(
        self,
        *,
        run: dict[str, Any],
        frame_id: str,
        feature_path: Path,
        feature: np.ndarray,
        model_name: str,
        frame_evidence_id: str | None,
    ) -> dict[str, Any]:
        provider_generation_id = run["provider_generation"]["provider_generation_id"]
        base_identity = {
            "provider_generation_id": provider_generation_id,
            "source_id": run["source_id"],
            "rendition_id": run["rendition_id"],
            "frame_id": frame_id,
            "feature_name": run["feature_name"],
        }
        if model_name in {"ocr", "asr"}:
            semantic_role = "legacy_frame_text_projection"
            representation_kind = "normalized_text"
        else:
            semantic_role = "representation"
            representation_kind = "dense_vector"

        representation_id = stable_id(
            "rep",
            {**base_identity, "kind": representation_kind},
        )
        content_sha256 = file_sha256(feature_path)
        artifact_id = stable_id(
            "art",
            {
                "representation_id": representation_id,
                "content_sha256": content_sha256,
                "shape": list(feature.shape),
                "dtype": str(feature.dtype),
            },
        )
        return {
            "frame_id": frame_id,
            "frame_evidence_id": frame_evidence_id,
            "semantic_role": semantic_role,
            "representation_id": representation_id,
            "representation_kind": representation_kind,
            "artifact_id": artifact_id,
            "path": self._relative(feature_path),
            "content_sha256": content_sha256,
            "shape": list(feature.shape),
            "dtype": str(feature.dtype),
        }
