#!/usr/bin/env python3
"""Read-only BGE-M3 dense visibility on the existing frozen 38-row sample.

Uses only an already cached, explicitly pinned model. The exact pinned main
encoding and text-search methods are selected by AST. No Searcher or
MilvusDatabase construction, visual model, new extraction, index writes,
query rewrite, ground-truth access, or model download is permitted.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from collect_sparse_visibility import digest, digest_json, dump, load_main_text_harness, metadata_json


TEXT_EMBEDDING_SHA256 = "ec26570cf87a9d3e6a4e2d481531a46f470e0a7f70f220c1c5cb15da126d3f01"


def file_sha(path):
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def checkpoint_parameter_audit(model, snapshot, use_safetensors, torch):
    """Compare every active encoder parameter to the exact cached checkpoint."""
    keys_by_file = {}
    state = None
    if use_safetensors:
        from safetensors import safe_open
        index = snapshot / "model.safetensors.index.json"
        if index.is_file():
            mapping = json.loads(index.read_text(encoding="utf-8"))["weight_map"]
            keys_by_file = {key: snapshot / file for key, file in mapping.items()}
        else:
            checkpoint = snapshot / "model.safetensors"
            with safe_open(str(checkpoint), framework="pt", device="cpu") as handle:
                keys_by_file = {key: checkpoint for key in handle.keys()}
    else:
        checkpoint = snapshot / "pytorch_model.bin"
        if not checkpoint.is_file():
            raise ValueError("Only the observed monolithic PyTorch checkpoint is supported")
        state = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
        keys_by_file = {key: checkpoint for key in state}
    checked = []
    for name, parameter in model.named_parameters():
        if name.startswith("pooler."):
            continue
        candidates = [key for key in (name, "roberta." + name) if key in keys_by_file]
        if len(candidates) != 1:
            raise ValueError(f"Active encoder parameter lacks unique checkpoint mapping: {name}")
        key = candidates[0]
        path = keys_by_file[key]
        if use_safetensors:
            with safe_open(str(path), framework="pt", device="cpu") as handle:
                expected = handle.get_tensor(key)
                equal = tuple(parameter.shape) == tuple(expected.shape) and torch.equal(parameter.detach().cpu(), expected.to(dtype=parameter.dtype))
        else:
            expected = state[key]
            equal = tuple(parameter.shape) == tuple(expected.shape) and torch.equal(parameter.detach().cpu(), expected.to(dtype=parameter.dtype))
        if not equal:
            raise ValueError(f"Loaded active encoder parameter differs from checkpoint: {name}")
        checked.append({"parameter": name, "checkpoint_key": key, "checkpoint_file": path.name,
                        "shape": list(parameter.shape), "elements": parameter.numel(), "equal_after_declared_dtype_cast": True})
    del state
    return {"active_parameter_tensor_count": len(checked), "active_parameter_elements": sum(row["elements"] for row in checked),
            "all_active_encoder_parameters_equal_cached_checkpoint": True,
            "unused_pooler_exclusion": "Exact main embedding reads last_hidden_state[:,0] and never pooler_output; pooler parameters do not affect this output.",
            "parameter_mapping_sha256": digest_json(checked), "parameters": checked}


def load_encoder(source, config, np, torch, audit_path):
    raw = source.read_bytes().replace(b"\r\n", b"\n")
    if digest(raw) != TEXT_EMBEDDING_SHA256:
        raise ValueError("BGE source differs from pinned main")
    tree = ast.parse(raw.decode("utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TextEmbedding")
    names = {"_encode_texts", "get_text_features", "runtime_semantics"}
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in methods} != names:
        raise ValueError("Pinned BGE method dependency set incomplete")
    module = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name="PinnedBgeEncoder", bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[]))
    namespace = {"np": np, "torch": torch, "Optional": Optional, "Callable": Callable, "Any": object}
    exec(compile(module, str(source), "exec"), namespace)
    model_spec = config["model"]
    snapshot = Path(model_spec["snapshot_path"])
    if not snapshot.is_dir() or snapshot.name != model_spec["snapshot_revision"]:
        raise ValueError("Pinned existing BGE snapshot is absent")
    observed_names = sorted(p.name for p in snapshot.iterdir() if p.is_file())
    if observed_names != model_spec["snapshot_top_level_files"]:
        raise ValueError("Cached snapshot file inventory changed")
    required = {"config.json", "tokenizer_config.json", "special_tokens_map.json", "tokenizer.json", "sentencepiece.bpe.model"}
    if model_spec["use_safetensors"]:
        required.add("model.safetensors")
    else:
        required.add("pytorch_model.bin")
    supplied = [entry["relative_path"] for entry in model_spec["files"]]
    if len(supplied) != len(set(supplied)) or set(supplied) != required:
        raise ValueError("Frozen inventory must cover exactly every consumed config/tokenizer/checkpoint file")
    verified_files = []
    for expected in model_spec["files"]:
        path = snapshot / expected["relative_path"]
        if not path.is_file() or path.stat().st_size != expected["bytes"] or path.stat().st_mtime_ns != expected["mtime_ns"]:
            raise ValueError("BGE cache file metadata changed after identity probe")
        actual_sha = file_sha(path)
        if expected.get("sha256") and actual_sha != expected["sha256"]:
            raise ValueError("BGE cached file checksum mismatch")
        if expected.get("content_addressed_sha256") and actual_sha != expected["content_addressed_sha256"]:
            raise ValueError("BGE cached blob does not match its content address")
        if not expected.get("sha256") and not expected.get("content_addressed_sha256") and expected.get("digest_pin_scope") != "metadata_frozen_before_run_sha256_frozen_before_model_loading":
            raise ValueError("Missing explicit checksum provenance for model input")
        verified_files.append({"relative_path": expected["relative_path"], "bytes": expected["bytes"], "mtime_ns": expected["mtime_ns"], "sha256": actual_sha,
                               "digest_pin_scope": expected.get("digest_pin_scope", "checksum_verified_against_identity_probe")})
    dump(audit_path, {"status": "all_consumed_files_hashed_before_model_loading", "snapshot_revision": snapshot.name,
                      "files": verified_files, "snapshot_top_level_files": observed_names})
    from transformers import AutoModel, AutoTokenizer
    started = time.perf_counter_ns()
    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True, trust_remote_code=False)
    model, loading = AutoModel.from_pretrained(str(snapshot), local_files_only=True, trust_remote_code=False,
                                              torch_dtype=torch.float32, output_loading_info=True,
                                              use_safetensors=model_spec["use_safetensors"])
    dump(audit_path, {"status": "checkpoint_loaded_pending_parameter_verification", "loading_info": metadata_json(loading),
                      "snapshot_revision": snapshot.name, "files": verified_files})
    missing = loading.get("missing_keys", [])
    unexpected = loading.get("unexpected_keys", [])
    # Current path reads CLS last_hidden_state, never pooler_output or LM head.
    core_missing = [k for k in missing if not k.startswith("pooler.")]
    core_unexpected = [k for k in unexpected if not k.startswith(("pooler.", "lm_head.", "cls."))]
    if core_missing or core_unexpected or loading.get("mismatched_keys") or loading.get("error_msgs"):
        raise ValueError(f"BGE encoder checkpoint did not load completely: missing={core_missing[:8]}, unexpected={core_unexpected[:8]}, mismatched={loading.get('mismatched_keys', [])[:3]}")
    if type(model).__name__ != "XLMRobertaModel" or model.config.model_type != "xlm-roberta" or model.config.hidden_size != 1024:
        raise ValueError("Cached model architecture is not the configured BGE-M3 encoder")
    model.eval()
    model.to(torch.device("cpu"))
    parameter_audit = checkpoint_parameter_audit(model, snapshot, model_spec["use_safetensors"], torch)
    for record in verified_files:
        current = (snapshot / record["relative_path"]).stat()
        if current.st_size != record["bytes"] or current.st_mtime_ns != record["mtime_ns"]:
            raise ValueError("Cached input changed during model loading or checkpoint verification")
        record["size_and_mtime_stable_after_loading"] = True
    encoder = namespace["PinnedBgeEncoder"]()
    encoder._model, encoder._tokenizer = model, tokenizer
    encoder._onnx_backend, encoder._backend = None, "pytorch"
    encoder._device, encoder._compute_type = torch.device("cpu"), "float32"
    encoder._pytorch_max_length, encoder._batch_size = 1024, 1
    encoder._pretrained_model = "BAAI/bge-m3"
    identity = {"repository": "BAAI/bge-m3", "snapshot_revision": snapshot.name,
                "snapshot_path": str(snapshot), "files": verified_files,
                "snapshot_top_level_files": observed_names,
                "selected_methods": sorted(names), "selected_ast_sha256": digest(ast.dump(module, include_attributes=False).encode()),
                "source_lf_sha256": TEXT_EMBEDDING_SHA256, "model_class": type(model).__name__,
                "tokenizer_class": type(tokenizer).__name__, "runtime_semantics": encoder.runtime_semantics(),
                "loading_info": metadata_json(loading), "core_encoder_missing_keys": core_missing,
                "core_encoder_unexpected_keys": core_unexpected, "trainable_parameter_elements": sum(p.numel() for p in model.parameters()),
                "checkpoint_parameter_audit": parameter_audit,
                "initialization_wall_ns": time.perf_counter_ns() - started,
                "initialization_scope": "Same effective PyTorch CPU/float32 tokenizer/model settings as main, with local-files-only and loading-state audit; exact main encoding methods are executed."}
    dump(audit_path, {"status": "verified", **identity})
    return encoder, identity


def capture_dense_query(harness, encoder, client, collection, query, np):
    canonical, channel = query["query_text"], query["channel"]
    has_exact = bool(re.findall(r'"([^"]+)"', canonical))
    calls, vectors = [], []
    class AuditedEncoder:
        def get_text_features(self, texts):
            if len(texts) != 1:
                raise ValueError("Only one canonical query formulation permitted")
            untruncated_tokens = encoder._tokenizer(texts, padding=False, truncation=False)["input_ids"][0]
            started = time.perf_counter_ns()
            value = encoder.get_text_features(texts)
            vector = np.asarray(value, dtype=np.float32)
            if vector.shape != (1, 1024) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector), 1.0, atol=0.00001):
                raise ValueError("Invalid BGE query embedding")
            vectors.append({"query_input": texts[0], "vector_float32_le_sha256": digest(vector.astype("<f4").tobytes()),
                            "l2_norm": float(np.linalg.norm(vector)), "dimension": 1024,
                            "untruncated_token_count": len(untruncated_tokens), "max_length": 1024,
                            "truncation_applied": len(untruncated_tokens) > 1024,
                            "encoding_wall_ns": time.perf_counter_ns() - started})
            return value
    class SearchOnlyAdapter:
        def search(self, **kwargs):
            if calls or kwargs["anns_field"] != channel + "_dense" or kwargs["filter"] != "" or kwargs["offset"] != 0 or kwargs["search_params"] != {"nprobe": 32, "metric_type": "COSINE"}:
                raise ValueError("Undeclared dense provider query")
            started = time.perf_counter_ns()
            response = client.search(collection, data=kwargs["data"], filter="", offset=0, limit=100,
                                     anns_field=channel + "_dense", search_params=kwargs["search_params"],
                                     output_fields=["frame_id", channel], timeout=30)
            if len(response) != 1 or len(response[0]) > 100:
                raise ValueError("Unexpected dense result depth")
            calls.append({"requested_native_limit": kwargs["limit"], "effective_raw_limit": 100,
                          "anns_field": kwargs["anns_field"], "filter": "", "offset": 0,
                          "search_params": kwargs["search_params"], "search_wall_ns": time.perf_counter_ns() - started,
                          "response": response[0]})
            return response
    harness._extractors = {"pinned_bge_m3": {"feature_extractor": AuditedEncoder()}}
    harness._database = SearchOnlyAdapter()
    harness._search_text_component.__globals__["np"] = np
    results, _ = harness._search_text_component({"text": canonical}, channel, None, channel + "_dense", "pinned_bge_m3", "", 100, 32, 1.0)
    if len(calls) != 1 or len(vectors) != 1:
        raise ValueError("Expected exactly one embedding and dense search per query/channel")
    call = calls[0]
    raw = call.pop("response")
    if len({h["entity"]["frame_id"] for h in raw}) != len(raw):
        raise ValueError("Duplicate provider frame IDs")
    effective = {h["entity"]["frame_id"]: (rank, h) for rank, h in enumerate(results, 1)}
    raw_hits = []
    for rank, hit in enumerate(raw, 1):
        fid, text = hit["entity"]["frame_id"], hit["entity"][channel]
        video, frame = fid.rsplit("#", 1)
        score = float(hit["distance"])
        if not frame.isdigit() or not isinstance(text, str) or not math.isfinite(score):
            raise ValueError("Invalid indexed dense candidate identity/text/score")
        eligible_rank, selected = effective.get(fid, (None, None))
        boost = 1.5 if has_exact else 1.0
        if selected and not math.isclose(selected["scores"]["dense_raw"], score * boost, rel_tol=0, abs_tol=0.000001):
            raise ValueError("Actual main dense boost differs from captured raw score")
        raw_hits.append({"raw_rank": rank, "milvus_id": metadata_json(hit.get("id")), "frame_id": fid,
                         "video_id": video, "frame_idx": int(frame), "indexed_text": text,
                         "indexed_text_sha256": digest(text.encode("utf-8")), "cosine_score": score,
                         "eligible_after_main_phrase_filter": selected is not None, "eligible_rank": eligible_rank,
                         "boost_if_eligible": boost,
                         "main_normalized_score": float(selected["distance"]) if selected else None})
    return {"schema": "vecna82-dense-visibility-row-v1", **query, "provider": channel + "_dense",
            "state": "ok" if results else "empty", "raw_call": call, "query_embedding": vectors[0],
            "raw_hits": raw_hits, "effective_frame_order": [h["entity"]["frame_id"] for h in results],
            "raw_hit_count": len(raw_hits), "eligible_hit_count": len(results),
            "ascii_double_quote_filter_active": has_exact,
            "ground_truth_read": False, "visual_models_loaded": False,
            "surface_limit": "Main dense-only eligibility/boost/max normalization on a raw top100 cap; native200/500 expansion is recorded but not fetched. This is diagnostic query-model visibility, not proof of historical corpus encoder identity."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--searcher-source", type=Path, required=True)
    parser.add_argument("--text-embedding-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--milvus-uri", default="http://localhost:19530")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    data = args.queries.read_bytes()
    queries = [json.loads(line) for line in data.decode("utf-8").splitlines() if line]
    allowed = {"query_id", "channel", "query_text", "query_text_sha256"}
    if config["schema"] != "vecna82-dense-visibility-config-v1" or config["status"] != "identity_pinned_ready" or config["provider_depth"] != 100:
        raise ValueError("A reviewed, identity-pinned dense configuration is required")
    expected_model_settings = {"repository": "BAAI/bge-m3", "backend": "pytorch", "device": "cpu", "dtype": "float32", "max_length": 1024}
    if any(config["model"].get(k) != v for k, v in expected_model_settings.items()):
        raise ValueError("Dense diagnostic model settings differ from the declared main path")
    if len(queries) != 38 or any(set(q) != allowed or q["channel"] not in {"ocr", "asr"} or q["query_text_sha256"] != digest(q["query_text"].encode("utf-8")) for q in queries) or len({(q["channel"], q["query_id"]) for q in queries}) != 38:
        raise ValueError("Only the frozen truth-free38 query/channel projection is accepted")
    if digest(data) != config["query_file_sha256"] or digest_json(queries) != config["query_projection_sha256"]:
        raise ValueError("Frozen query projection mismatch")
    if args.output_dir.exists() or not args.output_dir.name.startswith("dense-"):
        raise ValueError("Use a fresh disposable dense-* output directory")
    endpoint = urlparse(args.milvus_uri)
    if endpoint.scheme not in {"http", "https"} or not endpoint.hostname or endpoint.username or endpoint.password:
        raise ValueError("Existing server URI without inline credentials required")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", TOKENIZERS_PARALLELISM="false")
    harness, code_identity = load_main_text_harness(args.searcher_source)
    from pymilvus import MilvusClient
    client = MilvusClient(uri=args.milvus_uri)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = args.output_dir / "collection_manifest.json"
    manifest = {"schema": "vecna82-dense-visibility-run-v1", "status": "preflight", "rows_written": 0,
                "queries_sha256": digest(data), "config_sha256": digest(args.config.read_bytes()),
                "collector_sha256": digest(Path(__file__).read_bytes()), "code_identity": code_identity,
                "ground_truth_read": False, "collection_mutations": False, "visual_models_loaded": False,
                "python": platform.python_version(), "python_hash_seed": os.environ.get("PYTHONHASHSEED", "process_randomized; observed order exported"),
                "index_generation_identity": config["index_generation_identity"]}
    try:
        registry_records = []
        for registry_name in config["index_registry_paths"]:
            path = Path(registry_name)
            record = {"path": str(path), "exists": path.is_file()}
            if path.is_file():
                raw = path.read_bytes()
                registry = json.loads(raw)
                record.update(sha256=digest(raw), bytes=len(raw), index_state=registry.get("index_state"),
                              current_index_generation_id=registry.get("current_index_generation_id"))
                if registry.get("index_state") == "mutating":
                    raise ValueError("Index provenance explicitly reports an active mutation")
                artifact_name = f"index_registry_{len(registry_records)}.json"
                (args.output_dir / artifact_name).write_bytes(raw)
                record["artifact_relative_path"] = artifact_name
            else:
                record["state"] = "legacy_or_unmanifested_index"
            registry_records.append(record)
        manifest["index_registry_records"] = registry_records
        collection = config["collection"]["name"]
        if not client.has_collection(collection):
            raise ValueError("Existing collection absent; creation/loading prohibited")
        description = metadata_json(client.describe_collection(collection))
        count = int(client.query(collection, output_fields=["count(*)"], timeout=30)[0]["count(*)"])
        names = sorted(client.list_indexes(collection))
        indexes = metadata_json([client.describe_index(collection, name) for name in names])
        identity = {"name": collection, "row_count": count, "description_sha256": digest_json(description),
                    "index_descriptions_sha256": digest_json(indexes), "fields": sorted(f["name"] for f in description["fields"]), "index_names": names}
        manifest.update(collection=identity, description=description, indexes=indexes)
        if identity != config["collection"]:
            raise ValueError("Collection metadata changed")
        for channel in ("ocr", "asr"):
            field = next(f for f in description["fields"] if f["name"] == channel + "_dense")
            if int(field["params"]["dim"]) != 1024:
                raise ValueError("Dense field dimensions differ from BGE-M3")
        dump(manifest_path, manifest)
        import numpy as np
        import torch
        torch.set_num_threads(4)
        encoder, model_identity = load_encoder(args.text_embedding_source, config, np, torch, args.output_dir / "model_initialization.json")
        manifest.update(status="running", model_identity=model_identity,
                        packages={name: importlib.metadata.version(name) for name in ("numpy", "torch", "transformers", "pymilvus", "tokenizers")})
        dump(manifest_path, manifest)
        rankings = args.output_dir / "dense_rankings.jsonl"
        with rankings.open("x", encoding="utf-8", newline="\n") as handle:
            for query in queries:
                row = capture_dense_query(harness, encoder, client, collection, query, np)
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                handle.flush()
                manifest["rows_written"] += 1
                dump(manifest_path, manifest)
                print(json.dumps({"query_id": row["query_id"], "channel": row["channel"], "raw_hits": row["raw_hit_count"], "eligible_hits": row["eligible_hit_count"]}), flush=True)
        manifest.update(status="complete", rankings_sha256=digest(rankings.read_bytes()))
        for record in registry_records:
            path = Path(record["path"])
            if record["exists"] != path.is_file() or (record["exists"] and digest(path.read_bytes()) != record["sha256"]):
                raise ValueError("Index-generation registry changed during capture")
    except Exception as exc:
        manifest.update(status="failed_closed", error_type=type(exc).__name__, error=str(exc)[:1200])
        raise
    finally:
        dump(manifest_path, manifest)
        client.close()


if __name__ == "__main__":
    main()
