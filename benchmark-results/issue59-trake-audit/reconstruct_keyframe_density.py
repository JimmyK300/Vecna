#!/usr/bin/env python3
"""Issue #59 audit follow-up: indexed-keyframe density around gold event points.

Milvus went down (host Docker Desktop engine stopped) after the search phase of
`run_issue59_trake_audit.py`, so the live `query()` density probe could not be
(re)executed. This script reconstructs the SAME information read-only:

  1. The Milvus-ingest keyframe rule is deterministic and recorded in
     provenance (`selection_rule: ffprobe_packet_keyframes_plus_max_scene_gap`,
     aic51.cli.commands.add._extract_keyframes, config add.max_scene_length=2):
     emit a keyframe at decoded-frame i iff
         (i - last_emit_index) >= round-free threshold 2*rounded_fps
         or i is an ffprobe video-packet keyframe index.
     We replay that exact loop over the official source videos on D:.
  2. Validation: every gold-video frame OBSERVED in the k=1000 retrieval
     evidence must be a member of the reconstructed indexable set; any mismatch
     is reported loudly instead of being silently ignored.

Nothing is written outside this audit directory; source videos are only read.
"""
from __future__ import annotations

import json
import statistics
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIDEO_ROOT = Path(r"D:\Official-Dataset\videos")
MAX_SCENE_LENGTH_S = 2.0
FPS_TABLE = {"l26_v194": 25.0, "l24_v033": 30.0, "l26_v072": 25.0}


def find_video(video_id: str) -> Path | None:
    prefix = video_id.split("_")[0]
    direct = VIDEO_ROOT / prefix / f"{video_id}.mp4"
    if direct.exists():
        return direct
    letter = "".join(ch for ch in video_id if ch.isalpha() or ch.isdigit())
    for sub in sorted((VIDEO_ROOT).glob(f"{prefix}*")):
        candidate = sub / f"{video_id}.mp4"
        if candidate.exists():
            return candidate
    for sub in sorted(VIDEO_ROOT.iterdir()):
        if sub.is_dir():
            candidate = sub / f"{video_id}.mp4"
            if candidate.exists():
                return candidate
    return None


def ffprobe_packet_keyframes(path: Path) -> tuple[list[int], int]:
    """Replicates aic51 add._get_keyframes_list exactly (packet flag scan)."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-select_streams",
        "v:0",
        "-show_entries",
        "packet=flags",
        "-of",
        "csv",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    lines = [x for x in res.stdout.strip().split("\n") if x.startswith("packet")]
    return [i for i, line in enumerate(lines) if "K" in line], len(lines)


def replay_ingest(packet_key_frames: list[int], total_packets: int, fps: float) -> list[int]:
    """Replay add._extract_keyframes do_clip=False emission loop."""
    keyframes_set = set(packet_key_frames)
    emitted = []
    scene_length = 0
    max_scene_length = MAX_SCENE_LENGTH_S * fps
    for frame_counter in range(total_packets):
        if scene_length >= max_scene_length or frame_counter in keyframes_set:
            emitted.append(frame_counter)
            scene_length = 0
        scene_length += 1
    return emitted


def main() -> int:
    records = [
        json.loads(line)
        for line in (HERE / "trake-audit.jsonl").open(encoding="utf-8")
        if line.strip()
    ]

    density = {
        "collection": "official_l21_l30_all_v2",
        "method": "ffprobe_reconstruction_fallback (Milvus engine unavailable)",
        "rule": "ffprobe_packet_keyframes_plus_max_scene_gap, max_scene_length=2s, rounded fps",
        "videos": {},
    }
    observed_by_video = {}
    for record in records:
        vid = record["gold_video"].lower()
        seen = set()
        for item in record.get("top_results_serialized") or []:
            if item["video_id"].lower() == vid and item.get("frame_id") is not None:
                seen.add(int(item["frame_id"]))
        for event in record["events"]:
            nearest = event.get("nearest_returned_gt_frame")
            if nearest:
                seen.add(int(nearest["frame"]))
        observed_by_video[vid] = sorted(seen)

    validation = {}
    for record in records:
        group_video = record["gold_video"]
        norm = group_video.lower()
        fps = FPS_TABLE[norm]
        path = find_video(group_video)
        if path is None:
            raise SystemExit(f"source video not found for {group_video}")
        packet_k, total = ffprobe_packet_keyframes(path)
        frames = replay_ingest(packet_k, total, fps)
        frame_set = set(frames)
        gaps = [b - a for a, b in zip(frames, frames[1:]) if b > a]
        gap_seconds = [round(g / fps, 4) for g in gaps]

        missing_observed = [f for f in observed_by_video[norm] if f not in frame_set]
        validation[norm] = {
            "observed_in_retrieval_evidence": observed_by_video[norm],
            "observed_missing_from_reconstructed_set": missing_observed,
            "validated": not missing_observed,
        }

        per_event = []
        for event in record["events"]:
            gold = int(event["gold_frame"])
            if frames:
                nearest = min(frames, key=lambda f: abs(f - gold))
                delta = abs(nearest - gold)
            else:
                nearest, delta = None, None
            per_event.append(
                {
                    "event": event["event"],
                    "gold_frame": gold,
                    "nearest_indexed_frame": nearest,
                    "delta_frames": delta,
                    "delta_seconds": round(delta / fps, 4) if delta is not None else None,
                    "indexed_frame_within_2s": bool(delta is not None and (delta / fps) <= 2.0),
                    "indexed_frame_within_official_12f": bool(delta is not None and delta <= 12),
                }
            )

        density["videos"][norm] = {
            "source_video": str(path),
            "indexed_frame_count_reconstructed": len(frames),
            "fps": fps,
            "gap_seconds_median": round(statistics.median(gap_seconds), 4) if gap_seconds else None,
            "gap_seconds_p95": (
                round(sorted(gap_seconds)[min(len(gap_seconds) - 1, int(0.95 * len(gap_seconds)))], 4)
                if gap_seconds
                else None
            ),
            "gap_seconds_max": round(max(gap_seconds), 4) if gap_seconds else None,
            "per_gold_point": per_event,
        }

    density["validation"] = validation
    (HERE / "keyframe-density.json").write_text(
        json.dumps(density, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # ---- recompute mechanism counts against the corrected density ----------
    mechanisms = {
        "single_vector_multi_event_no_decomposition": 0,
        "correct_video_but_event_window_missing_from_top20": 0,
        "event_window_absent_entirely_from_top1000": 0,
        "visual_semantics_wrong_video_crowding": 0,
        "index_frame_gap_at_gold_point_over_2s": 0,
        "duplicate_results_same_video_slot_flooding": 0,
        "unresolved": 0,
    }
    per_query = {}
    for record in records:
        found = []
        if record["event_count"] >= 2 and record["serving_query_mode"] != "temporal":
            found.append("single_vector_multi_event_no_decomposition")
            mechanisms["single_vector_multi_event_no_decomposition"] += 1
        ev20 = record["official_depth20_metrics"]["target_ranks"]
        if any(r is None for r in ev20):
            found.append("correct_video_but_event_window_missing_from_top20")
            mechanisms["correct_video_but_event_window_missing_from_top20"] += 1
        if any(r is None for r in record["event_level_full_k"]["per_event_first_rank_within_tolerance"]):
            found.append("event_window_absent_entirely_from_top1000")
            mechanisms["event_window_absent_entirely_from_top1000"] += 1
        crowding = record["crowding"]["wrong_video_slots_above_first_event_correct"]
        if crowding and sum(crowding.values()) >= 5:
            found.append("visual_semantics_wrong_video_crowding")
            mechanisms["visual_semantics_wrong_video_crowding"] += 1
        vd = density["videos"].get(record["gold_video"].lower()) or {}
        if any(not e["indexed_frame_within_2s"] for e in (vd.get("per_gold_point") or [])):
            found.append("index_frame_gap_at_gold_point_over_2s")
            mechanisms["index_frame_gap_at_gold_point_over_2s"] += 1
        if len(record["video_level"]["gt_video_entry_ranks_first_20"]) >= 3:
            found.append("duplicate_results_same_video_slot_flooding")
            mechanisms["duplicate_results_same_video_slot_flooding"] += 1
        if not found:
            found.append("unresolved")
            mechanisms["unresolved"] += 1
        per_query[record["query_id"]] = found

    counts = {
        "schema_version": "issue59-mechanism-counts-v1",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "note": (
            "query-level flags (one query can carry several mechanisms); rules fixed "
            "in run_issue59_trake_audit.py; density input via reconstruction fallback"
        ),
        "queries_analyzed": [r["query_id"] for r in records],
        "mechanism_counts": mechanisms,
        "per_query_mechanisms": per_query,
    }
    (HERE / "mechanism-counts.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps({"density": {k: v["per_gold_point"] for k, v in density["videos"].items()},
                      "validation": validation,
                      "mechanisms": mechanisms}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
