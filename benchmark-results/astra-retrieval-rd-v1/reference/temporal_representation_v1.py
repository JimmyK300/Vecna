#!/usr/bin/env python3
"""Vecna issue #81: temporal representation v1 over retained frame embeddings.

This experiment is deliberately outside production retrieval.  It uses the
frozen 113-row control and the retained per-frame qwen_vl vectors, and only
encodes query text with the already-used Qwen checkpoint.  No corpus
re-embedding, index mutation, or ground-truth-driven candidate construction is
performed.
"""

from __future__ import annotations

import argparse
import io
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONTROL = ROOT / ".worktrees" / "issue79-temporal" / "benchmark-results" / "temporal-sequence-v1" / "control_113.jsonl"
DEFAULT_FEATURE_ROOT = Path(r"D:\Official-Dataset\features_L21-L30_branch-feats-siglip\features")
DEFAULT_MODEL = Path(r"C:\Users\minhc\.cache\huggingface\hub\models--Qwen--Qwen3-VL-Embedding-2B\snapshots\9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda")
DEFAULT_OUT = ROOT / "benchmark-results" / "temporal-representation-v1"
EXCLUSIONS = {"p0_q15", "p3_q09"}
TEMPORAL_TAGS = {"BOUND", "TRACK", "SEQ", "MOTION"}
QUERY_INSTRUCTION = "Retrieve images or text relevant to the user's query."
DEFAULT_INSTRUCTION = "Represent the user's input."
FFMPEG = Path(r"C:\Users\minhc\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")
WINDOW_SPECS = {
    "w3_d60": {"offsets": [-60, 0, 60], "weights": [0.25, 0.5, 0.25]},
    "w5_d60": {"offsets": [-120, -60, 0, 60, 120], "weights": [0.1, 0.2, 0.4, 0.2, 0.1]},
}
ARMS = ("window_max", "window_top2_mean", "ordered_weighted")
STAGE2B_QUERY_IDS = (
    "p0_q22", "p0_q23", "p0_q24", "p1_q25",
    "p2_q29", "p2_q30", "p3_q21", "p3_q34",
)
STAGE2B_MODE_SPECS = {
    "contact_sheet": "w3_d60",
    "native3": "w3_d60",
    "native5": "w5_d60",
}


def jsonl_read(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"invalid JSONL {path}:{line_no}: {exc}") from exc
    return rows


def jsonl_write(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_frame_id(item: dict[str, Any]) -> str:
    source = item.get("source_frame_id")
    if source:
        return str(source)
    video = video_id(item)
    frame = frame_number(item)
    if video and frame is not None:
        return f"{video}#{frame:06d}"
    return str(item.get("frame_id") or "")


def video_id(item: dict[str, Any]) -> str | None:
    value = item.get("video_id")
    if value:
        return str(value)
    source = str(item.get("source_frame_id") or item.get("frame_id") or "")
    if "#" in source:
        return source.split("#", 1)[0]
    match = re.match(r"(L\d+_V\d+)", source)
    return match.group(1) if match else None


def frame_number(item: dict[str, Any]) -> int | None:
    for value in (item.get("frame_id"), item.get("source_frame_id")):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
        match = re.search(r"#(\d+)$", str(value or ""))
        if match:
            return int(match.group(1))
    return None


def normalized_result(item: dict[str, Any], rank: int) -> dict[str, Any]:
    value = item.get("distance", item.get("score", item.get("final")))
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = None
    result = dict(item)
    result["rank"] = rank
    result["distance"] = score
    result["score"] = score
    result["video_id"] = video_id(result)
    result["source_frame_id"] = source_frame_id(result)
    return result


def normalize_results(items: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    values = [normalized_result(item, i + 1) for i, item in enumerate(items[:limit])]
    values.sort(key=lambda x: (-(x["distance"] if x["distance"] is not None else -math.inf), x["source_frame_id"]))
    for rank, item in enumerate(values, 1):
        item["rank"] = rank
    return values


def accepted_videos(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    if row.get("accepted_video_id"):
        values.add(str(row["accepted_video_id"]))
    for group in row.get("accepted_groups") or []:
        for item in group or []:
            if item.get("video_id"):
                values.add(str(item["video_id"]))
    return values


def truth_intervals(row: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in row.get("accepted_ranges") or []:
        if not isinstance(item, dict):
            continue
        start = item.get("start_frame", item.get("start"))
        end = item.get("end_frame", item.get("end"))
        if start is not None and end is not None:
            values.append({"video_id": item.get("video_id") or row.get("accepted_video_id"), "start_frame": int(start), "end_frame": int(end)})
    for group in row.get("accepted_groups") or []:
        for item in group or []:
            start = item.get("start_frame", item.get("start"))
            end = item.get("end_frame", item.get("end"))
            if start is not None and end is not None:
                values.append({"video_id": item.get("video_id"), "start_frame": int(start), "end_frame": int(end)})
    return values


def item_frames(item: dict[str, Any]) -> list[dict[str, Any]]:
    frames = item.get("window_frames")
    return frames if isinstance(frames, list) and frames else [item]


def video_hit(item: dict[str, Any], row: dict[str, Any]) -> bool:
    expected = accepted_videos(row)
    return any(video_id(frame) in expected for frame in item_frames(item))


def range_hit(item: dict[str, Any], row: dict[str, Any]) -> bool:
    intervals = truth_intervals(row)
    if not intervals:
        return False
    for frame_item in item_frames(item):
        vid = video_id(frame_item)
        frame = frame_number(frame_item)
        if vid is None or frame is None:
            continue
        if any((interval.get("video_id") in (None, vid) and interval["start_frame"] <= frame <= interval["end_frame"]) for interval in intervals):
            return True
    return False


def metrics(results: list[dict[str, Any]], row: dict[str, Any]) -> dict[str, float]:
    output: dict[str, float] = {}
    for k in (1, 5, 20):
        output[f"video_R@{k}"] = float(any(video_hit(item, row) for item in results[:k]))
        output[f"range_R@{k}"] = float(any(range_hit(item, row) for item in results[:k]))
    return output


def summarize(rows: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    values = [float(row[metric]) for row in rows if metric in row]
    return {"n": len(values), "hits": int(sum(values)), "recall": (sum(values) / len(values) if values else None)}


def temporal_eligible(row: dict[str, Any]) -> tuple[bool, str]:
    tags = set(str(x).upper() for x in row.get("capability_tags") or [])
    scoreability = row.get("scoreability") or {}
    if not scoreability.get("video"):
        return False, "video_scoreability_false"
    if tags & TEMPORAL_TAGS:
        return True, "temporal_capability_tag"
    if scoreability.get("trake_event") or row.get("trake_event_truth"):
        return True, "trake_event_truth"
    return False, "no_temporal_capability_tag_or_event_truth"


def build(args: argparse.Namespace) -> None:
    if not args.control.exists():
        raise FileNotFoundError(f"control missing: {args.control}")
    controls = jsonl_read(args.control)
    ids = [str(row.get("query_id")) for row in controls]
    if len(controls) != 113 or len(set(ids)) != 113:
        raise RuntimeError(f"expected 113 unique control rows, got {len(controls)} rows and {len(set(ids))} ids")
    leaked = EXCLUSIONS & set(ids)
    if leaked:
        raise RuntimeError(f"documented exclusions leaked into control: {sorted(leaked)}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target_rows = []
    for row in controls:
        eligible, reason = temporal_eligible(row)
        if eligible:
            target_rows.append({"query_id": row["query_id"], "reason": reason, "capability_tags": row.get("capability_tags", []), "scoreability": row.get("scoreability", {})})
    control_out = args.out_dir / "control_113.jsonl"
    shutil.copyfile(args.control, control_out)
    write_json(args.out_dir / "temporal_target_subset.json", {
        "selection_source": "control metadata only",
        "ground_truth_used_for_selection": False,
        "count": len(target_rows),
        "rows": target_rows,
    })
    write_json(args.out_dir / "stage0_manifest.json", {
        "issue": 81,
        "experiment": "temporal-representation-v1",
        "control_source": str(args.control),
        "control_sha256": sha256_file(args.control),
        "control_copy": str(control_out),
        "control_copy_sha256": sha256_file(control_out),
        "control_count": len(controls),
        "excluded": sorted(EXCLUSIONS),
        "temporal_target_count": len(target_rows),
        "feature_root": str(args.feature_root),
        "model_snapshot": str(args.model_snapshot),
        "candidate_pool": "frozen baseline_results top 100 per query",
        "window_specs": WINDOW_SPECS,
        "arms": list(ARMS),
        "ground_truth_used_for_window_construction": False,
        "production_mutation": False,
        "full_corpus_reembedding": False,
    })
    print(f"build: exact control={len(controls)} temporal_targets={len(target_rows)} sha256={sha256_file(args.control)}", flush=True)


def load_model(snapshot: Path):
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    if not snapshot.exists():
        raise FileNotFoundError(f"model snapshot missing: {snapshot}")
    model = Qwen3VLForConditionalGeneration.from_pretrained(snapshot, dtype=torch.bfloat16, low_cpu_mem_usage=False)
    processor = AutoProcessor.from_pretrained(snapshot)
    model.eval()
    return torch, model, processor


def encode_texts(torch: Any, model: Any, processor: Any, texts: list[str]) -> list[list[float]]:
    conversations = [
        [{"role": "system", "content": [{"type": "text", "text": QUERY_INSTRUCTION}]},
         {"role": "user", "content": [{"type": "text", "text": text}]}]
        for text in texts
    ]
    inputs = processor.apply_chat_template(
        conversations, add_generation_prompt=True, tokenize=True, return_dict=True,
        return_tensors="pt", padding=True,
    )
    with torch.inference_mode():
        output = model(**inputs, output_hidden_states=True)
    hidden = output.hidden_states[-1]
    last = inputs["attention_mask"].sum(dim=1) - 1
    vectors = hidden[torch.arange(hidden.shape[0]), last]
    vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
    return vectors.detach().cpu().float().numpy().tolist()


def encode(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = {str(row["query_id"]): row for row in jsonl_read(out / "control_113.jsonl")}
    target = json.loads((out / "temporal_target_subset.json").read_text(encoding="utf-8"))
    selected = {x.strip() for x in args.query_ids.split(",") if x.strip()} if args.query_ids else {row["query_id"] for row in target["rows"]}
    selected.add(args.parity_query)
    missing_ids = sorted(selected - set(controls))
    if missing_ids:
        raise RuntimeError(f"unknown query ids: {missing_ids}")
    vector_path = out / "query_vectors.jsonl"
    existing = {}
    if vector_path.exists():
        for row in jsonl_read(vector_path):
            if row.get("query_id") in selected and row.get("query_text_sha256") == sha256_text(str(controls[row["query_id"]].get("query_text", ""))):
                existing[row["query_id"]] = row
    missing = [qid for qid in sorted(selected) if qid not in existing]
    if not missing:
        print(f"encode: all {len(selected)} query vectors already present", flush=True)
        return
    torch, model, processor = load_model(args.model_snapshot)
    started = time.time()
    for start in range(0, len(missing), max(1, args.encode_batch_size)):
        batch_ids = missing[start:start + max(1, args.encode_batch_size)]
        vectors = encode_texts(torch, model, processor, [str(controls[qid].get("query_text", "")) for qid in batch_ids])
        for qid, vector in zip(batch_ids, vectors):
            existing[qid] = {
                "query_id": qid,
                "query_text_sha256": sha256_text(str(controls[qid].get("query_text", ""))),
                "instruction": QUERY_INSTRUCTION,
                "model_snapshot": str(args.model_snapshot),
                "vector": vector,
                "ground_truth_used": False,
            }
        jsonl_write(vector_path, [existing[qid] for qid in sorted(existing)])
        print(f"encode [{start + 1}-{start + len(batch_ids)}/{len(missing)}] ids={','.join(batch_ids)} elapsed_s={round(time.time() - started, 1)}", flush=True)
    write_json(out / "query_vector_manifest.json", {
        "count": len(existing),
        "selected_query_ids": sorted(existing),
        "instruction": QUERY_INSTRUCTION,
        "model_snapshot": str(args.model_snapshot),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
        "elapsed_s": round(time.time() - started, 3),
        "ground_truth_used": False,
    })


def run_parity(args: argparse.Namespace, controls: dict[str, dict[str, Any]], vectors: dict[str, list[float]]) -> None:
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    from pymilvus import MilvusClient

    client = MilvusClient(uri=args.milvus_uri)
    vector = vectors[args.parity_query]
    hits = client.search(
        collection_name=args.collection, data=[vector], anns_field="qwen_vl",
        limit=20, search_params={"metric_type": "COSINE", "params": {"nprobe": args.nprobe}},
        output_fields=["frame_id"],
    )
    live = []
    for index, hit in enumerate((hits[0] if hits else []), 1):
        entity = hit.get("entity") if isinstance(hit, dict) else None
        frame = entity.get("frame_id") if isinstance(entity, dict) else hit.get("id")
        live.append(source_frame_id({"frame_id": frame}))
    frozen = [source_frame_id(item) for item in normalize_results(controls[args.parity_query].get("baseline_results", []), 20)]
    overlap = len(set(frozen) & set(live))
    write_json(args.out_dir / "surface_parity.json", {
        "query_id": args.parity_query,
        "ground_truth_used": False,
        "baseline_source": controls[args.parity_query].get("baseline_source"),
        "baseline_top1": frozen[0] if frozen else None,
        "live_top1": live[0] if live else None,
        "top20_overlap": overlap,
        "top20_overlap_fraction": overlap / len(set(frozen)) if frozen else None,
        "top20_baseline": frozen,
        "top20_live": live,
        "parity_status": "top1_and_top20_overlap" if frozen and live and frozen[0] == live[0] and overlap / len(set(frozen)) >= 0.8 else "diagnostic_mismatch",
        "collection": args.collection,
        "anns_field": "qwen_vl",
        "metric_type": "COSINE",
        "nprobe": args.nprobe,
    })
    print(f"parity: qid={args.parity_query} top1={live[0] if live else None} overlap20={overlap}/20", flush=True)


class FeatureStore:
    def __init__(self, root: Path):
        self.root = root
        self.index: dict[str, list[tuple[int, Path]]] = {}
        self.cache: dict[Path, np.ndarray] = {}

    def _paths(self, video: str) -> list[tuple[int, Path]]:
        if video not in self.index:
            directory = self.root / video
            values = []
            if directory.exists():
                for path in directory.glob("*/qwen_vl.npy"):
                    try:
                        values.append((int(path.parent.name), path))
                    except ValueError:
                        continue
            self.index[video] = sorted(values)
        return self.index[video]

    def nearest(self, video: str, requested: int) -> tuple[int, np.ndarray] | None:
        values = self._paths(video)
        if not values:
            return None
        frame, path = min(values, key=lambda item: (abs(item[0] - requested), item[0]))
        if path not in self.cache:
            vector = np.asarray(np.load(path), dtype=np.float32).reshape(-1)
            norm = np.linalg.norm(vector)
            if not np.isfinite(norm) or norm == 0:
                return None
            self.cache[path] = vector / norm
        return frame, self.cache[path]


def run_windows(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = {str(row["query_id"]): row for row in jsonl_read(out / "control_113.jsonl")}
    target = json.loads((out / "temporal_target_subset.json").read_text(encoding="utf-8"))
    vector_rows = {row["query_id"]: row for row in jsonl_read(out / "query_vectors.jsonl")}
    selected = {x.strip() for x in args.query_ids.split(",") if x.strip()} if args.query_ids else {row["query_id"] for row in target["rows"]}
    selected -= EXCLUSIONS
    store = FeatureStore(args.feature_root)
    rows: list[dict[str, Any]] = []
    started = time.time()
    for number, qid in enumerate(sorted(selected), 1):
        if qid not in controls or qid not in vector_rows:
            raise RuntimeError(f"missing control/vector for {qid}")
        query_vector = np.asarray(vector_rows[qid]["vector"], dtype=np.float32)
        baseline = normalize_results(controls[qid].get("baseline_results", []), args.candidate_limit)
        arm_rows: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}
        missing = 0
        for candidate in baseline:
            video = video_id(candidate)
            center = frame_number(candidate)
            if not video or center is None:
                missing += 1
                continue
            for spec_name, spec in WINDOW_SPECS.items():
                window = []
                for offset in spec["offsets"]:
                    found = store.nearest(video, center + int(offset))
                    if found is None:
                        continue
                    actual_frame, feature = found
                    similarity = float(np.dot(query_vector, feature))
                    window.append({
                        "video_id": video,
                        "frame_id": actual_frame,
                        "source_frame_id": f"{video}#{actual_frame:06d}",
                        "requested_offset": int(offset),
                        "actual_offset": int(actual_frame - center),
                        "similarity": similarity,
                    })
                if not window:
                    missing += 1
                    continue
                by_offset = {item["requested_offset"]: item for item in window}
                center_item = by_offset.get(0, window[len(window) // 2])
                ordered_scores = [by_offset[offset]["similarity"] for offset in spec["offsets"] if offset in by_offset]
                ranked_scores = sorted((item["similarity"] for item in window), reverse=True)
                aggregate = {
                    "window_max": max(ranked_scores),
                    "window_top2_mean": sum(ranked_scores[:2]) / min(2, len(ranked_scores)),
                    "ordered_weighted": sum(item["similarity"] * weight for item, weight in zip(window, spec["weights"])) / sum(spec["weights"][:len(window)]),
                }
                window_payload = {
                    "window_spec": spec_name,
                    "window_offsets": spec["offsets"],
                    "window_frames": window,
                    "center_source_frame_id": center_item["source_frame_id"],
                    "baseline_center_rank": candidate["rank"],
                }
                for arm in ARMS:
                    representative = max(window, key=lambda item: (item["similarity"], item["source_frame_id"])) if arm == "window_max" else center_item
                    item = {
                        "rank": 0,
                        "distance": float(aggregate[arm]),
                        "score": float(aggregate[arm]),
                        "video_id": representative["video_id"],
                        "frame_id": representative["frame_id"],
                        "source_frame_id": representative["source_frame_id"],
                        "center_source_frame_id": center_item["source_frame_id"],
                        "window_frames": window,
                        "window_spec": spec_name,
                        "baseline_center_rank": candidate["rank"],
                    }
                    arm_rows[arm].append(item)
        variants = {}
        for arm, values in arm_rows.items():
            values.sort(key=lambda item: (-item["score"], item["source_frame_id"], item["window_spec"]))
            for rank, item in enumerate(values, 1):
                item["rank"] = rank
            variants[arm] = values[:args.result_limit]
        rows.append({
            "query_id": qid,
            "query_text_sha256": sha256_text(str(controls[qid].get("query_text", ""))),
            "candidate_limit": args.candidate_limit,
            "candidate_count": len(baseline),
            "feature_root": str(args.feature_root),
            "missing_candidates": missing,
            "variants": variants,
        })
        if number == 1 or number % 5 == 0 or number == len(selected):
            print(f"run [{number}/{len(selected)}] qid={qid} cache={len(store.cache)} elapsed_s={round(time.time() - started, 1)}", flush=True)
    jsonl_write(out / "window_results.jsonl", rows)
    write_json(out / "window_surface_manifest.json", {
        "feature_root": str(args.feature_root),
        "feature_subpath": "video/frame/qwen_vl.npy",
        "feature_vector_normalization": "per-file L2 normalize before dot product",
        "candidate_pool": "frozen baseline_results top 100",
        "query_vector_source": "Qwen text vectors cached by encode stage",
        "windows": WINDOW_SPECS,
        "arms": list(ARMS),
        "query_count": len(rows),
        "feature_videos_loaded": len(store.index),
        "feature_files_loaded": len(store.cache),
        "ground_truth_used_for_construction": False,
        "corpus_reembedding": False,
    })


def find_video_path(video: str, cache: dict[str, Path | None]) -> Path | None:
    if video in cache:
        return cache[video]
    video_root = Path(r"D:\Official-Dataset\videos")
    matches = sorted(video_root.glob(f"*/{video}.mp4"))
    cache[video] = matches[0] if matches else None
    return cache[video]


def extract_exact_frame(video_path: Path, frame: int) -> bytes:
    if not FFMPEG.exists():
        raise FileNotFoundError(f"ffmpeg missing: {FFMPEG}")
    expression = f"select=eq(n\\,{int(frame)})"
    completed = subprocess.run(
        [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-i", str(video_path),
         "-vf", expression, "-frames:v", "1", "-vsync", "0", "-f", "image2pipe",
         "-vcodec", "png", "pipe:1"],
        check=False, capture_output=True,
    )
    if completed.returncode != 0 or not completed.stdout:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"exact frame decode failed video={video_path.name} frame={frame}: {detail}")
    return completed.stdout


def make_contact_sheet(frame_paths: list[Path], output_path: Path) -> None:
    from PIL import Image

    tile_width, tile_height = 384, 216
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (tile_width * len(frame_paths), tile_height), (0, 0, 0))
    for index, path in enumerate(frame_paths):
        with Image.open(path) as image:
            tile = image.convert("RGB").resize((tile_width, tile_height), Image.Resampling.LANCZOS)
        canvas.paste(tile, (index * tile_width, 0))
    canvas.save(output_path, format="PNG")


def stage2_prepare(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = {str(row["query_id"]): row for row in jsonl_read(out / "control_113.jsonl")}
    selected = {x.strip() for x in args.query_ids.split(",") if x.strip()}
    if not selected:
        raise RuntimeError("Stage 2 requires explicit --query-ids to keep the visual run bounded")
    if selected - set(controls):
        raise RuntimeError(f"unknown Stage 2 query ids: {sorted(selected - set(controls))}")
    candidate_rows = []
    video_cache: dict[str, Path | None] = {}
    frame_cache = out / "stage2_frames" / "_cache"
    frame_cache.mkdir(parents=True, exist_ok=True)
    for qid in sorted(selected):
        baseline = normalize_results(controls[qid].get("baseline_results", []), args.stage2_candidate_limit)
        for spec_name, spec in WINDOW_SPECS.items():
            for candidate in baseline:
                video = video_id(candidate)
                center = frame_number(candidate)
                row = {
                    "candidate_id": f"{qid}:{spec_name}:r{candidate['rank']:03d}",
                    "query_id": qid,
                    "window_spec": spec_name,
                    "baseline_center_rank": candidate["rank"],
                    "video_id": video,
                    "center_frame_id": center,
                    "requested_offsets": spec["offsets"],
                    "frames": [],
                    "status": "ready",
                }
                if not video or center is None:
                    row["status"] = "missing_video_or_frame_id"
                    candidate_rows.append(row)
                    continue
                path = find_video_path(video, video_cache)
                if path is None:
                    row["status"] = "source_video_missing"
                    candidate_rows.append(row)
                    continue
                for offset in spec["offsets"]:
                    frame = int(center + offset)
                    frame_path = frame_cache / f"{video}_{frame:08d}.png"
                    try:
                        if not frame_path.exists():
                            frame_path.write_bytes(extract_exact_frame(path, frame))
                        row["frames"].append({
                            "video_id": video,
                            "frame_id": frame,
                            "source_frame_id": f"{video}#{frame:06d}",
                            "offset": int(offset),
                            "path": str(frame_path),
                        })
                    except Exception as exc:
                        row["status"] = "frame_decode_failed"
                        row["error"] = str(exc)
                        row["frames"] = []
                        break
                if row["status"] == "ready":
                    contact_sheet = out / "stage2_frames" / "contact_sheets" / (
                        row["candidate_id"].replace(":", "_") + ".png"
                    )
                    make_contact_sheet([Path(item["path"]) for item in row["frames"]], contact_sheet)
                    row["contact_sheet_path"] = str(contact_sheet)
                candidate_rows.append(row)
    jsonl_write(out / "stage2_candidates.jsonl", candidate_rows)
    write_json(out / "stage2_prepare_manifest.json", {
        "candidate_query_ids": sorted(selected),
        "candidate_limit_per_query": args.stage2_candidate_limit,
        "window_specs": WINDOW_SPECS,
        "candidate_count": len(candidate_rows),
        "ready_count": sum(row["status"] == "ready" for row in candidate_rows),
        "frame_decode_method": "FFmpeg select=eq(n\\,FRAME), exact decoded frame",
        "contact_sheet": "left-to-right ordered tiles, each 384x216",
        "source_video_root": str(Path(r"D:\Official-Dataset\videos")),
        "ground_truth_used": False,
    })
    print(f"stage2_prepare: candidates={len(candidate_rows)} ready={sum(row['status'] == 'ready' for row in candidate_rows)}", flush=True)


def encode_multiframe(torch: Any, model: Any, processor: Any, image_paths: list[Path]) -> list[float]:
    from PIL import Image

    opened = [Image.open(path).convert("RGB") for path in image_paths]
    conversation = [
        {"role": "system", "content": [{"type": "text", "text": DEFAULT_INSTRUCTION}]},
        {"role": "user", "content": [{"type": "image", "image": image} for image in opened]},
    ]
    text = processor.apply_chat_template([conversation], add_generation_prompt=True, tokenize=False)
    inputs = processor(
        text=text, images=opened, truncation=True, max_length=8192, padding=True,
        return_tensors="pt",
    )
    inputs = {key: value.to(model.device) for key, value in inputs.items()}
    with torch.inference_mode():
        outputs = model(**inputs)
    hidden = outputs.last_hidden_state
    mask = inputs["attention_mask"]
    last_positions = mask.shape[1] - 1 - mask.flip(dims=[1]).argmax(dim=1)
    vector = hidden[torch.arange(hidden.shape[0]), last_positions]
    vector = torch.nn.functional.normalize(vector, p=2, dim=1)
    for image in opened:
        image.close()
    return vector[0].detach().cpu().float().numpy().tolist()


def load_embedding_model(snapshot: Path):
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    import torch
    from transformers import Qwen3VLProcessor
    from transformers.models.qwen3_vl.modeling_qwen3_vl import Qwen3VLModel, Qwen3VLPreTrainedModel

    class Qwen3VLEmbedding(Qwen3VLPreTrainedModel):
        _checkpoint_conversion_mapping = {}
        accepts_loss_kwargs = False

        def __init__(self, config):
            super().__init__(config)
            self.model = Qwen3VLModel(config)
            self.post_init()

        def get_input_embeddings(self):
            return self.model.get_input_embeddings()

        def set_input_embeddings(self, value):
            return self.model.set_input_embeddings(value)

        def get_decoder(self):
            return self.model.get_decoder()

        def set_decoder(self, value):
            return self.model.set_decoder(value)

        def forward(self, **kwargs):
            return self.model(**kwargs)

    if not snapshot.exists():
        raise FileNotFoundError(f"model snapshot missing: {snapshot}")
    model = Qwen3VLEmbedding.from_pretrained(
        snapshot, trust_remote_code=True, dtype=torch.bfloat16, low_cpu_mem_usage=True
    )
    processor = Qwen3VLProcessor.from_pretrained(snapshot)
    model.eval()
    return torch, model, processor


def stage2_encode(args: argparse.Namespace) -> None:
    out = args.out_dir
    candidates = jsonl_read(out / "stage2_candidates.jsonl")
    selected = {x.strip() for x in args.query_ids.split(",") if x.strip()}
    candidates = [row for row in candidates if row["query_id"] in selected]
    vector_path = out / "stage2_embeddings.jsonl"
    existing = {}
    if vector_path.exists():
        for row in jsonl_read(vector_path):
            if row.get("candidate_id"):
                existing[row["candidate_id"]] = row
    pending = [row for row in candidates if row["status"] == "ready" and row["candidate_id"] not in existing]
    if not pending:
        print(f"stage2_encode: all {len(candidates)} candidate rows already present", flush=True)
        return
    torch, model, processor = load_embedding_model(args.model_snapshot)
    started = time.time()
    for index, row in enumerate(pending, 1):
        input_paths = [Path(row["contact_sheet_path"])] if row.get("contact_sheet_path") else [Path(item["path"]) for item in row["frames"]]
        vector = encode_multiframe(torch, model, processor, input_paths)
        existing[row["candidate_id"]] = {
            "candidate_id": row["candidate_id"],
            "query_id": row["query_id"],
            "window_spec": row["window_spec"],
            "baseline_center_rank": row["baseline_center_rank"],
            "video_id": row["video_id"],
            "center_frame_id": row["center_frame_id"],
            "frame_ids": [item["frame_id"] for item in row["frames"]],
            "frame_paths": [item["path"] for item in row["frames"]],
            "contact_sheet_path": row.get("contact_sheet_path"),
            "input_mode": "ordered_contact_sheet",
            "vector": vector,
            "model_snapshot": str(args.model_snapshot),
            "instruction": DEFAULT_INSTRUCTION,
            "ground_truth_used": False,
        }
        jsonl_write(vector_path, [existing[key] for key in sorted(existing)])
        print(f"stage2_encode [{index}/{len(pending)}] {row['candidate_id']} elapsed_s={round(time.time() - started, 1)}", flush=True)
    write_json(out / "stage2_surface_manifest.json", {
        "model_snapshot": str(args.model_snapshot),
        "instruction": DEFAULT_INSTRUCTION,
        "input": "one ordered contact-sheet image tiled left-to-right from exact decoded frames",
        "candidate_count": len(existing),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
        "ground_truth_used": False,
        "full_corpus_run": False,
        "elapsed_s": round(time.time() - started, 3),
    })


def stage2_score(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = {str(row["query_id"]): row for row in jsonl_read(out / "control_113.jsonl")}
    selected = {x.strip() for x in args.query_ids.split(",") if x.strip()}
    vectors = {row["query_id"]: np.asarray(row["vector"], dtype=np.float32) for row in jsonl_read(out / "query_vectors.jsonl")}
    candidate_meta = {row["candidate_id"]: row for row in jsonl_read(out / "stage2_candidates.jsonl")}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in jsonl_read(out / "stage2_embeddings.jsonl"):
        if row["query_id"] not in selected:
            continue
        qvec = vectors[row["query_id"]]
        score = float(np.dot(qvec, np.asarray(row["vector"], dtype=np.float32)))
        meta = candidate_meta[row["candidate_id"]]
        item = {
            "rank": 0,
            "distance": score,
            "score": score,
            "video_id": row["video_id"],
            "frame_id": row["center_frame_id"],
            "source_frame_id": f"{row['video_id']}#{int(row['center_frame_id']):06d}",
            "center_source_frame_id": f"{row['video_id']}#{int(row['center_frame_id']):06d}",
            "window_spec": row["window_spec"],
            "baseline_center_rank": row["baseline_center_rank"],
            "window_frames": [
                {"video_id": meta["video_id"], "frame_id": frame, "source_frame_id": f"{meta['video_id']}#{int(frame):06d}"}
                for frame in row["frame_ids"]
            ],
            "candidate_id": row["candidate_id"],
        }
        grouped.setdefault((row["query_id"], row["window_spec"]), []).append(item)
    scored = []
    for (qid, spec), values in sorted(grouped.items()):
        values.sort(key=lambda item: (-item["score"], item["candidate_id"]))
        for rank, item in enumerate(values, 1):
            item["rank"] = rank
        baseline = normalize_results(controls[qid].get("baseline_results", []), args.stage2_candidate_limit)
        scored.append({
            "query_id": qid,
            "window_spec": spec,
            "baseline": {"metrics": metrics(baseline, controls[qid]), "top": baseline},
            "stage2": {"metrics": metrics(values, controls[qid]), "top": values},
        })
    jsonl_write(out / "stage2_scored.jsonl", scored)
    summary = {}
    for spec in sorted({row["window_spec"] for row in scored}):
        spec_rows = [row for row in scored if row["window_spec"] == spec]
        baseline_rows = [row["baseline"]["metrics"] for row in spec_rows]
        stage_rows = [row["stage2"]["metrics"] for row in spec_rows]
        summary[spec] = {
            "n": len(spec_rows),
            "baseline": {metric: summarize(baseline_rows, metric) for metric in ("video_R@1", "video_R@5", "video_R@20", "range_R@20")},
            "stage2": {metric: summarize(stage_rows, metric) for metric in ("video_R@1", "video_R@5", "video_R@20", "range_R@20")},
        }
    write_json(out / "stage2_summaries.json", summary)
    lines = [
        "# Stage 2 ordered contact-sheet Qwen probe (Vecna issue #81)",
        "",
        f"Bounded candidate pool: frozen baseline top {args.stage2_candidate_limit} per selected query; exact decoded source frames; no ground truth used in construction.",
        "",
        "| arm | n | baseline video R@20 | Stage 2 video R@20 | Stage 2 video R@1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for spec in sorted(summary):
        value = summary[spec]
        lines.append(f"| {spec} | {value['n']} | {fmt(value['baseline']['video_R@20']['recall'])} | {fmt(value['stage2']['video_R@20']['recall'])} | {fmt(value['stage2']['video_R@1']['recall'])} |")
    lines += ["", "The probe is evidence about ordered contact-sheet Qwen inputs over this bounded candidate pool only; Qwen receives one image tiled left-to-right, not native multiple image tokens, and this is not a full-corpus video-encoder result.", ""]
    (out / "STAGE2_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def stage2b_selected(args: argparse.Namespace, controls: dict[str, dict[str, Any]]) -> list[str]:
    selected = [x.strip() for x in args.query_ids.split(",") if x.strip()] if args.query_ids else list(STAGE2B_QUERY_IDS)
    selected = sorted(set(selected) - EXCLUSIONS)
    missing = sorted(set(selected) - set(controls))
    if missing:
        raise RuntimeError(f"unknown Stage 2b query ids: {missing}")
    if not selected:
        raise RuntimeError("Stage 2b requires at least one explicit or default query id")
    return selected


def stage2b_prepare(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = {str(row["query_id"]): row for row in jsonl_read(out / "control_113.jsonl")}
    selected = stage2b_selected(args, controls)
    candidate_rows: list[dict[str, Any]] = []
    video_cache: dict[str, Path | None] = {}
    frame_cache = out / "stage2b_frames" / "_cache"
    frame_cache.mkdir(parents=True, exist_ok=True)
    for qid in selected:
        baseline = normalize_results(controls[qid].get("baseline_results", []), args.stage2b_candidate_limit)
        for spec_name, spec in WINDOW_SPECS.items():
            for candidate in baseline:
                video = video_id(candidate)
                center = frame_number(candidate)
                row: dict[str, Any] = {
                    "candidate_id": f"{qid}:{spec_name}:r{candidate['rank']:03d}",
                    "query_id": qid,
                    "window_spec": spec_name,
                    "baseline_center_rank": candidate["rank"],
                    "video_id": video,
                    "center_frame_id": center,
                    "requested_offsets": spec["offsets"],
                    "frames": [],
                    "status": "ready",
                }
                if not video or center is None:
                    row["status"] = "missing_video_or_frame_id"
                    candidate_rows.append(row)
                    continue
                path = find_video_path(video, video_cache)
                if path is None:
                    row["status"] = "source_video_missing"
                    candidate_rows.append(row)
                    continue
                for offset in spec["offsets"]:
                    frame = int(center + offset)
                    frame_path = frame_cache / f"{video}_{frame:08d}.png"
                    try:
                        if not frame_path.exists():
                            frame_path.write_bytes(extract_exact_frame(path, frame))
                        row["frames"].append({
                            "video_id": video,
                            "frame_id": frame,
                            "source_frame_id": f"{video}#{frame:06d}",
                            "offset": int(offset),
                            "path": str(frame_path),
                        })
                    except Exception as exc:
                        row["status"] = "frame_decode_failed"
                        row["error"] = str(exc)
                        row["frames"] = []
                        break
                if row["status"] == "ready":
                    contact_sheet = out / "stage2b_frames" / "contact_sheets" / (
                        row["candidate_id"].replace(":", "_") + ".png"
                    )
                    make_contact_sheet([Path(item["path"]) for item in row["frames"]], contact_sheet)
                    row["contact_sheet_path"] = str(contact_sheet)
                candidate_rows.append(row)
    jsonl_write(out / "stage2b_candidates.jsonl", candidate_rows)
    write_json(out / "stage2b_prepare_manifest.json", {
        "issue": 81,
        "experiment": "temporal-representation-v1-stage2b",
        "control_sha256": sha256_file(out / "control_113.jsonl"),
        "query_ids": selected,
        "candidate_limit_per_query": args.stage2b_candidate_limit,
        "candidate_count": len(candidate_rows),
        "ready_count": sum(row["status"] == "ready" for row in candidate_rows),
        "candidate_pool": "frozen baseline_results top N per selected query",
        "windows": WINDOW_SPECS,
        "frame_decode_method": "FFmpeg select=eq(n\\,FRAME), exact decoded frame",
        "contact_sheet": "left-to-right ordered tiles, each 384x216",
        "source_video_root": str(Path(r"D:\Official-Dataset\videos")),
        "ground_truth_used": False,
        "production_mutation": False,
        "full_corpus_run": False,
    })
    print(f"stage2b_prepare: qids={len(selected)} candidates={len(candidate_rows)} ready={sum(row['status'] == 'ready' for row in candidate_rows)}", flush=True)


def stage2b_encode_manifest(
    args: argparse.Namespace,
    existing: dict[str, dict[str, Any]],
    requested_count: int,
    started: float,
    status: str,
    native_supported: bool | None,
    last_candidate_id: str | None,
    error: str | None = None,
    device: str | None = None,
) -> None:
    out = args.out_dir
    mode_counts: dict[str, int] = {}
    for row in existing.values():
        mode_counts[row["input_mode"]] = mode_counts.get(row["input_mode"], 0) + 1
    total_inference_s = sum(float(row.get("elapsed_s", 0.0)) for row in existing.values())
    payload: dict[str, Any] = {
        "issue": 81,
        "experiment": "temporal-representation-v1-stage2b",
        "status": status,
        "control_sha256": sha256_file(out / "control_113.jsonl"),
        "candidate_manifest_sha256": sha256_file(out / "stage2b_candidates.jsonl"),
        "model_snapshot": str(args.model_snapshot),
        "instruction": DEFAULT_INSTRUCTION,
        "input_modes": {
            "contact_sheet": "one ordered contact-sheet image tiled left-to-right from exact decoded w3_d60 frames",
            "native3": "native Qwen image list of exact decoded w3_d60 frames in offset order",
            "native5": "native Qwen image list of exact decoded w5_d60 frames in offset order",
        },
        "query_ids": sorted({row["query_id"] for row in existing.values()}),
        "requested_count": requested_count,
        "completed_count": len(existing),
        "mode_counts": mode_counts,
        "native_multi_image_supported": native_supported,
        "ground_truth_used": False,
        "production_mutation": False,
        "full_corpus_run": False,
        "device": device,
        "run_elapsed_s": round(time.time() - started, 3),
        "cumulative_inference_s": round(total_inference_s, 3),
        "last_candidate_id": last_candidate_id,
    }
    if error:
        payload["error"] = error
    vector_path = out / "stage2b_embeddings.jsonl"
    if vector_path.exists():
        payload["embedding_manifest_sha256"] = sha256_file(vector_path)
    write_json(out / "stage2b_surface_manifest.json", payload)


def stage2b_encode(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = {str(row["query_id"]): row for row in jsonl_read(out / "control_113.jsonl")}
    selected = stage2b_selected(args, controls)
    modes = [x.strip() for x in args.stage2b_modes.split(",") if x.strip()]
    invalid = sorted(set(modes) - set(STAGE2B_MODE_SPECS))
    if invalid:
        raise RuntimeError(f"unsupported Stage 2b modes: {invalid}; choose from {sorted(STAGE2B_MODE_SPECS)}")
    if not modes:
        raise RuntimeError("Stage 2b requires at least one mode")
    candidates = [
        row
        for row in jsonl_read(out / "stage2b_candidates.jsonl")
        if row["query_id"] in selected
        and int(row["baseline_center_rank"]) <= args.stage2b_candidate_limit
    ]
    requested: list[tuple[str, dict[str, Any]]] = []
    for mode in modes:
        spec_name = STAGE2B_MODE_SPECS[mode]
        requested.extend((mode, row) for row in candidates if row["window_spec"] == spec_name and row["status"] == "ready")
    vector_path = out / "stage2b_embeddings.jsonl"
    existing: dict[str, dict[str, Any]] = {}
    if vector_path.exists():
        for row in jsonl_read(vector_path):
            if row.get("candidate_id") and row.get("input_mode"):
                existing[f"{row['candidate_id']}:{row['input_mode']}"] = row
    pending = [(mode, row) for mode, row in requested if f"{row['candidate_id']}:{mode}" not in existing]
    if not pending:
        existing_native = any(row.get("input_mode", "").startswith("native") for row in existing.values())
        stage2b_encode_manifest(args, existing, len(requested), time.time(), "complete", existing_native or None, None)
        print(f"stage2b_encode: all {len(requested)} requested rows already present", flush=True)
        return
    missing_qids = sorted(set(selected) - {row["query_id"] for row in jsonl_read(out / "query_vectors.jsonl")})
    if missing_qids:
        raise RuntimeError(f"missing cached text vectors for Stage 2b query ids: {missing_qids}")
    torch, model, processor = load_embedding_model(args.model_snapshot)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    started = time.time()
    native_supported: bool | None = True if any(row.get("input_mode", "").startswith("native") for row in existing.values()) else None
    stage2b_encode_manifest(args, existing, len(requested), started, "in_progress", native_supported, None, device=device)
    for index, (mode, row) in enumerate(pending, 1):
        if mode == "contact_sheet":
            input_paths = [Path(row["contact_sheet_path"])]
        else:
            input_paths = [Path(item["path"]) for item in row["frames"]]
        row_started = time.time()
        try:
            vector = encode_multiframe(torch, model, processor, input_paths)
        except KeyboardInterrupt:
            stage2b_encode_manifest(
                args, existing, len(requested), started, "interrupted", native_supported,
                row["candidate_id"], "pilot interrupted at the bounded runtime cap", device=device,
            )
            raise
        except Exception as exc:
            if mode.startswith("native"):
                native_supported = False
            stage2b_encode_manifest(args, existing, len(requested), started, "error", native_supported, row["candidate_id"], str(exc), device=device)
            raise
        if mode.startswith("native"):
            native_supported = True
        elapsed_s = round(time.time() - row_started, 3)
        key = f"{row['candidate_id']}:{mode}"
        existing[key] = {
            "candidate_id": row["candidate_id"],
            "query_id": row["query_id"],
            "window_spec": row["window_spec"],
            "baseline_center_rank": row["baseline_center_rank"],
            "video_id": row["video_id"],
            "center_frame_id": row["center_frame_id"],
            "frame_ids": [item["frame_id"] for item in row["frames"]],
            "frame_paths": [item["path"] for item in row["frames"]],
            "frame_source_ids": [item["source_frame_id"] for item in row["frames"]],
            "requested_offsets": row["requested_offsets"],
            "contact_sheet_path": row.get("contact_sheet_path"),
            "input_paths": [str(path) for path in input_paths],
            "input_mode": mode,
            "native_multi_image": mode.startswith("native"),
            "vector": vector,
            "elapsed_s": elapsed_s,
            "model_snapshot": str(args.model_snapshot),
            "instruction": DEFAULT_INSTRUCTION,
            "ground_truth_used": False,
        }
        jsonl_write(vector_path, [existing[key] for key in sorted(existing)])
        stage2b_encode_manifest(args, existing, len(requested), started, "in_progress", native_supported, row["candidate_id"], device=device)
        print(f"stage2b_encode [{index}/{len(pending)}] mode={mode} {row['candidate_id']} elapsed_s={elapsed_s}", flush=True)
    stage2b_encode_manifest(args, existing, len(requested), started, "complete", native_supported, pending[-1][1]["candidate_id"], device=device)


def stage2b_candidate_item(candidate: dict[str, Any], mode: str, score: float) -> dict[str, Any]:
    frames = candidate.get("frames") or []
    if mode == "single_frame":
        window_frames = [{
            "video_id": candidate["video_id"],
            "frame_id": candidate["center_frame_id"],
            "source_frame_id": f"{candidate['video_id']}#{int(candidate['center_frame_id']):06d}",
        }]
    else:
        window_frames = [
            {
                "video_id": item["video_id"],
                "frame_id": item["frame_id"],
                "source_frame_id": item["source_frame_id"],
                "requested_offset": item["offset"],
                "path": item["path"],
            }
            for item in frames
        ]
    return {
        "rank": 0,
        "distance": float(score),
        "score": float(score),
        "video_id": candidate["video_id"],
        "frame_id": candidate["center_frame_id"],
        "source_frame_id": f"{candidate['video_id']}#{int(candidate['center_frame_id']):06d}",
        "center_source_frame_id": f"{candidate['video_id']}#{int(candidate['center_frame_id']):06d}",
        "window_spec": candidate["window_spec"],
        "window_frames": window_frames,
        "baseline_center_rank": candidate["baseline_center_rank"],
        "candidate_id": candidate["candidate_id"],
        "input_mode": mode,
    }


def stage2b_score(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = {str(row["query_id"]): row for row in jsonl_read(out / "control_113.jsonl")}
    selected = stage2b_selected(args, controls)
    vectors = {row["query_id"]: np.asarray(row["vector"], dtype=np.float32) for row in jsonl_read(out / "query_vectors.jsonl")}
    if sorted(set(selected) - set(vectors)):
        raise RuntimeError(f"missing cached text vectors for Stage 2b query ids: {sorted(set(selected) - set(vectors))}")
    candidates = {
        row["candidate_id"]: row
        for row in jsonl_read(out / "stage2b_candidates.jsonl")
        if row["query_id"] in selected
        and row["status"] == "ready"
        and int(row["baseline_center_rank"]) <= args.stage2b_candidate_limit
    }
    embeddings = jsonl_read(out / "stage2b_embeddings.jsonl")
    by_mode: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in embeddings:
        if row["query_id"] not in selected:
            continue
        by_mode.setdefault((row["query_id"], row["input_mode"]), []).append(row)
    scored: list[dict[str, Any]] = []
    mode_order = ("single_frame", "contact_sheet", "native3", "native5")
    for qid in selected:
        control = controls[qid]
        baseline = normalize_results(control.get("baseline_results", []), args.stage2b_candidate_limit)
        baseline_items = []
        for candidate in baseline:
            meta = {
                "candidate_id": f"{qid}:w3_d60:r{candidate['rank']:03d}",
                "query_id": qid,
                "window_spec": "w3_d60",
                "video_id": video_id(candidate),
                "center_frame_id": frame_number(candidate),
                "baseline_center_rank": candidate["rank"],
                "frames": [{
                    "video_id": video_id(candidate),
                    "frame_id": frame_number(candidate),
                    "source_frame_id": source_frame_id(candidate),
                    "offset": 0,
                    "path": "",
                }],
            }
            baseline_items.append(stage2b_candidate_item(meta, "single_frame", float(candidate["score"])))
        modes: dict[str, dict[str, Any]] = {
            "single_frame": {
                "source": "frozen baseline single-frame qwen_vl score",
                "metrics": metrics(baseline_items, control),
                "event_proxy_at_pool": event_summary(baseline_items, control, args.stage2b_candidate_limit),
                "top": baseline_items,
            }
        }
        for mode in ("contact_sheet", "native3", "native5"):
            values: list[dict[str, Any]] = []
            for row in by_mode.get((qid, mode), []):
                meta = candidates.get(row["candidate_id"])
                if not meta:
                    continue
                score_value = float(np.dot(vectors[qid], np.asarray(row["vector"], dtype=np.float32)))
                values.append(stage2b_candidate_item(meta, mode, score_value))
            if not values:
                continue
            values.sort(key=lambda item: (-item["score"], item["candidate_id"]))
            for rank, item in enumerate(values, 1):
                item["rank"] = rank
            modes[mode] = {
                "source": {
                    "contact_sheet": "Qwen single-image embedding over one left-to-right exact-frame contact sheet",
                    "native3": "Qwen native ordered 3-image embedding over exact decoded frames",
                    "native5": "Qwen native ordered 5-image embedding over exact decoded frames",
                }[mode],
                "metrics": metrics(values, control),
                "event_proxy_at_pool": event_summary(values, control, args.stage2b_candidate_limit),
                "top": values,
            }
        full_baseline = normalize_results(control.get("baseline_results", []), None)
        accepted = accepted_videos(control)
        scored.append({
            "query_id": qid,
            "query_text_sha256": sha256_text(str(control.get("query_text", ""))),
            "candidate_limit": args.stage2b_candidate_limit,
            "candidate_pool": [item["source_frame_id"] for item in baseline_items],
            "accepted_video_ids": sorted(accepted),
            "accepted_video_in_pool": any(video_id(item) in accepted for item in baseline_items),
            "baseline_video_rank_full": next((item["rank"] for item in full_baseline if video_id(item) in accepted), None),
            "modes": modes,
        })
    jsonl_write(out / "stage2b_scored.jsonl", scored)
    mode_names = [mode for mode in mode_order if any(mode in record["modes"] for record in scored)]
    summaries: dict[str, Any] = {
        "selected_query_count": len(scored),
        "candidate_limit": args.stage2b_candidate_limit,
        "candidate_pool_metric_note": "R@k is computed over the frozen baseline top-N bounded pool, not a fresh full-corpus retrieval.",
    }
    for mode in mode_names:
        rows = [record["modes"][mode] for record in scored if mode in record["modes"]]
        metric_rows = [row["metrics"] for row in rows]
        events = [row["event_proxy_at_pool"] for row in rows if row["event_proxy_at_pool"]]
        summaries[mode] = {
            "n": len(rows),
            "source": rows[0]["source"] if rows else None,
            "video_R@1": summarize(metric_rows, "video_R@1"),
            "video_R@5": summarize(metric_rows, "video_R@5"),
            "video_R@20": summarize(metric_rows, "video_R@20"),
            "range_R@20": summarize(metric_rows, "range_R@20"),
            "trake_proxy": {
                "n": len(events),
                "event_hits": sum(item["hit_count"] for item in events),
                "event_count": sum(item["event_count"] for item in events),
                "all_events_hit": sum(int(item["all_events_hit"]) for item in events),
            },
        }
    write_json(out / "stage2b_summaries.json", summaries)
    deltas = []
    for record in scored:
        delta = {
            "query_id": record["query_id"],
            "accepted_video_in_pool": record["accepted_video_in_pool"],
            "baseline_video_rank_full": record["baseline_video_rank_full"],
            "modes": {},
        }
        for mode in mode_names:
            value = record["modes"].get(mode)
            if not value:
                continue
            rank = next((item["rank"] for item in value["top"] if video_id(item) in set(record["accepted_video_ids"])), None)
            delta["modes"][mode] = {
                "video_rank_in_pool": rank,
                "video_R@1": value["metrics"]["video_R@1"],
                "video_R@5": value["metrics"]["video_R@5"],
                "video_R@20": value["metrics"]["video_R@20"],
            }
        deltas.append(delta)
    write_json(out / "stage2b_per_query_deltas.json", deltas)
    write_json(out / "stage2b_score_manifest.json", {
        "issue": 81,
        "control_sha256": sha256_file(out / "control_113.jsonl"),
        "candidate_manifest_sha256": sha256_file(out / "stage2b_candidates.jsonl"),
        "embedding_manifest_sha256": sha256_file(out / "stage2b_embeddings.jsonl"),
        "selected_query_ids": selected,
        "candidate_limit": args.stage2b_candidate_limit,
        "modes_scored": mode_names,
        "ground_truth_used_for_construction": False,
        "full_corpus_run": False,
        "production_mutation": False,
    })
    lines = [
        "# Stage 2b native ordered multi-image Qwen comparison (Vecna issue #81)",
        "",
        f"Eight-query bounded comparison over frozen baseline top {args.stage2b_candidate_limit} candidates per query. R@k below is pool ranking over those candidates, not a fresh full-corpus retrieval.",
        "",
        "| mode | n | pool video R@1 | pool video R@5 | pool video R@20 | event hits / events |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode in mode_names:
        value = summaries[mode]
        event = value["trake_proxy"]
        lines.append(f"| {mode} | {value['n']} | {fmt(value['video_R@1']['recall'])} | {fmt(value['video_R@5']['recall'])} | {fmt(value['video_R@20']['recall'])} | {event['event_hits']} / {event['event_count']} |")
    lines += [
        "",
        "Mode definitions:",
        "- `single_frame`: frozen baseline score for the center frame using the existing qwen_vl retrieval surface.",
        "- `contact_sheet`: one Qwen image tiled left-to-right from the exact 3-frame window.",
        "- `native3`: native ordered Qwen image list containing the exact 3-frame window.",
        "- `native5`: conditional native ordered Qwen image list containing the exact 5-frame window; absent unless explicitly run.",
        "",
        "The native3 feasibility pilot was stopped at a 600-second cap before its first embedding completed; see `stage2b_native3_pilot_manifest.json`. Native3 and native5 are therefore not scored in this bounded run.",
        "",
        "TRAKE/event values are development proxies, not reviewed organizer ground truth. No production index, corpus features, or benchmark truth were changed.",
        "",
    ]
    (out / "STAGE2B_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def event_summary(item: dict[str, Any], row: dict[str, Any], k: int) -> dict[str, Any] | None:
    events = row.get("trake_event_truth") or []
    if not events:
        return None
    top = item[:k]
    checks = []
    for event in events:
        window = event.get("proxy_window") or {}
        start = window.get("start_frame")
        end = window.get("end_frame")
        hit = False
        for candidate in top:
            for frame in item_frames(candidate):
                number = frame_number(frame)
                if video_id(frame) in accepted_videos(row) and start is not None and end is not None and int(start) <= int(number or -1) <= int(end):
                    hit = True
        checks.append({"event_index": event.get("event_index"), "hit": hit, "truth_tier": event.get("truth_tier")})
    return {"event_count": len(checks), "hit_count": sum(int(x["hit"]) for x in checks), "all_events_hit": bool(checks) and all(x["hit"] for x in checks), "events": checks}


def score(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = {str(row["query_id"]): row for row in jsonl_read(out / "control_113.jsonl")}
    target = json.loads((out / "temporal_target_subset.json").read_text(encoding="utf-8"))
    selected = {x.strip() for x in args.query_ids.split(",") if x.strip()} if args.query_ids else {row["query_id"] for row in target["rows"]}
    window_rows = {row["query_id"]: row for row in jsonl_read(out / "window_results.jsonl")}
    scored = []
    for qid in sorted(selected):
        row = controls[qid]
        baseline = normalize_results(row.get("baseline_results", []), args.candidate_limit)
        record = {
            "query_id": qid,
            "operational_phase": row.get("operational_phase"),
            "capability_tags": row.get("capability_tags", []),
            "scoreability": row.get("scoreability", {}),
            "truth_provenance": row.get("truth_provenance"),
            "baseline": {"metrics": metrics(baseline, row), "accepted_video_ids": sorted(accepted_videos(row)), "truth_interval_count": len(truth_intervals(row)), "top20": baseline[:20]},
            "variants": {},
        }
        for arm in ARMS:
            values = (window_rows.get(qid) or {}).get("variants", {}).get(arm, [])
            record["variants"][arm] = {
                "metrics": metrics(values, row),
                "event_proxy_at_20": event_summary(values, row, 20),
                "top20": values[:20],
            }
        scored.append(record)
    jsonl_write(out / "scored_variants.jsonl", scored)
    summaries: dict[str, Any] = {"selected_query_count": len(scored)}
    for arm in ("baseline",) + ARMS:
        metric_rows = [record["baseline"]["metrics"] if arm == "baseline" else record["variants"][arm]["metrics"] for record in scored]
        summaries[arm] = {metric: summarize(metric_rows, metric) for metric in ("video_R@1", "video_R@5", "video_R@20", "range_R@1", "range_R@5", "range_R@20")}
    summaries["trake_proxy"] = {}
    for arm in ARMS:
        values = [record["variants"][arm]["event_proxy_at_20"] for record in scored if record["variants"][arm]["event_proxy_at_20"]]
        summaries["trake_proxy"][arm] = {"n": len(values), "all_events_hit": sum(int(x["all_events_hit"]) for x in values), "all_events_recall": (sum(int(x["all_events_hit"]) for x in values) / len(values) if values else None), "event_hits": sum(x["hit_count"] for x in values), "event_count": sum(x["event_count"] for x in values)}
    write_json(out / "arm_summaries.json", summaries)
    write_json(out / "per_query_deltas.json", [
        {
            "query_id": record["query_id"],
            "baseline_video_rank": next((x["rank"] for x in record["baseline"]["top20"] if video_id(x) in set(record["baseline"]["accepted_video_ids"])), None),
            "baseline": record["baseline"]["metrics"],
            "variants": {arm: record["variants"][arm]["metrics"] for arm in ARMS},
        }
        for record in scored
    ])
    write_report(args, scored, summaries)


def fmt(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def write_report(args: argparse.Namespace, scored: list[dict[str, Any]], summaries: dict[str, Any]) -> None:
    stage0 = json.loads((args.out_dir / "stage0_manifest.json").read_text(encoding="utf-8"))
    parity_path = args.out_dir / "surface_parity.json"
    parity = json.loads(parity_path.read_text(encoding="utf-8")) if parity_path.exists() else {}
    lines = [
        "# Temporal representation v1 (Vecna issue #81)",
        "",
        "Stage 1 tests deterministic temporal windows over retained per-frame qwen_vl embeddings. It does not modify production retrieval, re-embed the corpus, or use ground truth to construct candidates/windows.",
        "",
        f"- Exact control: {stage0['control_count']} rows; excluded {', '.join(stage0['excluded'])}; control SHA256 {stage0['control_sha256']}.",
        f"- Metadata-selected temporal subset: {stage0['temporal_target_count']} rows; selection used ground truth: {stage0['ground_truth_used_for_window_construction']}.",
        f"- Candidate pool: frozen baseline top {args.candidate_limit} per query; result limit {args.result_limit}.",
        f"- Windows: {json.dumps(WINDOW_SPECS, sort_keys=True)}.",
        f"- Existing feature root: {args.feature_root}; loaded feature files: {json.loads((args.out_dir / 'window_surface_manifest.json').read_text(encoding='utf-8')).get('feature_files_loaded')}.",
        f"- Frozen-surface parity: {parity.get('parity_status', 'not-run')}; top-20 overlap {parity.get('top20_overlap_fraction')}.",
        "",
        "## Stage 1 arm summary",
        "",
        "| arm | n | video R@1 | video R@5 | video R@20 | range R@20 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm in ("baseline",) + ARMS:
        summary = summaries[arm]
        lines.append(f"| {arm} | {summary['video_R@20']['n']} | {fmt(summary['video_R@1']['recall'])} | {fmt(summary['video_R@5']['recall'])} | {fmt(summary['video_R@20']['recall'])} | {fmt(summary['range_R@20']['recall'])} |")
    lines += ["", "## TRAKE event proxy", "", "These are submission-derived development proxies, not reviewed organizer ground truth.", "", "| arm | queries | all-events hit | event hits / events |", "|---|---:|---:|---:|"]
    for arm in ARMS:
        value = summaries["trake_proxy"][arm]
        lines.append(f"| {arm} | {value['n']} | {value['all_events_hit']} | {value['event_hits']} / {value['event_count']} |")
    lines += ["", "## Interpretation", "", "A temporal arm is a candidate for Stage 2 only if its held-out/control comparison shows a material, reproducible rescue of temporal failures without an unacceptable regression. Per-query deltas are in per_query_deltas.json; full ranked outputs and window provenance are in scored_variants.jsonl and window_results.jsonl.", "", "## Reproduction", "", f"py -3.12 aic51-src/script/temporal_representation_v1.py --stage build --out-dir {args.out_dir}", f"py -3.12 aic51-src/script/temporal_representation_v1.py --stage encode --out-dir {args.out_dir}", f"py -3.12 aic51-src/script/temporal_representation_v1.py --stage run --out-dir {args.out_dir}", f"py -3.12 aic51-src/script/temporal_representation_v1.py --stage score --out-dir {args.out_dir}", ""]
    (args.out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("build", "encode", "run", "score", "stage2_prepare", "stage2_encode", "stage2_score", "stage2b_prepare", "stage2b_encode", "stage2b_score", "all"), required=True)
    parser.add_argument("--control", type=Path, default=DEFAULT_CONTROL)
    parser.add_argument("--feature-root", type=Path, default=DEFAULT_FEATURE_ROOT)
    parser.add_argument("--model-snapshot", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--query-ids", default="")
    parser.add_argument("--parity-query", default="p3_q01")
    parser.add_argument("--candidate-limit", type=int, default=100)
    parser.add_argument("--result-limit", type=int, default=100)
    parser.add_argument("--stage2-candidate-limit", type=int, default=3)
    parser.add_argument("--stage2b-candidate-limit", type=int, default=3)
    parser.add_argument("--stage2b-modes", default="contact_sheet,native3")
    parser.add_argument("--encode-batch-size", type=int, default=4)
    parser.add_argument("--milvus-uri", default="http://127.0.0.1:19530")
    parser.add_argument("--collection", default="official_l21_l30_all_v2")
    parser.add_argument("--nprobe", type=int, default=32)
    args = parser.parse_args()
    if args.stage in ("build", "all"):
        build(args)
    if args.stage in ("encode", "all"):
        encode(args)
    if args.stage in ("run", "all"):
        run_windows(args)
    if args.stage in ("score", "all"):
        score(args)
    if args.stage == "stage2_prepare":
        stage2_prepare(args)
    if args.stage == "stage2_encode":
        stage2_encode(args)
    if args.stage == "stage2_score":
        stage2_score(args)
    if args.stage == "stage2b_prepare":
        stage2b_prepare(args)
    if args.stage == "stage2b_encode":
        stage2b_encode(args)
    if args.stage == "stage2b_score":
        stage2b_score(args)
    if args.stage == "encode":
        controls = {row["query_id"]: row for row in jsonl_read(args.out_dir / "control_113.jsonl")}
        vectors = {row["query_id"]: row["vector"] for row in jsonl_read(args.out_dir / "query_vectors.jsonl")}
        run_parity(args, controls, vectors)


if __name__ == "__main__":
    main()
