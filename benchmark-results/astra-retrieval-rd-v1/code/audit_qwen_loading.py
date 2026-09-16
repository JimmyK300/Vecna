#!/usr/bin/env python3
"""Audit the exact current Qwen constructor, without inference or database use.

Usage: python -B -u audit_qwen_loading.py REPO_ROOT RUNTIME_CONFIG NEW_OUTPUT_DIR
This allocates one Qwen model. It preserves the ordinary SentenceTransformer
constructor and observes complete AutoModel loading info without substituting
the separately validated temporal wrapper or changing checkpoint key mappings.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import json
import os
import sys
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path


class AuditError(RuntimeError):
    """A safe, explicit audit-contract failure."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_id(obj):
    path = Path(inspect.getfile(obj))
    raw = path.read_bytes()
    return {"path": str(path), "sha256": sha(raw),
            "lf_sha256": sha(raw.decode("utf-8-sig").replace("\r\n", "\n").encode())}


def safe_loading_metadata(value, dtype_type=()):
    """Explicit JSON normalization; integer label keys require no collisions."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dtype_type):
        return str(value)
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if isinstance(key, str):
                normalized_key = key
            elif type(key) is int:
                normalized_key = str(key)
            else:
                raise AuditError("Unsupported key type in structured loading metadata")
            if normalized_key in result:
                raise AuditError("Integer/string key collision in structured loading metadata")
            result[normalized_key] = safe_loading_metadata(item, dtype_type)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        return [safe_loading_metadata(item, dtype_type) for item in value]
    raise AuditError("Unsupported structured loading-information type")


def main():
    if len(sys.argv) != 4:
        raise AuditError("Expected REPO_ROOT RUNTIME_CONFIG NEW_OUTPUT_DIR")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    root = Path(sys.argv[1]).resolve()
    config_path = Path(sys.argv[2]).resolve()
    out = Path(sys.argv[3]).resolve()
    allowed = (root / "benchmark-results/astra-retrieval-rd-v1/outputs/fusion").resolve()
    if not out.is_relative_to(allowed):
        raise AuditError("Output must be in scoped fusion artifacts")
    out.mkdir(parents=True, exist_ok=False)
    report = {"schema": "vecna82-qwen-loading-info-v1", "status": "starting", "load_calls": [],
              "model_inference": False, "database_access": False,
              "checkpoint_mapping_changed": False, "text_weight_equality_verified": False,
              "validity_verdict": "NOT_ESTABLISHED_BY_CONSTRUCTOR_COMPLETION"}

    def dump():
        temp = out / "loading_info.json.tmp"
        temp.write_text(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
                        encoding="utf-8", newline="\n")
        os.replace(temp, out / "loading_info.json")

    dump()
    try:
        import yaml
        import torch
        torch.set_num_threads(6)
        from transformers import AutoModel
        from sentence_transformers.base.modules.transformer import Transformer
        sys.path.insert(0, str(root / "aic51-src"))
        from aic51.packages.analyse.features.qwen_vl import QwenVLEmbedding
        def plain(value):
            return safe_loading_metadata(value, torch.dtype)

        report["versions"] = {name: importlib.metadata.version(name)
                              for name in ["torch", "transformers", "sentence-transformers"]}
        report["threads"] = {"intraop": torch.get_num_threads(), "interop": torch.get_num_interop_threads()}
        report["extractor_source"] = source_id(QwenVLEmbedding)
        report["st_transformer_source"] = source_id(Transformer)
        if report["extractor_source"]["lf_sha256"] != "2b49052e371f9cb7b0299392a5e81c6433c09941b5bc95056c9aebcda285de80":
            raise AuditError("Pinned Qwen extractor source mismatch")
        if report["st_transformer_source"]["lf_sha256"] != "72f81977845250ac3da432c6201b19a5d6b24c13250c32bb5d1e5c80da95d61a":
            raise AuditError("Pinned ST loader source mismatch")
        if report["versions"]["transformers"] != "4.57.6" or report["versions"]["sentence-transformers"] != "5.4.0":
            raise AuditError("Package version mismatch")
        raw = config_path.read_bytes()
        report["runtime_config_sha256"] = sha(raw)
        config = yaml.safe_load(raw)
        entries = [(name, desc) for name, desc in config.get("searcher", {}).get("language_models", {}).items()
                   if "qwen_vl" in (desc.get("target") or [])]
        if len(entries) != 1:
            raise AuditError("Expected exactly one Qwen declaration")
        name, desc = entries[0]
        if desc.get("model") != "qwen_vl_embedding":
            raise AuditError("Unexpected Qwen extractor class")
        report["declaration"] = {key: desc[key] for key in ["model", "pretrained_model", "arch_name", "target"]
                                 if key in desc}
        init_kwargs = {"source": desc.get("source"), "arch_name": desc.get("arch_name"),
                       "pretrained_model": desc.get("pretrained_model"), "text_source": desc.get("text_source"),
                       "name": name, "batch_size": 1, "device": torch.device("cpu")}
        del config, entries, desc, raw
        original = AutoModel.from_pretrained
        absent = object()
        previous_local = AutoModel.__dict__.get("from_pretrained", absent)

        def capture(cls, *args, **kwargs):
            if kwargs.get("output_loading_info"):
                raise AuditError("Unexpected preexisting loading-info request")
            result = original(*args, **dict(kwargs, output_loading_info=True))
            if not isinstance(result, tuple) or len(result) != 2:
                raise AuditError("Unexpected AutoModel loading-info return")
            model, info = result
            # Persist the primary evidence before any optional config/source
            # introspection. A metadata error must never erase loaded-key info.
            primary = {key: plain(info[key]) for key in
                       ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs") if key in info}
            call = {"model_class": type(model).__module__ + "." + type(model).__qualname__,
                    "loading_info": primary}
            report["load_calls"].append(call)
            report["status"] = "checkpoint_loaded"
            dump()
            schema = {"schema": "vecna82-qwen-expected-state-v1", "model_class": call["model_class"],
                      "tensors": [{"name": name, "shape": list(tensor.shape), "dtype": str(tensor.dtype),
                                   "device": str(tensor.device)}
                                  for name, tensor in sorted(model.state_dict().items())]}
            schema["tensor_count"] = len(schema["tensors"])
            schema_bytes = (json.dumps(schema, indent=2, sort_keys=True) + "\n").encode()
            schema_path = out / "expected_state_schema.json"
            with schema_path.open("xb") as handle:
                handle.write(schema_bytes)
            call["expected_state_schema"] = {"path": schema_path.name, "sha256": sha(schema_bytes),
                                              "tensor_count": schema["tensor_count"]}
            dump()
            safe_config = {key: getattr(model.config, key, None)
                           for key in ["_name_or_path", "_commit_hash", "model_type", "architectures"]}
            loader_keys = ["torch_dtype", "dtype", "revision", "subfolder", "key_mapping", "local_files_only",
                           "trust_remote_code", "attn_implementation"]
            try:
                call.update(plain({
                    "model_source": source_id(type(model)), "model_config": safe_config,
                    "model_config_sha256": sha(json.dumps(plain(model.config.to_dict()), sort_keys=True,
                                                           allow_nan=False).encode()),
                    "model_config_json_key_policy": "Integer label keys converted to decimal strings; collisions rejected",
                    "base_model_prefix": getattr(model, "base_model_prefix", None),
                    "class_checkpoint_conversion_mapping": getattr(type(model), "_checkpoint_conversion_mapping", None),
                    "safe_loader_kwargs": {key: kwargs[key] for key in loader_keys if key in kwargs},
                }))
            except Exception as exc:
                call["optional_metadata_error"] = type(exc).__name__
            dump()
            return model

        AutoModel.from_pretrained = classmethod(capture)
        try:
            extractor = QwenVLEmbedding.from_pretrained(**init_kwargs)
        finally:
            if previous_local is absent:
                delattr(AutoModel, "from_pretrained")
            else:
                setattr(AutoModel, "from_pretrained", previous_local)
        if len(report["load_calls"]) != 1:
            raise AuditError("Expected one captured Qwen AutoModel load")
        report["status"] = "constructor_complete"
        del extractor
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        if isinstance(exc, AuditError):
            report["contract_error"] = str(exc)
        report["error_frames"] = [{"file": frame.filename, "line": frame.lineno, "function": frame.name}
                                  for frame in traceback.extract_tb(exc.__traceback__)]
    finally:
        dump()
    print(json.dumps({"status": report["status"], "load_calls": len(report["load_calls"]),
                      "report": str(out / "loading_info.json")}), flush=True)
    return 0 if report["status"] == "constructor_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
