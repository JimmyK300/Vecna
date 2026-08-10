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
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, value: Any, length: int = 24) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def implementation_fingerprint(obj: Any) -> dict[str, Any]:
    target = obj if inspect.isclass(obj) else obj.__class__
    source_file = inspect.getsourcefile(target)
    digest = None
    if source_file:
        try:
            digest = hashlib.sha256(Path(source_file).read_bytes()).hexdigest()
        except OSError:
            digest = None
    return {"module": target.__module__, "class": target.__name__, "source_sha256": digest}


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
    """Compatibility sidecars for the legacy Vecna analysis pipeline."""

    def __init__(self, work_dir: Path | str):
        self.work_dir = Path(work_dir)
        self.root = self.work_dir / PROVENANCE_DIR

    def _relative(self, path: Path | str | None) -> str | None:
        if path is None:
            return None
        path = Path(path)
        try:
            return str(path.resolve().relative_to(self.work_dir.resolve()))
        except (OSError, ValueError):
            return str(path)

    def source_path(self, video_id: str) -> Path:
        return self.root / "sources" / f"{video_id}.json"

    def keyframe_path(self, video_id: str) -> Path:
        return self.root / "keyframes" / f"{video_id}.json"

    def analysis_path(self, video_id: str, feature_name: str, run_id: str) -> Path:
        return self.root / "analysis" / video_id / feature_name / f"{run_id}.json"

    def evidence_path(self, video_id: str, feature_name: str, run_id: str) -> Path:
        return self.root / "evidence" / video_id / feature_name / f"{run_id}.json"

    def ensure_source(self, video_id: str) -> dict[str, Any]:
        path = self.source_path(video_id)
        existing = read_json(path)
        if existing:
            return existing

        video_path = self.work_dir / constant.VIDEO_DIR / f"{video_id}{constant.VIDEO_EXTENSION}"
        info_path = self.work_dir / constant.VIDEO_INFO_DIR / f"{video_id}.json"
        info = read_json(info_path) or {}
        rounded_fps = info.get(constant.FPS_KEY)

        source_id = new_id("src")
        rendition_id = new_id("rnd")
        record = {
            "schema_version": SCHEMA_VERSION,
            "logical_source": {
                "source_id": source_id,
                "legacy_video_id": video_id,
                "registered_at": utc_now(),
                "registration_origin": "observed_at_analysis",
                "historical_import_provenance": "unknown",
            },
            "current_rendition_id": rendition_id,
            "renditions": [
                {
                    "rendition_id": rendition_id,
                    "registered_at": utc_now(),
                    "registration_origin": "observed_at_analysis",
                    "physical_asset": self._relative(video_path) if video_path.exists() else None,
                    "container": video_path.suffix.lower() if video_path.exists() else None,
                    "file_size_bytes": video_path.stat().st_size if video_path.exists() else None,
                    "native_timing": "unknown",
                    "legacy_rounded_fps": rounded_fps,
                    "legacy_time_projection_quality": "reconstructed_from_rounded_fps" if rounded_fps else "unknown",
                    "historical_rendition_derivation": "unknown",
                }
            ],
        }
        atomic_write_json(path, record)
        return record

    def ensure_keyframe_generation(self, video_id: str) -> dict[str, Any]:
        path = self.keyframe_path(video_id)
        existing = read_json(path)
        if existing:
            return existing

        source = self.ensure_source(video_id)
        source_id = source["logical_source"]["source_id"]
        rendition_id = source["current_rendition_id"]
        keyframe_dir = self.work_dir / constant.KEYFRAME_DIR / video_id
        frame_ids = sorted(p.stem for p in keyframe_dir.glob("*") if p.is_file() and not p.stem.startswith("."))
        descriptor = {
            "source_id": source_id,
            "rendition_id": rendition_id,
            "observed_frame_ids": frame_ids,
            "registration_origin": "observed_at_analysis",
            "producer_configuration": "unknown",
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
                "natural_locator": {"kind": "source_frame", "frame_id": frame_id},
            }
            for frame_id in frame_ids
        ]
        record = {
            "schema_version": SCHEMA_VERSION,
            "selection_generation_id": generation_id,
            "source_id": source_id,
            "rendition_id": rendition_id,
            "registered_at": utc_now(),
            "registration_origin": "observed_at_analysis",
            "producer_family": "frame_selection",
            "producer_configuration": "unknown",
            "historical_generation_identity": "unknown",
            "frames": frames,
        }
        atomic_write_json(path, record)
        return record

    def provider_generation(self, *, feature_name: str, model_name: str, source: str | None,
                            arch_name: str | None, pretrained_model: str | None,
                            batch_size: int, extractor: Any) -> dict[str, Any]:
        descriptor = {
            "provider_family": model_name,
            "feature_name": feature_name,
            "source": source,
            "arch_name": arch_name,
            "pretrained_model": pretrained_model,
            "analyse": {"batch_size": batch_size},
            "implementation": implementation_fingerprint(extractor),
        }
        return {"provider_generation_id": stable_id("prv", descriptor), "descriptor": descriptor}

    def begin_analysis_run(self, *, video_id: str, feature_name: str,
                           provider_generation: dict[str, Any], requested_frame_ids: list[str]) -> dict[str, Any]:
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
        return {entry["frame_id"]: entry["evidence_id"] for entry in selection["frames"]}

    def write_evidence(self, *, video_id: str, feature_name: str, run_id: str,
                       payload: dict[str, Any]) -> str:
        path = self.evidence_path(video_id, feature_name, run_id)
        value = {"schema_version": SCHEMA_VERSION, "analysis_run_id": run_id, **payload}
        atomic_write_json(path, value)
        return self._relative(path) or str(path)

    def finish_analysis_run(self, record: dict[str, Any], *, status: str,
                            outputs: list[dict[str, Any]] | None = None,
                            evidence_manifest: str | None = None,
                            error: BaseException | None = None) -> None:
        record = dict(record)
        record["status"] = status
        record["finished_at"] = utc_now()
        if outputs is not None:
            record["outputs"] = outputs
        if evidence_manifest is not None:
            record["evidence_manifest"] = evidence_manifest
        if error is not None:
            record["error"] = {"type": error.__class__.__name__, "message": str(error)}
        atomic_write_json(self.analysis_path(record["video_id"], record["feature_name"], record["analysis_run_id"]), record)

    def output_record(self, *, run: dict[str, Any], frame_id: str, feature_path: Path,
                      feature: np.ndarray, model_name: str,
                      frame_evidence_id: str | None) -> dict[str, Any]:
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

        representation_id = stable_id("rep", {**base_identity, "kind": representation_kind})
        artifact_id = stable_id(
            "art",
            {
                "representation_id": representation_id,
                "output_path": self._relative(feature_path),
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
            "shape": list(feature.shape),
            "dtype": str(feature.dtype),
        }
