#!/usr/bin/env python3
"""Bounded, read-only provider export for Packet B. Never call production HTTP.

Uses an isolated process, frozen Searcher code, and an adapter exposing only
search. It never constructs MilvusDatabase, creates/loads/releases collections,
inserts records, writes a production config, or parses/translates the query.
The control is main's fusion replay on the frozen raw top100 provider surface;
it is explicitly not a replay of the UI's 200+/segment-diversified result pool.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlparse

from fusion_study import (ContractError, PROVIDERS, SCHEMA, digest_bytes, digest_json,
                          frame_video, load_jsonl, nominal_weights, study_query,
                          run_identity_digest, validate_config)

MAIN_SHA = "95d63a6abf10c598e0e54af7d2071bedbe542d1e"
SEARCHER_SHA256 = "6f94bdd147c4b2b29b522a1f4bbbf004fb726fdfdf68a7cb316a4aec9e869e51"
TRANSFORMATIONS = {"query_expansion": False, "translation": False, "reranking": False,
                   "yolo": False, "temporal_parser": False, "segment_clustering": False}


def metadata_json(value):
    """Normalize SDK metadata without unstable repr/string fallbacks.

    Milvus describe calls can contain protobuf repeated containers inside an
    otherwise ordinary dictionary. Preserve sequence order and scalar types;
    messages use the explicit ProtoJSON representation with numeric enums.
    Unsupported values, non-string keys, and non-finite numbers fail closed.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("non-finite collection/index metadata")
        return float(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ContractError("collection/index metadata keys must be strings")
        return {key: metadata_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        return [metadata_json(item) for item in value]
    # Some protobuf C-extension versions do not register repeated containers
    # with collections.abc.Sequence. These exact container types are ordered.
    value_type = type(value)
    if (value_type.__module__ in {"google._upb._message", "google.protobuf.pyext._message",
                                  "google.protobuf.internal.containers"}
            and value_type.__name__ in {"RepeatedScalarContainer", "RepeatedCompositeContainer",
                                         "RepeatedScalarFieldContainer", "RepeatedCompositeFieldContainer"}):
        return [metadata_json(item) for item in value]
    try:
        from google.protobuf.json_format import MessageToDict
        from google.protobuf.message import Message
    except ImportError:
        Message = ()
    if isinstance(value, Message):
        return metadata_json(MessageToDict(value, preserving_proto_field_name=True,
                                            use_integers_for_enums=True))
    raise ContractError("unsupported collection/index metadata type: "
                        f"{value_type.__module__}.{value_type.__qualname__}")


def configure_cpu_threads(torch, requested):
    """Bound intra-op CPU parallelism; report actual runtime thread settings."""
    if type(requested) is not int or requested < 1:
        raise ContractError("cpu_threads must be a positive integer")
    torch.set_num_threads(requested)
    return {"requested_intraop_threads": requested,
            "actual_intraop_threads": torch.get_num_threads(),
            "actual_interop_threads": torch.get_num_interop_threads()}


class SearchOnlyDatabase:
    """Deliberately has no mutation, auto-load, release, or destructor methods."""
    def __init__(self, client, collection: str, fields: set[str]):
        self.client, self.collection, self.fields = client, collection, fields

    @staticmethod
    def process_field_name(field_name: str) -> str:
        return field_name.replace("-", "_")

    def search(self, *, data, filter="", offset=0, limit=100, anns_field,
               search_params, output_fields=None):
        field = self.process_field_name(anns_field)
        if field not in self.fields or filter or offset:
            raise ContractError("undeclared field/filter/offset in collection read")
        scalar_fields = [name for name in ("frame_id", "ocr", "asr") if name in self.fields]
        return self.client.search(self.collection, data=data, filter="", offset=0, limit=limit,
                                  anns_field=field, search_params=search_params,
                                  output_fields=scalar_fields)


def provider_fields(searcher) -> dict:
    return {"qwen": "qwen_vl", "siglip": "image_siglip_so400m-384",
            "ocr_sparse": searcher._ocr_name,
            "ocr_dense": getattr(searcher, "_ocr_dense_name", None),
            "asr_sparse": searcher._asr_name,
            "asr_dense": getattr(searcher, "_asr_dense_name", None)}


def capture_query(searcher, query: dict, config: dict, run_identity_sha256: str) -> dict:
    """Run exactly one full canonical query and prove offline/source parity.

    All DB result lists are capped to the same predeclared raw depth. Native
    text quote eligibility/boost runs identically in the source and exporter.
    The original requested text depth (200/500) is retained as provenance.
    """
    validate_config(config)
    fields = provider_fields(searcher)
    weights = nominal_weights(config)
    providers = {}
    for name in PROVIDERS:
        configured = bool(fields[name])
        if name in ("qwen", "siglip") or name.endswith("dense"):
            configured = configured and fields[name] in searcher._features
        state = "disabled" if weights[name] == 0 else ("not_attempted" if configured else "unavailable")
        providers[name] = {"state": state, "field": fields[name], "hits": [],
                           "metric": "BM25" if name.endswith("sparse") else "COSINE",
                           "score_orientation": "higher_is_better"}
    canonical = query["query_text"]
    expected_hash = digest_bytes(canonical.encode("utf-8"))
    if query.get("query_text_sha256", expected_hash) != expected_hash:
        raise ContractError("canonical input text hash is invalid")
    database = searcher._database
    raw_calls = {}
    trace_state = {}
    method = searcher._similarity_search
    method_code = method.__func__.__code__
    exact_match = searcher._search_text_component.__func__.__globals__["check_exact_phrases"]

    class CaptureDatabase:
        def search(self, **kwargs):
            name_candidates = [name for name, field in fields.items() if field == kwargs["anns_field"]]
            if len(name_candidates) != 1:
                raise ContractError("database call does not map to one declared provider")
            name = name_candidates[0]
            if name in raw_calls:
                raise ContractError("more than one formulation/call for a provider")
            requested_limit = kwargs["limit"]
            bounded_kwargs = {**kwargs, "limit": config["provider_depth"]}
            started = time.perf_counter_ns()
            try:
                results = database.search(**bounded_kwargs)
            except Exception:
                providers[name]["state"] = "failed"
                raise
            elapsed = time.perf_counter_ns() - started
            if len(results) != 1:
                raise ContractError("provider must return exactly one query list")
            raw = results[0]
            if len(raw) > config["provider_depth"]:
                raise ContractError("provider exceeded requested depth")
            raw_calls[name] = {"requested_native_limit": requested_limit,
                               "effective_raw_limit": config["provider_depth"],
                               "search_params": kwargs["search_params"],
                               "query_input_sha256": digest_json(kwargs["data"]),
                               "search_wall_ns": elapsed,
                               "raw_hits": [{"frame_id": item["entity"]["frame_id"],
                                              "score": float(item["distance"]),
                                              "text": item["entity"].get(name.split("_")[0], "")}
                                             for item in raw]}
            has_exact = name.startswith(("ocr_", "asr_")) and bool(re.findall(r'"([^"]+)"', canonical))
            hits = []
            for item in raw:
                fid = item["entity"]["frame_id"]
                if has_exact:
                    doc_text = item["entity"].get(name.split("_")[0], "")
                    if not exact_match(canonical, doc_text, fallback_query=canonical)[0]:
                        continue
                hits.append({"frame_id": fid, "video_id": frame_video(fid),
                             "score": float(item["distance"]) * (1.5 if has_exact else 1.0),
                             "rank": len(hits) + 1})
            providers[name].update(state="ok" if hits else "empty", hits=hits,
                                   raw_hit_count=len(raw), exact_phrase_filter=has_exact,
                                   raw_call=raw_calls[name])
            return results

    def tracer(frame, event, arg):
        if frame.f_code is not method_code:
            return None
        if frame.f_code is method_code and event == "return":
            trace_state["candidate_tie_order"] = list(frame.f_locals.get("all_frame_ids", ()))
        return tracer

    old_trace = sys.gettrace()
    searcher._database = CaptureDatabase()
    started = time.perf_counter_ns()
    try:
        sys.settrace(tracer)
        reference = method({"text": canonical}, [], 0, config["provider_depth"],
                           [fields[name] for name in config["visual_providers"]],
                           ocr_weight=config["ocr_weight"], asr_weight=config["asr_weight"],
                           ocr_alpha=config["ocr_alpha"], asr_alpha=config["asr_alpha"],
                           nprobe=config["nprobe"], exclude_video_ids=[])
    finally:
        sys.settrace(old_trace)
        searcher._database = database
    row = {"schema": SCHEMA, "status": "complete", "query_id": query["query_id"],
           "query_text": canonical, "query_text_sha256": expected_hash,
           "run_identity_sha256": run_identity_sha256,
           "config_sha256": digest_json(config), "transformations": TRANSFORMATIONS,
           "providers": providers,
           "candidate_tie_order": trace_state.get("candidate_tie_order"),
           "current_control_reference": [{"frame_id": item["entity"]["frame_id"],
                                          "score": float(item["distance"])} for item in reference],
           "source_call_wall_ns": time.perf_counter_ns() - started,
           "control_surface": "exact_main_method_with_frozen_raw_provider_depth_cap"}
    study_query(row, config)  # Fail before returning an export that cannot replay.
    return row


def loaded_model_identity(extractor) -> dict:
    """Hash actual loaded weights/config without copying credentials to output."""
    import torch
    root = extractor
    visited = set()
    model = None
    frontier = [root]
    for _ in range(4):
        next_frontier = []
        for obj in frontier:
            if id(obj) in visited:
                continue
            visited.add(id(obj))
            if isinstance(obj, torch.nn.Module):
                model = obj
                break
            for key in ("_model", "model", "embedder", "_embedder"):
                child = getattr(obj, key, None)
                if child is not None:
                    next_frontier.append(child)
        if model is not None:
            break
        frontier = next_frontier
    if model is None:
        raise ContractError("cannot establish exact loaded model identity; do not invent a snapshot")
    digest = hashlib.sha256()
    tensor_count = 0
    tensor_bytes = 0
    for name, tensor in sorted(model.state_dict().items()):
        identity = {"name": name, "dtype": str(tensor.dtype), "shape": list(tensor.shape)}
        digest.update(json.dumps(identity, sort_keys=True).encode("utf-8"))
        byte_tensor = tensor.detach().cpu().contiguous().reshape(-1).view(torch.uint8)
        array = byte_tensor.numpy()
        # Memory view avoids an additional weights-sized bytes allocation.
        digest.update(memoryview(array))
        tensor_bytes += array.nbytes
        tensor_count += 1
    model_config = getattr(model, "config", None)
    config_hash = digest_json(model_config.to_dict()) if hasattr(model_config, "to_dict") else None
    preprocessing = preprocessing_identity(extractor, model)
    source_path = Path(inspect.getfile(type(extractor)))
    return {"extractor_class": type(extractor).__qualname__, "model_class": type(model).__qualname__,
            "loaded_state_dict_sha256": digest.hexdigest(), "tensor_count": tensor_count,
            "tensor_bytes": tensor_bytes, "model_config_sha256": config_hash,
            "model_module_structure_sha256": digest_bytes(str(model).encode("utf-8")),
            "preprocessing": preprocessing,
            "extractor_source_sha256": digest_bytes(source_path.read_bytes()),
            "identity_note": "exact loaded state/config identity; not a claimed Hugging Face revision"}


def preprocessing_identity(extractor, model) -> dict:
    """Bind the loaded text tokenizer, special tokens, templates and processor."""
    def stable_hash(value):
        # AddedToken/config objects have stable textual representations. Only
        # the hash is exported; no local auth/config values are serialized out.
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        return digest_bytes(encoded)
    queue = [extractor, model]
    visited, entries = set(), []
    tokenization_bound = False
    while queue:
        obj = queue.pop(0)
        if id(obj) in visited:
            continue
        visited.add(id(obj))
        entry = {"class": type(obj).__module__ + "." + type(obj).__qualname__}
        backend = getattr(obj, "backend_tokenizer", None)
        if backend is not None and callable(getattr(backend, "to_str", None)):
            entry["backend_tokenizer_sha256"] = digest_bytes(backend.to_str().encode("utf-8"))
            tokenization_bound = True
        if callable(getattr(obj, "get_vocab", None)):
            entry["vocab_sha256"] = stable_hash(obj.get_vocab())
            tokenization_bound = True
        for key in ("init_kwargs", "special_tokens_map", "special_tokens_map_extended", "chat_template",
                    "model_max_length", "padding_side", "truncation_side", "clean_up_tokenization_spaces",
                    "bos_token_id", "eos_token_id", "pad_token_id", "unk_token_id"):
            value = getattr(obj, key, None)
            if value is not None:
                entry[key + "_sha256"] = stable_hash(value)
        if callable(getattr(obj, "to_dict", None)):
            entry["configuration_sha256"] = stable_hash(obj.to_dict())
        get_config = getattr(obj, "get_config_dict", None)
        if callable(get_config):
            try:
                inspect.signature(get_config).bind()
            except (TypeError, ValueError):
                # HF PretrainedConfig.get_config_dict(path) is a loader, not
                # a zero-argument getter. Its in-memory to_dict is above.
                pass
            else:
                entry["module_configuration_sha256"] = stable_hash(get_config())
        if len(entry) > 1:
            try:
                entry["implementation_sha256"] = digest_bytes(Path(inspect.getfile(type(obj))).read_bytes())
            except (TypeError, OSError):
                entry["implementation_sha256"] = None
            entries.append(entry)
        for key in ("_model", "model", "tokenizer", "_tokenizer", "processor", "_processor", "auto_model", "config"):
            child = getattr(obj, key, None)
            if child is not None and id(child) not in visited:
                queue.append(child)
        # SentenceTransformer's first module owns the multimodal processor.
        first_module = getattr(obj, "_first_module", None)
        if callable(first_module):
            queue.append(first_module())
    if not tokenization_bound:
        raise ContractError("actual tokenizer identity unavailable; do not claim exact query embeddings")
    return {"sha256": digest_json(entries), "components": entries,
            "text_tokenization_bound": tokenization_bound}


def prepare_searcher(args, config):
    """Read only existing collection and import the inspected main searcher."""
    import yaml
    runtime_root = args.runtime_root.resolve()
    source = runtime_root / "aic51-src/aic51/packages/search/searcher.py"
    if digest_bytes(source.read_text(encoding="utf-8").encode("utf-8")) != SEARCHER_SHA256:
        raise ContractError("runtime Searcher differs from the exact inspected Vecna main")
    runtime_config = yaml.safe_load(args.runtime_config.read_text(encoding="utf-8"))
    effective = copy.deepcopy(runtime_config)
    search_config = effective.setdefault("searcher", {})
    for key in ("llm", "reranker", "yolo"):
        search_config.setdefault(key, {})["enable"] = False
        # Never expose or pass an unused LLM credential into the research run.
        search_config[key].pop("api_key", None)
    weights = nominal_weights(config)
    target_fields = {"qwen_vl", "image_siglip_so400m-384"}
    for modality in ("ocr", "asr"):
        if weights[modality + "_dense"] > 0:
            field = search_config.get(modality, {}).get(modality + "_dense_field")
            if field:
                target_fields.add(field)
    selected_models = {name: desc for name, desc in search_config.get("language_models", {}).items()
                       if set(desc.get("target", ())) & target_fields}
    search_config["language_models"] = selected_models
    effective.setdefault("backends", {}).setdefault("search", {})["gpu"] = args.device != "cpu"
    effective["backends"]["search"]["collection"] = config["collection_name"]
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(runtime_root / "aic51-src"))
    import torch
    cpu_threading = configure_cpu_threads(torch, args.cpu_threads)
    from pymilvus import MilvusClient
    from aic51.packages.config import GlobalConfig
    GlobalConfig._GlobalConfig__config = effective
    from aic51.packages.search.searcher import Searcher
    if Path(inspect.getfile(Searcher)).resolve() != source.resolve():
        raise ContractError("import resolved to a different checkout")
    endpoint = urlparse(args.milvus_uri)
    if endpoint.scheme not in ("http", "https") or not endpoint.hostname:
        raise ContractError("existing Milvus server URI required; filesystem/Lite database paths are prohibited")
    client = MilvusClient(uri=args.milvus_uri)
    collection = config["collection_name"]
    if not client.has_collection(collection):
        raise ContractError("declared collection does not exist; collection creation is prohibited")
    description = metadata_json(client.describe_collection(collection))
    fields = {field["name"] for field in description["fields"]}
    count = int(client.query(collection, output_fields=["count(*)"])[0]["count(*)"])
    if count != config["collection_row_count"]:
        raise ContractError("collection row count differs from frozen authority")
    index_names = sorted(client.list_indexes(collection))
    indexes = metadata_json([client.describe_index(collection, index_name) for index_name in index_names])
    collection_identity = {"name": collection, "row_count": count,
                           "description_sha256": digest_json(description),
                           "index_descriptions_sha256": digest_json(indexes),
                           "fields": sorted(fields), "index_names": index_names}
    searcher = Searcher.__new__(Searcher)
    searcher._database = SearchOnlyDatabase(client, collection, fields)
    searcher._prepare_feature_extractors(torch.device(args.device))
    identities = {name: loaded_model_identity(desc["feature_extractor"])
                  for name, desc in searcher._extractors.items()}
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=runtime_root,
                              check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        head = None
    identity = {"searcher_sha256": SEARCHER_SHA256, "declared_main": MAIN_SHA,
                "searcher_raw_file_sha256": digest_bytes(source.read_bytes()),
                "searcher_source_newline_policy": "LF canonicalized for authority match; actual bytes hashed separately",
                "runtime_head": head, "runtime_config_sha256": digest_bytes(args.runtime_config.read_bytes()),
                "effective_config_sha256": digest_json(effective),
                "collection": collection_identity, "models": identities,
                "model_declarations_sha256": digest_json(selected_models),
                "device": args.device, "cpu_threading": cpu_threading,
                "python": platform.python_version(),
                "packages": {name: importlib.metadata.version(name)
                             for name in ("torch", "numpy", "transformers", "sentence-transformers", "pymilvus", "open-clip-torch")},
                "transformations": TRANSFORMATIONS,
                "disabled_unselected_model_loading": True,
                "production_database_mutations": False}
    return searcher, identity, client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--milvus-uri", default="http://localhost:19530")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--cpu-threads", type=int, default=6,
                        help="intra-op CPU thread count, fixed before model preparation")
    parser.add_argument("--smoke-count", type=int, help="GT-blind first N rows; never a full benchmark")
    args = parser.parse_args()
    if args.cpu_threads < 1:
        parser.error("--cpu-threads must be positive")
    config = validate_config(json.loads(args.config.read_text(encoding="utf-8")))
    queries = load_jsonl(args.queries)
    allowed = {"query_id", "query_text", "query_text_sha256", "phase", "task_type", "capabilities"}
    if any(set(row) - allowed for row in queries):
        raise ContractError("collector accepts a GT-free query projection only")
    if len(queries) != config["expected_query_count"] or len({q["query_id"] for q in queries}) != len(queries):
        raise ContractError("canonical projection count/IDs differ from frozen config")
    projection_hash = digest_json({q["query_id"]: digest_bytes(q["query_text"].encode("utf-8")) for q in queries})
    if config.get("canonical_query_projection_sha256") != projection_hash:
        raise ContractError("canonical query IDs/text differ from frozen authority")
    if args.smoke_count is not None and not 1 <= args.smoke_count < len(queries):
        raise ContractError("smoke count must be a positive proper subset")
    selected = queries[:args.smoke_count] if args.smoke_count else queries
    if args.output_dir.exists():
        raise ContractError("output directory exists; select a fresh run directory")
    searcher, identity, client = prepare_searcher(args, config)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": SCHEMA, "status": "running", "config_sha256": digest_json(config),
                "run_id": uuid.uuid4().hex, "collector_sha256": digest_bytes(Path(__file__).read_bytes()),
                "canonical_queries_sha256": digest_bytes(args.queries.read_bytes()),
                "expected_query_count": len(queries), "planned_query_count": len(selected),
                "scope": "smoke_only" if args.smoke_count else "full_query_projection",
                "identity": identity, "ground_truth_read": False, "rows_written": 0}
    manifest["run_identity_sha256"] = run_identity_digest(manifest)
    manifest_path = args.output_dir / "collection_manifest.json"
    def write_manifest():
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                 encoding="utf-8")
    write_manifest()
    rows_path = args.output_dir / "provider_rankings.jsonl"
    try:
        with rows_path.open("x", encoding="utf-8", newline="\n") as handle:
            for query in selected:
                row = capture_query(searcher, query, config, manifest["run_identity_sha256"])
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
                manifest["rows_written"] += 1
                write_manifest()
                print(json.dumps({"query_id": query["query_id"], "replay_verified": True,
                                  "provider_hits": {p: len(row["providers"][p]["hits"]) for p in PROVIDERS}}), flush=True)
        manifest.update(status="complete", rankings_sha256=digest_bytes(rows_path.read_bytes()))
    except Exception as exc:
        manifest.update(status="failed_closed", error_type=type(exc).__name__)
        raise
    finally:
        write_manifest()
        client.close()  # Closes this connection; no collection release/load calls.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
