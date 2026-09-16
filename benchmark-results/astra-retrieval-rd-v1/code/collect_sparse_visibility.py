#!/usr/bin/env python3
"""Read-only BM25 visibility capture for the frozen dataset #17 query sample.

Executes only pinned pure text-search functions extracted by AST from main.
No production imports, Searcher/MilvusDatabase constructors, visual/dense model
loading, collection load/release, mutation, truth access, or result scoring.
"""
from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping, Sequence
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import threading
import time
from typing import Callable
import unicodedata
from urllib.parse import urlparse


MAIN_SHA = "95d63a6abf10c598e0e54af7d2071bedbe542d1e"
SEARCHER_SHA256 = "6f94bdd147c4b2b29b522a1f4bbbf004fb726fdfdf68a7cb316a4aec9e869e51"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def digest_json(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def metadata_json(value):
    """Preserve SDK metadata, including protobuf repeated containers, exactly."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite metadata")
        return float(value)
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ValueError("Metadata keys must be strings")
        return {k: metadata_json(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        return [metadata_json(v) for v in value]
    t = type(value)
    if t.__module__ in {"google._upb._message", "google.protobuf.pyext._message", "google.protobuf.internal.containers"} and t.__name__ in {"RepeatedScalarContainer", "RepeatedCompositeContainer", "RepeatedScalarFieldContainer", "RepeatedCompositeFieldContainer"}:
        return [metadata_json(v) for v in value]
    try:
        from google.protobuf.json_format import MessageToDict
        from google.protobuf.message import Message
    except ImportError:
        Message = ()
    if isinstance(value, Message):
        return metadata_json(MessageToDict(value, preserving_proto_field_name=True, use_integers_for_enums=True))
    raise ValueError(f"Unsupported metadata type: {t.__module__}.{t.__qualname__}")


def load_main_text_harness(path):
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    if digest(normalized) != SEARCHER_SHA256:
        raise ValueError("Text-search source differs from the pinned main file")
    module = ast.parse(normalized.decode("utf-8"))
    helper_names = {"_check_cancelled", "remove_diacritics", "_build_exact_regex", "check_exact_phrases"}
    helpers = [n for n in module.body if isinstance(n, ast.FunctionDef) and n.name in helper_names]
    cancellation = [n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "SearchCancelledException"]
    searcher = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "Searcher")
    method_names = {"_normalize_scores", "_text_field_from_index_field", "_extract_query_texts", "_search_text_component"}
    methods = [n for n in searcher.body if isinstance(n, ast.FunctionDef) and n.name in method_names]
    if {n.name for n in helpers} != helper_names or {n.name for n in methods} != method_names or len(cancellation) != 1:
        raise ValueError("Pinned text-method dependency set is incomplete")
    harness = ast.ClassDef(name="SparseTextHarness", bases=[], keywords=[], body=methods, decorator_list=[])
    selected = ast.fix_missing_locations(ast.Module(body=cancellation + helpers + [harness], type_ignores=[]))
    class QuietLogger:
        def info(self, *args, **kwargs):
            pass
    namespace = {"re": re, "unicodedata": unicodedata, "threading": threading,
                 "Callable": Callable, "logger": QuietLogger()}
    exec(compile(selected, str(path), "exec"), namespace)
    instance = namespace["SparseTextHarness"]()
    instance._extractors = {}
    return instance, {"main_commit": MAIN_SHA, "source_lf_sha256": digest(normalized),
                      "source_raw_sha256": digest(raw), "selected_ast_sha256": digest(ast.dump(selected, include_attributes=False).encode()),
                      "methods": sorted(method_names), "helpers": sorted(helper_names),
                      "production_module_imported": False, "models_loaded": False}


def capture_query(harness, client, collection, query, depth=100):
    canonical, channel = query["query_text"], query["channel"]
    if digest(canonical.encode("utf-8")) != query["query_text_sha256"]:
        raise ValueError("Canonical query identity mismatch")
    calls = []
    class SearchOnlyAdapter:
        def search(self, **kwargs):
            if calls or kwargs["anns_field"] != channel + "_sparse" or kwargs["filter"] != "" or kwargs["offset"] != 0 or kwargs["search_params"] != {"metric_type": "BM25"}:
                raise ValueError("Undeclared provider, filter, offset, parameters, or additional search")
            started = time.perf_counter_ns()
            result = client.search(collection, data=kwargs["data"], filter="", offset=0, limit=depth,
                                   anns_field=channel + "_sparse", search_params={"metric_type": "BM25"},
                                   output_fields=["frame_id", channel], timeout=30)
            if len(result) != 1 or len(result[0]) > depth:
                raise ValueError("Unexpected provider response depth")
            calls.append({"requested_native_limit": kwargs["limit"], "effective_raw_limit": depth,
                          "query_input": kwargs["data"][0], "query_input_sha256": digest_json(kwargs["data"]),
                          "anns_field": kwargs["anns_field"], "filter": "", "offset": 0,
                          "search_params": kwargs["search_params"], "search_wall_ns": time.perf_counter_ns() - started,
                          "raw_response": result[0]})
            return result
    harness._database = SearchOnlyAdapter()
    results, _ = harness._search_text_component({"text": canonical}, channel, channel + "_sparse", None, None, "", depth, 32, 0.0)
    if len(calls) != 1:
        raise ValueError("Expected exactly one BM25 formulation per query/channel")
    call = calls[0]
    raw = call.pop("raw_response")
    if len({hit["entity"]["frame_id"] for hit in raw}) != len(raw):
        raise ValueError("Duplicate frame IDs in raw provider response")
    effective = {hit["entity"]["frame_id"]: (rank, hit) for rank, hit in enumerate(results, 1)}
    has_exact = bool(re.findall(r'"([^"]+)"', canonical))
    raw_hits = []
    for rank, hit in enumerate(raw, 1):
        entity = hit["entity"]
        fid, text = entity["frame_id"], entity[channel]
        if not isinstance(fid, str) or not isinstance(text, str) or "#" not in fid:
            raise ValueError("Missing indexed frame/text identity")
        video, frame = fid.rsplit("#", 1)
        if not frame.isdigit():
            raise ValueError("Unparseable indexed frame identity")
        score = float(hit["distance"])
        if not math.isfinite(score):
            raise ValueError("Non-finite BM25 score")
        effective_rank, selected = effective.get(fid, (None, None))
        boost = 1.5 if has_exact else 1.0
        if selected and not math.isclose(selected["scores"]["sparse_raw"], score * boost, rel_tol=0, abs_tol=0.000001):
            raise ValueError("Actual main boost differs from captured raw score")
        raw_hits.append({"raw_rank": rank, "milvus_id": metadata_json(hit.get("id")), "frame_id": fid,
                         "video_id": video, "frame_idx": int(frame), "indexed_text": text,
                         "indexed_text_sha256": digest(text.encode("utf-8")), "bm25_score": score,
                         "eligible_after_main_phrase_filter": selected is not None,
                         "boost_if_eligible": boost, "eligible_rank": effective_rank,
                         "main_normalized_score": float(selected["distance"]) if selected else None})
    return {"schema": "vecna82-sparse-visibility-row-v1", "query_id": query["query_id"], "channel": channel,
            "query_text": canonical, "query_text_sha256": query["query_text_sha256"],
            "provider": channel + "_sparse", "state": "ok" if results else "empty",
            "raw_call": call, "ascii_double_quote_filter_active": has_exact,
            "query_transform": "exact main strip of ASCII double quotes and surrounding whitespace only",
            "raw_hits": raw_hits, "effective_frame_order": [h["entity"]["frame_id"] for h in results],
            "raw_hit_count": len(raw_hits), "eligible_hit_count": len(results),
            "ground_truth_read": False, "dense_models_loaded": False, "visual_models_loaded": False,
            "surface_limit": "Main text eligibility/boost/normalization on a predeclared raw top100 cap; native 200/500 pool expansion is recorded but not fetched. SDK raw order and observed main tie order are both retained."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--searcher-source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--milvus-uri", default="http://localhost:19530")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    query_bytes = args.queries.read_bytes()
    queries = [json.loads(line) for line in query_bytes.decode("utf-8").splitlines() if line]
    allowed = {"query_id", "channel", "query_text", "query_text_sha256"}
    if len(queries) != 38 or any(set(q) != allowed or q["channel"] not in {"ocr", "asr"} for q in queries):
        raise ValueError("Only the 38-row truth-free query projection is accepted")
    if len({(q["channel"], q["query_id"]) for q in queries}) != 38 or digest(query_bytes) != config["query_file_sha256"] or digest_json(queries) != config["query_projection_sha256"]:
        raise ValueError("Frozen query projection mismatch")
    if config["provider_depth"] != 100 or config["collection"]["name"] != "official_l21_l30_all_v2" or config["collection"]["row_count"] != 322924:
        raise ValueError("Unexpected collection or retrieval depth")
    if args.output_dir.exists() or not args.output_dir.resolve().name.startswith("sparse-"):
        raise ValueError("Use a fresh disposable sparse-* output directory")
    endpoint = urlparse(args.milvus_uri)
    if endpoint.scheme not in {"http", "https"} or not endpoint.hostname or endpoint.username or endpoint.password:
        raise ValueError("Existing server URI without inline credentials required; no Milvus Lite path")
    harness, code_identity = load_main_text_harness(args.searcher_source)
    from pymilvus import MilvusClient
    client = MilvusClient(uri=args.milvus_uri)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": "vecna82-sparse-visibility-run-v1", "status": "preflight", "rows_written": 0,
                "queries_sha256": digest(query_bytes), "config_sha256": digest(args.config.read_bytes()),
                "collector_sha256": digest(Path(__file__).read_bytes()), "code_identity": code_identity,
                "ground_truth_read": False, "collection_mutations": False, "models_loaded": False,
                "python": platform.python_version(), "pymilvus_version": importlib.metadata.version("pymilvus"),
                "python_hash_seed": os.environ.get("PYTHONHASHSEED", "process_randomized; observed order exported")}
    manifest_path = args.output_dir / "collection_manifest.json"
    try:
        collection = config["collection"]["name"]
        if not client.has_collection(collection):
            raise ValueError("Frozen collection is absent; creation/loading is prohibited")
        description = metadata_json(client.describe_collection(collection))
        count = int(client.query(collection, output_fields=["count(*)"], timeout=30)[0]["count(*)"])
        names = sorted(client.list_indexes(collection))
        indexes = metadata_json([client.describe_index(collection, name) for name in names])
        identity = {"name": collection, "row_count": count, "description_sha256": digest_json(description),
                    "index_descriptions_sha256": digest_json(indexes),
                    "fields": sorted(field["name"] for field in description["fields"]), "index_names": names}
        manifest.update(collection=identity, description=description, indexes=indexes)
        if identity != config["collection"]:
            raise ValueError("Collection metadata differs from the previously verified identity")
        if not {"frame_id", "ocr", "asr", "ocr_sparse", "asr_sparse"}.issubset(identity["fields"]):
            raise ValueError("Required indexed text fields are absent")
        manifest["status"] = "running"
        dump(manifest_path, manifest)
        output = args.output_dir / "sparse_rankings.jsonl"
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            for query in queries:
                row = capture_query(harness, client, collection, query)
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                handle.flush()
                manifest["rows_written"] += 1
                dump(manifest_path, manifest)
                print(json.dumps({"query_id": row["query_id"], "channel": row["channel"], "raw_hits": row["raw_hit_count"], "eligible_hits": row["eligible_hit_count"]}), flush=True)
        manifest.update(status="complete", rankings_sha256=digest(output.read_bytes()))
    except Exception as exc:
        manifest.update(status="failed_closed", error_type=type(exc).__name__, error=str(exc)[:800])
        raise
    finally:
        dump(manifest_path, manifest)
        client.close()


if __name__ == "__main__":
    main()
