from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA_VERSION = "vecna.analysis-manifest.v1"
EVIDENCE_SCHEMA_VERSION = "vecna.native-evidence.v1"


def canonical_json(value: Any) -> str:
    """Serialize material configuration deterministically for identity hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def provider_generation_id(descriptor: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(descriptor).encode("utf-8")).hexdigest()
    return f"pg_sha256_{digest}"


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compatibility_output_status(feature: np.ndarray) -> str:
    if feature.size == 0:
        return "success_empty"

    if feature.dtype.kind in {"U", "S", "O"}:
        values = feature.reshape(-1).tolist()
        if all(str(value or "").strip() == "" for value in values):
            return "success_empty"

    return "success_output"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_code_revision() -> str:
    """Return a truthful code revision when available, otherwise explicit unknown."""
    configured = os.getenv("VECNA_CODE_REVISION")
    if configured:
        return configured

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        revision = result.stdout.strip()
        if result.returncode == 0 and revision:
            return revision
    except (OSError, subprocess.SubprocessError):
        pass

    return "unknown"


def relative_path(path: Path | str, root: Path | str) -> str:
    path = Path(path)
    root = Path(root)
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def build_artifact_record(
    artifact_path: Path | str,
    root: Path | str,
    video_id: str,
    frame_id: str,
    feature: np.ndarray,
    native_evidence_path: str | None = None,
) -> dict[str, Any]:
    record = {
        "artifact_path": relative_path(artifact_path, root),
        "sha256": sha256_file(artifact_path),
        "natural_locator": {
            "kind": "frame",
            "video_id": video_id,
            "frame_id": str(frame_id),
        },
        "status": compatibility_output_status(feature),
    }
    if native_evidence_path:
        record["native_evidence_path"] = native_evidence_path
    return record


def write_json(path: Path | str, payload: Any) -> None:
    """Atomically replace a JSON sidecar so interrupted writes do not leave partial metadata."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    temp_path.replace(path)


def read_json(path: Path | str) -> Any | None:
    path = Path(path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def merge_artifact_records(existing: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge only records actually observed by provenance-aware runs.

    Existing legacy `.npy` files that never had provenance records are deliberately
    not discovered/backfilled here.
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for record in [*existing, *new]:
        locator = record.get("natural_locator", {})
        key = (str(locator.get("frame_id", "")), str(record.get("artifact_path", "")))
        merged[key] = record
    return sorted(
        merged.values(),
        key=lambda record: (
            str(record.get("natural_locator", {}).get("frame_id", "")),
            str(record.get("artifact_path", "")),
        ),
    )
