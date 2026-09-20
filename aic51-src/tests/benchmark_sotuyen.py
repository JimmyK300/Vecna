"""
SOTUYEN Competition Benchmark Suite for Vecna Multimodal Search Engine.
Evaluates:
  1. Config A: Hybrid 3 Models (CLIP PE-L-14 + SigLIP SO400M + Qwen-VL 2B)
  2. Config B: Hybrid 2 Models (SigLIP SO400M + Qwen-VL 2B)
  3. Baselines: Qwen-VL only, SigLIP only, CLIP only

Evaluates on all 91 queries from SOTUYEN 1, 2, and 3 against user ground truth.
"""

import os
import sys
import time
import json
import glob
import statistics
import psutil
from pathlib import Path
from collections import defaultdict

# Add aic51-src to sys.path
repo_root = Path(r"E:\Projects\Vecna")
src_path = repo_root / "aic51-src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Windows utf-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import torch
import numpy as np

def get_ram_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

def get_vram_mb() -> tuple[float, float]:
    if torch.cuda.is_available():
        alloc = torch.cuda.memory_allocated(0) / (1024 * 1024)
        res = torch.cuda.memory_reserved(0) / (1024 * 1024)
        return alloc, res
    return 0.0, 0.0

def load_ground_truth():
    base = Path(r"E:\Projects\Vecna\SOTUYEN")
    exam_sets = [
        ("SOTUYEN1", base / "SOTUYEN1-bo-de-thi", base / "submission_1" / "submission"),
        ("SOTUYEN2", base / "SOTUYEN2-bo-de-thi", base / "submission_2"),
        ("SOTUYEN3", base / "SOTUYEN3-bo-de-thi", base / "submission_3" / "submission"),
    ]

    queries = []
    for set_name, q_dir, sub_dir in exam_sets:
        q_files = sorted(glob.glob(str(q_dir / "*.txt")))
        for qf in q_files:
            stem = Path(qf).stem
            csv_path = sub_dir / f"{stem}.csv"
            if not csv_path.exists():
                continue

            with open(qf, "r", encoding="utf-8-sig", errors="replace") as f:
                q_text = f.read().strip()

            target_videos = set()
            candidate_rows = []
            with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as cf:
                for line in cf:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    vid = parts[0].strip().lstrip("\ufeff")
                    target_videos.add(vid)
                    try:
                        fid = int(parts[1].strip().strip('"'))
                    except Exception:
                        fid = -1
                    candidate_rows.append({"video_id": vid, "frame_idx": fid})

            if not candidate_rows:
                continue

            q_type = "kis" if "kis" in stem else ("qa" if "qa" in stem else "trake")
            queries.append({
                "set_name": set_name,
                "stem": stem,
                "type": q_type,
                "text": q_text,
                "target_videos": target_videos,
                "top1_video": candidate_rows[0]["video_id"],
                "top1_frame": candidate_rows[0]["frame_idx"],
                "all_candidates": candidate_rows,
            })

    return queries

def evaluate_predictions(results, gt, frame_tolerance=50):
    """
    Evaluates rank of target video and keyframe hit.
    results: list of dicts from searcher, each has entity: {frame_id: 'VID#FRAME_IDX'}
    gt: dict with target_videos, top1_video, top1_frame, all_candidates
    """
    target_vids = gt["target_videos"]
    top1_vid = gt["top1_video"]
    top1_frame = gt["top1_frame"]
    target_frames_set = {c["frame_idx"] for c in gt["all_candidates"] if c["frame_idx"] > 0}

    video_rank = None
    frame_hit_k20 = False
    frame_hit_k50 = False

    for rank, item in enumerate(results, start=1):
        fid_full = item.get("entity", {}).get("frame_id", "")
        if "#" in fid_full:
            vid, fid_str = fid_full.split("#", 1)
            try:
                fid = int(fid_str)
            except ValueError:
                fid = -1
        else:
            vid, fid = fid_full, -1

        # Check video match
        if video_rank is None and (vid in target_vids or vid == top1_vid):
            video_rank = rank

        # Check frame match (within tolerance of top1 frame or inside target frames)
        if vid in target_vids or vid == top1_vid:
            is_frame_match = False
            if top1_frame > 0 and abs(fid - top1_frame) <= frame_tolerance:
                is_frame_match = True
            elif fid in target_frames_set:
                is_frame_match = True

            if is_frame_match:
                if rank <= 20:
                    frame_hit_k20 = True
                if rank <= 50:
                    frame_hit_k50 = True

    return {
        "video_rank": video_rank,
        "hit_v_1": video_rank == 1 if video_rank else False,
        "hit_v_5": video_rank is not None and video_rank <= 5,
        "hit_v_10": video_rank is not None and video_rank <= 10,
        "hit_v_20": video_rank is not None and video_rank <= 20,
        "reciprocal_rank": (1.0 / video_rank) if video_rank else 0.0,
        "frame_hit_k20": frame_hit_k20,
        "frame_hit_k50": frame_hit_k50,
    }

def run_benchmark():
    print("=" * 80)
    print("     VECNA BENCHMARK: 3-MODEL (CLIP+SigLIP+Qwen) vs 2-MODEL (SigLIP+Qwen)     ")
    print("=" * 80)

    # 1. Load Ground Truth
    queries = load_ground_truth()
    print(f"\n[+] Loaded {len(queries)} competition queries across SOTUYEN 1, 2, 3:")
    kis_count = sum(1 for q in queries if q["type"] == "kis")
    qa_count = sum(1 for q in queries if q["type"] == "qa")
    trake_count = sum(1 for q in queries if q["type"] == "trake")
    print(f"    - KIS (Visual Scenes): {kis_count}")
    print(f"    - QA (Visual QA):      {qa_count}")
    print(f"    - TRAKE (Multi-event): {trake_count}")

    # 2. Configure in-memory models to include all 3 models
    from aic51.packages.config import GlobalConfig
    
    # Trigger load
    GlobalConfig.get()
    raw_cfg = getattr(GlobalConfig, "_GlobalConfig__config", None)
    if raw_cfg is None:
        raw_cfg = {}
        setattr(GlobalConfig, "_GlobalConfig__config", raw_cfg)

    raw_cfg.setdefault("searcher", {})
    raw_cfg["searcher"].setdefault("language_models", {})
    lang_models = raw_cfg["searcher"]["language_models"]

    lang_models["language_clip_pe-l-14-336"] = {
        "model": "image_clip",
        "source": "open_clip",
        "arch_name": "PE-Core-L-14-336",
        "pretrained_model": "meta",
        "target": ["image_clip_pe-l-14-336"],
    }
    lang_models["language_siglip_so400m-384"] = {
        "model": "image_siglip",
        "source": "open_clip",
        "arch_name": "ViT-SO400M-14-SigLIP-384",
        "pretrained_model": "webli",
        "target": ["image_siglip_so400m-384"],
    }
    lang_models["language_qwen_vl"] = {
        "model": "qwen_vl_embedding",
        "pretrained_model": "Qwen/Qwen3-VL-Embedding-2B",
        "target": ["qwen_vl"],
    }

    # Disable reranker for raw visual retrieval comparison
    raw_cfg["searcher"].setdefault("reranker", {})
    raw_cfg["searcher"]["reranker"]["enable"] = False

    # 3. Initialize Searcher
    print("\n[+] Initializing Searcher with CLIP + SigLIP + Qwen-VL...")
    t0 = time.time()
    from aic51.packages.webui.backend.search import setup_searcher
    searcher = setup_searcher()
    t_init = time.time() - t0
    print(f"[+] Initialized in {t_init:.2f}s")

    ram_loaded = get_ram_mb()
    vram_alloc, vram_res = get_vram_mb()
    print(f"    - RAM RSS:         {ram_loaded:.1f} MB")
    print(f"    - VRAM Allocated:  {vram_alloc:.1f} MB ({vram_alloc / 1024:.2f} GB)")
    print(f"    - VRAM Reserved:   {vram_res:.1f} MB ({vram_res / 1024:.2f} GB)")

    # 4. Define Test Configurations
    configs = [
        {
            "name": "Config A: 3 Models (CLIP + SigLIP + Qwen)",
            "short": "3-Model (Hybrid)",
            "features": ["image_clip_pe-l-14-336", "image_siglip_so400m-384", "qwen_vl"],
        },
        {
            "name": "Config B: 2 Models (SigLIP + Qwen)",
            "short": "2-Model (SigLIP+Qwen)",
            "features": ["image_siglip_so400m-384", "qwen_vl"],
        },
        {
            "name": "Config C: Qwen-VL Only",
            "short": "Qwen-VL only",
            "features": ["qwen_vl"],
        },
        {
            "name": "Config D: SigLIP Only",
            "short": "SigLIP only",
            "features": ["image_siglip_so400m-384"],
        },
        {
            "name": "Config E: CLIP Only",
            "short": "CLIP only",
            "features": ["image_clip_pe-l-14-336"],
        },
    ]

    # Warm-up run
    print("\n[+] Warming up models and CUDA kernels...")
    searcher.search_multimodal("người đi xe máy", 0, 10, ["qwen_vl"], auto_translate=True)

    config_metrics = []

    # Run Benchmark for each configuration
    for cfg in configs:
        c_name = cfg["name"]
        c_features = cfg["features"]
        print(f"\n========================================================================")
        print(f"  RUNNING: {c_name}")
        print(f"  Features: {c_features}")
        print(f"========================================================================")

        latencies = []
        eval_records = []

        for i, q in enumerate(queries, start=1):
            q_text = q["text"]
            t_start = time.perf_counter()
            res = searcher.search_multimodal(
                q_text,
                0,
                100,
                c_features,
                ocr_weight=0.0,
                asr_weight=0.0,
                auto_translate=True,
            )
            lat_ms = (time.perf_counter() - t_start) * 1000.0
            latencies.append(lat_ms)

            hit_list = res.get("results", []) if isinstance(res, dict) else res
            ev = evaluate_predictions(hit_list, q)
            ev["query_id"] = q["stem"]
            ev["type"] = q["type"]
            ev["latency_ms"] = lat_ms
            eval_records.append(ev)

            if i % 20 == 0 or i == len(queries):
                current_vr1 = sum(1 for e in eval_records if e["hit_v_1"]) / len(eval_records) * 100.0
                current_vr5 = sum(1 for e in eval_records if e["hit_v_5"]) / len(eval_records) * 100.0
                print(f"  [{i:>2}/{len(queries)}] Avg Latency: {statistics.mean(latencies):.1f}ms | VR@1: {current_vr1:.1f}% | VR@5: {current_vr5:.1f}%")

        # Metrics for All Queries
        n = len(eval_records)
        vr1 = sum(1 for e in eval_records if e["hit_v_1"]) / n * 100.0
        vr5 = sum(1 for e in eval_records if e["hit_v_5"]) / n * 100.0
        vr10 = sum(1 for e in eval_records if e["hit_v_10"]) / n * 100.0
        vr20 = sum(1 for e in eval_records if e["hit_v_20"]) / n * 100.0
        mrr = statistics.mean([e["reciprocal_rank"] for e in eval_records])
        fr20 = sum(1 for e in eval_records if e["frame_hit_k20"]) / n * 100.0
        fr50 = sum(1 for e in eval_records if e["frame_hit_k50"]) / n * 100.0

        # Metrics for KIS Queries only
        kis_records = [e for e in eval_records if e["type"] == "kis"]
        n_kis = len(kis_records)
        kis_vr1 = sum(1 for e in kis_records if e["hit_v_1"]) / n_kis * 100.0
        kis_vr5 = sum(1 for e in kis_records if e["hit_v_5"]) / n_kis * 100.0
        kis_vr20 = sum(1 for e in kis_records if e["hit_v_20"]) / n_kis * 100.0
        kis_mrr = statistics.mean([e["reciprocal_rank"] for e in kis_records])

        avg_lat = statistics.mean(latencies)
        p50_lat = statistics.median(latencies)
        p95_lat = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)

        metrics = {
            "name": cfg["name"],
            "short": cfg["short"],
            "features": c_features,
            "total_queries": n,
            "vr1": vr1,
            "vr5": vr5,
            "vr10": vr10,
            "vr20": vr20,
            "mrr": mrr,
            "fr20": fr20,
            "fr50": fr50,
            "kis_vr1": kis_vr1,
            "kis_vr5": kis_vr5,
            "kis_vr20": kis_vr20,
            "kis_mrr": kis_mrr,
            "avg_lat": avg_lat,
            "p50_lat": p50_lat,
            "p95_lat": p95_lat,
            "eval_records": eval_records,
        }
        config_metrics.append(metrics)

    # 5. Print Comparison Summary
    print("\n" + "=" * 90)
    print("                    SOTUYEN RETRIEVAL BENCHMARK REPORT")
    print("=" * 90)
    print(f"{'Configuration':<26} | {'VR@1':<7} | {'VR@5':<7} | {'VR@20':<7} | {'MRR':<7} | {'KIS VR@5':<9} | {'Lat(ms)':<8}")
    print("-" * 90)
    for m in config_metrics:
        print(f"{m['short']:<26} | {m['vr1']:5.1f}% | {m['vr5']:5.1f}% | {m['vr20']:5.1f}% | {m['mrr']:5.3f} | {m['kis_vr5']:7.1f}% | {m['avg_lat']:6.1f}ms")
    print("=" * 90)

    # Save detailed JSON report
    out_dir = Path(r"E:\Projects\Vecna\workspace\benchmark_results")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / "sotuyen_benchmark_report.json"

    # Export metrics without raw eval_records in main json summary
    json_summary = []
    for m in config_metrics:
        summary_entry = {k: v for k, v in m.items() if k != "eval_records"}
        json_summary.append(summary_entry)

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(json_summary, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Detailed benchmark summary saved to: {report_file}")

    # Export per-query comparison CSV
    csv_file = out_dir / "sotuyen_per_query_comparison.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        headers = ["query_id", "type"]
        for m in config_metrics:
            headers.extend([f"{m['short']}_rank", f"{m['short']}_hit5"])
        f.write(",".join(headers) + "\n")

        for i in range(len(queries)):
            qid = queries[i]["stem"]
            qtype = queries[i]["type"]
            row = [qid, qtype]
            for m in config_metrics:
                rec = m["eval_records"][i]
                rnk = str(rec["video_rank"]) if rec["video_rank"] else "Miss"
                h5 = "1" if rec["hit_v_5"] else "0"
                row.extend([rnk, h5])
            f.write(",".join(row) + "\n")
    print(f"[+] Per-query CSV comparison saved to: {csv_file}")

    # Final Verdict Analysis
    cfg_3m = config_metrics[0]
    cfg_2m = config_metrics[1]
    diff_vr5 = cfg_2m["vr5"] - cfg_3m["vr5"]
    diff_mrr = cfg_2m["mrr"] - cfg_3m["mrr"]
    speedup = cfg_3m["avg_lat"] - cfg_2m["avg_lat"]

    print("\n" + "=" * 90)
    print("                              ARCHITECTURAL VERDICT")
    print("=" * 90)
    print(f"3-Model (CLIP+SigLIP+Qwen)  -> VR@5: {cfg_3m['vr5']:.1f}% | MRR: {cfg_3m['mrr']:.3f} | Latency: {cfg_3m['avg_lat']:.1f}ms")
    print(f"2-Model (SigLIP+Qwen only)  -> VR@5: {cfg_2m['vr5']:.1f}% | MRR: {cfg_2m['mrr']:.3f} | Latency: {cfg_2m['avg_lat']:.1f}ms")
    print(f"Delta (2-Model vs 3-Model)  -> VR@5: {diff_vr5:+.1f}% | MRR: {diff_mrr:+.3f} | Latency: {speedup:+.1f}ms faster")
    print("=" * 90)

if __name__ == "__main__":
    run_benchmark()
