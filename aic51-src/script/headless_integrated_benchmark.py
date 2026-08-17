#!/usr/bin/env python3
"""Integrated Issue #34 benchmark entrypoint for the current Qwen+BGE serving line.

This wrapper deliberately leaves production retrieval behavior unchanged. It
loads the canonical headless benchmark, adds benchmark-only stable tie ordering,
and records the runtime semantics of every configured query extractor (including
Qwen-VL and BGE-M3 backends) in the run metadata.
"""
from __future__ import annotations

from collections.abc import Mapping
import importlib.metadata
import importlib.util
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HEADLESS_PATH = ROOT / "script" / "headless_benchmark.py"


def _load_headless_module():
    spec = importlib.util.spec_from_file_location("vecna_headless_benchmark", HEADLESS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load benchmark module from {HEADLESS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json_safe(value: Any) -> Any:
    """Recursively normalize runtime metadata into stdlib-JSON-safe values.

    PyMilvus collection descriptions can contain protobuf repeated-field
    containers (for example RepeatedScalarContainer), which behave like
    iterables but are not directly serializable by json.dumps(). Keep the
    benchmark metadata structured by converting mappings and generic iterables
    recursively instead of stringifying the whole Milvus schema.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _json_safe(to_dict())
        except Exception:
            pass

    try:
        iterator = iter(value)
    except TypeError:
        return str(value)
    return [_json_safe(item) for item in iterator]


def _runtime_semantics_for_extractor(extractor: Any) -> dict[str, Any]:
    getter = getattr(extractor, "runtime_semantics", None)
    if callable(getter):
        value = getter() or {}
        if isinstance(value, dict):
            return dict(value)

    result: dict[str, Any] = {}
    device = getattr(extractor, "_device", None)
    if device is not None:
        result["device"] = str(device)
    compute_type = getattr(extractor, "_compute_type", None)
    if compute_type is not None:
        result["compute_type"] = str(compute_type)
    model = getattr(extractor, "_pretrained_model", None)
    if model is not None:
        result["pretrained_model"] = str(model)
    return result


def capture_extractor_runtime(searcher: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    for name, entry in sorted(getattr(searcher, "_extractors", {}).items()):
        extractor = entry.get("feature_extractor") if isinstance(entry, dict) else None
        if extractor is None:
            continue
        captured[name] = {
            "target_features": list(entry.get("target_features", [])) if isinstance(entry, dict) else [],
            "runtime_semantics": _runtime_semantics_for_extractor(extractor),
        }
    return captured


def stable_result_key(record: Any) -> tuple[Any, ...]:
    if isinstance(record, dict):
        distance = record.get("distance", 0.0)
        entity = record.get("entity", {}) or {}
        frame_id = entity.get("frame_id", "") if isinstance(entity, dict) else ""
        timeline = record.get("time_line", []) or []
    else:
        try:
            distance = record["distance"]
        except Exception:
            distance = getattr(record, "distance", 0.0)
        try:
            entity = record["entity"]
        except Exception:
            entity = getattr(record, "entity", {}) or {}
        try:
            frame_id = entity.get("frame_id", "")
        except Exception:
            frame_id = ""
        timeline = []

    try:
        numeric_distance = float(distance)
    except (TypeError, ValueError):
        numeric_distance = 0.0
    return (-numeric_distance, str(frame_id), tuple(str(value) for value in timeline))


def install_benchmark_patches(headless: Any) -> dict[str, Any]:
    """Install benchmark-only instrumentation and return mutable runtime state."""
    from aic51.packages.search.searcher import Searcher
    import aic51.packages.webui.backend.search as search_backend

    state: dict[str, Any] = {"extractors": {}}
    original_setup_searcher = search_backend.setup_searcher
    original_search_multimodal = Searcher.search_multimodal
    original_runtime_versions = headless.runtime_versions
    original_write_run_metadata = headless.write_run_metadata

    def setup_searcher_with_runtime_capture():
        searcher = original_setup_searcher()
        state["extractors"] = capture_extractor_runtime(searcher)
        return searcher

    def stable_search_multimodal(self, *args, **kwargs):
        response = original_search_multimodal(self, *args, **kwargs)
        if isinstance(response, dict) and isinstance(response.get("results"), list):
            response = dict(response)
            response["results"] = sorted(response["results"], key=stable_result_key)
        return response

    def enriched_runtime_versions():
        runtime = dict(original_runtime_versions())
        packages = dict(runtime.get("packages", {}))
        for package in ("sentence-transformers", "onnxruntime", "onnxruntime-directml", "tokenizers"):
            try:
                packages[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                packages[package] = None
        runtime["packages"] = packages
        runtime["retrieval_extractors"] = state.get("extractors", {})
        return runtime

    def write_run_metadata_json_safe(path: Path, metadata: dict[str, Any]) -> None:
        original_write_run_metadata(path, _json_safe(metadata))

    search_backend.setup_searcher = setup_searcher_with_runtime_capture
    Searcher.search_multimodal = stable_search_multimodal
    headless.runtime_versions = enriched_runtime_versions
    headless.write_run_metadata = write_run_metadata_json_safe
    headless.CRITICAL_CODE_PATHS = {
        **headless.CRITICAL_CODE_PATHS,
        "headless_integrated_wrapper": Path(__file__).resolve(),
    }
    return state


def main() -> int:
    headless = _load_headless_module()
    install_benchmark_patches(headless)
    return headless.main()


if __name__ == "__main__":
    raise SystemExit(main())
