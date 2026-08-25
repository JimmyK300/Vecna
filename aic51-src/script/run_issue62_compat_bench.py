#!/usr/bin/env python3
"""Issue #62 local compatibility-matrix benchmark (benchmark/report only).

Measures the model/harness combinations that already exist locally:

  harnesses
    pytorch-cpu       primary venv, torch CPU build
    pytorch-directml  .venv-amd, torch-directml on AMD Radeon RX 6900 XT
    onnxruntime-cpu   primary venv, ONNX Runtime CPUExecutionProvider

  models (identifiers read from the repo config.yaml)
    image_clip_pe-l-14-336      open_clip PE-Core-L-14-336 / meta
    image_siglip_so400m-384     open_clip ViT-SO400M-14-SigLIP-384 / webli
    qwen_vl                     Qwen/Qwen3-VL-Embedding-2B (bf16 on CPU)
    text_bge_m3                 BAAI/bge-m3 (pytorch + local ONNX artifact)

Workload: N keyframes from data-staging/keyframes/sample_video (read-only)
plus a fixed set of vi/en query strings. Image-embedding throughput and
query-time text latency are measured separately per issue #62.

Hard rules enforced here:
  * zero downloads: HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1 in workers
  * shared venvs are used read-only (PYTHONDONTWRITEBYTECODE=1)
  * writes only inside --output-dir

Usage:
  python run_issue62_compat_bench.py --output-dir benchmark-results/issue62-compat-bench
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = Path(__file__).resolve()

DEFAULT_OUTPUT = REPO_ROOT / "benchmark-results" / "issue62-compat-bench"
DEFAULT_VENV_CPU = Path(r"C:\Users\minhc\Code\Vecna\.venv")
DEFAULT_VENV_DML = Path(r"C:\Users\minhc\Code\Vecna\.venv-amd")
DEFAULT_FRAMES_DIR = Path(r"C:\Users\minhc\Code\Vecna\data-staging\keyframes\sample_video")
DEFAULT_CONFIG = REPO_ROOT / "config.yaml"

QUERY_TEXTS = [
    "một người đang cầm micro trên sân khấu",
    "cảnh quay bên trong nhà bếp có khói",
    "hai người đang chơi bóng rổ trong nhà thi đấu",
    "a person holding a microphone on a stage",
    "smoke inside a kitchen while cooking",
    "two people playing basketball in an arena",
]

IMAGE_BATCH_LEVELS = [1, 4, 16, 32, 64]
TEXT_REPS = 3
IMAGE_REPS = 2


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _psapi_memory_info():
    import ctypes.wintypes as wt

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    pmc = PROCESS_MEMORY_COUNTERS()
    pmc.cb = ctypes.sizeof(pmc)
    psapi = ctypes.WinDLL("psapi")
    k32 = ctypes.WinDLL("kernel32")
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), ctypes.c_ulong]
    psapi.GetProcessMemoryInfo.restype = ct = ctypes.c_int
    k32.GetCurrentProcess.restype = wt.HANDLE
    handle = k32.GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb)
    return int(pmc.PeakWorkingSetSize), int(pmc.WorkingSetSize), bool(ok)


def peak_working_set_kb() -> int:
    peak, _, _ = _psapi_memory_info()
    return peak


def rss_now_bytes() -> int:
    _, ws, _ = _psapi_memory_info()
    return ws


def error_signature(exc: BaseException) -> dict:
    import traceback as _tb

    msg = str(exc).strip()
    first_line = msg.splitlines()[0][:300] if msg else ""
    origin = ""
    tb = exc.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    if tb is not None:
        frame = tb.tb_frame
        code = frame.f_code
        origin = f"{Path(code.co_filename).name}:{tb.tb_lineno} in {code.co_name}"
    raw = f"{type(exc).__module__}.{type(exc).__name__}:{first_line}:{origin}"
    return {
        "error_class": type(exc).__name__,
        "error_message": first_line or origin,
        "error_origin": origin,
        "error_signature_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


# ---------------------------------------------------------------------------
# worker mode: runs one cell in whatever interpreter launched this process
# ---------------------------------------------------------------------------

def load_config_features(config_path: Path) -> dict:
    features = {}
    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        for name, spec in (cfg.get("features") or {}).items():
            if isinstance(spec, dict) and "model" in spec:
                features[name] = spec
        searcher_lm = ((cfg.get("searcher") or {}).get("language_models")) or {}
        for name, spec in searcher_lm.items():
            if isinstance(spec, dict) and "model" in spec and name not in features:
                features[name] = spec
    except Exception:
        pass
    return features


def worker_openclip(arch: str, pretrained: str, frames: list[str], queries: list[str],
                    side: str, batch_levels: list[int], device_mode: str,
                    deadline_s: float) -> dict:
    import open_clip
    import torch

    if device_mode == "dml":
        import torch_directml

        device = torch_directml.device()
        device_name = torch_directml.device_name(0).strip("\x00 ")
    else:
        device = torch.device("cpu")
        device_name = "cpu"

    rec: dict = {"device_resolved": f"{device}", "device_name": device_name}
    t0 = time.perf_counter()
    model, _, preprocess = open_clip.create_model_and_transforms(arch, pretrained)
    tokenizer_meta = {"path": "open_clip.get_tokenizer", "fallback": None}
    try:
        raw_tok = open_clip.get_tokenizer(arch)
    except Exception as exc:
        sig = error_signature(exc)
        tokenizer_meta["fallback"] = (
            "PreTrainedTokenizerFast(tokenizer.json) - AutoTokenizer offline "
            f"load failed: {sig['error_class']}: {sig['error_message'][:160]}"
        )
        hub_dir = Path(os.path.expanduser("~")) / ".cache" / "huggingface" / "hub"
        snap = next((hub_dir / f"models--timm--{arch}").glob("snapshots/*"), None)
        if snap is None or not (snap / "tokenizer.json").is_file():
            raise
        from transformers import PreTrainedTokenizerFast

        raw_tok = PreTrainedTokenizerFast(tokenizer_file=str(snap / "tokenizer.json"))
        cfg_path = snap / "tokenizer_config.json"
        if cfg_path.is_file():
            tcfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            for key in ("pad_token", "eos_token", "bos_token"):
                val = tcfg.get(key)
                content = val.get("content") if isinstance(val, dict) else val
                if isinstance(content, str) and getattr(raw_tok, key, None) is None:
                    try:
                        setattr(raw_tok, key, content)
                    except Exception:
                        pass
            if getattr(raw_tok, "pad_token", None) is None:
                raw_tok.pad_token = raw_tok.eos_token or "[PAD_EOS_MISSING]"
        else:
            raw_tok.pad_token = raw_tok.eos_token or "[PAD_EOS_MISSING]"

    ctx = model.context_length
    context_length = int(ctx[0]) if isinstance(ctx, (tuple, list)) else int(ctx)

    class _TokAdapter:
        """Mirrors open_clip HFTokenizer semantics: returns padded/truncated input_ids."""

        def __init__(self, inner):
            self._inner = inner
            self.context_length = context_length

        def __call__(self, texts):
            out = self._inner(list(texts))
            if torch.is_tensor(out):
                return out
            enc = self._inner(
                list(texts), return_tensors="pt", max_length=context_length,
                padding="max_length", truncation=True)
            ids = enc.input_ids
            return torch.as_tensor(ids)

    tok = _TokAdapter(raw_tok)
    probe_out = tok(["probe"])
    tokenizer_meta["returns_tensor"] = bool(torch.is_tensor(probe_out))
    tokenizer_meta["context_length"] = context_length
    model = model.to(device).eval()
    rec["load_s"] = round(time.perf_counter() - t0, 3)

    from PIL import Image

    if side == "embed":
        images = [preprocess(Image.open(p).convert("RGB")) for p in frames]
        warm_start = time.perf_counter()
        with torch.no_grad():
            out = model.encode_image(images[0].unsqueeze(0).to(device)).cpu()
        rec["first_inference_ms"] = round((time.perf_counter() - warm_start) * 1000, 1)
        rec["embed_dim"] = int(out.shape[1])
        rec["precision"] = "fp32"
        rec["batch_results"] = []
        for bs in batch_levels:
            if time.perf_counter() > deadline_s:
                rec["batch_results"].append({"batch": bs, "status": "skipped_time_budget"})
                break
            times = []
            err = None
            for _ in range(IMAGE_REPS):
                t = time.perf_counter()
                try:
                    with torch.no_grad():
                        for i in range(0, len(images), bs):
                            chunk = images[i : i + bs]
                            model.encode_image(torch.stack(chunk).to(device))
                except Exception as exc:  # noqa: BLE001
                    err = error_signature(exc)
                    break
                times.append(time.perf_counter() - t)
            if err is not None:
                rec["batch_results"].append(
                    {"batch": bs, "status": "failed", **err}
                )
                break
            n_imgs = len(images) * IMAGE_REPS
            per_call_ms = sorted(times)[-1] * 1000.0 / IMAGE_REPS
            rec["batch_results"].append({
                "batch": bs,
                "status": "ok",
                "throughput_img_per_s": round(n_imgs / sum(times), 2),
                "p50_batch_ms": round(sorted(times)[len(times) // 2] * 1000 / max(1, len(times)), 1),
                "worst_pass_batch_ms": round(per_call_ms, 1),
            })
        ok_batches = [b for b in rec["batch_results"] if b.get("status") == "ok"]
        if ok_batches:
            best = max(ok_batches, key=lambda r: r["throughput_img_per_s"])
            rec["best_throughput_img_per_s"] = best["throughput_img_per_s"]
            rec["batch_ceiling_tested"] = best["batch"]
    else:
        times = []

        def encode_texts(texts):
            return tok(list(texts)).to(device)

        with torch.no_grad():
            encoded = encode_texts(queries[:1])
            t = time.perf_counter()
            model.encode_text(encoded).cpu()
            rec["first_inference_ms"] = round((time.perf_counter() - t) * 1000, 1)
            for _ in range(TEXT_REPS):
                t = time.perf_counter()
                tf = model.encode_text(encode_texts(queries))
                times.append(time.perf_counter() - t)
        rec["query_latency_p50_ms"] = round(sorted(times)[len(times) // 2] * 1000 / len(queries), 2)
        rec["query_throughput_text_per_s"] = round(len(queries) * TEXT_REPS / sum(times), 2)
        rec["embed_dim_text"] = int(tf.shape[1])
        rec["precision"] = "fp32"
    rec["tokenizer_meta"] = tokenizer_meta
    return rec


def worker_qwen(frames: list[str], queries: list[str], side: str, device_mode: str,
                dtype_mode: str, max_pixels: int, deadline_s: float) -> dict:
    import torch
    import numpy as np
    from transformers.models.qwen3_vl.modeling_qwen3_vl import (
        Qwen3VLModel,
        Qwen3VLPreTrainedModel,
    )
    from transformers.models.qwen3_vl.processing_qwen3_vl import Qwen3VLProcessor
    from transformers.modeling_outputs import ModelOutput

    MODEL_ID = "Qwen/Qwen3-VL-Embedding-2B"
    QUERY_INSTRUCTION = "Retrieve images or text relevant to the user's query."
    DEFAULT_INSTRUCTION = "Represent the user's input."

    class Qwen3VLForEmbedding(Qwen3VLPreTrainedModel):
        def __init__(self, config):
            super().__init__(config)
            self.model = Qwen3VLModel(config)
            self.post_init()

        def forward(self, input_ids=None, attention_mask=None, pixel_values=None,
                    image_grid_thw=None, **kw):
            out = self.model(input_ids=input_ids, attention_mask=attention_mask,
                             pixel_values=pixel_values, image_grid_thw=image_grid_thw)
            return ModelOutput(last_hidden_state=out.last_hidden_state,
                               attention_mask=attention_mask)

    if device_mode == "dml":
        import torch_directml

        device = torch_directml.device()
        device_name = torch_directml.device_name(0).strip("\x00 ")
    else:
        device = torch.device("cpu")
        device_name = "cpu"

    rec: dict = {"device_resolved": f"{device}", "device_name": device_name}
    dtype = {"bf16": torch.bfloat16, "fp32": torch.float32}[dtype_mode]
    rec["dtype_requested"] = str(dtype)

    t0 = time.perf_counter()
    model = Qwen3VLForEmbedding.from_pretrained(MODEL_ID, dtype=dtype).to(device).eval()
    proc = Qwen3VLProcessor.from_pretrained(MODEL_ID, padding_side="right")
    rec["load_s"] = round(time.perf_counter() - t0, 3)

    def encode(items):
        convs = []
        for it in items:
            content = []
            if it.get("image") is not None:
                content.append({"type": "image", "image": "file://" + it["image"],
                                "min_pixels": 4 * 32 * 32, "max_pixels": max_pixels})
            content.append({"type": "text", "text": it.get("text", "NULL")})
            instr = it.get("instruction", DEFAULT_INSTRUCTION)
            convs.append([
                {"role": "system", "content": [{"type": "text", "text": instr}]},
                {"role": "user", "content": content},
            ])
        text = proc.apply_chat_template(convs, add_generation_prompt=True, tokenize=False)
        images = [[it["image"]] for it in items if it.get("image")]
        flat_images = [im for group in images for im in group]
        kwargs = {}
        if flat_images:
            kwargs["images"] = [Image.open(p).convert("RGB") for p in flat_images]
        inp = proc(text=text, padding=True, truncation=True, max_length=8192,
                   return_tensors="pt", **kwargs)
        inp = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inp.items()}
        with torch.no_grad():
            out = model(**inp)
            am = inp["attention_mask"]
            last = am.shape[1] - am.flip(dims=[1]).argmax(dim=1) - 1
            rows = torch.arange(out.last_hidden_state.shape[0], device=device)
            emb = out.last_hidden_state[rows, last]
            emb = torch.nn.functional.normalize(emb, p=2, dim=-1).float().cpu().numpy()
        if emb.ndim != 2 or not np.isfinite(emb).all():
            raise RuntimeError("non-finite embedding")
        return emb

    from PIL import Image  # noqa: F401  (used via proc images kwarg path above)

    if side == "embed":
        t = time.perf_counter()
        e = encode([{"image": frames[0], "instruction": DEFAULT_INSTRUCTION}])
        rec["first_inference_ms"] = round((time.perf_counter() - t) * 1000, 1)
        rec["embed_dim"] = int(e.shape[1])
        times = []
        done_frames = 0
        for p in frames:
            if time.perf_counter() > deadline_s:
                rec["frames_completed"] = done_frames
                break
            t = time.perf_counter()
            encode([{"image": p, "instruction": DEFAULT_INSTRUCTION}])
            times.append(time.perf_counter() - t)
            done_frames += 1
        if times:
            rec["frames_completed"] = done_frames
            rec["throughput_img_per_s"] = round(1.0 / (sum(times) / len(times)), 4)
            rec["p50_image_s"] = round(sorted(times)[len(times) // 2], 2)
        rec["batch_ceiling_tested"] = 1
        rec["precision"] = "bf16" if dtype == torch.bfloat16 else "fp32(forced)"
    else:
        items = [{"text": q, "instruction": QUERY_INSTRUCTION} for q in queries[:1]]
        t = time.perf_counter()
        e = encode(items)
        rec["first_inference_ms"] = round((time.perf_counter() - t) * 1000, 1)
        times = []
        for _ in range(TEXT_REPS):
            t = time.perf_counter()
            encode([{"text": q, "instruction": QUERY_INSTRUCTION} for q in queries])
            times.append(time.perf_counter() - t)
        rec["query_latency_p50_ms"] = round(sorted(times)[len(times) // 2] * 1000 / len(queries), 2)
        rec["query_throughput_text_per_s"] = round(len(queries) * TEXT_REPS / sum(times), 2)
        rec["embed_dim_text"] = int(e.shape[1])
        rec["precision"] = "bf16" if dtype == torch.bfloat16 else "fp32(forced)"
    return rec


def worker_bge_pytorch(queries: list[str], device_mode: str, deadline_s: float) -> dict:
    import torch
    from transformers import AutoModel, AutoTokenizer

    MODEL_ID = "BAAI/bge-m3"
    MAX_LEN = 1024  # mirrors aic51 TextEmbedding._pytorch_max_length

    if device_mode == "dml":
        import torch_directml

        device = torch_directml.device()
        device_name = torch_directml.device_name(0).strip("\x00 ")
        dtype = torch.float32
    else:
        device = torch.device("cpu")
        device_name = "cpu"
        dtype = torch.float32

    rec: dict = {"device_resolved": f"{device}", "device_name": device_name}
    t0 = time.perf_counter()
    tokz = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID, torch_dtype=dtype).to(device).eval()
    rec["load_s"] = round(time.perf_counter() - t0, 3)

    def encode(texts):
        batch = tokz(texts, return_tensors="pt", padding=True, truncation=True, max_length=MAX_LEN)
        batch = {k: v.to(device) for k, v in batch.items()}
        with torch.no_grad():
            hs = model(**batch).last_hidden_state
            emb = torch.nn.functional.normalize(hs[:, 0], p=2, dim=-1)
        return emb.cpu().numpy()

    t = time.perf_counter()
    e = encode(queries[:1])
    rec["first_inference_ms"] = round((time.perf_counter() - t) * 1000, 1)
    times = []
    for _ in range(TEXT_REPS):
        t = time.perf_counter()
        encode(queries)
        times.append(time.perf_counter() - t)
    rec.update({
        "query_latency_p50_ms": round(sorted(times)[len(times) // 2] * 1000 / len(queries), 2),
        "query_throughput_text_per_s": round(len(queries) * TEXT_REPS / sum(times), 2),
        "embed_dim_text": int(e.shape[1]),
        "precision": "fp32",
        "pooling": "cls+l2norm",
        "max_length": MAX_LEN,
    })
    return rec


def worker_bge_onnx(queries: list[str]) -> dict:
    import numpy as np
    import onnxruntime as ort
    from pathlib import Path as P
    from transformers import AutoTokenizer

    hub = P(os.path.expanduser("~")) / ".cache/huggingface/hub/models--BAAI--bge-m3/snapshots"
    main_ref = (hub.parent / "refs" / "main").read_text(encoding="utf-8").strip()
    snap = hub / main_ref
    model_path = snap / "onnx" / "model.onnx"
    rec: dict = {"artifact": str(model_path), "device_resolved": "CPUExecutionProvider",
                 "device_name": "CPUExecutionProvider"}
    so = ort.SessionOptions()
    so.intra_op_num_threads = os.cpu_count() or 4
    t0 = time.perf_counter()
    sess = ort.InferenceSession(str(model_path), sess_options=so,
                                providers=["CPUExecutionProvider"])
    tokz = AutoTokenizer.from_pretrained(str(snap))
    rec["session_create_s"] = round(time.perf_counter() - t0, 3)
    rec["providers"] = sess.get_providers()
    inputs_info = {i.name: i.shape for i in sess.get_inputs()}
    rec["inputs"] = inputs_info

    MAX_LEN = 1024

    def encode(texts):
        enc = tokz(texts, padding=True, truncation=True, max_length=MAX_LEN, return_tensors="np")
        feed = {}
        names = set(inputs_info.keys())
        mapping = {"input_ids": "input_ids", "attention_mask": "attention_mask"}
        if any("token_type_ids" in n for n in names):
            mapping["token_type_ids"] = "token_type_ids"
        for local, ortname in mapping.items():
            if ortname in names and local in enc:
                feed[ortname] = enc[local].astype(np.int64)
        out_names = [o.name for o in sess.get_outputs()]
        hidden = sess.run(out_names, feed)[0]
        emb = hidden[:, 0]
        emb = emb / np.maximum(np.linalg.norm(emb, axis=-1, keepdims=True), 1e-12)
        return emb

    t = time.perf_counter()
    e = encode(queries[:1])
    rec["first_inference_ms"] = round((time.perf_counter() - t) * 1000, 1)
    times = []
    for _ in range(TEXT_REPS):
        t = time.perf_counter()
        encode(queries)
        times.append(time.perf_counter() - t)
    rec.update({
        "query_latency_p50_ms": round(sorted(times)[len(times) // 2] * 1000 / len(queries), 2),
        "query_throughput_text_per_s": round(len(queries) * TEXT_REPS / sum(times), 2),
        "embed_dim_text": int(e.shape[1]),
        "finite": bool(np.isfinite(e).all()),
        "precision": "fp32",
        "pooling": "cls+l2norm",
        "max_length": MAX_LEN,
    })
    return rec


def run_worker_cell(spec: dict) -> dict:
    """Executes one measurement cell inside the current interpreter."""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    cell_id = spec["cell_id"]
    result: dict = {"cell_id": cell_id, "harness": spec["harness"], "model": spec["model"],
                    "side": spec["side"]}
    rss_start = rss_now_bytes()
    peak_start = peak_working_set_kb()
    t0 = time.perf_counter()
    try:
        kind = spec["kind"]
        if kind == "openclip":
            payload = worker_openclip(
                arch=spec["arch"], pretrained=spec["pretrained"], frames=spec["frames"],
                queries=spec["queries"], side=spec["side"],
                batch_levels=spec["batch_levels"], device_mode=spec["device_mode"],
                deadline_s=time.perf_counter() + spec["deadline_s"])
        elif kind == "qwen":
            payload = worker_qwen(frames=spec["frames"], queries=spec["queries"],
                                  side=spec["side"], device_mode=spec["device_mode"],
                                  dtype_mode=spec["dtype_mode"],
                                  max_pixels=spec["max_pixels"],
                                  deadline_s=time.perf_counter() + spec["deadline_s"])
        elif kind == "bge_pytorch":
            payload = worker_bge_pytorch(queries=spec["queries"],
                                         device_mode=spec["device_mode"],
                                         deadline_s=time.perf_counter() + spec["deadline_s"])
        elif kind == "bge_onnx":
            payload = worker_bge_onnx(spec["queries"])
        else:
            raise ValueError(f"unknown cell kind {kind}")
        result.update(payload)
        result["status"] = "ok"
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        result.update(error_signature(exc))
    result["wall_s"] = round(time.perf_counter() - t0, 3)
    peak_bytes = max(peak_working_set_kb(), peak_start)
    result["peak_rss_bytes"] = peak_bytes
    result["peak_rss_mb"] = round(peak_bytes / (1024.0 * 1024.0), 1)
    return result


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

def python_version_of(interp: Path) -> str | None:
    try:
        out = subprocess.run([str(interp), "-c", "import platform;print(platform.python_version())"],
                             capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def pip_versions(interp: Path) -> dict:
    code = (
        "import json,importlib.metadata as m;"
        "pkgs=['torch','torchvision','torch-directml','open-clip-torch','transformers',"
        "'numpy','onnxruntime','onnxruntime-directml','tokenizers','pillow','sentence-transformers'];"
        "d={}\nfor p in pkgs:\n"
        "    try: d[p]=m.version(p)\n"
        "    except Exception: d[p]=None\n"
        "print(json.dumps(d))"
    )
    try:
        out = subprocess.run([str(interp), "-c", code], capture_output=True, text=True, timeout=180)
        if out.returncode == 0:
            return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        pass
    return {}


def build_cells(args, features: dict, frames: list[str]) -> list[dict]:
    clip = features.get("image_clip_pe-l-14-336", {})
    siglip = features.get("image_siglip_so400m-384", {})
    cells: list[dict] = []

    def add(harness, interp_root, model, side, kind, extra):
        spec = {
            "cell_id": f"{harness}::{model}::{side}",
            "harness": harness,
            "interp": str(Path(interp_root) / "Scripts" / "python.exe"),
            "model": model,
            "side": side, "kind": kind, "frames": frames, "queries": QUERY_TEXTS,
            "deadline_s": args.cell_timeout,
            "batch_levels": IMAGE_BATCH_LEVELS,
        }
        spec.update(extra)
        cells.append(spec)

    cpu, dml = Path(args.venv_cpu), Path(args.venv_dml)
    # --- pytorch-cpu ---
    add("pytorch-cpu", cpu, "image_clip_pe-l-14-336", "embed", "openclip",
        {"arch": clip.get("arch_name", "PE-Core-L-14-336"),
         "pretrained": clip.get("pretrained_model", "meta"), "device_mode": "cpu"})
    add("pytorch-cpu", cpu, "image_clip_pe-l-14-336", "query_text", "openclip",
        {"arch": clip.get("arch_name", "PE-Core-L-14-336"),
         "pretrained": clip.get("pretrained_model", "meta"), "device_mode": "cpu"})
    add("pytorch-cpu", cpu, "image_siglip_so400m-384", "embed", "openclip",
        {"arch": siglip.get("arch_name", "ViT-SO400M-14-SigLIP-384"),
         "pretrained": siglip.get("pretrained_model", "webli"), "device_mode": "cpu"})
    add("pytorch-cpu", cpu, "image_siglip_so400m-384", "query_text", "openclip",
        {"arch": siglip.get("arch_name", "ViT-SO400M-14-SigLIP-384"),
         "pretrained": siglip.get("pretrained_model", "webli"), "device_mode": "cpu"})
    add("pytorch-cpu", cpu, "qwen_vl", "embed", "qwen",
        {"device_mode": "cpu", "dtype_mode": "bf16",
         "max_pixels": 1800 * 32 * 32, "frames": frames})
    add("pytorch-cpu", cpu, "qwen_vl", "query_text", "qwen",
        {"device_mode": "cpu", "dtype_mode": "bf16", "max_pixels": 1800 * 32 * 32})
    add("pytorch-cpu", cpu, "text_bge_m3_pytorch", "query_text", "bge_pytorch",
        {"device_mode": "cpu"})
    # --- pytorch-directml ---
    add("pytorch-directml", dml, "image_clip_pe-l-14-336", "embed", "openclip",
        {"arch": clip.get("arch_name", "PE-Core-L-14-336"),
         "pretrained": clip.get("pretrained_model", "meta"), "device_mode": "dml"})
    add("pytorch-directml", dml, "image_clip_pe-l-14-336", "query_text", "openclip",
        {"arch": clip.get("arch_name", "PE-Core-L-14-336"),
         "pretrained": clip.get("pretrained_model", "meta"), "device_mode": "dml"})
    add("pytorch-directml", dml, "image_siglip_so400m-384", "embed", "openclip",
        {"arch": siglip.get("arch_name", "ViT-SO400M-14-SigLIP-384"),
         "pretrained": siglip.get("pretrained_model", "webli"), "device_mode": "dml"})
    add("pytorch-directml", dml, "image_siglip_so400m-384", "query_text", "openclip",
        {"arch": siglip.get("arch_name", "ViT-SO400M-14-SigLIP-384"),
         "pretrained": siglip.get("pretrained_model", "webli"), "device_mode": "dml"})
    add("pytorch-directml", dml, "qwen_vl_bf16_registered", "query_text", "qwen",
        {"device_mode": "dml", "dtype_mode": "bf16", "max_pixels": 1800 * 32 * 32})
    add("pytorch-directml", dml, "qwen_vl_fp32_forced", "query_text", "qwen",
        {"device_mode": "dml", "dtype_mode": "fp32", "max_pixels": 1800 * 32 * 32})
    add("pytorch-directml", dml, "qwen_vl_fp32_forced", "embed", "qwen",
        {"device_mode": "dml", "dtype_mode": "fp32", "max_pixels": 1024 * 1024})
    add("pytorch-directml", dml, "text_bge_m3_pytorch", "query_text", "bge_pytorch",
        {"device_mode": "dml"})
    # --- onnxruntime-cpu ---
    add("onnxruntime-cpu", cpu, "text_bge_m3_onnx_local_artifact", "query_text", "bge_onnx", {})
    return cells


STATIC_INVENTORY = [
    {
        "candidate": "torch-directml inside primary .venv (any model)",
        "eligible": False,
        "status": "failed-not-runnable",
        "error_class": "ImportError",
        "evidence": "import torch_directml -> ImportError: DLL load failed while importing "
                    "torch_directml_native: The specified procedure could not be found "
                    "(torch-directml 0.2.5.dev240914 vs torch 2.8.0 in C:\\Users\\minhc\\Code\\Vecna\\.venv)",
    },
    {
        "candidate": "onnxruntime DirectML EP (both venvs)",
        "eligible": False,
        "status": "not-installed-locally",
        "error_class": None,
        "evidence": ".venv has onnxruntime==1.27.0 with providers "
                    "[AzureExecutionProvider, CPUExecutionProvider]; onnxruntime-directml "
                    "not installed anywhere; installing it is a new dependency (out of scope)",
    },
    {
        "candidate": "qwen_vl repo path in .venv-amd",
        "eligible": False,
        "status": "dependency-missing",
        "error_class": None,
        "evidence": "repo feature module imports qwen_vl_utils; .venv-amd does not have "
                    "qwen_vl_utils installed; harness uses self-contained preprocessing instead",
    },
    {
        "candidate": "registered BGE-M3 ONNX backend artifact (fp16 dense-only)",
        "eligible": False,
        "status": "artifact-absent-locally",
        "error_class": None,
        "evidence": "bge_onnx.py expects BAAI-bge-m3_fp16.onnx "
                    "(hotchpotch/vespa-onnx-BAAI-bge-m3-only-dense); no such file found under "
                    "C:\\Users\\minhc\\Code\\Vecna; downloading is prohibited by issue #62",
    },
]


def probe_runtime(interp: Path) -> dict:
    code = (
        "import json, torch;"
        "d={'torch_build': torch.__version__, 'torch_cuda_version': torch.version.cuda,"
        "'cuda_available': bool(torch.cuda.is_available())};"
        "import importlib.util;"
        "d['torch_directml_importable']=importlib.util.find_spec('torch_directml') is not None;"
        "print(json.dumps(d))"
    )
    try:
        out = subprocess.run([str(interp), "-c", code], capture_output=True,
                             text=True, timeout=180, encoding="utf-8", errors="replace")
        if out.returncode == 0:
            return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        pass
    return {}


def dml_device_probe(interp: Path) -> dict | None:
    if not interp.is_file():
        return None
    try:
        out = subprocess.run(
            [str(interp), "-c",
             "import torch_directml,json;print(json.dumps({'count':torch_directml.device_count(),"
             "'name':torch_directml.device_name(0)}))"],
            capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace")
        if out.returncode == 0:
            return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        pass
    return None


def collect_model_evidence() -> list[dict]:
    hub = Path(os.path.expanduser("~")) / ".cache/huggingface/hub"
    wanted = {
        "timm/PE-Core-L-14-336": ["open_clip_model.safetensors"],
        "timm/ViT-SO400M-14-SigLIP-384": ["open_clip_model.safetensors", "open_clip_config.json"],
        "Qwen/Qwen3-VL-Embedding-2B": ["model.safetensors"],
        "BAAI/bge-m3": ["pytorch_model.bin", "model.safetensors", "onnx/model.onnx",
                        "onnx/model.onnx_data"],
    }
    evidence = []
    for repo_id, files in wanted.items():
        d = hub / ("models--" + repo_id.replace("/", "--"))
        rec: dict = {"repo_id": repo_id, "present_locally": False}
        ref_main = d / "refs" / "main"
        if ref_main.is_file():
            rev = ref_main.read_text(encoding="utf-8").strip()
            rec["snapshot_revision"] = rev
            snap = d / "snapshots" / rev
            if snap.is_dir():
                rec["present_locally"] = True
                found = {}
                for rel in files:
                    p = snap / rel
                    found[rel] = {"exists": p.is_file(),
                                  "bytes": p.stat().st_size if p.is_file() else None}
                rec["files"] = found
        evidence.append(rec)
    return evidence


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--venv-cpu", default=str(DEFAULT_VENV_CPU))
    ap.add_argument("--venv-dml", default=str(DEFAULT_VENV_DML))
    ap.add_argument("--frames-dir", default=str(DEFAULT_FRAMES_DIR))
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--num-frames", type=int, default=12)
    ap.add_argument("--qwen-frames", type=int, default=4)
    ap.add_argument("--cell-timeout", type=float, default=420.0,
                    help="in-cell steady-state time budget (seconds)")
    ap.add_argument("--process-timeout", type=float, default=1500.0)
    ap.add_argument("--worker-spec", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--only", default=None,
                    help="comma-separated cell_id substrings to (re)run; others are skipped")
    ap.add_argument("--report-only", action="store_true",
                    help="do not execute cells; rewrite matrix/env/RERUN from measurements.jsonl")
    args = ap.parse_args()

    if args.worker_spec:
        spec = json.loads(Path(args.worker_spec).read_text(encoding="utf-8"))
        res = run_worker_cell(spec)
        result_path = spec.get("_result_path")
        if result_path:
            try:
                Path(result_path).write_text(
                    "@@RESULT@@" + json.dumps(res), encoding="utf-8")
            except Exception:
                pass
        print("@@RESULT@@" + json.dumps(res))
        return 0

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    frames_parent = Path(args.frames_dir)
    frame_files = sorted(frames_parent.glob("*.jpg"))[: max(args.num_frames, args.qwen_frames)]
    if not frame_files:
        print(f"no frames found in {frames_parent}", file=sys.stderr)
        return 2
    frame_paths = [str(p) for p in frame_files]
    embed_frames = frame_paths[: args.num_frames]
    qwen_embed_frames = frame_paths[: args.qwen_frames]

    features = load_config_features(Path(args.config))

    manifest = {
        "issue": "JimmyK300/Vecna#62",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "worktree_branch": subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(REPO_ROOT),
            capture_output=True, text=True).stdout.strip(),
        "worktree_base_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
            capture_output=True, text=True).stdout.strip(),
        "os": f"{platform.system()} {platform.release()} build {platform.version()}",
        "machine": platform.machine(),
        "python_host": platform.python_version(),
        "offline_env_enforced": ["HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1",
                                 "PYTHONDONTWRITEBYTECODE=1"],
        "downloads_allowed": False,
        "venvs": {},
        "gpu": [],
        "workload": {
            "frames_source": str(frames_parent),
            "frames_used_embed": [Path(p).name for p in embed_frames],
            "qwen_embed_frame_cap": args.qwen_frames,
            "frame_sha256_first12": {Path(p).name: sha256_file(Path(p)) for p in embed_frames},
            "queries_vi_en": QUERY_TEXTS,
            "image_batch_levels": IMAGE_BATCH_LEVELS,
            "image_reps": IMAGE_REPS,
            "text_reps": TEXT_REPS,
        },
        "static_inventory": STATIC_INVENTORY,
    }

    for name, root in (("pytorch-cpu", Path(args.venv_cpu)),
                       ("pytorch-directml", Path(args.venv_dml))):
        interp = root / "Scripts" / "python.exe"
        manifest["venvs"][name] = {
            "root": str(root),
            "interpreter": str(interp),
            "exists": interp.is_file(),
            "python_version": python_version_of(interp) if interp.is_file() else None,
            "pip_versions": pip_versions(interp) if interp.is_file() else {},
            "runtime_probe": probe_runtime(interp) if interp.is_file() else {},
        }
    dml_probe = dml_device_probe(Path(args.venv_dml) / "Scripts" / "python.exe")
    dml_cpu_probe = dml_device_probe(Path(args.venv_cpu) / "Scripts" / "python.exe")
    if dml_cpu_probe is None:
        dml_cpu_probe = {"import_error": "torch_directml DLL load failed in primary .venv "
                         "(deterministic; see static_inventory)"}
    manifest["directml"] = {"venv-amd": dml_probe, "primary_venv": dml_cpu_probe}
    manifest["model_weights_evidence"] = collect_model_evidence()

    try:
        import wmi  # type: ignore
    except Exception:
        wmi = None
    gpus = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_VideoController | ForEach-Object { \"$($_.Name)|driver=$($_.DriverVersion)\" }"],
        capture_output=True, text=True, timeout=90)
    manifest["gpu"] = [ln for ln in gpus.stdout.splitlines() if ln.strip()]
    cpu_info = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$c=Get-CimInstance Win32_Processor; $os=Get-CimInstance Win32_OperatingSystem; "
         "\"$($c.Name.Trim()) cores=$($c.NumberOfCores) logical=$($c.NumberOfLogicalProcessors) \" + "
         "\"ram_gb=$([math]::Round($os.TotalVisibleMemorySize/1MB,1))\""],
        capture_output=True, text=True, timeout=90)
    manifest["cpu_ram"] = cpu_info.stdout.strip()

    cells = build_cells(args, features, embed_frames)
    for c in cells:
        if c["model"].startswith("qwen") and c["side"] == "embed":
            c["frames"] = qwen_embed_frames
        if c["kind"] == "qwen":
            c["process_timeout_factor"] = 4.0

    tmp_specs = outdir / "_worker_specs"
    tmp_specs.mkdir(exist_ok=True)

    measurements_path = outdir / "measurements.jsonl"
    only = [s.strip() for s in (args.only.split(",") if args.only else []) if s.strip()]
    existing: dict[str, dict] = {}
    if measurements_path.is_file():
        for line in measurements_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                cid = rec.get("cell_id")
                if cid:
                    existing[cid] = rec
            except Exception:
                pass
    results: list[dict] = []
    with open(measurements_path, "w", encoding="utf-8") as jf:
        for cid, rec in existing.items():
            if only and any(o in cid for o in only):
                continue
            if "peak_rss_unit" not in rec and rec.get("peak_rss_mb") is not None:
                legacy_kb = float(rec["peak_rss_mb"])
                if "peak_rss_bytes" not in rec:
                    rec["peak_rss_bytes"] = legacy_kb * 1024.0
                rec["peak_rss_mb"] = round(rec["peak_rss_bytes"] / (1024.0 * 1024.0), 1)
                rec["peak_rss_unit"] = "MiB(normalized-from-legacy-KB)"
            results.append(rec)
            jf.write(json.dumps(rec) + "\n")
        if results:
            print(f"[merge] kept {len(results)} previous cell record(s)", flush=True)
        for cell in cells:
            if args.report_only:
                break
            if only and not any(o in cell["cell_id"] for o in only):
                continue
            interp = cell.pop("interp")
            if not Path(interp).is_file():
                rec = {"cell_id": cell["cell_id"], "harness": cell["harness"],
                       "model": cell["model"], "side": cell["side"],
                       "status": "interpreter-missing", "wall_s": 0}
                results.append(rec)
                jf.write(json.dumps(rec) + "\n")
                jf.flush()
                continue
            spec_path = tmp_specs / f"{uuid.uuid4().hex}.json"
            result_path = tmp_specs / f"{spec_path.stem}.result.json"
            cell["_result_path"] = str(result_path)
            spec_path.write_text(json.dumps(cell), encoding="utf-8")
            env = dict(os.environ)
            env.update({
                "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
            })
            timeout = args.process_timeout * cell.pop("process_timeout_factor", 1.0)
            t0 = time.perf_counter()
            try:
                proc = subprocess.run(
                    [interp, str(SCRIPT_PATH), "--worker-spec", str(spec_path)],
                    capture_output=True, text=True, timeout=timeout, env=env,
                    cwd=str(REPO_ROOT), encoding="utf-8", errors="replace")
                stdout_tail = [ln for ln in (proc.stdout or "").splitlines() if ln.startswith("@@RESULT@@")]
                rec = None
                if result_path.is_file():
                    try:
                        content = result_path.read_text(encoding="utf-8")
                        if content.startswith("@@RESULT@@"):
                            rec = json.loads(content[len("@@RESULT@@"):])
                    except Exception:
                        rec = None
                if rec is None and stdout_tail:
                    rec = json.loads(stdout_tail[-1][len("@@RESULT@@"):])
                if rec is None:
                    tail = (proc.stderr or "").strip().splitlines()[-5:]
                    rec = {"cell_id": cell["cell_id"], "harness": cell["harness"],
                           "model": cell["model"], "side": cell["side"],
                           "status": "failed",
                           "stderr_tail": tail,
                           "returncode": proc.returncode}
                    stderr_all = proc.stderr or ""
                    if "dml_util.cc" in stderr_all and "BFloat16" in stderr_all:
                        msg = ("DirectML fatal abort: Invalid or unsupported data type "
                               "BFloat16 (torch-directml cannot execute bf16 ops)")
                        rec.update({
                            "error_class": "DirectMLFatalAbort_BFloat16Unsupported",
                            "error_message": msg,
                            "error_signature_sha256": hashlib.sha256(
                                msg.encode("utf-8")).hexdigest(),
                            "process_exit_code_hex": hex(proc.returncode & 0xFFFFFFFF),
                        })
                    elif proc.returncode != 0:
                        rec["error_class"] = "ProcessFatalAbnormalExit"
            except subprocess.TimeoutExpired:
                rec = {"cell_id": cell["cell_id"], "harness": cell["harness"],
                       "model": cell["model"], "side": cell["side"],
                       "status": "failed-timeout",
                       "timeout_s": timeout}
            rec["orchestrator_wall_s"] = round(time.perf_counter() - t0, 2)
            spec_path.unlink(missing_ok=True)
            result_path.unlink(missing_ok=True)
            results.append(rec)
            jf.write(json.dumps(rec) + "\n")
            jf.flush()
            print(f"[{len(results)}/{len(cells)}] {rec['cell_id']}: {rec['status']}", flush=True)

    tmp_specs.rmdir()

    matrix = {
        "manifest": manifest,
        "cells": results,
        "static_inventory": STATIC_INVENTORY,
    }
    (outdir / "matrix.json").write_text(json.dumps(matrix, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    write_matrix_md(outdir / "matrix.md", matrix)
    (outdir / "environment.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    write_rerun_md(outdir / "RERUN.md", args, only)
    print(f"\ndone -> {outdir}")
    return 0


def fmt(v, nd=2):
    return "-" if v is None else (round(v, nd) if isinstance(v, float) else v)


def write_matrix_md(path: Path, matrix: dict) -> None:
    m = matrix["manifest"]
    lines = []
    lines.append("# Issue #62 local compatibility matrix\n")
    lines.append(f"Generated: `{m['generated_utc']}`  |  branch `{m['worktree_branch']}` "
                 f"@ `{m['worktree_base_commit'][:12]}`\n")
    lines.append("Machine: " + m.get("cpu_ram", "?") + "\n")
    lines.append("GPU: " + "; ".join(m.get("gpu", [])) + "\n")
    for name, v in m["venvs"].items():
        pv = v.get("pip_versions") or {}
        lines.append(
            f"- **{name}** (`{v['interpreter']}`): python {v.get('python_version')}, "
            f"torch {pv.get('torch')}, torchvision {pv.get('torchvision')}, "
            f"torch-directml {pv.get('torch-directml')}, open-clip {pv.get('open-clip-torch')}, "
            f"transformers {pv.get('transformers')}, onnxruntime {pv.get('onnxruntime')}, "
            f"numpy {pv.get('numpy')}")
    lines.append("")
    wl = m["workload"]
    lines.append(f"Workload: {len(wl['frames_used_embed'])} keyframes from "
                 f"`{wl['frames_source']}` ({wl['qwen_embed_frame_cap']} for Qwen embed), "
                 f"{len(wl['queries_vi_en'])} fixed vi/en queries, batch levels "
                 f"{wl['image_batch_levels']}, {wl['image_reps']} image reps, "
                 f"{wl['text_reps']} text reps. Offline env enforced; zero downloads.\n")

    def row(c):
        notes = []
        status = c.get("status")
        dev = c.get("device_name") or "-"
        thr = lat = peak = ceil_ = "-"
        if status == "ok":
            if c["side"] == "embed":
                thr = f"{fmt(c.get('best_throughput_img_per_s') or c.get('throughput_img_per_s'), 3)}"
                ceil_ = f"{c.get('batch_ceiling_tested')}"
                brs = [b for b in c.get("batch_results", []) if b.get("status") == "ok"]
                if brs:
                    best = max(brs, key=lambda r: r["throughput_img_per_s"])
                    lat = f"{fmt(best.get('p50_batch_ms'), 0)}ms/batch@{best['batch']}"
                elif c.get("p50_image_s") is not None:
                    lat = f"{c['p50_image_s']}s/img"
            else:
                lat = f"{fmt(c.get('query_latency_p50_ms'))}ms/query"
                thr = f"{fmt(c.get('query_throughput_text_per_s'))}/s"
            peak = f"{c.get('peak_rss_mb')}MB"
        elif status == "failed":
            status = f"failed[{c.get('error_class')}]"
        notes_bits = []
        if c.get("precision"):
            notes_bits.append(c["precision"])
        tm = c.get("tokenizer_meta") or {}
        if tm.get("fallback"):
            notes_bits.append("tok-fallback")
        if c.get("device_resolved"):
            notes_bits.append(str(c.get("device_resolved")))
        fb = [b for b in c.get("batch_results", []) or [] if b.get("status") == "failed"]
        if fb:
            first = fb[0]
            notes_bits.append(
                f"batch>={fb[0]['batch']} failed[{first.get('error_class')}]: "
                f"{(first.get('error_message') or '')[:80]}")
        if c.get("frames_completed") is not None and c["side"] == "embed":
            notes_bits.append(f"frames={c['frames_completed']} (capped)")
        if status.startswith("failed"):
            notes_bits.append((c.get("error_message") or "")[:140])
        return (f"| {c['model']} | {c['harness']} | {c['side']} | {status} | {dev} "
                f"| {thr} | {lat} | {ceil_} | {peak} | {fmt(c.get('load_s'), 1)}s "
                f"| {'; '.join(notes_bits)} |")

    lines.append("## Embedding throughput (image)\n")
    lines.append("| model | harness | side | status | device | img/s | p50 batch ms | batch ceiling | peak RSS | load s | notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in matrix["cells"]:
        if c["side"] == "embed":
            lines.append(row(c))
    lines.append("")
    lines.append("## Query-time text behavior\n")
    lines.append("| model | harness | side | status | device | texts/s | p50 ms/query | batch ceiling | peak RSS | load s | notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in matrix["cells"]:
        if c["side"] != "embed":
            lines.append(row(c))
    lines.append("")
    lines.append("## Not runnable locally (inventory, no execution)\n")
    lines.append("| candidate | status | evidence |")
    lines.append("|---|---|---|")
    for s in matrix["static_inventory"]:
        lines.append(f"| {s['candidate']} | {s['status']} | {s['evidence']} |")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_rerun_md(path: Path, args, only=None) -> None:
    cmd = (f'& "{Path(args.venv_cpu)}\\Scripts\\python.exe" '
           f'"{SCRIPT_PATH}" --output-dir "{Path(args.output_dir)}"')
    if only:
        cmd += f' --only "{",".join(only)}"'
    text = f"""# Rerun issue #62 compatibility bench

One command (PowerShell), full matrix:

```powershell
{cmd}
```

Partial rerun of specific cells (`--only` takes comma-separated cell-id
substrings; existing records are merged, never discarded):

```powershell
{cmd} --only "pytorch-directml::image_siglip"
```

Defaults: 12 keyframe workload frames (+4-frame cap for Qwen embed),
batch levels {IMAGE_BATCH_LEVELS}, {TEXT_REPS} text repetitions.
Offline env vars (`HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`,
`PYTHONDONTWRITEBYTECODE`) are forced by the script; nothing is downloaded
and the shared venvs are used read-only.

Outputs land in `--output-dir` only: `matrix.json`, `matrix.md`,
`measurements.jsonl`, `environment.json`, this file.

Determinism notes:
- identical frame subset (sorted jpg names) and identical fixed query list;
- seeds do not participate (pure inference);
- wall-clock timings vary with machine load; treat throughputs within ~10%
  as ties; error signatures are deterministic for missing deps/unsupported dtypes.
"""
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
