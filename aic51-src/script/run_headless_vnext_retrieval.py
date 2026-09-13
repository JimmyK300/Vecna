#!/usr/bin/env python3
"""Bounded Issue #77 Headless-vNext retrieval runner.

The runner is deliberately benchmark-local.  It loads the accepted #76
manifest and arm registry, performs a read-only collection preflight, then
invokes the existing Searcher directly with an explicit frozen call.  It
does not edit production configuration or retrieval code.
"""

from __future__ import annotations

import argparse
import ast
import csv
from collections.abc import Mapping
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AIC_ROOT = ROOT / "aic51-src"
MANIFEST_PATH = ROOT / "benchmark-results" / "headless-vnext" / "manifest.json"
CANONICAL_TEXT_PATH = ROOT / "benchmark-results" / "headless-vnext" / "canonical-query-texts.json"
SCORER_PATH = AIC_ROOT / "script" / "score_headless_vnext.py"
ARMS_PATH = ROOT / "benchmark-results" / "headless-vnext-run" / "ARMS.json"
EXPECTED_BASE_SHA = "9ea75434059cb006091d8070c6038d0add7cb62d"
EXPECTED_ISSUE76_SHA = "74e5e2bea99fbec6a42810b6822aa521cc0942fc"
EXPECTED_CONTRACT_SHA = "2344023ea4e2a152d1e9dc15778d8feb436dc396"
EXPECTED_MANIFEST_SHA = "354a41330cf056df1032dbffb0caf9709c665f536d32680c2d7ad74037c9360b"
EXPECTED_CANONICAL_TEXT_SHA = "512c5a0f1dc44ef4318d2205dd76a7c80af7be797c9450764c51854e40a55c9c"
EXPECTED_SCORER_SHA = "2c06e0a6d4544736f4d619001200a0e2f567b5225e9688d714559c958186a5d4"
EXPECTED_COLLECTION = "official_l21_l30_all_v2"
FROZEN_MANIFEST_PURPOSE = "Frozen 48-row P0/P1 scoring manifest for retrieval-independent Headless vNext."
P3_HEADLESS_CSV = Path(
    r"D:\Official-Dataset\evaluation\queries\p3-round3-benchmark-v1\p3_headless_queries.csv"
)
EXPECTED_ROW_COUNT = 322924
EXPECTED_INDEX_GENERATION = "idx_6baede5b9bc447e099c0004d8428ca7e"
EXPECTED_INDEX_FAMILIES = (
    "qwen_vl_SCANN",
    "image_siglip_so400m_384_SCANN",
    "ocr_BM25",
    "asr_BM25",
    "ocr_dense_SCANN",
    "asr_dense_SCANN",
)
REQUIRED_MANIFEST_COUNTS = {
    "execution_rows": 48,
    "p0_rows": 23,
    "p1_rows": 25,
    "p2_rows": 0,
    "range_scoreable_non_trake": 44,
    "trake_rows": 4,
    "trake_events": 15,
    "video_scoreable": 48,
}
REQUIRED_PROVIDER_PATHS = {
    "qwen_visual": {
        "fields": ("qwen_vl",),
        "encoder_names": ("language_qwen_vl",),
    },
    "siglip_visual": {
        "fields": ("image_siglip_so400m_384",),
        "encoder_names": ("language_siglip_so400m-384",),
    },
    "ocr_sparse_bm25": {"fields": ("ocr_sparse",), "encoder_names": ()},
    "ocr_dense_bge_m3": {"fields": ("ocr_dense",), "encoder_names": ("text_bge_m3",)},
    "asr_sparse_bm25": {"fields": ("asr_sparse",), "encoder_names": ()},
    "asr_dense_bge_m3": {"fields": ("asr_dense",), "encoder_names": ("text_bge_m3",)},
}


def _arm(
    *,
    target_features: list[str],
    ocr_weight: float,
    asr_weight: float,
    ocr_alpha: float,
    asr_alpha: float,
    provider_paths: list[str],
) -> dict[str, Any]:
    return {
        "kind": "vecna_searcher",
        "target_features": target_features,
        "ocr_weight": ocr_weight,
        "asr_weight": asr_weight,
        "ocr_alpha": ocr_alpha,
        "asr_alpha": asr_alpha,
        "top_k": 20,
        "nprobe": 32,
        "temporal_k": 2000,
        "max_interval": 1000,
        "reranking": False,
        "llm_query_expansion": False,
        "yolo_query_rewrite": False,
        "auto_translate": False,
        "en_to_vi_translate": False,
        "include_videos": "",
        "exclude_videos": "",
        "selected": None,
        "shot_clustering": "bypassed",
        "provider_paths": provider_paths,
    }


FROZEN_ARMS = {
    "qwen_only_v1": _arm(
        target_features=["qwen_vl"],
        ocr_weight=0.0,
        asr_weight=0.0,
        ocr_alpha=0.0,
        asr_alpha=0.0,
        provider_paths=["qwen_visual"],
    ),
    "all_fusion_v1": _arm(
        target_features=["qwen_vl", "image_siglip_so400m-384"],
        ocr_weight=0.25,
        asr_weight=0.25,
        ocr_alpha=0.7,
        asr_alpha=0.7,
        provider_paths=list(REQUIRED_PROVIDER_PATHS),
    ),
    "siglip_only_v1": _arm(
        target_features=["image_siglip_so400m-384"],
        ocr_weight=0.0,
        asr_weight=0.0,
        ocr_alpha=0.0,
        asr_alpha=0.0,
        provider_paths=["siglip_visual"],
    ),
    "semantic_evidence_shadow_v1": {
        "kind": "saved_rankings_only",
        "target_features": [],
        "source": "external_saved_evidence_rankings",
        "scorer": "aic51-src/script/score_headless_vnext.py",
        "retrieval_run_required": False,
        "provider_paths": [],
    },
}

FROZEN_REGISTRY = {
    "schema_version": 1,
    "benchmark_id": "headless-main-vnext-p0-p1-v1",
    "base": {
        "repository": "JimmyK300/Vecna",
        "branch": "shot-clustering",
        "commit": EXPECTED_BASE_SHA,
    },
    "issue76_authority": {
        "commit": EXPECTED_ISSUE76_SHA,
        "contract_commit": EXPECTED_CONTRACT_SHA,
        "manifest_path": "benchmark-results/headless-vnext/manifest.json",
        "manifest_sha256": EXPECTED_MANIFEST_SHA,
        "canonical_query_texts_path": "benchmark-results/headless-vnext/canonical-query-texts.json",
        "canonical_query_texts_sha256": EXPECTED_CANONICAL_TEXT_SHA,
        "scorer_path": "aic51-src/script/score_headless_vnext.py",
        "scorer_sha256": EXPECTED_SCORER_SHA,
    },
    "collection_expectation": {
        "name": EXPECTED_COLLECTION,
        "row_count": EXPECTED_ROW_COUNT,
        "index_generation_when_resolvable": EXPECTED_INDEX_GENERATION,
        "index_families": list(EXPECTED_INDEX_FAMILIES),
    },
    "arms": FROZEN_ARMS,
    "provider_audit": {
        "all_fusion_arm": "all_fusion_v1",
        "required_paths": REQUIRED_PROVIDER_PATHS,
        "proof_rule": "each requested field receives at least one search call and one positive-distance hit, and each requested encoder is called",
        "failure_action": "stop before continuing the arm",
    },
    "output_contract": {
        "one_row_per_manifest_query": 48,
        "top_k": 20,
        "ranking_order": "raw Searcher order preserved; serializer adds explicit 1-based rank only",
        "deduplicate_results": False,
        "renumber_after_retrieval": False,
        "scorer_allows_partial": False,
    },
}


class PacketError(RuntimeError):
    """A frozen packet invariant failed."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    try:
        return [json_safe(v) for v in value]
    except TypeError:
        return str(value)


def git_output(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise PacketError(f"git metadata unavailable: git {' '.join(args)}") from exc


def assert_base(root: Path = ROOT) -> dict[str, Any]:
    head = git_output(root, "rev-parse", "HEAD")
    if head != EXPECTED_BASE_SHA:
        raise PacketError(f"frozen Issue #77 base mismatch: {head} != {EXPECTED_BASE_SHA}")
    status = git_output(root, "status", "--porcelain=v1", "--untracked-files=all")
    return {
        "head": head,
        "branch": git_output(root, "branch", "--show-current"),
        "dirty": bool(status),
        "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
        "status_entries": status.splitlines(),
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PacketError(f"cannot load JSON authority: {path}") from exc
    if not isinstance(value, dict):
        raise PacketError(f"JSON authority must be an object: {path}")
    return value


def validate_registry(path: Path = ARMS_PATH) -> dict[str, Any]:
    doc = load_json(path)
    for key in ("schema_version", "benchmark_id", "base", "issue76_authority", "arms"):
        if doc.get(key) != FROZEN_REGISTRY[key]:
            raise PacketError(f"frozen arm registry mismatch at {key}")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "canonical_hash": canonical_json_hash(doc),
        "arms": sorted(doc["arms"]),
    }


def validate_manifest(
    manifest_path: Path = MANIFEST_PATH,
    canonical_path: Path = CANONICAL_TEXT_PATH,
    scorer_path: Path = SCORER_PATH,
) -> dict[str, Any]:
    actual = {
        "manifest": sha256_file(manifest_path),
        "canonical_query_texts": sha256_file(canonical_path),
        "scorer": sha256_file(scorer_path),
    }
    expected = {
        "manifest": EXPECTED_MANIFEST_SHA,
        "canonical_query_texts": EXPECTED_CANONICAL_TEXT_SHA,
        "scorer": EXPECTED_SCORER_SHA,
    }
    if actual != expected:
        raise PacketError(f"#76 authority hash mismatch: actual={actual} expected={expected}")

    manifest = load_json(manifest_path)
    if manifest.get("contract_commit") != EXPECTED_CONTRACT_SHA:
        raise PacketError("manifest is not pinned to accepted Issue #75 contract")
    counts = manifest.get("counts")
    if counts != REQUIRED_MANIFEST_COUNTS:
        raise PacketError(f"manifest count mismatch: {counts} != {REQUIRED_MANIFEST_COUNTS}")
    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != 48:
        raise PacketError("manifest must contain exactly 48 records")
    if any(record.get("operational_phase") == "P2" for record in records):
        raise PacketError("P2 record found in frozen P0/P1 manifest")

    authority = load_json(canonical_path)
    if authority.get("official_dataset_control_commit") != "646ec85c75141bb68078fa94ec26b9a1dbef6d04":
        raise PacketError("canonical query text authority commit mismatch")
    authority_queries = authority.get("queries", {})
    expected_texts = {
        f"{source}::{query_id}": entry
        for source, queries in authority_queries.items()
        for query_id, entry in queries.items()
    }
    if len(expected_texts) != 48:
        raise PacketError("canonical query text authority does not contain 48 queries")
    seen = set()
    for record in records:
        query_id = record.get("canonical_query_id")
        if query_id in seen or query_id not in expected_texts:
            raise PacketError(f"manifest query identity is not one-to-one: {query_id}")
        seen.add(query_id)
        expected_entry = expected_texts[query_id]
        if record.get("query_text") != expected_entry.get("query_text"):
            raise PacketError(f"manifest query text mismatch: {query_id}")
        expected_text_hash = hashlib.sha256(
            str(expected_entry["query_text"]).encode("utf-8")
        ).hexdigest()
        if record.get("query_text_sha256") != expected_text_hash:
            raise PacketError(f"manifest query text hash mismatch: {query_id}")
        if record.get("task_type") != expected_entry.get("task_type"):
            raise PacketError(f"manifest task type mismatch: {query_id}")
        if record.get("operational_phase") not in {"P0", "P1"}:
            raise PacketError(f"manifest contains non-P0/P1 row: {query_id}")
    if seen != set(expected_texts):
        raise PacketError("manifest does not consume every canonical query exactly once")

    return {
        "paths": {
            "manifest": str(manifest_path.resolve()),
            "canonical_query_texts": str(canonical_path.resolve()),
            "scorer": str(scorer_path.resolve()),
        },
        "sha256": actual,
        "counts": counts,
        "canonical_query_ids": sorted(seen),
    }


def p3_normalized_texts(path: Path = P3_HEADLESS_CSV) -> set[str]:
    texts: set[str] = set()
    if not path.exists():
        raise PacketError(f"P3 contamination CSV missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            query = (row.get("query") or "").strip()
            if query:
                texts.add(" ".join(query.split()).casefold())
    if len(texts) != 36:
        raise PacketError(f"P3 contamination CSV has {len(texts)} unique texts, expected 36")
    return texts


def canonical_round_of(record: Mapping[str, Any]) -> str:
    """Round identity is operational_phase + canonical_source_id, never the organizer prefix."""
    phase = str(record.get("operational_phase") or "")
    source = str(record.get("canonical_source_id") or "")
    if phase == "P2" and source == "actual_p2_official":
        return "P2"
    if phase in {"P0", "P1"}:
        return phase
    raise PacketError(
        f"cannot assign canonical round from organizer prefix; "
        f"phase={phase!r} source={source!r} raw={record.get('raw_query_id')!r}"
    )


def validate_extended_manifest(
    manifest_path: Path,
    canonical_path: Path,
    scorer_path: Path = SCORER_PATH,
) -> dict[str, Any]:
    frozen_actual = {
        "manifest": sha256_file(MANIFEST_PATH),
        "canonical_query_texts": sha256_file(CANONICAL_TEXT_PATH),
        "scorer": sha256_file(scorer_path),
    }
    frozen_expected = {
        "manifest": EXPECTED_MANIFEST_SHA,
        "canonical_query_texts": EXPECTED_CANONICAL_TEXT_SHA,
        "scorer": EXPECTED_SCORER_SHA,
    }
    if frozen_actual != frozen_expected:
        raise PacketError(f"frozen 48-row authority mutated: actual={frozen_actual} expected={frozen_expected}")
    frozen = load_json(MANIFEST_PATH)
    if frozen.get("purpose") != FROZEN_MANIFEST_PURPOSE:
        raise PacketError("frozen 48-row purpose string mutated")
    if frozen.get("counts") != REQUIRED_MANIFEST_COUNTS:
        raise PacketError("frozen 48-row counts mutated")

    if manifest_path.resolve() == MANIFEST_PATH.resolve():
        raise PacketError("extended packet must not be the frozen 48-row manifest")
    if sha256_file(manifest_path) == EXPECTED_MANIFEST_SHA:
        raise PacketError("extended packet hash matches frozen 48-row manifest")

    manifest = load_json(manifest_path)
    if manifest.get("purpose") == FROZEN_MANIFEST_PURPOSE:
        raise PacketError("extended packet must not reuse the frozen 48-row purpose string")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise PacketError("extended manifest records must be a list")

    p0 = [r for r in records if r.get("operational_phase") == "P0"]
    p1 = [r for r in records if r.get("operational_phase") == "P1"]
    p2 = [r for r in records if r.get("operational_phase") == "P2"]
    if len(p2) != 30:
        raise PacketError(f"extended packet P2 count {len(p2)} != 30")
    if p0 or p1:
        if len(p0) != 23 or len(p1) != 25 or len(records) != 78:
            raise PacketError(
                f"combined packet mix invalid: n={len(records)} p0={len(p0)} p1={len(p1)} p2={len(p2)}"
            )
    elif len(records) != 30:
        raise PacketError(f"P2-only packet must have 30 rows, got {len(records)}")

    ids = [r.get("canonical_query_id") for r in records]
    if any(not i for i in ids) or len(ids) != len(set(ids)):
        raise PacketError("extended packet has missing or duplicate canonical_query_id")
    provenances = [r.get("vecna_provenance_id") for r in records]
    if any(not i for i in provenances) or len(provenances) != len(set(provenances)):
        raise PacketError("extended packet has missing or duplicate vecna_provenance_id")

    p3_texts = p3_normalized_texts()
    overlap = []
    for record in p2:
        if record.get("canonical_source_id") != "actual_p2_official":
            raise PacketError(f"P2 row missing actual_p2_official source: {record.get('canonical_query_id')}")
        if canonical_round_of(record) != "P2":
            raise PacketError(f"P2 row failed round identity: {record.get('canonical_query_id')}")
        raw = str(record.get("raw_query_id") or "")
        if not raw.startswith("query-p2-"):
            raise PacketError(f"P2 organizer id unexpected: {raw}")
        expected_cid = f"actual_p2_official::{raw}"
        if record.get("canonical_query_id") != expected_cid:
            raise PacketError(
                f"canonical_query_id must be source+organizer id, not prefix-inferred: "
                f"{record.get('canonical_query_id')} != {expected_cid}"
            )
        norm = " ".join(str(record.get("query_text") or "").split()).casefold()
        if norm in p3_texts:
            overlap.append(record.get("canonical_query_id"))
    if overlap:
        raise PacketError(f"P3 text contamination in P2 packet: {overlap}")

    authority = load_json(canonical_path)
    p2_block = (authority.get("queries") or {}).get("actual_p2_official")
    if not isinstance(p2_block, dict) or len(p2_block) != 30:
        raise PacketError("canonical texts missing actual_p2_official 30-query block")
    for record in p2:
        raw = record["raw_query_id"]
        entry = p2_block.get(raw)
        if not entry or entry.get("query_text") != record.get("query_text"):
            raise PacketError(f"P2 query text mismatch: {raw}")
        if entry.get("task_type") != record.get("task_type"):
            raise PacketError(f"P2 task type mismatch: {raw}")

    unscored = [r for r in p2 if not (r.get("scoreability") or {}).get("video")]
    if len(unscored) != 4:
        raise PacketError(f"expected 4 unscoreable P2 rows, got {len(unscored)}")
    for record in unscored:
        if record.get("accepted_video_id"):
            raise PacketError(f"unscoreable P2 row has video: {record.get('canonical_query_id')}")
        if record.get("accepted_ranges"):
            raise PacketError(f"unscoreable P2 row has ranges: {record.get('canonical_query_id')}")

    return {
        "paths": {
            "manifest": str(manifest_path.resolve()),
            "canonical_query_texts": str(canonical_path.resolve()),
            "scorer": str(scorer_path.resolve()),
        },
        "frozen_sha256": frozen_actual,
        "extended": True,
        "counts": {
            "execution_rows": len(records),
            "p0_rows": len(p0),
            "p1_rows": len(p1),
            "p2_rows": len(p2),
            "p2_unscoreable": len(unscored),
        },
        "canonical_query_ids": sorted(ids),
    }


def load_config(path: Path) -> dict[str, Any]:
    try:
        import yaml

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ImportError, AttributeError) as exc:
        raise PacketError(f"cannot load workspace config: {path}") from exc
    except Exception as exc:
        raise PacketError(f"invalid workspace config: {path}") from exc
    if not isinstance(value, dict):
        raise PacketError(f"workspace config must be a YAML object: {path}")
    return value


def nested(config: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = config
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            return default
        value = value[key]
    return value


def benchmark_config_audit(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    collection = nested(config, "backends", "search", "collection")
    if collection != EXPECTED_COLLECTION:
        raise PacketError(
            f"workspace collection mismatch: {collection!r} != {EXPECTED_COLLECTION!r}"
        )

    language_models = nested(config, "searcher", "language_models", default={}) or {}
    required_models = {
        "language_qwen_vl": ("qwen_vl", "qwen_vl_embedding", "Qwen/Qwen3-VL-Embedding-2B"),
        "language_siglip_so400m-384": (
            "image_siglip_so400m-384",
            "image_siglip",
            None,
        ),
        "text_bge_m3": ("ocr_dense|asr_dense", "text_embedding", "BAAI/bge-m3"),
    }
    model_audit = {}
    for name, (target, model, pretrained) in required_models.items():
        entry = language_models.get(name)
        if not isinstance(entry, Mapping):
            raise PacketError(f"required searcher model missing: {name}")
        targets = list(entry.get("target") or [])
        if target == "ocr_dense|asr_dense":
            if set(targets) != {"ocr_dense", "asr_dense"}:
                raise PacketError(f"BGE target fields mismatch: {targets}")
        elif targets != [target]:
            raise PacketError(f"{name} target fields mismatch: {targets}")
        if entry.get("model") != model:
            raise PacketError(f"{name} model mismatch: {entry.get('model')!r}")
        if pretrained and entry.get("pretrained_model") != pretrained:
            raise PacketError(f"{name} pretrained model mismatch")
        model_audit[name] = {"target": targets, "model": entry.get("model")}

    ocr = nested(config, "searcher", "ocr", default={}) or {}
    asr = nested(config, "searcher", "asr", default={}) or {}
    if not ocr.get("enable") or not asr.get("enable"):
        raise PacketError("OCR and ASR must be enabled for the frozen all_fusion arm")
    if ocr.get("ocr_field", "ocr_sparse") != "ocr_sparse":
        raise PacketError("OCR sparse field mismatch")
    if asr.get("asr_field", "asr_sparse") != "asr_sparse":
        raise PacketError("ASR sparse field mismatch")

    overrides = {
        "searcher.ocr.ocr_dense_field": "ocr_dense",
        "searcher.asr.asr_dense_field": "asr_dense",
        "searcher.reranker.enable": False,
        "searcher.llm.enable": False,
        "searcher.yolo.enable": False,
        "searcher.ocr.hybrid_alpha": None,
        "searcher.asr.hybrid_alpha": None,
    }
    return {
        "config_path": str(config_path.resolve()),
        "config_sha256": sha256_file(config_path),
        "collection": collection,
        "models": model_audit,
        "sparse_fields": {"ocr": "ocr_sparse", "asr": "asr_sparse"},
        "benchmark_local_overrides": overrides,
        "root_config_rewriting_enabled": {
            "reranker": bool(nested(config, "searcher", "reranker", "enable", default=False)),
            "llm": bool(nested(config, "searcher", "llm", "enable", default=False)),
            "yolo": bool(nested(config, "searcher", "yolo", "enable", default=False)),
        },
    }


def runtime_versions(requested_device: str = "cuda") -> dict[str, Any]:
    packages: dict[str, Any] = {}
    for package in ("torch", "pymilvus", "PyYAML", "numpy", "sentence-transformers", "transformers"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    device: dict[str, Any] = {"requested": requested_device, "cuda_available": None}
    try:
        import torch

        device["cuda_available"] = bool(torch.cuda.is_available())
        device["torch_device_count"] = int(torch.cuda.device_count())
        if device["cuda_available"]:
            device["cuda_name"] = torch.cuda.get_device_name(0)
    except Exception as exc:
        device["error"] = str(exc)
    return {"packages": packages, "device": device}


def _count_from_response(value: Any) -> int:
    if isinstance(value, Mapping):
        for key in ("count(*)", "count", "num_entities"):
            if key in value:
                return int(value[key])
    data = getattr(value, "data", None)
    if data is not None:
        return _count_from_response(data)
    if isinstance(value, (list, tuple)) and value:
        return _count_from_response(value[0])
    if isinstance(value, str):
        try:
            return _count_from_response(ast.literal_eval(value))
        except (SyntaxError, ValueError):
            pass
    raise PacketError(f"could not parse Milvus count response: {value!r}")


def _collection_description(client: Any, collection: str) -> dict[str, Any]:
    try:
        if not client.has_collection(collection):
            raise PacketError(f"Milvus collection does not exist: {collection}")
        client.load_collection(collection)
        count = _count_from_response(client.query(collection, output_fields=["count(*)"]))
        description = client.describe_collection(collection)
        indexes = list(client.list_indexes(collection))
    except PacketError:
        raise
    except Exception as exc:
        raise PacketError(f"Milvus collection preflight failed: {exc}") from exc

    fields = []
    for field in description.get("fields", []) if isinstance(description, Mapping) else []:
        if isinstance(field, Mapping):
            fields.append(str(field.get("name") or field.get("field_name")))
    missing_fields = sorted(
        set(("frame_id", "qwen_vl", "image_siglip_so400m_384", "ocr_sparse", "asr_sparse", "ocr_dense", "asr_dense"))
        - set(fields)
    )
    missing_indexes = sorted(set(EXPECTED_INDEX_FAMILIES) - set(str(x) for x in indexes))
    if count != EXPECTED_ROW_COUNT:
        raise PacketError(f"Milvus row count mismatch: {count} != {EXPECTED_ROW_COUNT}")
    if missing_fields:
        raise PacketError(f"Milvus required fields missing: {missing_fields}")
    if missing_indexes:
        raise PacketError(f"Milvus required indexes missing: {missing_indexes}")
    return {
        "status": "live_verified",
        "collection": collection,
        "row_count": count,
        "fields": sorted(fields),
        "indexes": sorted(str(x) for x in indexes),
        "missing_fields": missing_fields,
        "missing_indexes": missing_indexes,
        "description": json_safe(description),
    }


def local_index_generation(root: Path, collection: str) -> dict[str, Any]:
    path = root / "provenance" / "indexes" / f"{collection}.json"
    if not path.exists():
        return {
            "status": "unavailable",
            "index_generation_id": None,
            "reason": "local index-generation registry is absent",
        }
    try:
        registry = load_json(path)
    except PacketError as exc:
        raise PacketError(f"invalid local index-generation registry: {path}") from exc
    current_id = registry.get("current_index_generation_id")
    generations = registry.get("generations") or []
    current = next(
        (item for item in generations if item.get("index_generation_id") == current_id),
        None,
    )
    if not current:
        return {
            "status": "unavailable",
            "index_generation_id": None,
            "reason": "registry has no resolvable current generation",
        }
    if current_id != EXPECTED_INDEX_GENERATION:
        raise PacketError(
            f"local index generation mismatch: {current_id} != {EXPECTED_INDEX_GENERATION}"
        )
    return {
        "status": "resolved",
        "index_generation_id": current_id,
        "feature_fields": current.get("feature_fields", []),
    }


def live_collection_preflight(root: Path = ROOT, collection: str = EXPECTED_COLLECTION) -> dict[str, Any]:
    try:
        from pymilvus import MilvusClient
    except ImportError as exc:
        raise PacketError("pymilvus is required for --live collection preflight") from exc
    result = _collection_description(MilvusClient(), collection)
    result["index_generation"] = local_index_generation(root, collection)
    return result


class ProviderAudit:
    """Trace provider encoders and Milvus field searches for one frozen call."""

    def __init__(self, required_paths: Mapping[str, Mapping[str, Any]] | None = None):
        self.required_paths = required_paths or REQUIRED_PROVIDER_PATHS
        self.encoder_calls: dict[str, int] = {}
        self.search_calls: dict[str, int] = {}
        self.positive_hits: dict[str, int] = {}

    @staticmethod
    def canonical_field(field: Any) -> str:
        return str(field or "").replace("-", "_")

    def record_encoder(self, name: str) -> None:
        self.encoder_calls[name] = self.encoder_calls.get(name, 0) + 1

    def record_search(self, field: str, hits: int, positive_hits: int) -> None:
        field = self.canonical_field(field)
        self.search_calls[field] = self.search_calls.get(field, 0) + 1
        self.positive_hits[field] = self.positive_hits.get(field, 0) + int(positive_hits)

    def report(self, requested_paths: list[str]) -> dict[str, Any]:
        paths = {}
        for path_name in requested_paths:
            spec = self.required_paths[path_name]
            fields = [self.canonical_field(field) for field in spec["fields"]]
            encoders = list(spec["encoder_names"])
            field_calls = sum(self.search_calls.get(field, 0) for field in fields)
            positive_hits = sum(self.positive_hits.get(field, 0) for field in fields)
            encoder_calls = sum(self.encoder_calls.get(name, 0) for name in encoders)
            paths[path_name] = {
                "fields": fields,
                "encoder_names": encoders,
                "search_calls": field_calls,
                "positive_distance_hits": positive_hits,
                "encoder_calls": encoder_calls,
                "nonzero": bool(field_calls and positive_hits and (not encoders or encoder_calls)),
            }
        return {
            "requested_paths": requested_paths,
            "paths": paths,
            "all_requested_nonzero": all(item["nonzero"] for item in paths.values()),
            "encoder_calls": dict(sorted(self.encoder_calls.items())),
            "search_calls": dict(sorted(self.search_calls.items())),
            "positive_distance_hits": dict(sorted(self.positive_hits.items())),
        }

    def assert_requested(self, requested_paths: list[str]) -> dict[str, Any]:
        report = self.report(requested_paths)
        if not report["all_requested_nonzero"]:
            missing = [name for name, item in report["paths"].items() if not item["nonzero"]]
            raise PacketError(f"provider audit failed; missing nonzero paths: {missing}")
        return report


def _iter_hits(response: Any):
    if response is None:
        return
    try:
        for group in response:
            try:
                for hit in group:
                    yield hit
            except TypeError:
                yield group
    except TypeError:
        return


def _hit_distance(hit: Any) -> float | None:
    try:
        value = hit["distance"]
    except (KeyError, TypeError, IndexError):
        value = getattr(hit, "distance", None)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def instrument_searcher(searcher: Any, audit: ProviderAudit) -> None:
    """Attach reversible, in-process tracing to the existing Searcher object."""

    for name, entry in getattr(searcher, "_extractors", {}).items():
        extractor = entry.get("feature_extractor") if isinstance(entry, Mapping) else None
        method = getattr(extractor, "get_text_features", None)
        if extractor is None or not callable(method):
            continue

        def traced_encoder(*args: Any, _method=method, _name=name, **kwargs: Any):
            audit.record_encoder(str(_name))
            return _method(*args, **kwargs)

        extractor.get_text_features = traced_encoder

    database = getattr(searcher, "_database", None)
    original_search = getattr(database, "search", None)
    if database is None or not callable(original_search):
        raise PacketError("Searcher database has no traceable search method")

    def traced_search(*args: Any, **kwargs: Any):
        field = kwargs.get("anns_field")
        if field is None and len(args) >= 5:
            field = args[4]
        result = original_search(*args, **kwargs)
        hits = list(_iter_hits(result))
        positive = sum(1 for hit in hits if (_hit_distance(hit) or 0.0) > 0.0)
        audit.record_search(str(field), len(hits), positive)
        return result

    database.search = traced_search


def apply_benchmark_config(config_path: Path) -> dict[str, Any]:
    """Overlay frozen benchmark settings on GlobalConfig in this process only."""

    if str(AIC_ROOT) not in sys.path:
        sys.path.insert(0, str(AIC_ROOT))
    from aic51.packages.config import GlobalConfig

    original_get = GlobalConfig.get
    overrides = {
        ("searcher", "ocr", "ocr_field"): "ocr_sparse",
        ("searcher", "ocr", "ocr_dense_field"): "ocr_dense",
        ("searcher", "asr", "asr_field"): "asr_sparse",
        ("searcher", "asr", "asr_dense_field"): "asr_dense",
        ("searcher", "reranker", "enable"): False,
        ("searcher", "llm"): {"enable": False},
        ("searcher", "llm", "enable"): False,
        ("searcher", "yolo", "enable"): False,
    }

    def benchmark_get(*keys: str) -> Any:
        key = tuple(keys)
        if key in overrides:
            return overrides[key]
        return original_get(*keys)

    GlobalConfig.get = staticmethod(benchmark_get)
    return {
        "config_path": str(config_path.resolve()),
        "overrides": {".".join(key): value for key, value in overrides.items()},
        "reranker_off": True,
        "llm_query_expansion_off": True,
        "translation_off": True,
        "yolo_query_rewrite_off": True,
    }


def _frame_parts(source_frame_id: Any) -> tuple[str, Any]:
    raw = str(source_frame_id or "")
    if "#" not in raw:
        return "", raw
    video, frame = raw.rsplit("#", 1)
    try:
        return video, int(frame)
    except ValueError:
        return video, frame


def _timeline_frames(values: Any) -> list[Any]:
    if not isinstance(values, (list, tuple)):
        return []
    out = []
    for value in values:
        _, frame = _frame_parts(value)
        if isinstance(frame, int):
            out.append(frame)
    return out


def normalize_result(raw: Mapping[str, Any], rank: int, arm_name: str) -> dict[str, Any]:
    entity = raw.get("entity") if isinstance(raw.get("entity"), Mapping) else raw
    source_frame_id = entity.get("frame_id") or raw.get("frame_id") or raw.get("id")
    video_id, frame_id = _frame_parts(source_frame_id)
    result: dict[str, Any] = {
        "rank": rank,
        "video_id": video_id,
        "frame_id": frame_id,
        "source_frame_id": str(source_frame_id or ""),
        "score": json_safe(raw.get("distance")),
        "distance": json_safe(raw.get("distance")),
        "scores": json_safe(raw.get("scores", {})),
        "arm": arm_name,
    }
    timeline = _timeline_frames(raw.get("time_line", raw.get("timeline")))
    if timeline:
        result["time_line"] = timeline
        result["time_line_frame_ids"] = [str(value) for value in raw.get("time_line", raw.get("timeline"))]
    for key in ("start_frame", "end_frame"):
        if key in raw:
            result[key] = json_safe(raw[key])
        elif key in entity:
            result[key] = json_safe(entity[key])
    if isinstance(raw.get("time_line_scores"), list):
        result["time_line_scores"] = json_safe(raw["time_line_scores"])
    return result


def convert_search_response(response: Mapping[str, Any], arm_name: str, top_k: int) -> list[dict[str, Any]]:
    raw_results = response.get("results")
    if not isinstance(raw_results, list):
        raise PacketError("Searcher response has no results list")
    if len(raw_results) > top_k:
        raise PacketError(f"Searcher returned {len(raw_results)} results above frozen top-K {top_k}")
    if any(not isinstance(raw, Mapping) for raw in raw_results):
        raise PacketError("Searcher response contains a non-object result")
    return [normalize_result(raw, index, arm_name) for index, raw in enumerate(raw_results, start=1)]


def invoke_frozen_search(
    searcher: Any,
    query_text: str,
    arm_name: str,
    *,
    visual_query_translate: bool = False,
    include_videos: str = "",
) -> Mapping[str, Any]:
    """Invoke a frozen arm with explicit, opt-in diagnostic overrides.

    The default remains the Issue #77 frozen call.  The override is deliberately
    opt-in and only changes the visual CLIP/SigLIP query text from Vietnamese to
    English or applies the Searcher's native include-video filter; it does not
    alter the arm registry or the OCR/ASR query paths.
    """
    if arm_name not in FROZEN_ARMS or FROZEN_ARMS[arm_name]["kind"] != "vecna_searcher":
        raise PacketError(f"{arm_name} is not a direct retrieval arm")
    arm = FROZEN_ARMS[arm_name]
    response = searcher.search_multimodal(
        query_text,
        0,
        arm["top_k"],
        arm["target_features"],
        nprobe=arm["nprobe"],
        temporal_k=arm["temporal_k"],
        ocr_weight=arm["ocr_weight"],
        asr_weight=arm["asr_weight"],
        ocr_alpha=arm["ocr_alpha"],
        asr_alpha=arm["asr_alpha"],
        max_interval=arm["max_interval"],
        selected=None,
        auto_translate=visual_query_translate,
        en_to_vi_translate=False,
        include_videos=include_videos,
        exclude_videos="",
    )
    if not isinstance(response, Mapping):
        raise PacketError("Searcher returned a non-object response")
    return response


def _load_scorer(path: Path = SCORER_PATH):
    spec = importlib.util.spec_from_file_location("headless_vnext_scorer", path)
    if spec is None or spec.loader is None:
        raise PacketError(f"cannot load #76 scorer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_saved_rankings(
    rankings_path: Path,
    manifest_path: Path = MANIFEST_PATH,
    scorer_path: Path = SCORER_PATH,
) -> dict[str, Any]:
    scorer = _load_scorer(scorer_path)
    manifest = load_json(manifest_path)
    rankings = scorer.load_rankings(rankings_path)
    rows, summary = scorer.score(manifest, rankings, allow_partial=False)
    if len(rows) != REQUIRED_MANIFEST_COUNTS["execution_rows"]:
        raise PacketError(f"saved rankings scored {len(rows)} rows instead of 48")
    return {
        "status": "scorer_compatible",
        "rankings_path": str(rankings_path.resolve()),
        "query_rows": len(rows),
        "summary": summary,
    }


def preflight(
    arm_name: str,
    *,
    root: Path = ROOT,
    config_path: Path | None = None,
    live: bool = False,
    requested_device: str = "cuda",
    extended_manifest: Path | None = None,
    canonical_texts: Path | None = None,
    skip_base_pin: bool = False,
) -> dict[str, Any]:
    if arm_name not in FROZEN_ARMS:
        raise PacketError(f"unknown arm: {arm_name}")
    if FROZEN_ARMS[arm_name]["kind"] != "vecna_searcher":
        raise PacketError(f"{arm_name} is a comparison/shadow arm, not a direct retrieval arm")
    if skip_base_pin:
        head = git_output(root, "rev-parse", "HEAD")
        status = git_output(root, "status", "--porcelain=v1", "--untracked-files=all")
        base = {
            "head": head,
            "branch": git_output(root, "branch", "--show-current"),
            "dirty": bool(status),
            "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
            "status_entries": status.splitlines(),
            "pin_skipped": True,
        }
    else:
        base = assert_base(root)
    if extended_manifest is not None:
        if canonical_texts is None:
            raise PacketError("--extended-manifest requires --canonical-texts")
        manifest = validate_extended_manifest(extended_manifest, canonical_texts)
    else:
        manifest = validate_manifest()
    registry = validate_registry()
    config_audit = benchmark_config_audit(config_path or root / "config.yaml")
    collection = (
        live_collection_preflight(root)
        if live
        else {
            "status": "not_live_checked",
            "collection": EXPECTED_COLLECTION,
            "row_count": None,
            "index_families": list(EXPECTED_INDEX_FAMILIES),
        }
    )
    runtime = runtime_versions(requested_device)
    return {
        "schema_version": 1,
        "status": "preflight_pass",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "arm": arm_name,
        "arm_parameters": FROZEN_ARMS[arm_name],
        "base": base,
        "authority": manifest,
        "arm_registry": registry,
        "config": config_audit,
        "collection": collection,
        "runtime": runtime,
        "provider_audit": {
            "status": "deferred_to_first_frozen_runtime_call",
            "required_paths": list(FROZEN_ARMS[arm_name]["provider_paths"]),
            "nonzero_contribution_proof": False,
            "stop_rule": "all_fusion_v1 must pass ProviderAudit before the runner continues past its first query",
        },
        "scope": {
            "models_loaded": False,
            "retrieval_queries_executed": 0,
            "real_48_query_benchmark_executed": False,
            "extended_packet": bool(extended_manifest),
            "post_result_tuning": False,
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _translation_chunks(text: str, max_chars: int = 450) -> list[str]:
    """Split oversized external-translation inputs without splitting words."""
    chunks = []
    remaining = text.strip()
    while len(remaining) > max_chars:
        cut = max(
            remaining.rfind("\n", 0, max_chars + 1),
            remaining.rfind(" ", 0, max_chars + 1),
        )
        if cut <= 0:
            cut = max_chars
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def install_experimental_visual_translation() -> tuple[Any, Any, dict[str, int]]:
    """Install a deterministic-in-process VI->EN translator for the diagnostic run.

    The production utility currently uses GoogleTranslator, which returned HTTP
    500 for Vietnamese in this environment, and the temporary MyMemory fallback
    hit its request quota.  The frozen arm remains untouched; this explicit
    diagnostic uses a local fixed translation model and fails closed on errors
    instead of silently mixing translated and untranslated queries.
    """
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    from aic51.packages.search import utils as search_utils

    previous = search_utils.translate_vi_to_en_with_status
    translation_model_id = "Helsinki-NLP/opus-mt-vi-en"
    tokenizer = AutoTokenizer.from_pretrained(translation_model_id)
    translator = AutoModelForSeq2SeqLM.from_pretrained(translation_model_id)
    translator.eval()
    stats = {"calls": 0, "successes": 0, "failures": 0}

    @lru_cache(maxsize=1024)
    def translate_chunk(chunk: str) -> str:
        stats["calls"] += 1
        encoded = tokenizer(
            [chunk],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        with torch.no_grad():
            generated = translator.generate(
                **encoded,
                max_new_tokens=256,
                num_beams=4,
                do_sample=False,
            )
        translated = tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
        if search_utils._is_translation_error(translated):
            raise ValueError(f"local translation model returned error/invalid response: '{translated}'")
        stats["successes"] += 1
        return translated

    @lru_cache(maxsize=1024)
    def translate_inner(inner_text: str) -> str:
        return " ".join(translate_chunk(chunk) for chunk in _translation_chunks(inner_text))

    def translate_with_status(text: str) -> tuple[str, bool]:
        if not text or not text.strip():
            return text, True
        stripped = text.strip()
        is_quoted = stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2
        inner_text = stripped[1:-1].strip() if is_quoted else stripped
        if not inner_text:
            return text, True
        try:
            translated = translate_inner(inner_text)
            if not translated:
                raise ValueError("local translation model returned empty text")
            if is_quoted:
                translated = f'"{translated.strip(chr(34))}"'
            return translated, True
        except Exception as exc:
            stats["failures"] += 1
            raise RuntimeError(f"experimental VI->EN translation failed: {exc}") from exc

    search_utils.translate_vi_to_en_with_status = translate_with_status
    return search_utils, previous, stats


def run_arm(
    arm_name: str,
    output_path: Path,
    *,
    root: Path = ROOT,
    config_path: Path | None = None,
    overwrite: bool = False,
    device_name: str = "cuda",
    visual_query_translate: bool = False,
    extended_manifest: Path | None = None,
    canonical_texts: Path | None = None,
    skip_base_pin: bool = False,
) -> dict[str, Any]:
    if arm_name not in FROZEN_ARMS or FROZEN_ARMS[arm_name]["kind"] != "vecna_searcher":
        raise PacketError(f"{arm_name} is not a direct retrieval arm")
    if output_path.exists() and not overwrite and extended_manifest is None:
        raise PacketError(f"refusing to overwrite existing output: {output_path}")

    if device_name not in {"cuda", "cpu"}:
        raise PacketError(f"unsupported execution device: {device_name}")
    frozen = preflight(
        arm_name,
        root=root,
        config_path=config_path,
        live=True,
        requested_device=device_name,
        extended_manifest=extended_manifest,
        canonical_texts=canonical_texts,
        skip_base_pin=skip_base_pin or extended_manifest is not None,
    )
    runtime = frozen["runtime"]
    if device_name == "cuda" and not runtime["device"].get("cuda_available"):
        raise PacketError("qwen/fusion friend arms require CUDA; refusing CPU fallback")
    config_path = config_path or root / "config.yaml"
    benchmark_config = apply_benchmark_config(config_path)
    if visual_query_translate:
        benchmark_config = dict(benchmark_config)
        benchmark_config["translation_off"] = False
        benchmark_config["visual_query_translation"] = "vi_to_en:Helsinki-NLP/opus-mt-vi-en"
    if str(AIC_ROOT) not in sys.path:
        sys.path.insert(0, str(AIC_ROOT))
    import torch
    from aic51.packages.search.searcher import Searcher

    # The packet explicitly bypasses optional clustering/diversification.  A
    # missing path is used instead of changing SegmentClustering production code.
    segment_map_key = "SEGMENT_MAP_PATH"
    previous_segment_map = os.environ.get(segment_map_key)
    os.environ[segment_map_key] = str(root / ".headless-vnext-no-segment-map")
    translation_state = None
    translation_stats = None
    audit = ProviderAudit()
    manifest_path = extended_manifest or MANIFEST_PATH
    manifest = load_json(manifest_path)
    expected_rows = len(manifest["records"])
    started = datetime.now(timezone.utc).isoformat()
    run_path = output_path.with_suffix(".run.json")
    existing_ids: set[str] = set()
    if output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            qid = row.get("canonical_query_id")
            if not qid:
                raise PacketError(f"existing ranking row missing canonical_query_id in {output_path}")
            if qid in existing_ids:
                raise PacketError(f"duplicate canonical_query_id in existing rankings: {qid}")
            existing_ids.add(qid)
    manifest_ids = [record["canonical_query_id"] for record in manifest["records"]]
    extra = existing_ids.difference(manifest_ids)
    if extra:
        raise PacketError(f"existing rankings contain ids not in manifest: {sorted(extra)}")
    run_metadata: dict[str, Any] = {
        "status": "running",
        "started_at": started,
        "output_path": str(output_path.resolve()),
        "arm": arm_name,
        "arm_parameters": FROZEN_ARMS[arm_name],
        "execution_overrides": {
            "visual_query_translation": (
                {"direction": "vi_to_en", "provider": "Helsinki-NLP/opus-mt-vi-en"}
                if visual_query_translate
                else None
            ),
            "frozen_arm_registry_unchanged": True,
            "extended_manifest": str(manifest_path) if extended_manifest else None,
        },
        "translation_stats": translation_stats,
        "preflight": frozen,
        "benchmark_config": benchmark_config,
        "records_written": len(existing_ids),
        "resumed_existing_rows": len(existing_ids),
        "provider_audit": {"status": "pending"},
        "real_48_query_benchmark_executed": extended_manifest is None,
        "post_result_tuning": False,
    }
    write_json(run_path, run_metadata)
    try:
        if visual_query_translate:
            translation_state = install_experimental_visual_translation()
            translation_stats = translation_state[2]
        searcher = Searcher(EXPECTED_COLLECTION, torch.device(device_name))
        expected_targets = FROZEN_ARMS[arm_name]["target_features"]
        if any(target not in searcher.target_features for target in expected_targets):
            raise PacketError(
                f"Searcher does not expose frozen target features: expected={expected_targets} "
                f"available={searcher.target_features}"
            )
        if getattr(searcher, "_reranker", None) is not None:
            raise PacketError("benchmark-local reranker override failed; refusing run")
        if getattr(searcher, "_llm_expander", None) is not None:
            raise PacketError("benchmark-local LLM override failed; refusing run")

        audit = ProviderAudit()
        instrument_searcher(searcher, audit)
        records_written = len(existing_ids)
        run_metadata["translation_stats"] = translation_stats
        write_json(run_path, run_metadata)
        provider_report = None
        with output_path.open("a" if existing_ids else "w", encoding="utf-8", newline="\n") as output:
            for record in manifest["records"]:
                if record["canonical_query_id"] in existing_ids:
                    continue
                response = invoke_frozen_search(
                    searcher,
                    record["query_text"],
                    arm_name,
                    visual_query_translate=visual_query_translate,
                )
                if provider_report is None:
                    provider_report = audit.assert_requested(FROZEN_ARMS[arm_name]["provider_paths"])
                    provider_report["status"] = "verified_on_first_frozen_call"
                results = convert_search_response(
                    response,
                    arm_name,
                    FROZEN_ARMS[arm_name]["top_k"],
                )
                saved = {
                    "canonical_query_id": record["canonical_query_id"],
                    "vecna_provenance_id": record["vecna_provenance_id"],
                    "query_text": record["query_text"],
                    "task_type": record["task_type"],
                    "operational_phase": record["operational_phase"],
                    "arm": arm_name,
                    "execution_variant": "visual_query_vi_to_en" if visual_query_translate else "frozen",
                    "results": results,
                }
                output.write(json.dumps(json_safe(saved), ensure_ascii=False, sort_keys=True) + "\n")
                output.flush()
                records_written += 1
                run_metadata["records_written"] = records_written
                run_metadata["provider_audit"] = provider_report
                write_json(run_path, run_metadata)
        if records_written != expected_rows:
            raise PacketError(f"runner wrote {records_written} rows instead of {expected_rows}")
        if extended_manifest is None:
            compatible = validate_saved_rankings(output_path)
        else:
            compatible = {
                "status": "deferred_to_p0_p1_p2_wrapper",
                "rankings_path": str(output_path.resolve()),
                "query_rows": records_written,
            }
        run_metadata.update(
            {
                "status": "completed",
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "records_written": records_written,
                "provider_audit": provider_report,
                "scorer_validation": compatible,
                "output_sha256": sha256_file(output_path),
                "run_metadata_sha256": None,
            }
        )
        run_metadata["translation_stats"] = translation_stats
        write_json(run_path, run_metadata)
        run_metadata["run_metadata_sha256"] = sha256_file(run_path)
        write_json(run_path, run_metadata)
        return run_metadata
    except Exception as exc:
        run_path = output_path.with_suffix(".run.json")
        failure = {
            "status": "failed",
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "arm": arm_name,
            "error": str(exc),
            "records_written": locals().get("records_written", 0),
            "provider_audit": audit.report(FROZEN_ARMS[arm_name]["provider_paths"]),
            "translation_stats": translation_stats,
            "real_48_query_benchmark_executed": False,
            "post_result_tuning": False,
        }
        write_json(run_path, failure)
        if isinstance(exc, PacketError):
            raise
        raise PacketError(str(exc)) from exc
    finally:
        if translation_state is not None:
            translation_state[0].translate_vi_to_en_with_status = translation_state[1]
        if previous_segment_map is None:
            os.environ.pop(segment_map_key, None)
        else:
            os.environ[segment_map_key] = previous_segment_map


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue #77 Headless-vNext bounded retrieval packet")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--validate", action="store_true")
    parser.add_argument("--arm", choices=sorted(FROZEN_ARMS))
    parser.add_argument("--live", action="store_true", help="connect to Milvus for --preflight")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--rankings", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--translate-visual-query",
        action="store_true",
        help="experimental: translate Vietnamese query text to English for CLIP/SigLIP only",
    )
    parser.add_argument(
        "--extended-manifest",
        type=Path,
        help="Additive P2 or P0/P1/P2 packet. Does not rewrite frozen 48-row SHA files.",
    )
    parser.add_argument(
        "--canonical-texts",
        type=Path,
        help="Canonical query texts for --extended-manifest.",
    )
    parser.add_argument(
        "--skip-base-pin",
        action="store_true",
        help="Skip frozen HEAD pin. Implied by --extended-manifest.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.extended_manifest and not args.canonical_texts:
            raise PacketError("--extended-manifest requires --canonical-texts")
        if args.canonical_texts and not args.extended_manifest:
            raise PacketError("--canonical-texts requires --extended-manifest")
        if args.dry_run:
            if args.skip_base_pin or args.extended_manifest:
                head = git_output(ROOT, "rev-parse", "HEAD")
                status = git_output(ROOT, "status", "--porcelain=v1", "--untracked-files=all")
                base = {
                    "head": head,
                    "branch": git_output(ROOT, "branch", "--show-current"),
                    "dirty": bool(status),
                    "pin_skipped": True,
                }
            else:
                base = assert_base()
            manifest = (
                validate_extended_manifest(args.extended_manifest, args.canonical_texts)
                if args.extended_manifest
                else validate_manifest()
            )
            registry = validate_registry()
            result = {
                "status": "dry_pass",
                "base": base,
                "authority": manifest,
                "arm_registry": registry,
                "arms": FROZEN_ARMS,
                "scope": {
                    "models_loaded": False,
                    "retrieval_queries_executed": 0,
                    "real_48_query_benchmark_executed": False,
                    "extended_packet": bool(args.extended_manifest),
                },
            }
        elif args.preflight:
            if not args.arm:
                raise PacketError("--arm is required for --preflight")
            result = preflight(
                args.arm,
                config_path=args.config,
                live=args.live,
                requested_device=args.device,
                extended_manifest=args.extended_manifest,
                canonical_texts=args.canonical_texts,
                skip_base_pin=args.skip_base_pin or args.extended_manifest is not None,
            )
        elif args.validate:
            if not args.rankings:
                raise PacketError("--rankings is required for --validate")
            if args.extended_manifest:
                validate_extended_manifest(args.extended_manifest, args.canonical_texts)
                result = {
                    "status": "deferred_to_p0_p1_p2_wrapper",
                    "rankings_path": str(args.rankings.resolve()),
                }
            else:
                validate_manifest()
                result = validate_saved_rankings(args.rankings)
        else:
            if not args.arm:
                raise PacketError("--arm is required for --run")
            if not args.output:
                raise PacketError("--output is required for --run")
            if args.translate_visual_query and args.arm != "all_fusion_v1":
                raise PacketError("--translate-visual-query is only supported for all_fusion_v1")
            result = run_arm(
                args.arm,
                args.output,
                config_path=args.config,
                overwrite=args.overwrite,
                device_name=args.device,
                visual_query_translate=args.translate_visual_query,
                extended_manifest=args.extended_manifest,
                canonical_texts=args.canonical_texts,
                skip_base_pin=args.skip_base_pin or args.extended_manifest is not None,
            )
        if args.output and not args.run:
            write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except PacketError as exc:
        print(f"HEADLESS-VNEXT STOP: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
