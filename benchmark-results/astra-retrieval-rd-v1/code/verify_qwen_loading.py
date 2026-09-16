#!/usr/bin/env python3
"""Verify the declared Qwen loader repair with one ordinary ST construction.

No inference or database access. The reviewed production helper compares every
loaded tensor to its checkpoint in bounded chunks; this audit binds that helper,
the checkpoint bytes, complete AutoModel loading info and the resulting proof.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import struct
import sys
import traceback
from pathlib import Path

from audit_qwen_loading import AuditError, safe_loading_metadata, source_id


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_sha(path):
    return hashlib.sha256(Path(path).read_text(encoding="utf-8-sig").encode()).hexdigest()


def require_complete_proof(call, proof):
    fields = ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")
    info = call.get("loading_info", {})
    if any(key not in info or not isinstance(info[key], list) or info[key] for key in fields):
        raise AuditError("Checkpoint loading discrepancies remain or loading information is incomplete")
    if call.get("expected_state_schema", {}).get("tensor_count") != 625:
        raise AuditError("Loaded Qwen state does not contain the frozen625 tensors")
    if proof.get("status") != "VERIFIED_ALL_CHECKPOINT_TENSORS" or proof.get("tensor_count") != 625:
        raise AuditError("Complete625-tensor equality proof is missing")
    if proof.get("second_model_loaded") is not False:
        raise AuditError("Checkpoint proof does not establish the one-model constraint")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_root", type=Path)
    parser.add_argument("runtime_config", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--expected-extractor-lf-sha256", required=True)
    parser.add_argument("--expected-helper-lf-sha256", required=True)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--expected-checkpoint-sha256", required=True)
    args = parser.parse_args()
    for value in (args.expected_extractor_lf_sha256, args.expected_helper_lf_sha256,
                  args.expected_checkpoint_sha256):
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            parser.error("Every expected source/checkpoint hash must be an exact lowercase SHA256")
    root, out = args.runtime_root.resolve(), args.output_dir.resolve()
    allowed = root / "benchmark-results/astra-retrieval-rd-v1/outputs/fusion"
    if not out.is_relative_to(allowed):
        raise AuditError("Output must be in scoped fusion artifacts")
    out.mkdir(parents=True, exist_ok=False)
    report = {"schema": "vecna82-qwen-repair-verification-v1", "status": "starting", "load_calls": [],
              "model_inference": False, "database_access": False, "audit_changes_checkpoint_mapping": False,
              "checkpoint_tensor_equality_verified": False, "expected_tensor_count": 625}

    def dump():
        temp = out / "verification.json.tmp"
        temp.write_text(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
                        encoding="utf-8", newline="\n")
        os.replace(temp, out / "verification.json")

    dump()
    try:
        extractor_path = root / "aic51-src/aic51/packages/analyse/features/qwen_vl.py"
        helper_path = extractor_path.with_name("qwen_vl_checkpoint.py")
        if source_sha(extractor_path) != args.expected_extractor_lf_sha256:
            raise AuditError("Repaired extractor differs from the declared source")
        if source_sha(helper_path) != args.expected_helper_lf_sha256:
            raise AuditError("Checkpoint verifier differs from the declared source")
        checkpoint = args.checkpoint.resolve()
        report["checkpoint"] = {"path": str(checkpoint), "bytes": checkpoint.stat().st_size,
                                "sha256": file_sha(checkpoint)}
        if report["checkpoint"]["sha256"] != args.expected_checkpoint_sha256:
            raise AuditError("Actual checkpoint bytes differ from the frozen model identity")
        with checkpoint.open("rb") as handle:
            header_size = struct.unpack("<Q", handle.read(8))[0]
            if not 0 < header_size < 16 * 1024 * 1024:
                raise AuditError("Invalid checkpoint header size")
            header_bytes = handle.read(header_size)
        if len(header_bytes) != header_size:
            raise AuditError("Incomplete checkpoint header")
        header = json.loads(header_bytes)
        keys = {key for key in header if key != "__metadata__"}
        if len(keys) != 625:
            raise AuditError("Frozen checkpoint does not contain625 tensors")
        report["checkpoint"].update(header_sha256=hashlib.sha256(header_bytes).hexdigest(), tensor_count=len(keys))
        checkpoint_schema = {"schema": "vecna82-qwen-checkpoint-state-v1",
                             "checkpoint_sha256": report["checkpoint"]["sha256"],
                             "header_sha256": report["checkpoint"]["header_sha256"], "tensor_count": len(keys),
                             "tensors": [{"name": key, "shape": header[key]["shape"], "dtype": header[key]["dtype"]}
                                         for key in sorted(keys)]}
        schema_bytes = (json.dumps(checkpoint_schema, indent=2, sort_keys=True) + "\n").encode()
        with (out / "checkpoint_state_schema.json").open("xb") as handle:
            handle.write(schema_bytes)
        report["checkpoint_state_schema"] = {"path": "checkpoint_state_schema.json", "tensor_count": len(keys),
                                               "sha256": hashlib.sha256(schema_bytes).hexdigest()}
        report["audit_sources"] = {Path(__file__).name: file_sha(Path(__file__)),
                                   "audit_qwen_loading.py": file_sha(Path(__file__).with_name("audit_qwen_loading.py"))}
        report["declared_source_lf_sha256"] = {"qwen_vl.py": args.expected_extractor_lf_sha256,
                                               "qwen_vl_checkpoint.py": args.expected_helper_lf_sha256}
        dump()
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        sys.dont_write_bytecode = True
        import yaml
        import torch
        torch.set_num_threads(6)
        from transformers import AutoModel
        from sentence_transformers.base.modules.transformer import Transformer
        sys.path.insert(0, str(root / "aic51-src"))
        from aic51.packages.analyse.features.qwen_vl import QwenVLEmbedding
        from aic51.packages.analyse.features.qwen_vl_checkpoint import CheckpointLoadError, verify_loaded_checkpoint
        if Path(inspect.getfile(QwenVLEmbedding)).resolve() != extractor_path.resolve():
            raise AuditError("Repaired extractor import resolved outside the declared checkout")
        if Path(inspect.getfile(verify_loaded_checkpoint)).resolve() != helper_path.resolve():
            raise AuditError("Checkpoint verifier import resolved outside the declared checkout")
        report["versions"] = {name: importlib.metadata.version(name)
                              for name in ("torch", "transformers", "sentence-transformers", "safetensors")}
        if report["versions"]["transformers"] != "4.57.6" or report["versions"]["sentence-transformers"] != "5.4.0":
            raise AuditError("Package versions differ from the observed loading contract")
        report["st_transformer_source"] = source_id(Transformer)
        if report["st_transformer_source"]["lf_sha256"] != "72f81977845250ac3da432c6201b19a5d6b24c13250c32bb5d1e5c80da95d61a":
            raise AuditError("ST loader source differs from the frozen inspection")
        report["threads"] = {"intraop": torch.get_num_threads(), "interop": torch.get_num_interop_threads()}
        raw = args.runtime_config.read_bytes()
        report["runtime_config_sha256"] = hashlib.sha256(raw).hexdigest()
        config = yaml.safe_load(raw)
        declarations = [(name, desc) for name, desc in config.get("searcher", {}).get("language_models", {}).items()
                        if "qwen_vl" in (desc.get("target") or [])]
        if len(declarations) != 1 or declarations[0][1].get("model") != "qwen_vl_embedding":
            raise AuditError("Expected the frozen single Qwen extractor declaration")
        name, desc = declarations[0]
        report["declaration"] = {key: desc[key] for key in ("model", "pretrained_model", "arch_name", "target")
                                 if key in desc}
        init_kwargs = {"source": desc.get("source"), "arch_name": desc.get("arch_name"),
                       "pretrained_model": desc.get("pretrained_model"), "text_source": desc.get("text_source"),
                       "name": name, "batch_size": 1, "device": torch.device("cpu")}
        del config, declarations, desc, raw
        original = AutoModel.from_pretrained
        absent = object()
        previous_local = AutoModel.__dict__.get("from_pretrained", absent)

        def plain(value):
            return safe_loading_metadata(value, torch.dtype)

        def capture(cls, *values, **kwargs):
            if kwargs.get("output_loading_info"):
                raise AuditError("Unexpected existing loading-info request")
            model, info = original(*values, **dict(kwargs, output_loading_info=True))
            primary = {key: plain(info[key]) for key in
                       ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs") if key in info}
            call = {"model_class": type(model).__module__ + "." + type(model).__qualname__, "loading_info": primary}
            report["load_calls"].append(call)
            report["status"] = "checkpoint_loaded"
            dump()
            schema = {"schema": "vecna82-qwen-expected-state-v1", "model_class": call["model_class"],
                      "tensors": [{"name": key, "shape": list(value.shape), "dtype": str(value.dtype),
                                   "device": str(value.device)} for key, value in sorted(model.state_dict().items())]}
            schema["tensor_count"] = len(schema["tensors"])
            payload = (json.dumps(schema, sort_keys=True, indent=2) + "\n").encode()
            with (out / "expected_state_schema.json").open("xb") as handle:
                handle.write(payload)
            call["expected_state_schema"] = {"path": "expected_state_schema.json", "tensor_count": schema["tensor_count"],
                                              "sha256": hashlib.sha256(payload).hexdigest()}
            call["model_source"] = source_id(type(model))
            call["resolved_commit_hash"] = getattr(model.config, "_commit_hash", None)
            call["safe_loader_kwargs"] = plain({key: kwargs[key] for key in
                ("torch_dtype", "dtype", "revision", "key_mapping", "local_files_only", "attn_implementation") if key in kwargs})
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
            raise AuditError("Expected exactly one ordinary Qwen AutoModel load")
        proof = plain(getattr(extractor, "_checkpoint_validation", {}))
        report["checkpoint_validation"] = proof
        dump()
        require_complete_proof(report["load_calls"][0], proof)
        verified_files = [Path(proof["checkpoint_directory"]) / name for name in proof["checkpoint_files"]]
        if len(verified_files) != 1 or verified_files[0].resolve() != checkpoint:
            raise AuditError("Verified model used a different checkpoint file")
        if source_sha(helper_path) != args.expected_helper_lf_sha256 or source_sha(extractor_path) != args.expected_extractor_lf_sha256:
            raise AuditError("Repaired source changed during verification")
        report["checkpoint_tensor_equality_verified"] = True
        report["status"] = "verified"
        report["validity_scope"] = "All625 loaded values equal the actual hashed checkpoint after dtype cast; unchanged ST pipeline. No index lineage or historical C loader claim."
        del extractor
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        if isinstance(exc, AuditError) or type(exc).__name__ == "CheckpointLoadError":
            report["contract_error"] = str(exc)
        report["error_frames"] = [{"file": frame.filename, "line": frame.lineno, "function": frame.name}
                                  for frame in traceback.extract_tb(exc.__traceback__)]
    finally:
        dump()
    print(json.dumps({"status": report["status"], "load_calls": len(report["load_calls"]),
                      "checkpoint_tensor_equality_verified": report["checkpoint_tensor_equality_verified"],
                      "report": str(out / "verification.json")}), flush=True)
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
