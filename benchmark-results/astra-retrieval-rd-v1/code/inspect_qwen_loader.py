#!/usr/bin/env python3
"""Read cached Qwen metadata and loader source without importing model libraries.

Usage: python -B -u inspect_qwen_loader.py REPO_ROOT RUNTIME_CONFIG [OUTPUT_JSONL]
No model construction, tensor allocation, query inference, network, or DB calls.
Only safe config fields are emitted. Optional output is a fresh research file.
"""
import ast
import collections
import hashlib
import importlib.metadata
import json
import struct
import sys
import sysconfig
from pathlib import Path

import yaml

root = Path(sys.argv[1])
config_path = Path(sys.argv[2])
site = Path(sysconfig.get_paths()["purelib"])
hub = Path("C:/Users/minhc/.cache/huggingface/hub/models--Qwen--Qwen3-VL-Embedding-2B")
snapshot = hub / "snapshots/9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda"
records = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def emit(kind, **fields):
    records.append(dict(kind=kind, **fields))


def selected(data, keys):
    return {key: data[key] for key in keys if key in data}


cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
for name, desc in cfg.get("searcher", {}).get("language_models", {}).items():
    if "qwen_vl" in (desc.get("target") or []):
        emit("safe_qwen_declaration", name=name,
             fields=selected(desc, ["model", "pretrained_model", "arch_name", "target"]))
del cfg
emit("runtime", python=sys.version, executable=sys.executable,
     versions={name: importlib.metadata.version(name)
               for name in ["sentence-transformers", "transformers", "torch"]})
ref = hub / "refs/main"
emit("cached_ref", name="main", exists=ref.is_file(),
     value=ref.read_text().strip() if ref.is_file() else None)

for path in [snapshot / "config.json", snapshot / "modules.json",
             snapshot / "config_sentence_transformers.json", snapshot / "sentence_bert_config.json",
             snapshot / "1_Pooling/config.json"]:
    if not path.is_file():
        emit("checkpoint_json", name=str(path.relative_to(snapshot)), exists=False)
        continue
    raw = path.read_bytes()
    data = json.loads(raw)
    if isinstance(data, list):
        fields = [selected(value, ["idx", "name", "path", "type"])
                  for value in data if isinstance(value, dict)]
    else:
        fields = selected(data, ["architectures", "model_type", "torch_dtype", "dtype", "auto_map",
                                 "max_seq_length", "do_lower_case", "default_prompt_name",
                                 "pooling_mode", "pooling_mode_lasttoken", "pooling_mode_mean_tokens",
                                 "include_prompt", "word_embedding_dimension"])
        for key in ["model_kwargs", "model_args"]:
            if isinstance(data.get(key), dict):
                fields[key] = selected(data[key], ["torch_dtype", "dtype", "revision", "key_mapping",
                                                   "trust_remote_code", "attn_implementation"])
        if "prompts" in data:
            fields["prompts_sha256"] = sha(json.dumps(data["prompts"], sort_keys=True).encode())
    emit("checkpoint_json", name=str(path.relative_to(snapshot)), sha256=sha(raw), fields=fields)

path = snapshot / "model.safetensors"
with path.open("rb") as handle:
    size = struct.unpack("<Q", handle.read(8))[0]
    if not 0 < size < 16 * 1024 * 1024:
        raise RuntimeError("Unexpected safetensors header length")
    raw = handle.read(size)
    if len(raw) != size:
        raise RuntimeError("Short safetensors header")
header = json.loads(raw)
tensors = {key: value for key, value in header.items() if key != "__metadata__"}
groups = collections.Counter(".".join(key.split(".")[:2]) for key in tensors)
emit("checkpoint_header", path=str(path), file_bytes=path.stat().st_size, header_bytes=size,
     header_sha256=sha(raw), tensor_count=len(tensors), prefix_counts=dict(sorted(groups.items())),
     dtype_counts=dict(collections.Counter(value["dtype"] for value in tensors.values())))
for marker in ["language_model", "visual"]:
    names = sorted(key for key in tensors if marker in key)
    emit("checkpoint_key_samples", marker=marker, count=len(names),
         samples=[dict(name=key, shape=tensors[key]["shape"], dtype=tensors[key]["dtype"])
                  for key in names[:4] + names[-2:]])


def source(path, class_name=None, methods=(), first_lines=None, markers=()):
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    lines, snippets = text.splitlines(), []
    tree = ast.parse(text)
    scope = next((node for node in ast.walk(tree)
                  if isinstance(node, ast.ClassDef) and node.name == class_name), tree) if class_name else tree
    for name in methods:
        node = next((node for node in ast.walk(scope)
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name), None)
        if node:
            snippets.append({"method": name, "start": node.lineno,
                             "text": "\n".join(lines[node.lineno - 1:node.end_lineno])})
    if first_lines and isinstance(scope, ast.ClassDef):
        snippets.append({"class": class_name,
                         "text": "\n".join(lines[scope.lineno - 1:scope.lineno - 1 + first_lines])})
    for marker in markers:
        for index, line in enumerate(lines):
            if marker in line:
                snippets.append({"marker": marker, "start": max(1, index - 2),
                                 "text": "\n".join(lines[max(0, index - 3):index + 7])})
    emit("source", path=str(path), sha256=sha(raw),
         lf_sha256=sha(text.replace("\r\n", "\n").encode()), snippets=snippets)


source(root / "aic51-src/aic51/packages/analyse/features/qwen_vl.py", "QwenVLEmbedding",
       methods=["__init__", "get_text_features"])
source(site / "sentence_transformers/base/modules/transformer.py", "Transformer", methods=["_load_model"])
source(site / "transformers/models/qwen3_vl/modeling_qwen3_vl.py", "Qwen3VLModel", first_lines=18,
       markers=["if pixel_values is not None:", "if pixel_values_videos is not None:"])
source(site / "transformers/modeling_utils.py", "PreTrainedModel",
       methods=["_get_key_renaming_mapping"], markers=["has_prefix_module = any("])

payload = "".join(json.dumps(record, ensure_ascii=True) + "\n" for record in records)
if len(sys.argv) > 3:
    output = Path(sys.argv[3])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(json.dumps({"records": len(records), "output": str(output),
                      "bytes": len(payload.encode()), "sha256": sha(payload.encode())}))
else:
    print(payload, end="")
