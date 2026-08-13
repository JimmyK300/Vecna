#!/usr/bin/env python3
"""Inventory, package, preflight, and verify the minimum Issue #34 runtime.

The bundle contains one collection-filtered Milvus logical backup, the exact
query-model snapshot closure, a retrieval-only Vecna source slice, the live
configuration, the benchmark CSV, and a source-machine smoke-query result.

It deliberately excludes raw videos/audio, thumbnails, keyframes, corpus-side
``features/*.npy`` files, extraction intermediates, and frontend assets. The
tool never invokes corpus analysis, extraction, indexing, or embedding code.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


AIC51_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AIC51_ROOT.parent
DEFAULT_CSV = AIC51_ROOT / "benchmark" / "issue34_headless_queries.csv"
DEFAULT_COMPOSE = (
    AIC51_ROOT
    / "aic51"
    / "resources"
    / "milvus-standalone"
    / "milvus-standalone-docker-compose.yaml"
)
DEFAULT_CONTAINERS = ("milvus-etcd", "milvus-minio", "milvus-standalone")
BACKUP_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SECRET_KEY_RE = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|credential|private[_-]?key)",
    re.I,
)
SECRET_QUERY_RE = re.compile(r"(?:token|key|secret|password)=", re.I)
PUBLIC_COMPOSE_PLACEHOLDER_VALUES = {
    "minioadmin",
    "changeme",
    "replace_me",
    "replace-with-secret",
}
CRITICAL_DISTRIBUTIONS = (
    "torch",
    "torchvision",
    "numpy",
    "pillow",
    "pymilvus",
    "transformers",
    "huggingface-hub",
    "open-clip-torch",
    "pyyaml",
    "fastapi",
    "deep-translator",
    "omegaconf",
    "opencv-python",
    "pytesseract",
)
SOURCE_TREE_ROOTS = (
    AIC51_ROOT / "aic51" / "packages" / "analyse" / "features",
    AIC51_ROOT / "aic51" / "packages" / "analyse" / "datasets",
    AIC51_ROOT / "aic51" / "packages" / "config",
    AIC51_ROOT / "aic51" / "packages" / "constant",
    AIC51_ROOT / "aic51" / "packages" / "index",
    AIC51_ROOT / "aic51" / "packages" / "logger",
    AIC51_ROOT / "aic51" / "packages" / "search",
    AIC51_ROOT / "aic51" / "packages" / "utils",
)
SOURCE_EXPLICIT_FILES = (
    AIC51_ROOT / "aic51" / "packages" / "__init__.py",
    AIC51_ROOT / "aic51" / "packages" / "analyse" / "__init__.py",
    AIC51_ROOT / "aic51" / "packages" / "webui" / "__init__.py",
    AIC51_ROOT / "aic51" / "packages" / "webui" / "backend" / "__init__.py",
    AIC51_ROOT / "aic51" / "packages" / "webui" / "backend" / "search.py",
    AIC51_ROOT / "aic51" / "packages" / "webui" / "backend" / "utils.py",
    AIC51_ROOT / "aic51" / "resources" / "__init__.py",
    AIC51_ROOT / "aic51" / "resources" / "file_paths.py",
    AIC51_ROOT / "script" / "headless_benchmark.py",
    Path(__file__).resolve(),
    AIC51_ROOT / "pyproject.toml",
)
EXCLUDED_RUNTIME_ARTIFACTS = (
    "raw videos/audio/clips",
    "keyframes and thumbnails",
    "video_info/FPS playback metadata",
    "corpus features/**/*.npy",
    "raw OCR/ASR extraction intermediates",
    "frontend/Node assets",
    "corpus extraction/indexing models and tools",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if hasattr(value, "name") and hasattr(value, "value"):
        return {"name": str(value.name), "value": jsonable(value.value)}
    return str(value)


VOLATILE_DEFINITION_KEYS = {
    "collection_id",
    "field_id",
    "function_id",
    "id",
    "create_timestamp",
    "created_timestamp",
    "update_timestamp",
    "updated_timestamp",
    "state",
    "load_state",
    "indexed_rows",
    "pending_index_rows",
    "total_rows",
    "fail_reason",
    "indexedRows",
    "pendingIndexRows",
    "totalRows",
}


def semantic_definition(value: Any) -> Any:
    """Remove restore-specific IDs/progress while retaining schema semantics."""
    value = jsonable(value)
    if isinstance(value, dict):
        return {
            key: semantic_definition(item)
            for key, item in sorted(value.items())
            if key not in VOLATILE_DEFINITION_KEYS
        }
    if isinstance(value, list):
        normalized = [semantic_definition(item) for item in value]
        if all(isinstance(item, dict) for item in normalized):
            return sorted(
                normalized,
                key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False),
            )
        return normalized
    return value


def run(
    command: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path, base: Path | None = None) -> dict[str, Any]:
    path = path.absolute()
    relative = path.relative_to(base.absolute()) if base else Path(path.name)
    return {
        "path": str(path),
        "relative_path": relative.as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def portable_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "path"}


def tree_records(root: Path) -> list[dict[str, Any]]:
    root = root.absolute()
    return [
        file_record(path, root)
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def records_signature(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "relative_path": record["relative_path"],
                "size_bytes": int(record["size_bytes"]),
                "sha256": record["sha256"],
            }
            for record in records
        ],
        key=lambda record: record["relative_path"],
    )


def ensure_within(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    resolved_root = root.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError(f"{label} escapes {resolved_root}: {resolved}") from exc
    return resolved


def safe_child(root: Path, name: str, label: str) -> Path:
    return ensure_within(root.resolve() / name, root, label)


def validate_backup_name(name: str) -> str:
    if not BACKUP_NAME_RE.fullmatch(name) or name in {".", ".."}:
        raise ValueError(
            "backup name must be 1-128 ASCII letters/digits/dot/underscore/hyphen, "
            "start with a letter or digit, and contain no path separators"
        )
    return name


def safe_bundle_relative(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        not normalized
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(f"unsafe bundle path: {value!r}")
    return relative


def sanitize_url(value: str) -> str:
    """Remove URL credentials and query/fragment tokens before manifest transfer."""
    value = clean(value)
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def secret_paths(value: Any, prefix: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if SECRET_KEY_RE.search(str(key)) and clean(item):
                findings.append(path)
            findings.extend(secret_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(secret_paths(item, f"{prefix}[{index}]"))
    elif isinstance(value, str):
        parsed = urlsplit(value)
        if (parsed.username or parsed.password) or SECRET_QUERY_RE.search(parsed.query):
            findings.append(prefix or "<value>")
    return sorted(set(findings))


def assert_no_secrets(value: Any, label: str) -> None:
    findings = secret_paths(value)
    if findings:
        raise RuntimeError(
            f"{label} contains credential-like fields/URLs at {findings}; "
            "use environment injection or a redacted runtime config before transfer"
        )


def known_secret_values(value: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)) and isinstance(item, (str, int)) and clean(item):
                values.add(str(item))
            values.update(known_secret_values(item))
    elif isinstance(value, list):
        for item in value:
            values.update(known_secret_values(item))
    return values


def redact_known_secrets(text: str, config: dict[str, Any]) -> str:
    for secret in sorted(known_secret_values(config), key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    return text


def unsafe_compose_secret_paths(value: Any, prefix: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if SECRET_KEY_RE.search(str(key)) and clean(item):
                text = clean(item)
                allowed = (
                    text.lower() in PUBLIC_COMPOSE_PLACEHOLDER_VALUES
                    or text.startswith("${")
                    or text.startswith("REPLACE_")
                )
                if not allowed:
                    findings.append(path)
            findings.extend(unsafe_compose_secret_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            if isinstance(item, str) and "=" in item:
                key, item_value = item.split("=", 1)
                if SECRET_KEY_RE.search(key) and clean(item_value):
                    text = clean(item_value)
                    if not (
                        text.lower() in PUBLIC_COMPOSE_PLACEHOLDER_VALUES
                        or text.startswith("${")
                        or text.startswith("REPLACE_")
                    ):
                        findings.append(path)
            findings.extend(unsafe_compose_secret_paths(item, path))
    elif isinstance(value, str):
        parsed = urlsplit(value)
        if parsed.username or parsed.password or SECRET_QUERY_RE.search(parsed.query):
            findings.append(prefix or "<value>")
    return sorted(set(findings))


def assert_compose_transfer_safe(value: Any) -> None:
    findings = unsafe_compose_secret_paths(value)
    if findings:
        raise RuntimeError(
            "Compose contains non-placeholder credential-like values at "
            f"{findings}; supply a redacted equivalent Compose file for transfer"
        )


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        from yaml import safe_load
    except ImportError as exc:
        raise RuntimeError("PyYAML is required in the Vecna runtime environment") from exc
    data = safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"expected YAML mapping in {path}")
    return data


def configured_models(config: dict[str, Any]) -> list[dict[str, Any]]:
    models = config.get("searcher", {}).get("language_models", {}) or {}
    output = []
    for name, model in models.items():
        output.append(
            {
                "name": name,
                "model": model.get("model"),
                "source": model.get("source"),
                "arch_name": model.get("arch_name"),
                "pretrained_model": model.get("pretrained_model"),
                "target_features": list(model.get("target") or []),
            }
        )
    if not output:
        raise RuntimeError(
            "config has no searcher.language_models; current query encoders are unknown"
        )
    return output


def force_offline_environment(
    hf_home: Path | None = None,
    hub_cache: Path | None = None,
    torch_home: Path | None = None,
) -> dict[str, str]:
    default_hf = Path.home() / ".cache" / "huggingface"
    hf_home = (hf_home or Path(os.environ.get("HF_HOME", default_hf))).resolve()
    hub_cache = (
        hub_cache
        or Path(
            os.environ.get("HF_HUB_CACHE")
            or os.environ.get("HUGGINGFACE_HUB_CACHE")
            or (hf_home / "hub")
        )
    ).resolve()
    torch_home = (
        torch_home or Path(os.environ.get("TORCH_HOME", Path.home() / ".cache" / "torch"))
    ).resolve()
    values = {
        "HF_HOME": str(hf_home),
        "HF_HUB_CACHE": str(hub_cache),
        "HUGGINGFACE_HUB_CACHE": str(hub_cache),
        "TORCH_HOME": str(torch_home),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
    }
    os.environ.update(values)
    return values


def resolve_model_cache(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cache_env = force_offline_environment()
    hub_root = Path(cache_env["HF_HUB_CACHE"]).resolve()
    try:
        from huggingface_hub import snapshot_download
        import open_clip
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub and open_clip are required to resolve cached query models"
        ) from exc

    resolved: list[dict[str, Any]] = []
    for model in models:
        repo_id = None
        pretrained_config = None
        if clean(model.get("source")).lower() == "open_clip":
            pretrained_config = open_clip.get_pretrained_cfg(
                clean(model.get("arch_name")), clean(model.get("pretrained_model"))
            )
            if not pretrained_config:
                raise RuntimeError(f"OpenCLIP has no pretrained config for {model['name']}")
            repo_id = clean(pretrained_config.get("hf_hub")).rstrip("/") or None
            if not repo_id and pretrained_config.get("url"):
                raise RuntimeError(
                    f"{model['name']} uses a URL/Torch-cache checkpoint; "
                    "extend the inventory contract explicitly before transfer"
                )
        elif "/" in clean(model.get("pretrained_model")):
            repo_id = clean(model.get("pretrained_model"))
        if not repo_id:
            raise RuntimeError(
                f"cannot resolve a portable local Hugging Face cache for query model {model['name']}"
            )

        snapshot = Path(
            snapshot_download(repo_id=repo_id, local_files_only=True)
        ).resolve()
        ensure_within(snapshot, hub_root, f"model snapshot for {repo_id}")
        cache_repo = snapshot.parent.parent
        refs_root = cache_repo / "refs"
        snapshot_files = tree_records(snapshot)
        refs_files = tree_records(refs_root) if refs_root.is_dir() else []
        if not snapshot_files:
            raise RuntimeError(f"cached query-model snapshot is empty: {snapshot}")
        resolved.append(
            {
                **model,
                "repo_id": repo_id,
                "revision": snapshot.name,
                "snapshot_path": str(snapshot),
                "cache_repo_path": str(cache_repo),
                "cache_repo_name": cache_repo.name,
                "snapshot_files": snapshot_files,
                "refs_files": refs_files,
                "cache_size_bytes": sum(
                    item["size_bytes"] for item in [*snapshot_files, *refs_files]
                ),
                "pretrained_config": jsonable(pretrained_config),
            }
        )
    return resolved


def model_signature(models: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "name": model["name"],
                "model": model.get("model"),
                "source": model.get("source"),
                "arch_name": model.get("arch_name"),
                "pretrained_model": model.get("pretrained_model"),
                "target_features": list(model.get("target_features") or []),
                "repo_id": model["repo_id"],
                "revision": model["revision"],
                "cache_repo_name": model["cache_repo_name"],
                "snapshot_files": records_signature(model["snapshot_files"]),
                "refs_files": records_signature(model.get("refs_files") or []),
                "pretrained_config": model.get("pretrained_config"),
            }
            for model in models
        ],
        key=lambda model: model["name"],
    )


def _load_state_is_loaded(state: Any) -> bool:
    text = json.dumps(jsonable(state), ensure_ascii=False).lower()
    return "loaded" in text and "notload" not in text and "not_load" not in text


def _index_progress(client: Any, collection: str, name: str) -> dict[str, Any] | None:
    getter = getattr(client, "get_index_build_progress", None)
    if getter is not None:
        try:
            return jsonable(getter(collection_name=collection, index_name=name))
        except TypeError:
            return jsonable(getter(collection, name))
    try:
        from pymilvus import utility

        return jsonable(
            utility.index_building_progress(
                collection_name=collection,
                index_name=name,
                using=getattr(client, "_using", "default"),
            )
        )
    except (AttributeError, TypeError):
        return None


def index_readiness(client: Any, collection: str) -> dict[str, Any]:
    names = list(client.list_indexes(collection))
    if not names:
        raise RuntimeError(f"collection {collection!r} has no indexes")
    details: dict[str, Any] = {}
    pending: list[str] = []
    failed: list[str] = []
    for name in names:
        description = jsonable(client.describe_index(collection, name))
        progress = _index_progress(client, collection, name)
        blob = json.dumps(
            {"description": description, "progress": progress}, ensure_ascii=False
        ).lower()
        if "failed" in blob or '"state": 4' in blob or '"state": "4"' in blob:
            failed.append(name)
        finished = "finished" in blob or '"state": 3' in blob or '"state": "3"' in blob
        if not finished and isinstance(progress, dict):
            total = progress.get("total_rows", progress.get("totalRows"))
            indexed = progress.get("indexed_rows", progress.get("indexedRows"))
            pending_rows = progress.get(
                "pending_index_rows", progress.get("pendingIndexRows")
            )
            if total is not None and indexed is not None:
                finished = (
                    int(total) > 0
                    and int(indexed) >= int(total)
                    and int(pending_rows or 0) == 0
                )
        if not finished:
            pending.append(name)
        details[name] = {"description": description, "progress": progress}
    if failed:
        raise RuntimeError(f"Milvus index build failed for {failed}")
    if pending:
        raise RuntimeError(
            f"Milvus indexes are not demonstrably Finished for collection {collection!r}: {pending}"
        )
    return details


def _server_version(client: Any) -> Any:
    try:
        return jsonable(client.get_server_version(detail=True))
    except TypeError:
        return jsonable(client.get_server_version())


def milvus_snapshot(collection: str, require_ready: bool = True) -> dict[str, Any]:
    try:
        from pymilvus import MilvusClient
    except ImportError as exc:
        raise RuntimeError("pymilvus is required in the Vecna runtime environment") from exc

    client = MilvusClient()
    try:
        if not client.has_collection(collection):
            raise RuntimeError(
                f"configured collection {collection!r} does not exist; refusing empty fallback"
            )
        load_state = jsonable(client.get_load_state(collection))
        if require_ready and not _load_state_is_loaded(load_state):
            raise RuntimeError(
                f"collection {collection!r} is not Loaded on the source runtime: {load_state}"
            )
        readiness = index_readiness(client, collection) if require_ready else None
        count_result = client.query(collection, output_fields=["count(*)"])
        row_count = int(count_result[0]["count(*)"]) if count_result else 0
        if row_count <= 0:
            raise RuntimeError(f"configured collection {collection!r} is empty")
        index_names = list(client.list_indexes(collection))
        schema = jsonable(client.describe_collection(collection))
        indexes = {
            name: jsonable(client.describe_index(collection, name)) for name in index_names
        }
        return {
            "uri": "http://localhost:19530",
            "database": "default",
            "collection": collection,
            "server_version": _server_version(client),
            "row_count": row_count,
            "schema": schema,
            "schema_signature": semantic_definition(schema),
            "indexes": indexes,
            "index_signatures": semantic_definition(indexes),
            "index_readiness": readiness,
            "load_state": load_state,
            "stats": jsonable(client.get_collection_stats(collection)),
        }
    finally:
        client.close()


def milvus_signature(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "uri": snapshot["uri"],
        "database": snapshot["database"],
        "collection": snapshot["collection"],
        "server_version": snapshot["server_version"],
        "row_count": int(snapshot["row_count"]),
        "schema_signature": snapshot["schema_signature"],
        "index_signatures": snapshot["index_signatures"],
    }


def wait_loaded(collection: str, timeout_seconds: int) -> dict[str, Any]:
    from pymilvus import MilvusClient

    client = MilvusClient()
    try:
        if not client.has_collection(collection):
            raise RuntimeError(
                f"restored collection {collection!r} does not exist; do not let Vecna create an empty one"
            )
        client.load_collection(collection)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            state = jsonable(client.get_load_state(collection))
            if _load_state_is_loaded(state):
                return state
            time.sleep(2)
        raise RuntimeError(
            f"collection {collection!r} did not reach Loaded within {timeout_seconds}s"
        )
    finally:
        client.close()


def wait_indexes_ready(collection: str, timeout_seconds: int) -> dict[str, Any]:
    from pymilvus import MilvusClient

    client = MilvusClient()
    try:
        deadline = time.monotonic() + timeout_seconds
        last_error = ""
        while time.monotonic() < deadline:
            try:
                return index_readiness(client, collection)
            except RuntimeError as exc:
                last_error = str(exc)
                if "failed" in last_error.lower():
                    raise
            time.sleep(2)
        raise RuntimeError(
            f"indexes for collection {collection!r} were not ready within "
            f"{timeout_seconds}s: {last_error}"
        )
    finally:
        client.close()


def docker_snapshot(container_names: Iterable[str]) -> list[dict[str, Any]]:
    entries = []
    for name in container_names:
        inspected = json.loads(run(["docker", "inspect", name]).stdout)[0]
        image_id = inspected["Image"]
        image_data = json.loads(
            run(["docker", "image", "inspect", image_id]).stdout
        )[0]
        state = inspected.get("State", {})
        health = (state.get("Health") or {}).get("Status")
        if not state.get("Running"):
            raise RuntimeError(f"required container {name!r} is not running")
        if health and health.lower() != "healthy":
            raise RuntimeError(f"required container {name!r} is not healthy: {health}")
        entries.append(
            {
                "name": name,
                "configured_image": inspected.get("Config", {}).get("Image"),
                "image_id": image_id,
                "repo_digests": sorted(image_data.get("RepoDigests", [])),
                "state": {
                    "running": bool(state.get("Running")),
                    "status": state.get("Status"),
                    "health": health,
                },
                "mounts": sorted(
                    [
                        {
                            "type": mount.get("Type"),
                            "name": mount.get("Name"),
                            "destination": mount.get("Destination"),
                            "rw": mount.get("RW"),
                        }
                        for mount in inspected.get("Mounts", [])
                    ],
                    key=lambda mount: (
                        clean(mount["destination"]),
                        clean(mount["type"]),
                        clean(mount["name"]),
                    ),
                ),
            }
        )
    return entries


def docker_signature(
    entries: Iterable[dict[str, Any]], include_volume_names: bool = True
) -> list[dict[str, Any]]:
    output = []
    for entry in entries:
        repo_digests = sorted(entry.get("repo_digests") or [])
        mounts = []
        for mount in entry.get("mounts") or []:
            normalized_mount = dict(mount)
            if not include_volume_names and normalized_mount.get("type") == "volume":
                normalized_mount.pop("name", None)
            mounts.append(normalized_mount)
        output.append(
            {
                "name": entry["name"],
                "configured_image": entry.get("configured_image"),
                "image_identity": repo_digests or [entry.get("image_id")],
                "mounts": mounts,
            }
        )
    return sorted(output, key=lambda entry: entry["name"])


def dependency_snapshot() -> dict[str, Any]:
    distributions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = clean(distribution.metadata.get("Name"))
        if name:
            distributions[name.lower().replace("_", "-")] = distribution.version
    try:
        import torch

        device = {
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "mps_available": bool(
                getattr(torch.backends, "mps", None)
                and torch.backends.mps.is_available()
            ),
            "selected_by_vecna_when_gpu_requested": (
                "cuda"
                if torch.cuda.is_available()
                else (
                    "mps"
                    if getattr(torch.backends, "mps", None)
                    and torch.backends.mps.is_available()
                    else "cpu"
                )
            ),
        }
    except Exception as exc:
        device = {"error": str(exc)}
    critical = {
        name: distributions.get(name.lower().replace("_", "-"))
        for name in CRITICAL_DISTRIBUTIONS
    }
    missing = [name for name, version in critical.items() if version is None]
    if missing:
        raise RuntimeError(f"critical retrieval distributions are missing: {missing}")
    return {
        "python": sys.version,
        "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": platform.platform(),
        "machine": platform.machine(),
        "critical_packages": critical,
        "installed_versions": [
            {"name": name, "version": version}
            for name, version in sorted(distributions.items())
        ],
        "torch_device": device,
    }


def dependency_signature(snapshot: dict[str, Any], full: bool) -> dict[str, Any]:
    signature = {
        "python": snapshot["python"],
        "platform": snapshot["platform"],
        "machine": snapshot["machine"],
        "critical_packages": snapshot["critical_packages"],
    }
    if full:
        signature["installed_versions"] = snapshot["installed_versions"]
    return signature


def repo_snapshot() -> dict[str, Any]:
    sha = run(["git", "rev-parse", "HEAD"], REPO_ROOT).stdout.strip()
    status = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], REPO_ROOT
    ).stdout
    remote = run(["git", "remote", "get-url", "origin"], REPO_ROOT).stdout.strip()
    return {
        "root": str(REPO_ROOT.resolve()),
        "git_sha": sha,
        "dirty": bool(status),
        "git_status_porcelain": status.splitlines(),
        "git_status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
        "remote": sanitize_url(remote),
    }


def runtime_source_paths() -> list[Path]:
    paths = set(SOURCE_EXPLICIT_FILES)
    for root in SOURCE_TREE_ROOTS:
        paths.update(root.rglob("*.py"))
    missing = sorted(str(path) for path in paths if not path.is_file())
    if missing:
        raise RuntimeError(f"retrieval source slice is missing required files: {missing}")
    output = sorted(path.absolute() for path in paths)
    for path in output:
        ensure_within(path, REPO_ROOT, "retrieval source")
        if path.is_symlink():
            raise RuntimeError(f"retrieval source slice may not contain symlinks: {path}")
    return output


def runtime_source_records() -> list[dict[str, Any]]:
    return [file_record(path, REPO_ROOT) for path in runtime_source_paths()]


@contextlib.contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def load_smoke_query(csv_path: Path, query_id: str) -> str:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = {row["query_id"]: row for row in csv.DictReader(handle, strict=True)}
    if query_id not in rows:
        raise RuntimeError(f"smoke query id {query_id!r} is not present in {csv_path}")
    row = rows[query_id]
    if clean(row.get("query_mode")).lower() != "text" or not clean(row.get("query")):
        raise RuntimeError(f"smoke query {query_id!r} is not an executable text query")
    return row["query"]


def smoke_search(workspace: Path, query: str, target_features: list[str]) -> dict[str, Any]:
    if str(AIC51_ROOT) not in sys.path:
        sys.path.insert(0, str(AIC51_ROOT))
    searcher = None
    with block_milvus_writes():
        try:
            with working_directory(workspace):
                from aic51.packages.webui.backend.search import setup_searcher

                started = time.perf_counter()
                searcher = setup_searcher()
                init_ms = (time.perf_counter() - started) * 1000
                unknown = [
                    feature
                    for feature in target_features
                    if feature not in searcher.target_features
                ]
                if unknown:
                    raise RuntimeError(
                        f"smoke target features {unknown} unavailable; "
                        f"got {searcher.target_features}"
                    )
                started = time.perf_counter()
                raw = searcher.search_multimodal(
                    query,
                    0,
                    20,
                    target_features,
                    nprobe=32,
                    temporal_k=10000,
                    ocr_weight=0.5,
                    asr_weight=0.0,
                    max_interval=1000,
                    selected=None,
                    auto_translate=False,
                    en_to_vi_translate=False,
                )
                latency_ms = (time.perf_counter() - started) * 1000
        finally:
            # MilvusDatabase.__del__ normally releases the shared collection.
            # The guard suppresses load/release while still allowing close().
            if searcher is not None:
                del searcher
            gc.collect()
    results = []
    for record in list(raw.get("results", []))[:20]:
        entity = record.get("entity", {})
        results.append(
            {
                "frame_id": entity.get("frame_id"),
                "time_line": record.get("time_line"),
                "distance": record.get("distance"),
            }
        )
    if not results:
        raise RuntimeError("smoke query returned no results")
    return {
        "query": query,
        "target_features": target_features,
        "params": {
            "limit": 20,
            "nprobe": 32,
            "temporal_k": 10000,
            "ocr_weight": 0.5,
            "asr_weight": 0.0,
            "max_interval": 1000,
            "auto_translate": False,
            "en_to_vi_translate": False,
        },
        "model_initialization_ms": round(init_ms, 3),
        "query_latency_ms": round(latency_ms, 3),
        "top_results": results,
    }


def normalized_ids(
    results: list[dict[str, Any]], depth: int = 20
) -> list[tuple[str, tuple[Any, ...]]]:
    return [
        (clean(item.get("frame_id")), tuple(item.get("time_line") or []))
        for item in results[:depth]
    ]


def manifest_files_unchanged(manifest: dict[str, Any]) -> None:
    for label, record in manifest["files"].items():
        path = Path(record["path"])
        if not path.is_file():
            raise RuntimeError(f"inventoried {label} disappeared: {path}")
        observed = file_record(path)
        if (
            observed["size_bytes"] != record["size_bytes"]
            or observed["sha256"] != record["sha256"]
        ):
            raise RuntimeError(f"inventoried {label} changed since inventory: {path}")
    observed_source = records_signature(runtime_source_records())
    expected_source = records_signature(manifest["runtime_source_files"])
    if observed_source != expected_source:
        raise RuntimeError("retrieval source slice changed since inventory")


def unique_model_cache_bytes(models: Iterable[dict[str, Any]]) -> int:
    files: set[tuple[str, str, str]] = set()
    total = 0
    for model in models:
        key_prefix = (model["cache_repo_name"], model["revision"])
        for record in model["snapshot_files"]:
            key = (*key_prefix, record["relative_path"])
            if key not in files:
                files.add(key)
                total += int(record["size_bytes"])
        for record in model.get("refs_files") or []:
            key = (model["cache_repo_name"], "refs", record["relative_path"])
            if key not in files:
                files.add(key)
                total += int(record["size_bytes"])
    return total


def command_inventory(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    config_path = workspace / "config.yaml"
    if not config_path.is_file():
        raise RuntimeError(f"workspace config not found: {config_path}")
    csv_path = args.csv.resolve()
    compose_path = args.compose.resolve()
    for label, path in (("benchmark CSV", csv_path), ("Compose", compose_path)):
        if not path.is_file():
            raise RuntimeError(f"{label} not found: {path}")
    if args.manifest.exists() and not args.overwrite_manifest:
        raise RuntimeError(
            f"manifest already exists: {args.manifest}; use --overwrite-manifest only after preserving it"
        )

    config = load_yaml(config_path)
    assert_no_secrets(config, "workspace config")
    assert_compose_transfer_safe(load_yaml(compose_path))
    collection = (
        config.get("backends", {}).get("search", {}).get("collection") or "milvus"
    )
    models = configured_models(config)
    target_features = [
        item.strip() for item in args.target_features.split(",") if item.strip()
    ]
    if not target_features:
        raise RuntimeError("no explicit or configured target features are available")
    containers = list(args.container or DEFAULT_CONTAINERS)

    source_files = runtime_source_records()
    query_models = resolve_model_cache(models)
    manifest = {
        "manifest_version": 2,
        "created_at": utc_now(),
        "purpose": "Vecna Issue #34 minimum headless retrieval runtime",
        "files": {
            "workspace_config": file_record(config_path),
            "benchmark_csv": file_record(csv_path),
            "compose": file_record(compose_path),
            "runtime_guide": file_record(
                REPO_ROOT / "docs" / "issue34-minimum-runtime.md"
            ),
            "backup_config_template": file_record(
                AIC51_ROOT / "benchmark" / "backup-local.template.yaml"
            ),
        },
        "runtime_source_files": source_files,
        "repository": repo_snapshot(),
        "dependencies": dependency_snapshot(),
        "milvus": milvus_snapshot(collection, require_ready=True),
        "docker": docker_snapshot(containers),
        "query_models": query_models,
        "excluded_runtime_artifacts": list(EXCLUDED_RUNTIME_ARTIFACTS),
    }
    query = load_smoke_query(csv_path, args.smoke_query_id)
    manifest["smoke_query"] = {
        "query_id": args.smoke_query_id,
        **smoke_search(workspace, query, target_features),
    }
    after_smoke_milvus = milvus_snapshot(collection, require_ready=True)
    if milvus_signature(after_smoke_milvus) != milvus_signature(manifest["milvus"]):
        raise RuntimeError("source Milvus identity changed during the smoke query")
    manifest["estimated_required_bytes_before_backup"] = (
        sum(item["size_bytes"] for item in manifest["files"].values())
        + sum(item["size_bytes"] for item in source_files)
        + unique_model_cache_bytes(query_models)
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Manifest: {args.manifest.resolve()}")
    print(f"Collection: {collection} rows={manifest['milvus']['row_count']}")
    print(
        "Config/code/model bytes before Milvus backup: "
        f"{manifest['estimated_required_bytes_before_backup']}"
    )
    print("No corpus regeneration was invoked.")
    return 0


def portable_source_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    portable = json.loads(json.dumps(manifest))
    portable["files"] = {
        key: portable_record(record) for key, record in manifest["files"].items()
    }
    portable["runtime_source_files"] = [
        portable_record(record) for record in manifest["runtime_source_files"]
    ]
    portable["repository"].pop("root", None)
    portable["repository"].pop("git_status_porcelain", None)
    portable["dependencies"].pop("python_executable", None)
    for model in portable["query_models"]:
        model.pop("snapshot_path", None)
        model.pop("cache_repo_path", None)
        model["snapshot_files"] = [
            portable_record(record) for record in model["snapshot_files"]
        ]
        model["refs_files"] = [
            portable_record(record) for record in model.get("refs_files") or []
        ]
    return portable


def copy_model_caches(manifest: dict[str, Any], destination: Path) -> None:
    copied: set[tuple[str, str]] = set()
    for model in manifest["query_models"]:
        source_snapshot = Path(model["snapshot_path"]).resolve()
        cache_repo_name = model["cache_repo_name"]
        revision = model["revision"]
        key = (cache_repo_name, revision)
        target_repo = destination / cache_repo_name
        target_snapshot = target_repo / "snapshots" / revision
        if key not in copied:
            shutil.copytree(source_snapshot, target_snapshot, symlinks=False)
            refs_source = Path(model["cache_repo_path"]) / "refs"
            if refs_source.is_dir() and not (target_repo / "refs").exists():
                shutil.copytree(refs_source, target_repo / "refs", symlinks=False)
            copied.add(key)
        if records_signature(tree_records(target_snapshot)) != records_signature(
            model["snapshot_files"]
        ):
            raise RuntimeError(f"model snapshot copy mismatch for {model['repo_id']}")


def copy_source_slice(manifest: dict[str, Any], destination: Path) -> None:
    for record in manifest["runtime_source_files"]:
        relative = safe_bundle_relative(record["relative_path"])
        source = Path(record["path"])
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256_file(target) != record["sha256"]:
            raise RuntimeError(f"source copy mismatch: {record['relative_path']}")


def validate_backup_config(
    path: Path, expected_root: Path, expected_milvus_uri: str
) -> dict[str, Any]:
    config = load_yaml(path)
    backup_storage = config.get("backup", {}).get("storage", {}) or {}
    if clean(backup_storage.get("provider")).lower() != "local":
        raise RuntimeError("backup config must use backup.storage.provider: local")
    configured_root = Path(clean(backup_storage.get("rootPath"))).resolve()
    if configured_root != expected_root.resolve():
        raise RuntimeError(
            f"backup.storage.rootPath mismatch: config={configured_root} "
            f"--backup-root={expected_root.resolve()}"
        )
    grpc = config.get("milvus", {}).get("grpc", {}) or {}
    expected = urlsplit(expected_milvus_uri)
    address = clean(grpc.get("address"))
    port = int(grpc.get("port") or 19530)
    if address not in {expected.hostname, "127.0.0.1", "::1"} or port != (
        expected.port or 19530
    ):
        raise RuntimeError(
            "backup config Milvus gRPC endpoint does not match the inventoried direct client: "
            f"{address}:{port} versus {expected.hostname}:{expected.port or 19530}"
        )
    return config


def backup_tool_identity(command: str) -> dict[str, Any]:
    resolved = shutil.which(command)
    if not resolved:
        raise RuntimeError(f"milvus-backup executable not found: {command}")
    executable = Path(resolved).resolve()
    help_result = run([str(executable), "--help"])
    normalized_help = (help_result.stdout + help_result.stderr).replace("\r\n", "\n")
    return {
        "executable_name": executable.name,
        "binary_sha256": sha256_file(executable),
        "help_sha256": hashlib.sha256(normalized_help.encode("utf-8")).hexdigest(),
    }


def write_bundle_manifest(bundle: Path, metadata: dict[str, Any]) -> Path:
    path = bundle / "bundle-manifest.json"
    files = [
        portable_record(record)
        for record in tree_records(bundle)
        if record["relative_path"] != path.name
    ]
    metadata = {
        **metadata,
        "files": files,
        "total_file_bytes": sum(item["size_bytes"] for item in files),
    }
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def archive_bundle(bundle: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output, "x", compression=zipfile.ZIP_STORED, allowZip64=True
    ) as archive:
        for path in sorted(item for item in bundle.rglob("*") if item.is_file()):
            if path.is_symlink():
                raise RuntimeError(f"bundle archive may not contain symlinks: {path}")
            archive.write(path, Path(bundle.name) / path.relative_to(bundle))


def paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def validate_package_outputs(
    bundle: Path, archive: Path, checksum: Path, backup_dir: Path
) -> None:
    if paths_overlap(bundle, archive) or paths_overlap(bundle, checksum):
        raise RuntimeError(
            "bundle, archive, and checksum paths must not contain one another; "
            "an archive inside its bundle can recursively archive itself"
        )
    for output in (bundle, archive, checksum):
        if paths_overlap(output, backup_dir):
            raise RuntimeError(
                f"package output overlaps logical-backup directory: {output} and {backup_dir}"
            )
    existing = [path for path in (bundle, archive, checksum) if path.exists()]
    if existing:
        raise RuntimeError(
            "refusing to overwrite package outputs: "
            + ", ".join(str(path) for path in existing)
        )


def command_package(args: argparse.Namespace) -> int:
    backup_name = validate_backup_name(args.backup_name)
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 2:
        raise RuntimeError("package requires an Issue #34 runtime manifest_version 2")
    bundle = args.bundle_dir.resolve()
    archive = (args.archive or bundle.with_suffix(".zip")).resolve()
    checksum = Path(str(archive) + ".sha256")
    backup_root = args.backup_root.resolve()
    backup_dir = safe_child(backup_root, backup_name, "backup destination")
    validate_package_outputs(bundle, archive, checksum, backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)
    if backup_dir.exists():
        raise RuntimeError(
            f"backup name already exists at {backup_dir}; preserve it and choose a new name"
        )

    manifest_files_unchanged(manifest)
    current_sha = run(["git", "rev-parse", "HEAD"], REPO_ROOT).stdout.strip()
    if current_sha != manifest["repository"]["git_sha"]:
        raise RuntimeError(
            f"repository SHA changed since inventory: "
            f"{manifest['repository']['git_sha']} -> {current_sha}"
        )
    config_path = Path(manifest["files"]["workspace_config"]["path"])
    config = load_yaml(config_path)
    assert_no_secrets(config, "workspace config")
    models = configured_models(config)
    observed_models = resolve_model_cache(models)
    if model_signature(observed_models) != model_signature(manifest["query_models"]):
        raise RuntimeError("query-model snapshot closure changed since inventory")
    observed_dependencies = dependency_snapshot()
    if dependency_signature(observed_dependencies, full=True) != dependency_signature(
        manifest["dependencies"], full=True
    ):
        raise RuntimeError("Python environment changed since inventory")
    observed_milvus = milvus_snapshot(
        manifest["milvus"]["collection"], require_ready=True
    )
    if milvus_signature(observed_milvus) != milvus_signature(manifest["milvus"]):
        raise RuntimeError("live Milvus runtime changed since inventory")
    observed_docker = docker_snapshot([item["name"] for item in manifest["docker"]])
    if docker_signature(observed_docker) != docker_signature(manifest["docker"]):
        raise RuntimeError("Docker image/mount runtime changed since inventory")
    observed_smoke = smoke_search(
        config_path.parent,
        manifest["smoke_query"]["query"],
        manifest["smoke_query"]["target_features"],
    )
    if normalized_ids(observed_smoke["top_results"]) != normalized_ids(
        manifest["smoke_query"]["top_results"]
    ):
        raise RuntimeError("source smoke-query top-20 IDs changed since inventory")
    after_smoke_milvus = milvus_snapshot(
        manifest["milvus"]["collection"], require_ready=True
    )
    if milvus_signature(after_smoke_milvus) != milvus_signature(observed_milvus):
        raise RuntimeError("live Milvus identity changed during package smoke query")

    backup_connection_config = validate_backup_config(
        args.backup_config.resolve(), backup_root, manifest["milvus"]["uri"]
    )
    source_backup_tool = backup_tool_identity(args.milvus_backup)
    backup_cmd = [args.milvus_backup, "--config", str(args.backup_config.resolve())]
    run([*backup_cmd, "check"])
    print(
        f"Creating logical backup for collection {manifest['milvus']['collection']!r} ...",
        flush=True,
    )
    run(
        [
            *backup_cmd,
            "create",
            "-n",
            backup_name,
            "--filter",
            manifest["milvus"]["collection"],
        ]
    )
    if not backup_dir.is_dir():
        raise RuntimeError(
            f"backup completed but {backup_dir} was not found; "
            "verify backup.storage.rootPath"
        )
    inspection = run([*backup_cmd, "get", "-n", backup_name])
    inspection_text = redact_known_secrets(
        inspection.stdout + inspection.stderr, backup_connection_config
    )
    if manifest["milvus"]["collection"].lower() not in inspection_text.lower():
        raise RuntimeError(
            "milvus-backup get did not report the inventoried collection; refusing bundle"
        )
    after_backup = milvus_snapshot(
        manifest["milvus"]["collection"], require_ready=True
    )
    if milvus_signature(after_backup) != milvus_signature(observed_milvus):
        raise RuntimeError("live Milvus collection changed during logical backup")
    manifest_files_unchanged(manifest)
    if model_signature(resolve_model_cache(models)) != model_signature(
        manifest["query_models"]
    ):
        raise RuntimeError("query-model snapshot closure changed during backup")
    after_docker = docker_snapshot([item["name"] for item in manifest["docker"]])
    if docker_signature(after_docker) != docker_signature(manifest["docker"]):
        raise RuntimeError("Docker image/mount runtime changed during backup")

    portable_manifest = portable_source_manifest(manifest)
    portable_manifest["milvus_backup_tool"] = source_backup_tool
    with tempfile.TemporaryDirectory(prefix="vecna-issue34-bundle-") as temporary:
        staging = Path(temporary) / bundle.name
        runtime = staging / "runtime"
        source_root = runtime / "vecna-source"
        model_root = staging / "model-cache" / "hub"
        backup_staging = staging / "milvus-backup"
        source_root.mkdir(parents=True)
        model_root.mkdir(parents=True)
        backup_staging.mkdir(parents=True)
        portable_manifest_path = staging / "source-runtime-manifest.json"
        portable_manifest_path.write_text(
            json.dumps(portable_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.copy2(config_path, runtime / "config.yaml")
        shutil.copy2(
            manifest["files"]["benchmark_csv"]["path"],
            runtime / "issue34_headless_queries.csv",
        )
        shutil.copy2(
            manifest["files"]["compose"]["path"], runtime / "milvus-compose.yaml"
        )
        shutil.copy2(
            manifest["files"]["runtime_guide"]["path"],
            runtime / "issue34-minimum-runtime.md",
        )
        shutil.copy2(
            manifest["files"]["backup_config_template"]["path"],
            runtime / "backup-local.template.yaml",
        )
        (runtime / "activate-offline.ps1").write_text(
            "$BundleRoot = Split-Path -Parent $PSScriptRoot\n"
            "$env:HF_HOME = Join-Path $BundleRoot 'model-cache'\n"
            "$env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'\n"
            "$env:HUGGINGFACE_HUB_CACHE = $env:HF_HUB_CACHE\n"
            "$env:TORCH_HOME = Join-Path $env:HF_HOME 'torch'\n"
            "$env:HF_HUB_OFFLINE = '1'\n"
            "$env:TRANSFORMERS_OFFLINE = '1'\n"
            "$env:HF_HUB_DISABLE_TELEMETRY = '1'\n",
            encoding="utf-8",
        )
        (runtime / "requirements.versions.txt").write_text(
            "\n".join(
                f"{item['name']}=={item['version']}"
                for item in manifest["dependencies"]["installed_versions"]
            )
            + "\n",
            encoding="utf-8",
        )
        copy_source_slice(manifest, source_root)
        copy_model_caches(manifest, model_root)
        shutil.copytree(
            backup_dir, backup_staging / backup_name, symlinks=False
        )
        (staging / "backup-inspection.json").write_text(
            json.dumps(
                {
                    "backup_name": backup_name,
                    "collection": manifest["milvus"]["collection"],
                    "milvus_backup_get_output_sha256": hashlib.sha256(
                        inspection_text.encode("utf-8")
                    ).hexdigest(),
                    "collection_name_observed_in_get_output": True,
                    "output_text_omitted_to_avoid_transferring_connection_metadata": True,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (staging / "README.txt").write_text(
            "Minimum Vecna Issue #34 headless retrieval runtime.\n"
            "Excluded: raw media, thumbnails/keyframes, corpus feature .npy files, "
            "extraction intermediates, and frontend assets.\n"
            "Run preflight-restore before the human-controlled restore, then run verify.\n"
            "See runtime/issue34-minimum-runtime.md for exact stop-gated commands.\n",
            encoding="utf-8",
        )
        write_bundle_manifest(
            staging,
            {
                "bundle_manifest_version": 2,
                "created_at": utc_now(),
                "source_manifest_sha256": sha256_file(manifest_path),
                "portable_source_manifest_sha256": sha256_file(
                    portable_manifest_path
                ),
                "backup_name": backup_name,
                "collection": manifest["milvus"]["collection"],
            },
        )
        shutil.move(str(staging), str(bundle))

    archive_bundle(bundle, archive)
    archive_hash = sha256_file(archive)
    checksum.write_text(f"{archive_hash}  {archive.name}\n", encoding="ascii")
    print(f"Bundle directory: {bundle} ({tree_size(bundle)} bytes)")
    print(f"Transfer archive: {archive} ({archive.stat().st_size} bytes)")
    print(f"Archive SHA-256: {archive_hash}")
    print(f"Checksum sidecar: {checksum}")
    return 0


def verify_bundle_hashes(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    manifest_path = bundle / "bundle-manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError("bundle-manifest.json is missing or unsafe")
    bundle_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {"bundle-manifest.json"}
    for record in bundle_manifest["files"]:
        relative = safe_bundle_relative(record["relative_path"])
        relative_text = relative.as_posix()
        if relative_text in expected:
            raise RuntimeError(f"duplicate bundle manifest path: {relative_text}")
        expected.add(relative_text)
        path = ensure_within(
            bundle.joinpath(*relative.parts), bundle, "bundle manifest path"
        )
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"bundle file missing or unsafe: {relative_text}")
        if (
            path.stat().st_size != record["size_bytes"]
            or sha256_file(path) != record["sha256"]
        ):
            raise RuntimeError(f"bundle file mismatch: {relative_text}")
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise RuntimeError(
            f"bundle file set is not closed; missing={sorted(expected - actual)} "
            f"unexpected={sorted(actual - expected)}"
        )
    return bundle_manifest


def verify_local_source(source: dict[str, Any]) -> None:
    expected = records_signature(source["runtime_source_files"])
    observed = records_signature(runtime_source_records())
    if observed != expected:
        raise RuntimeError(
            "verification tool/source tree differs from the bundled retrieval source slice; "
            "run the tool from runtime/vecna-source"
        )


def verify_model_caches(bundle: Path, source: dict[str, Any]) -> None:
    model_cache = bundle / "model-cache"
    hub_cache = model_cache / "hub"
    force_offline_environment(
        hf_home=model_cache,
        hub_cache=hub_cache,
        torch_home=model_cache / "torch",
    )
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for offline cache verification") from exc
    seen: set[tuple[str, str]] = set()
    for model in source["query_models"]:
        key = (model["repo_id"], model["revision"])
        if key in seen:
            continue
        seen.add(key)
        explicit = Path(
            snapshot_download(
                repo_id=model["repo_id"],
                revision=model["revision"],
                local_files_only=True,
            )
        ).resolve()
        default = Path(
            snapshot_download(repo_id=model["repo_id"], local_files_only=True)
        ).resolve()
        ensure_within(explicit, hub_cache, f"offline snapshot {model['repo_id']}")
        ensure_within(default, hub_cache, f"offline default snapshot {model['repo_id']}")
        if explicit.name != model["revision"] or default.name != model["revision"]:
            raise RuntimeError(
                f"offline model revision mismatch for {model['repo_id']}: "
                f"expected {model['revision']}, got explicit={explicit.name}, default={default.name}"
            )
        if records_signature(tree_records(explicit)) != records_signature(
            model["snapshot_files"]
        ):
            raise RuntimeError(f"offline model snapshot files differ for {model['repo_id']}")


def backup_config_root_for_bundle(bundle: Path) -> Path:
    return (bundle / "milvus-backup").resolve()


def ensure_collection_absent(collection: str) -> None:
    from pymilvus import MilvusClient

    client = MilvusClient()
    try:
        if client.has_collection(collection):
            raise RuntimeError(
                f"target collection {collection!r} already exists. Stop: do not overwrite, "
                "drop, rename, or restore over it without an explicit human decision."
            )
    finally:
        client.close()


def command_preflight_restore(args: argparse.Namespace) -> int:
    bundle = args.bundle_dir.resolve()
    bundle_manifest = verify_bundle_hashes(bundle)
    source = json.loads(
        (bundle / "source-runtime-manifest.json").read_text(encoding="utf-8")
    )
    collection = source["milvus"]["collection"]
    backup_name = validate_backup_name(bundle_manifest["backup_name"])
    verify_model_caches(bundle, source)
    current_docker = docker_snapshot([item["name"] for item in source["docker"]])
    if docker_signature(current_docker, include_volume_names=False) != docker_signature(
        source["docker"], include_volume_names=False
    ):
        raise RuntimeError("target Docker image/mount contract differs from source")
    ensure_collection_absent(collection)
    validate_backup_config(
        args.restore_config.resolve(),
        backup_config_root_for_bundle(bundle),
        source["milvus"]["uri"],
    )
    target_backup_tool = backup_tool_identity(args.milvus_backup)
    if (
        target_backup_tool["help_sha256"]
        != source["milvus_backup_tool"]["help_sha256"]
    ):
        raise RuntimeError(
            "target milvus-backup command surface differs from the source packager"
        )
    backup_cmd = [args.milvus_backup, "--config", str(args.restore_config.resolve())]
    run([*backup_cmd, "check"])
    listed = run([*backup_cmd, "get", "-n", backup_name])
    if collection.lower() not in (listed.stdout + listed.stderr).lower():
        raise RuntimeError("restore source does not report the expected collection")
    command = (
        f"{args.milvus_backup} --config {args.restore_config.resolve()} restore "
        f"-n {backup_name} --filter {collection} --rebuild_index"
    )
    print("Preflight passed. The target collection is absent and no restore was run.")
    print(f"Human-controlled restore command: {command}")
    print("Success: the command completes without an import/build failure.")
    print("Failure signal: any existing collection, error, or zero restored collection; stop.")
    return 0


@contextlib.contextmanager
def block_milvus_writes():
    from pymilvus import MilvusClient

    write_names = (
        "create_collection",
        "drop_collection",
        "insert",
        "upsert",
        "delete",
        "create_index",
        "drop_index",
    )
    state_names = ("load_collection", "release_collection")
    names = (*write_names, *state_names)
    originals = {name: getattr(MilvusClient, name, None) for name in names}

    def forbidden(*_args, **_kwargs):
        raise RuntimeError("runtime smoke forbids Milvus writes and corpus regeneration")

    def preserve_load_state(*_args, **_kwargs):
        return None

    try:
        for name in write_names:
            original = originals[name]
            if original is not None:
                setattr(MilvusClient, name, forbidden)
        for name in state_names:
            original = originals[name]
            if original is not None:
                setattr(MilvusClient, name, preserve_load_state)
        yield
    finally:
        for name, original in originals.items():
            if original is not None:
                setattr(MilvusClient, name, original)


def command_verify(args: argparse.Namespace) -> int:
    bundle = args.bundle_dir.resolve()
    bundle_manifest = verify_bundle_hashes(bundle)
    source = json.loads(
        (bundle / "source-runtime-manifest.json").read_text(encoding="utf-8")
    )
    verify_local_source(source)
    workspace = args.workspace.resolve()
    config_path = workspace / "config.yaml"
    if not config_path.is_file():
        raise RuntimeError(
            f"copy {bundle / 'runtime' / 'config.yaml'} to {config_path} before verification"
        )
    if sha256_file(config_path) != source["files"]["workspace_config"]["sha256"]:
        raise RuntimeError("workspace config hash differs from source runtime config")
    assert_no_secrets(load_yaml(config_path), "workspace config")
    verify_model_caches(bundle, source)

    local_dependencies = dependency_snapshot()
    if (
        local_dependencies["python_major_minor"]
        != source["dependencies"]["python_major_minor"]
    ):
        raise RuntimeError(
            f"Python major/minor differs: source={source['dependencies']['python_major_minor']} "
            f"local={local_dependencies['python_major_minor']}"
        )
    if (
        local_dependencies["critical_packages"]
        != source["dependencies"]["critical_packages"]
    ):
        raise RuntimeError(
            "critical Python dependency versions differ from the source runtime"
        )
    current_docker = docker_snapshot([item["name"] for item in source["docker"]])
    if docker_signature(current_docker, include_volume_names=False) != docker_signature(
        source["docker"], include_volume_names=False
    ):
        raise RuntimeError("target Docker image/mount contract differs from source")

    collection = source["milvus"]["collection"]
    wait_indexes_ready(collection, args.load_timeout_seconds)
    load_state = wait_loaded(collection, args.load_timeout_seconds)
    current = milvus_snapshot(collection, require_ready=True)
    if milvus_signature(current) != milvus_signature(source["milvus"]):
        raise RuntimeError(
            "restored Milvus server/schema/index/count identity differs from source"
        )

    smoke = source["smoke_query"]
    observed = smoke_search(
        workspace,
        smoke["query"],
        smoke["target_features"],
    )
    after_smoke = milvus_snapshot(collection, require_ready=True)
    if milvus_signature(after_smoke) != milvus_signature(source["milvus"]):
        raise RuntimeError("restored Milvus identity changed during verification smoke query")
    verify_bundle_hashes(bundle)
    expected_ids = normalized_ids(smoke["top_results"])
    observed_ids = normalized_ids(observed["top_results"])
    if expected_ids != observed_ids:
        raise RuntimeError(
            f"smoke top-20 IDs differ:\nsource={expected_ids}\nlocal={observed_ids}"
        )

    print(
        json.dumps(
            {
                "verified_at": utc_now(),
                "bundle": str(bundle),
                "bundle_file_count": len(bundle_manifest["files"]),
                "collection": collection,
                "row_count": current["row_count"],
                "load_state": load_state,
                "indexes_finished": True,
                "smoke_top_20_ids_match": True,
                "offline_model_cache": str(bundle / "model-cache"),
                "milvus_writes_blocked_during_smoke": True,
                "corpus_regeneration_invoked": False,
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser(
        "inventory", help="read-only runtime inventory plus one smoke query"
    )
    inventory.add_argument("--workspace", required=True, type=Path)
    inventory.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    inventory.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    inventory.add_argument("--manifest", required=True, type=Path)
    inventory.add_argument("--overwrite-manifest", action="store_true")
    inventory.add_argument("--smoke-query-id", default="p1_q01")
    inventory.add_argument(
        "--target-features",
        required=True,
        help="Exact comma-separated vector fields for the frozen smoke/baseline contract.",
    )
    inventory.add_argument(
        "--container",
        action="append",
        default=None,
        help="Repeat to replace the three default container names.",
    )
    inventory.set_defaults(func=command_inventory)

    package = subparsers.add_parser(
        "package", help="create one collection-filtered backup and transfer archive"
    )
    package.add_argument("--manifest", required=True, type=Path)
    package.add_argument("--backup-config", required=True, type=Path)
    package.add_argument("--backup-root", required=True, type=Path)
    package.add_argument("--backup-name", required=True)
    package.add_argument("--bundle-dir", required=True, type=Path)
    package.add_argument("--archive", type=Path)
    package.add_argument("--milvus-backup", default="milvus-backup")
    package.set_defaults(func=command_package)

    preflight = subparsers.add_parser(
        "preflight-restore",
        help="verify transfer and prove target collection absence; never restores",
    )
    preflight.add_argument("--bundle-dir", required=True, type=Path)
    preflight.add_argument("--restore-config", required=True, type=Path)
    preflight.add_argument("--milvus-backup", default="milvus-backup")
    preflight.set_defaults(func=command_preflight_restore)

    verify = subparsers.add_parser(
        "verify", help="post-restore hashes/schema/index/offline smoke verification"
    )
    verify.add_argument("--bundle-dir", required=True, type=Path)
    verify.add_argument("--workspace", required=True, type=Path)
    verify.add_argument("--load-timeout-seconds", type=int, default=600)
    verify.set_defaults(func=command_verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        RuntimeError,
        ValueError,
        FileNotFoundError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
