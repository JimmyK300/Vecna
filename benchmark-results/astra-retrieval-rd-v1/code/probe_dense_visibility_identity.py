#!/usr/bin/env python3
"""Bounded cache/config/source metadata probe; no model or database imports.

Reads only the named BGE cache, current configuration/source files, and at most
two frozen sample videos' dense provenance sidecars. Does not scan videos,
allocate tensors, download, change caches, or modify the dataset.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_meta(path, content_limit=0):
    result = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        return result
    stat = path.stat()
    result.update(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns, resolved_path=str(path.resolve()))
    if content_limit and stat.st_size <= content_limit:
        data = path.read_bytes()
        result["sha256"] = sha(data)
        if path.suffix == ".json":
            result["json"] = json.loads(data.decode("utf-8"))
        elif path.name in {"main", "refs"}:
            result["text"] = data.decode("utf-8").strip()
    return result


def config_projection(path):
    result = file_meta(path)
    if not result["exists"]:
        return result
    data = path.read_bytes()
    result["sha256"] = sha(data)
    try:
        import yaml
        config = yaml.safe_load(data)
    except ImportError:
        result["projection_status"] = "PyYAML unavailable; raw configuration intentionally not exported"
        return result
    allowed = {"model", "source", "pretrained_model", "backend", "onnx_provider", "onnx_model_path", "onnx_tokenizer_path", "onnx_max_length", "max_length", "text_source", "target", "index", "analyse"}
    def selected(value):
        return {k: v for k, v in (value or {}).items() if k in allowed}
    searcher = config.get("searcher", {})
    result["projection"] = {
        "features": {channel: selected(config.get("features", {}).get(channel)) for channel in ("ocr_dense", "asr_dense")},
        "text_bge_m3": selected(searcher.get("language_models", {}).get("text_bge_m3")),
        "text_fields": {channel: {k: v for k, v in (searcher.get(channel) or {}).items() if k in {"enable", f"{channel}_field", f"{channel}_dense_field"}} for channel in ("ocr", "asr")},
        "search_backend": {k: v for k, v in config.get("backends", {}).get("search", {}).items() if k in {"collection", "gpu"}},
    }
    result["projection_status"] = "explicit text-model/field allowlist; no unrelated configuration exported"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("C:/Users/minhc/.cache/huggingface/hub/models--BAAI--bge-m3"))
    parser.add_argument("--vecna-source", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=Path("D:/Official-Dataset"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh disposable output file")
    result = {"schema": "vecna82-dense-identity-probe-v1", "script_sha256": sha(Path(__file__).read_bytes()),
              "models_loaded": False, "tensor_allocations": False, "database_access": False,
              "dataset_or_cache_writes": False, "cache": {"path": str(args.cache), "exists": args.cache.is_dir(), "refs": [], "snapshots": []}}
    refs = args.cache / "refs"
    if refs.is_dir():
        for path in sorted(refs.iterdir())[:20]:
            if path.is_file():
                entry = file_meta(path)
                if entry["bytes"] <= 1024:
                    data = path.read_bytes()
                    entry.update(sha256=sha(data), revision=data.decode("utf-8").strip())
                result["cache"]["refs"].append(entry)
    snapshots = args.cache / "snapshots"
    if snapshots.is_dir():
        all_snapshots = sorted(p for p in snapshots.iterdir() if p.is_dir())
        result["cache"]["snapshot_count"] = len(all_snapshots)
        for directory in all_snapshots[:5]:
            files = sorted(p for p in directory.iterdir() if p.is_file())
            record = {"revision": directory.name, "path": str(directory), "top_level_file_count": len(files), "files": []}
            for path in files[:60]:
                limit = 200000 if path.name in {"config.json", "tokenizer_config.json", "special_tokens_map.json", "modules.json", "sentence_bert_config.json", "config_sentence_transformers.json"} else 0
                record["files"].append(file_meta(path, limit))
            pooling = directory / "1_Pooling" / "config.json"
            if pooling.is_file():
                record["pooling"] = file_meta(pooling, 200000)
            result["cache"]["snapshots"].append(record)
    source_paths = ["aic51-src/aic51/packages/analyse/features/text_embedding.py", "aic51-src/aic51/packages/search/searcher.py"]
    result["vecna_sources"] = []
    for relative in source_paths:
        path = args.vecna_source / relative
        entry = file_meta(path)
        if entry["exists"]:
            data = path.read_bytes()
            entry.update(sha256=sha(data), lf_sha256=sha(data.replace(b"\r\n", b"\n")), repository_path=relative)
        result["vecna_sources"].append(entry)
    result["configuration"] = [config_projection(args.vecna_source / "config.yaml"), config_projection(args.dataset_root / "config.yaml")]
    result["dense_provenance"] = []
    # First two OCR cases in the frozen source sample; identities fixed before
    # retrieval. These sidecars assess generation metadata, not correctness.
    for video in ("L30_V092", "L30_V072"):
        for root in (args.dataset_root, args.dataset_root / "features_L21-L30_branch-feats-siglip"):
            for channel in ("ocr_dense", "asr_dense"):
                directory = root / "provenance" / "analysis" / video / channel
                entry = {"path": str(directory), "exists": directory.is_dir(), "records": []}
                if directory.is_dir():
                    files = sorted(directory.glob("*.json"))
                    entry["record_count"] = len(files)
                    for path in files[-2:]:
                        record = file_meta(path)
                        if record["bytes"] <= 2000000:
                            data = path.read_bytes()
                            doc = json.loads(data)
                            record["sha256"] = sha(data)
                            record["projection"] = {k: doc.get(k) for k in ("schema_version", "run_id", "video_id", "feature_name", "status", "started_at", "finished_at", "provider_generation", "source_id", "selection_generation_id")}
                            record["outputs_count"] = len(doc.get("outputs", []))
                        entry["records"].append(record)
                result["dense_provenance"].append(entry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": sha(args.output.read_bytes()), "bytes": args.output.stat().st_size, "cache_exists": result["cache"]["exists"], "snapshot_count": result["cache"].get("snapshot_count", 0)}, indent=2))


if __name__ == "__main__":
    main()
