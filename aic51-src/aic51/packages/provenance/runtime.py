"""Runtime provenance for health checks and API result envelopes."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_commit(work_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(work_dir), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def runtime_provenance(work_dir: str | Path | None = None, collection_name: str | None = None) -> dict[str, Any]:
    root = Path(work_dir or Path.cwd()).resolve()
    config_path = root / "config.yaml"
    config_hash = _sha256(config_path)
    index_manifest = None
    if collection_name and config_hash:
        index_manifest = f"{collection_name}:{config_hash}"

    return {
        "repo_commit": _repo_commit(root),
        "config_hash": config_hash,
        "index_manifest": index_manifest,
    }
