#!/usr/bin/env python3
"""Issue #59 TRAKE exact-event timing audit (read-only diagnosis).

Runs the three current-corpus TRAKE queries from the frozen issue34-v1 set
through the LIVE primary stack (same cell as the issue #58 baseline sweep:
clip_siglip_qwen_sparse, rerank OFF, ocr/asr 0.25/0.25, nprobe 32,
temporal_k 2000) but requests k=1000 instead of k=20 so that ranked evidence
BELOW the judging cutoff becomes visible for diagnosis.

No retrieval parameter, model, index, or config is modified anywhere:
  * nothing under PRIMARY_ROOT is written (bytecode writing disabled);
  * Milvus is only queried (search/query reads), never mutated;
  * every artifact is written under THIS worktree's
    benchmark-results/issue59-trake-audit/.

Outputs (same directory):
  audit.launcher.json      -- identity/provenance of this run
  trake-audit.jsonl        -- per-query evidence records (k=1000 exposure)
  keyframe-density.json    -- indexed-frame density around gold event points
  mechanism-counts.json    -- aggregate failure-mechanism counts
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKTREE_ROOT = HERE.parent.parent
PRIMARY_ROOT = Path(os.environ.get("VECNA_PRIMARY_ROOT", r"C:\Users\minhc\Code\Vecna"))
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

AIC51 = PRIMARY_ROOT / "aic51-src"
SCRIPTS = AIC51 / "script"
for p in (str(AIC51), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)
os.chdir(PRIMARY_ROOT)  # GlobalConfig resolves workspace config.yaml from cwd

AUDIT_K = 1000
DEPTH_LADDER = [1, 5, 10, 20, 50, 100, 200, 500, 1000]
CELL_NAME = "clip_siglip_qwen_sparse"
TOP_SERIALIZED = 60


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*argv: str, cwd: Path = PRIMARY_ROOT) -> str:
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), check=True, capture_output=True, text=True
    ).stdout.strip()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    started_at = utc_now()
    t0 = time.perf_counter()

    launcher = {
        "packet": "issue59-trake-audit",
        "purpose": (
            "Read-only diagnosis: why the current stack misses exact TRAKE event "
            "timing even when video-level retrieval succeeds"
        ),
        "started_at": started_at,
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "python": sys.executable,
        "pythondontwritebytecode": True,
        "primary_root": str(PRIMARY_ROOT),
        "worktree_root": str(WORKTREE_ROOT),
        "worktree_git": {
            "sha": git("rev-parse", "HEAD", cwd=WORKTREE_ROOT),
            "branch": git("branch", "--show-current", cwd=WORKTREE_ROOT),
            "dirty": bool(git("status", "--porcelain=v1", cwd=WORKTREE_ROOT).strip()),
        },
        "primary_git": {
            "sha": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current"),
            "dirty": bool(git("status", "--porcelain=v1").strip()),
        },
        "audit_k": AUDIT_K,
        "cell": CELL_NAME,
        "ranking_note": (
            "k raised from 20 to 1000 to expose deeper ranks; scoring/fusion path "
            "identical to issue58 baseline sweep; no ranking behavior changed"
        ),
    }

    import headless_benchmark as hb
    import run_p20_p21_measurement as runner

    csv_path = runner.CSV_PATH
    content_sha = hb.canonical_content_sha256(csv_path)
    if content_sha != hb.EXPECTED_CANONICAL_CONTENT_SHA256:
        raise ValueError(
            f"canonical Issue #34 digest mismatch: expected "
            f"{hb.EXPECTED_CANONICAL_CONTENT_SHA256}, got {content_sha}"
        )
    cases_all = hb.load_cases(csv_path)
    validation = hb.validate_canonical_issue34_inventory(cases_all, False)

    trake_cases = [c for c in cases_all if c["task_type"] == "trake"]
    included = [
        c
        for c in trake_cases
        if c["evaluation_scope"] == "include_current_dataset" and c["scoreable"]
    ]
    excluded = [
        {
            "query_id": c["query_id"],
            "reason": f"evaluation_scope={c['evaluation_scope']} (corpus not in current index)",
        }
        for c in trake_cases
        if c not in included
    ]

    launcher["frozen_set"] = {
        "path": str(csv_path),
        "raw_file_sha256": sha256_file(csv_path),
        "canonical_content_sha256": content_sha,
        "expected_canonical_content_sha256": hb.EXPECTED_CANONICAL_CONTENT_SHA256,
        "schema_version": hb.CANONICAL_SCHEMA_VERSION,
        "inventory_complete": validation["complete"],
        "ground_truth_tier": "provisional (source_text_verified_needs_corpus_validation)",
        "trake_total": len(trake_cases),
        "trake_included": [c["query_id"] for c in included],
        "trake_excluded": excluded,
    }
    launcher_path = HERE / "audit.launcher.json"
    write_json(launcher_path, launcher)

    cell = runner.CELLS_BY_NAME[CELL_NAME]
    runner.apply_cell_config(cell)  # in-memory only; mirrors official quality cell
    collection = hb.preflight_collection(PRIMARY_ROOT / "config.yaml")
    from aic51.packages.webui.backend.search import setup_searcher

    init_started = time.perf_counter()
    searcher = setup_searcher()
    init_s = time.perf_counter() - init_started
    features = hb.choose_features(searcher, ",".join(cell["features"]))
    args = runner.benchmark_args()
    match_config = args.match_config

    records = []
    for case in included:
        q_started = time.perf_counter()
        raw = searcher.search_multimodal(
            case["query"],
            0,
            AUDIT_K,
            features,
            nprobe=args.nprobe,
            temporal_k=args.temporal_k,
            ocr_weight=args.ocr_weight,
            asr_weight=args.asr_weight,
            max_interval=args.max_interval,
            selected=None,
            auto_translate=args.auto_translate,
            en_to_vi_translate=args.en_to_vi_translate,
        )
        latency_ms = round((time.perf_counter() - q_started) * 1000, 3)
        results = hb.normalize_results(list(raw.get("results", [])), AUDIT_K)
        tree = getattr(searcher, "last_latency_tree", None) or {}
        serving_query_mode = tree.get("query_mode")

        metrics20 = hb.metrics_for_results(results[: hb.JUDGING_DEPTH], case, match_config)
        group = case["accepted_groups"][0]
        full_event_ranks = hb.group_match_ranks(results, group, match_config)
        video_targets = [{"kind": "video", "video_id": t["video_id"]} for t in group]
        full_video_ranks = hb.group_match_ranks(results, video_targets, match_config)

        gt_video = group[0]["video_id"]
        fps = match_config.fps_for(gt_video)
        gold_points = [t["frame"] for t in group]

        gt_entries = []
        for rank, record in enumerate(results, 1):
            video, frame, _timeline, _entity = hb.unpack_result(record)
            if hb.normalize_video_id(video) == hb.normalize_video_id(gt_video):
                gt_entries.append({"rank": rank, "frame": int(frame)})
        gt_ranks_sorted = sorted(e["rank"] for e in gt_entries)

        depth_ladder = {}
        for depth in DEPTH_LADDER:
            upto = results[:depth]
            ev_hits = sum(1 for r in full_event_ranks if r is not None and r <= depth)
            vid_hit = any(r is not None and r <= depth for r in full_video_ranks)
            depth_ladder[str(depth)] = {
                "events_within_tolerance": ev_hits,
                "event_recall": round(ev_hits / len(group), 6),
                "correct_video_present": bool(vid_hit),
            }

        # Per-event diagnostics over the full exposed list.
        events = []
        for idx, target in enumerate(group, 1):
            gold = int(target["frame"])
            hit_rank = full_event_ranks[idx - 1]
            # nearest returned GT-video frame to this gold point
            best = None
            for entry in gt_entries:
                delta = abs(entry["frame"] - gold)
                if best is None or delta < best["delta_frames"]:
                    best = {
                        "rank": entry["rank"],
                        "frame": entry["frame"],
                        "delta_frames": int(delta),
                        "delta_seconds": round(delta / fps, 4),
                    }
            events.append(
                {
                    "event": f"E{idx}",
                    "gold_frame": gold,
                    "gold_seconds": round(gold / fps, 3),
                    "first_candidate_rank_within_tolerance_full_k": hit_rank,
                    "hit_within_top20": bool(hit_rank is not None and hit_rank <= 20),
                    "nearest_returned_gt_frame": best,
                    "in_tolerance_anywhere_in_top_k": bool(hit_rank is not None),
                }
            )

        # Wrong-video crowding above the first event-correct rank.
        first_hit = next((r for r in full_event_ranks if r is not None), None)
        wrong_video_slots_above = {}
        if first_hit is not None:
            for rank, record in enumerate(results[: first_hit - 1], 1):
                video, _frame, _tl, _e = hb.unpack_result(record)
                if hb.normalize_video_id(video) != hb.normalize_video_id(gt_video):
                    wrong_video_slots_above[video] = wrong_video_slots_above.get(video, 0) + 1

        def channel_scores(record):
            scores = record.get("scores") or {}

            def num(key):
                try:
                    return float(scores.get(key) or 0.0)
                except (TypeError, ValueError):
                    return 0.0

            return {k: round(num(k), 6) for k in ("final", "clip", "ocr", "asr")}

        top1 = results[0] if results else None
        best_gt_event_candidate = None
        if first_hit is not None:
            best_gt_event_candidate = {
                "rank": first_hit,
                **channel_scores(results[first_hit - 1]),
                **{
                    "frame_id": hb.unpack_result(results[first_hit - 1])[1],
                },
            }

        record_out = {
            "schema_version": "issue59-trake-audit-v1",
            "generated_at": utc_now(),
            "query_id": case["query_id"],
            "task_type": case["task_type"],
            "ground_truth_tier": hb.ground_truth_tier(case),
            "validation_state": case["validation_state"],
            "answers": case["answer_strings"],
            "gold_video": gt_video,
            "fps": fps,
            "gold_points_frames": gold_points,
            "serving_query_mode": serving_query_mode,
            "event_count": len(group),
            "params": {
                "k_exposed": AUDIT_K,
                "nprobe": args.nprobe,
                "temporal_k": args.temporal_k,
                "ocr_weight": args.ocr_weight,
                "asr_weight": args.asr_weight,
                "max_interval": args.max_interval,
                "auto_translate": args.auto_translate,
                "target_features": features,
                "rerank": False,
                "cell": CELL_NAME,
            },
            "official_depth20_metrics": {
                k: metrics20[k]
                for k in (
                    "first_correct_rank",
                    "recall_at_1",
                    "recall_at_5",
                    "recall_at_10",
                    "recall_at_20",
                    "target_ranks",
                    "no_hit_within_20",
                )
            },
            "video_level": {
                "first_correct_video_rank_top20": (metrics20.get("video_retrieval") or {}).get(
                    "first_correct_video_rank"
                ),
                "first_correct_video_rank_full_k": next(
                    (r for r in full_video_ranks if r is not None), None
                ),
                "gt_video_entries_in_top_k": len(gt_entries),
                "gt_video_entry_ranks_first_20": gt_ranks_sorted[:20],
            },
            "event_level_full_k": {
                "per_event_first_rank_within_tolerance": full_event_ranks,
                "all_events_found_within_top_k": all(r is not None for r in full_event_ranks),
            },
            "depth_ladder": depth_ladder,
            "events": events,
            "crowding": {
                "first_event_correct_rank": first_hit,
                "wrong_video_slots_above_first_event_correct": dict(
                    sorted(
                        wrong_video_slots_above.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )
                ),
            },
            "score_evidence": {
                "top1": (
                    {
                        "rank": 1,
                        "frame_id": hb.unpack_result(top1)[1] if top1 else None,
                        "video_id": hb.unpack_result(top1)[0] if top1 else None,
                        **channel_scores(top1),
                    }
                    if top1
                    else None
                ),
                "best_gt_event_candidate": best_gt_event_candidate,
            },
            "latency_ms": latency_ms,
            "review_burden": {
                "clips_to_review_until_first_event_hit_depth20": metrics20.get(
                    "first_correct_rank"
                ),
                "per_event_clip_review_rank_full_k": full_event_ranks,
                "gt_video_keyframes_before_last_event_hit": (
                    sum(1 for r in gt_ranks_sorted if r <= max(full_event_ranks))
                    if all(r is not None for r in full_event_ranks)
                    else None
                ),
            },
            "top_results_serialized": [
                hb.serialize_result(item, rank, case, match_config)
                for rank, item in enumerate(results[:TOP_SERIALIZED], 1)
            ],
        }
        records.append(record_out)
        print(
            f"[{case['query_id']}] mode={serving_query_mode} "
            f"video@20={(metrics20.get('video_retrieval') or {}).get('first_correct_video_rank')} "
            f"events@20={metrics20.get('target_ranks')} "
            f"events@full={full_event_ranks} latency={latency_ms}ms",
            flush=True,
        )

    jsonl_path = HERE / "trake-audit.jsonl"
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ---- read-only Milvus density probe around gold points -----------------
    from pymilvus import MilvusClient
    from aic51.packages.config import GlobalConfig

    coll_name = GlobalConfig.get("backends", "search", "collection") or "milvus"
    client = MilvusClient(uri="http://localhost:19530")
    density = {"collection": coll_name, "videos": {}}
    try:
        for case in included:
            group = case["accepted_groups"][0]
            gt_video = group[0]["video_id"]
            norm_gt = hb.normalize_video_id(gt_video)
            frames = []
            batch_limit = 4096
            offset = 0
            while True:
                rows = client.query(
                    coll_name,
                    filter=f'frame_id like "{gt_video}#%"',
                    output_fields=["frame_id"],
                    limit=batch_limit,
                    offset=offset,
                )
                if not rows:
                    break
                for row in rows:
                    _, raw_frame = row["frame_id"].rsplit("#", 1)
                    frames.append(int(raw_frame))
                if len(rows) < batch_limit:
                    break
                offset += batch_limit
            frames = sorted(set(frames))
            fps = match_config.fps_for(norm_gt)
            gaps_frames = [b - a for a, b in zip(frames, frames[1:]) if b > a]
            gap_seconds = [round(g / fps, 4) for g in gaps_frames]
            per_event = []
            for idx, target in enumerate(group, 1):
                gold = int(target["frame"])
                if frames:
                    nearest = min(frames, key=lambda f: abs(f - gold))
                    delta = abs(nearest - gold)
                else:
                    nearest, delta = None, None
                per_event.append(
                    {
                        "event": f"E{idx}",
                        "gold_frame": gold,
                        "nearest_indexed_frame": nearest,
                        "delta_frames": delta,
                        "delta_seconds": round(delta / fps, 4) if delta is not None else None,
                        "indexed_frame_within_2s": bool(
                            delta is not None and (delta / fps) <= 2.0
                        ),
                        "indexed_frame_within_official_12f": bool(
                            delta is not None and delta <= 12
                        ),
                    }
                )
            density["videos"][norm_gt] = {
                "indexed_frame_count": len(frames),
                "fps": fps,
                "gap_seconds_median": round(statistics.median(gap_seconds), 4)
                if gap_seconds
                else None,
                "gap_seconds_p95": round(sorted(gap_seconds)[int(0.95 * len(gap_seconds))], 4)
                if gap_seconds
                else None,
                "gap_seconds_max": round(max(gap_seconds), 4) if gap_seconds else None,
                "per_gold_point": per_event,
            }
    finally:
        client.close()

    write_json(HERE / "keyframe-density.json", density)

    # ---- deterministic mechanism classification (rules fixed up-front) -----
    mechanisms = {
        "single_vector_multi_event_no_decomposition": 0,
        "correct_video_but_event_window_missing_from_top20": 0,
        "event_window_absent_entirely_from_top1000": 0,
        "visual_semantics_wrong_video_crowding": 0,
        "index_frame_gap_at_gold_point_over_2s": 0,
        "duplicate_results_same_video_slot_flooding": 0,
        "unresolved": 0,
    }
    per_query_mechanisms = {}
    for record in records:
        found = []
        n_events = record["event_count"]
        if n_events >= 2 and record["serving_query_mode"] != "temporal":
            found.append("single_vector_multi_event_no_decomposition")
            mechanisms["single_vector_multi_event_no_decomposition"] += 1
        ev20 = record["official_depth20_metrics"]["target_ranks"]
        missed20 = sum(1 for r in ev20 if r is None)
        if missed20:
            found.append("correct_video_but_event_window_missing_from_top20")
            mechanisms["correct_video_but_event_window_missing_from_top20"] += 1
        missing_forever = sum(
            1 for r in record["event_level_full_k"]["per_event_first_rank_within_tolerance"] if r is None
        )
        if missing_forever:
            found.append("event_window_absent_entirely_from_top1000")
            mechanisms["event_window_absent_entirely_from_top1000"] += 1
        crowding = record["crowding"]["wrong_video_slots_above_first_event_correct"]
        if crowding and sum(crowding.values()) >= 5:
            found.append("visual_semantics_wrong_video_crowding")
            mechanisms["visual_semantics_wrong_video_crowding"] += 1
        video_density = density["videos"].get(hb.normalize_video_id(record["gold_video"])) or {}
        gap_events = [
            e
            for e in (video_density.get("per_gold_point") or [])
            if not e["indexed_frame_within_2s"]
        ]
        if gap_events:
            found.append("index_frame_gap_at_gold_point_over_2s")
            mechanisms["index_frame_gap_at_gold_point_over_2s"] += 1
        gt_ranks = record["video_level"]["gt_video_entry_ranks_first_20"]
        if len(gt_ranks) >= 3:
            found.append("duplicate_results_same_video_slot_flooding")
            mechanisms["duplicate_results_same_video_slot_flooding"] += 1
        if not found:
            found.append("unresolved")
            mechanisms["unresolved"] += 1
        per_query_mechanisms[record["query_id"]] = found

    counts_payload = {
        "schema_version": "issue59-mechanism-counts-v1",
        "generated_at": utc_now(),
        "note": (
            "counts are query-level flags (a query can carry several mechanisms); "
            "rules declared before inspection in run_issue59_trake_audit.py"
        ),
        "queries_analyzed": [r["query_id"] for r in records],
        "mechanism_counts": mechanisms,
        "per_query_mechanisms": per_query_mechanisms,
    }
    write_json(HERE / "mechanism-counts.json", counts_payload)

    elapsed = round(time.perf_counter() - t0, 3)
    write_json(
        HERE / "audit.launcher.json",
        {
            **launcher,
            "status": "complete",
            "ended_at": utc_now(),
            "elapsed_s": elapsed,
            "searcher_init_s": round(init_s, 3),
            "collection_identity": {
                k: collection[k] for k in ("collection", "row_count", "indexes") if k in collection
            },
            "outputs": {
                "trake_audit_jsonl_sha256": sha256_file(jsonl_path),
                "keyframe_density_sha256": sha256_file(HERE / "keyframe-density.json"),
                "mechanism_counts_sha256": sha256_file(HERE / "mechanism-counts.json"),
            },
        },
    )
    print("mechanism counts:", json.dumps(mechanisms, indent=2), flush=True)
    print(f"issue59 TRAKE audit complete in {elapsed}s", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
