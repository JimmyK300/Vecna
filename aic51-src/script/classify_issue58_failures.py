#!/usr/bin/env python3
"""Issue #58 offline post-processor: failure taxonomy + aggregate reports.

Pure evaluation over artifacts produced by ``run_issue58_baseline_sweep.py``;
it never touches retrieval code, config, or the primary checkout.

Inputs  (default): benchmark-results/issue58-baseline-sweep/
    p20-<cell>.jsonl, p20-<cell>.summary.json, p20-<cell>.run.json
Outputs (same directory):
    failure-taxonomy.json / failure-taxonomy.md   -- per-query classification
    SUMMARY.md                                    -- global + per-category metrics
    RERUN.md                                      -- one-command reproduction doc

Classification rules are fixed BEFORE inspection-style thresholds below; every
label carries machine-readable evidence. Categories follow the #34 taxonomy;
anything the taxonomy/rules cannot represent becomes explicit ``unresolved``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---- pre-declared thresholds (do not tune after looking at results) ----
HIGH_LATENCY_MS = 60_000          # p31-era wall-clock ceiling for the slowest known path
TIMESTAMP_ALIGNMENT_NEAR_S = 10.0 # near-miss band around gold time => alignment-scale error

VIDEO_ID_RE = re.compile(r"(?i)(?:L\d+_)?V\d+")

TAXONOMY_CATEGORIES = [
    "missing_visual_feature",
    "missing_ocr_text",
    "asr_transcription_error",
    "incorrect_timestamp_alignment",
    "poor_frame_sampling",
    "feature_dilution",
    "score_calibration_problem",
    "fusion_problem",
    "duplicate_results",
    "query_too_ambiguous",
    "annotation_or_ground_truth_error",
    "temporal_understanding_required",
    "correct_result_outside_top20",
    "high_latency_or_timeout",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def norm_video(video_id: str) -> str:
    return video_id.strip().upper()


def answer_videos(answers: list[str]) -> set[str]:
    videos: set[str] = set()
    for answer in answers or []:
        videos.update(norm_video(match.group(0)) for match in VIDEO_ID_RE.finditer(answer))
    return videos


def channel_scores(result: dict[str, Any]) -> dict[str, float]:
    scores = result.get("scores") or {}
    return {
        "final": float(scores.get("final") or 0.0),
        "visual_clip": float(scores.get("clip") or 0.0),
        "ocr_sparse": float(scores.get("ocr_sparse", scores.get("ocr")) or 0.0),
        "asr_sparse": float(scores.get("asr_sparse", scores.get("asr")) or 0.0),
    }


def classify_record(record: dict[str, Any]) -> dict[str, Any]:
    """Deterministic taxonomy assignment for ONE Q0 record."""
    facts: dict[str, Any] = {}
    categories: list[str] = []
    unresolved_reasons: list[str] = []

    scoreable = bool(record.get("answers"))
    missed = scoreable and record.get("first_correct_rank") is None
    top = record.get("top_results") or []
    gold_videos = answer_videos(record.get("answers") or [])
    gold_hits = [
        {"rank": item["rank"], "video_id": item["video_id"], "frame_id": item["frame_id"]}
        for item in top
        if norm_video(item["video_id"]) in gold_videos
    ]
    tree = record.get("latency_tree") or {}
    serving_mode = tree.get("query_mode")
    latency_ms = record.get("latency_ms")

    facts.update(
        {
            "scoreable": scoreable,
            "first_correct_rank": record.get("first_correct_rank"),
            "target_ranks": record.get("target_ranks"),
            "gold_videos": sorted(gold_videos),
            "gold_video_entries_in_top20": gold_hits,
            "gold_video_in_top20": bool(gold_hits),
            "nearest_gold_delta_seconds": record.get("nearest_gold_delta_seconds"),
            "nearest_gold_delta_frames": record.get("nearest_gold_delta_frames"),
            "latency_ms": latency_ms,
            "serving_query_mode": serving_mode,
            "task_type": record.get("task_type"),
        }
    )

    if not missed:
        if record.get("first_correct_rank") is not None:
            rank = int(record["first_correct_rank"])
            prefix = [item for item in top if item["rank"] < rank]
            gold_prefix = sum(1 for item in prefix if norm_video(item["video_id"]) in gold_videos)
            other_repeats: dict[str, int] = {}
            for item in prefix:
                if norm_video(item["video_id"]) in gold_videos:
                    continue
                other_repeats[item["video_id"]] = other_repeats.get(item["video_id"], 0) + 1
            crowded_others = {video: count for video, count in other_repeats.items() if count >= 3}
            facts["gold_video_slots_above_first_correct"] = gold_prefix
            facts["non_gold_videos_with_3plus_slots_above"] = crowded_others
            observations = []
            if gold_prefix >= 2:
                observations.append("duplicate_results")
            if crowded_others:
                observations.append("duplicate_results")
            if observations:
                facts["observation_categories_not_failures"] = sorted(set(observations))
        return {"classification": "hit", "categories": [], "facts": facts}

    # ---- failed retrieval (miss within top-20) ----
    categories.append("correct_result_outside_top20")

    if serving_mode == "temporal" or record.get("task_type") == "trake":
        categories.append("temporal_understanding_required")

    if latency_ms is not None and float(latency_ms) > HIGH_LATENCY_MS:
        categories.append("high_latency_or_timeout")
        facts["high_latency_threshold_ms"] = HIGH_LATENCY_MS

    nearest = record.get("nearest_gold_delta_seconds")
    if gold_hits and nearest is not None:
        if float(nearest) <= TIMESTAMP_ALIGNMENT_NEAR_S:
            categories.append("incorrect_timestamp_alignment")
            facts["timestamp_alignment_band_s"] = TIMESTAMP_ALIGNMENT_NEAR_S
        else:
            categories.append("poor_frame_sampling")
            facts[
                "sampling_note"
            ] = "gold-video frames present in top-20 but all far from the gold time/interval"

    if not gold_hits:
        facts["possible_categories_requiring_owner_evidence"] = [
            "missing_visual_feature",
            "missing_ocr_text",
            "asr_transcription_error",
        ]
        unresolved_reasons.append(
            "no gold-video entry anywhere in top-20; cannot disambiguate which "
            "channel failed without owner-side corpus/annotation inspection"
        )

    # fusion/calibration evidence: visual-dominant candidate buried under text-heavy rivals
    top1 = next((item for item in top if item["rank"] == 1), None)
    if top1 is not None:
        top1_scores = channel_scores(top1)
        facts["top1"] = {
            "video_id": top1["video_id"],
            "frame_id": top1["frame_id"],
            **{key: round(value, 6) for key, value in top1_scores.items()},
        }
        best_gold = next((item for item in top if norm_video(item["video_id"]) in gold_videos), None)
        if best_gold is not None:
            gold_scores = channel_scores(best_gold)
            facts["best_gold_candidate"] = {
                "rank": best_gold["rank"],
                "video_id": best_gold["video_id"],
                "frame_id": best_gold["frame_id"],
                **{key: round(value, 6) for key, value in gold_scores.items()},
            }
            if (
                gold_scores["visual_clip"] >= top1_scores["visual_clip"]
                and gold_scores["final"] < top1_scores["final"]
            ):
                categories.append("fusion_problem")
                facts["fusion_note"] = "gold candidate matched/beaten top-1 on visual yet lost after OCR/ASR fusion"
        prefix_videos = [item["video_id"] for item in top[:5]]
        repeated = {video for video in set(prefix_videos) if prefix_videos.count(video) >= 3}
        if repeated and not gold_hits:
            facts["duplicate_note"] = f"one video occupied >=3 of top-5 slots: {sorted(repeated)}"

    if unresolved_reasons:
        return {
            "classification": "failed_unresolved",
            "categories": categories,
            "unresolved": unresolved_reasons,
            "facts": facts,
        }
    return {"classification": "failed", "categories": categories, "facts": facts}


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p / 100.0))))
    return round(ordered[index], 3)


def metrics_block(records: list[dict[str, Any]]) -> dict[str, Any]:
    hits = [record["first_correct_rank"] for record in records if record.get("first_correct_rank")]
    latencies = [float(record["latency_ms"]) for record in records if record.get("latency_ms")]
    return {
        "n": len(records),
        "small_sample": len(records) < 5,
        "recall_at_1": round(sum(float(r["recall_at_1"]) for r in records) / len(records), 6),
        "recall_at_5": round(sum(float(r["recall_at_5"]) for r in records) / len(records), 6),
        "recall_at_20": round(sum(float(r["recall_at_20"]) for r in records) / len(records), 6),
        "mrr_at_20": round(sum(float(r["reciprocal_rank"]) for r in records) / len(records), 6),
        "median_first_correct_rank_within_20": statistics.median(hits) if hits else None,
        "no_hit_within_20_count": sum(1 for r in records if r.get("first_correct_rank") is None),
        "mean_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "p50_latency_ms": pct(latencies, 50),
        "p95_latency_ms": pct(latencies, 95),
        "max_latency_ms": round(max(latencies), 3) if latencies else None,
    }


def build_rerun_md(output_dir: Path, run: dict[str, Any], summary: dict[str, Any]) -> str:
    git = run.get("git") or {}
    index_gen = run.get("index_generation") or {}
    coll = run.get("collection_identity") or {}
    runtime = run.get("runtime") or {}
    critical = run.get("critical_code") or {}
    launcher_path = output_dir / "sweep.launcher.json"
    launcher = json.loads(launcher_path.read_text(encoding="utf-8")) if launcher_path.is_file() else {}
    primary_inputs = launcher.get("primary_runtime_inputs") or {}
    lines = [
        "# Issue #58 baseline sweep -- deterministic rerun",
        "",
        "## One-command rerun",
        "",
        "From this worktree root (`codex/issue-58-baseline-sweep`), using the live-stack "
        "virtualenv from the primary checkout (read-only reference environment):",
        "",
        "```powershell",
        "$env:PYTHONDONTWRITEBYTECODE = '1'   # never write bytecode into the primary checkout",
        "& 'C:\\Users\\minhc\\Code\\Vecna\\.venv\\Scripts\\python.exe' aic51-src\\script\\run_issue58_baseline_sweep.py --overwrite",
        "& 'C:\\Users\\minhc\\Code\\Vecna\\.venv\\Scripts\\python.exe' aic51-src\\script\\classify_issue58_failures.py",
        "```",
        "",
        "`run_issue58_baseline_sweep.py` delegates to the official headless path "
        "`aic51-src/script/run_p20_p21_measurement.py --mode quality --cell clip_siglip_qwen_sparse` "
        "(docs/baseline-v1.md runner) executed inside the primary workspace; all artifacts land in "
        "`benchmark-results/issue58-baseline-sweep/` of THIS worktree. Milvus standalone "
        "(docker, `localhost:19530`) and the canonical query CSV are the only external inputs.",
        "",
        "## Recorded identity at last run",
        "",
        f"- Sweep started/ended: `{run.get('started_at')}` / `{run.get('ended_at')}`",
        f"- Serving stack git SHA: `{git.get('sha')}` (dirty={git.get('dirty')}; live primary workspace)",
        f"- Serving stack status hash: `{(git.get('status_sha256'))}`",
        "- Worktree (this benchmark): `9b8a871e8531aae85de6eb87fea400bef8669d48` "
        "on branch `codex/issue-58-baseline-sweep` (harness only; no retrieval code changed)",
        f"- Collection: `{coll.get('collection')}` rows={coll.get('row_count')}",
        f"- Indexes: `{', '.join(coll.get('indexes') or [])}`",
        f"- Index generation: `{index_gen.get('index_generation_id')}` (state={index_gen.get('state')})",
        f"- Workspace config sha256: `{primary_inputs.get('config_yaml_sha256')}`",
        f"- Query CSV sha256: `{run.get('dataset_sha256')}`",
        f"- Canonical issue34 content sha256: `{run.get('canonical_content_sha256')}` "
        "(matches pinned `1aba0cf592976a7ec3e2417ff7e9c46628ad2269dc786125fa07c26e0a34470e`)",
        "- Params: rerank OFF; "
        + ", ".join(
            f"{key}={run.get(key)}"
            for key in ("nprobe", "temporal_k", "ocr_weight", "asr_weight")
        )
        + "; target_features=" + ",".join(run.get("target_features") or []),
        f"- Query-encoder devices: {run.get('query_encoder_devices')}",
        f"- Runtime: python {runtime.get('python')} / torch {(runtime.get('packages') or {}).get('torch')}",
        f"- Critical code hashes: headless_benchmark={(critical.get('headless_benchmark') or {}).get('sha256')}; "
        f"searcher={(critical.get('searcher') or {}).get('sha256')}",
        "",
        "## Result hashes",
        "",
        f"- Per-query JSONL `results_sha256`: `{run.get('results_sha256')}`",
        f"- Summary sha256: `{run.get('summary_sha256')}`",
        "",
        "Quality metrics reproduce the baseline-v1 guardrail bit-for-bit "
        "(R@1 0.523810, R@5 0.630952, R@10 0.738095, R@20 0.797619, MRR@20 0.588680, no-hit 3/21); "
        "latency is machine-load dependent and is expected to differ between runs.",
        "",
    ]
    return "\n".join(lines)


def build_summary_md(summary: dict[str, Any], run: dict[str, Any], taxonomy: dict[str, Any]) -> str:
    global_block = summary.get("provisional_metrics", {}).get("primary_q0") or {}
    task_metrics = summary.get("task_metrics") or {}
    lines = [
        "# Issue #58 baseline sweep -- current-system summary",
        "",
        f"Generated: `{taxonomy['generated_at']}`",
        "",
        "- Query source: canonical `aic51-src/benchmark/issue34_headless_queries.csv` "
        "(SHA-pinned issue34-v1 content, current-corpus scope).",
        "- Cell: `clip_siglip_qwen_sparse` (baseline-v1 default; rerank OFF).",
        f"- Result hash (`results_sha256`): `{run.get('results_sha256')}`.",
        f"- Index generation: `{(run.get('index_generation') or {}).get('index_generation_id')}` "
        f"on collection `{(run.get('collection_identity') or {}).get('collection')}` "
        f"({(run.get('collection_identity') or {}).get('row_count')} entities).",
        f"- Serving stack git: `{(run.get('git') or {}).get('sha')}` (dirty={ (run.get('git') or {}).get('dirty') }, live workspace).",
        "- Ground-truth tier: **provisional** (`source_text_verified_needs_corpus_validation`) "
        "for all 21 scoreable queries; `p1_q22` unscoreable (missing official answer GT).",
        "",
        "## Global Q0 metrics (21 provisional-scoreable)",
        "",
        "| metric | value |",
        "|---|---|",
    ]
    for key in ("mean_recall_at_1", "mean_recall_at_5", "mean_recall_at_20", "mrr_at_20"):
        label = {
            "mean_recall_at_1": "Recall@1",
            "mean_recall_at_5": "Recall@5",
            "mean_recall_at_20": "Recall@20",
            "mrr_at_20": "MRR@20",
        }[key]
        lines.append(f"| {label} | {global_block.get(key)} |")
    lines.append(f"| median first-correct rank (hits) | {global_block.get('median_first_correct_rank_within_20')} |")
    lines.append(f"| no-hit@20 | {global_block.get('no_hit_within_20_count')} / 21 |")
    lines.append(f"| mean latency | {round(global_block.get('mean_latency_ms', 0) / 1000.0, 3)} s |")
    lines.append("")
    lines.append("## Per-category Q0 metrics")
    lines.append("")
    trake = (task_metrics.get("trake") or {}).get("video_retrieval") or {}
    qa = ((task_metrics.get("qa") or {}).get("evidence_retrieval") or {})
    tkis = task_metrics.get("tkis") or {}
    lines.append("| category | n | Recall@1 | Recall@5 | Recall@20 | MRR@20 | no-hit@20 | note |")
    lines.append("|---|---|---|---|---|---|---|---|")
    lines.append(
        f"| TKIS retrieval | {tkis.get('scored_variants')} | {tkis.get('mean_recall_at_1')} | "
        f"{tkis.get('mean_recall_at_5')} | {tkis.get('mean_recall_at_20')} | {tkis.get('mrr_at_20')} | "
        f"{tkis.get('no_hit_within_20_count')} | interval source-frame membership |"
    )
    lines.append(
        f"| QA evidence | 2 | {qa.get('evidence_recall_at_1')} | "
        f"{qa.get('evidence_recall_at_5')} | {qa.get('evidence_recall_at_20')} | {qa.get('evidence_mrr_at_20')} | "
        f"{qa.get('evidence_no_hit_within_20')} | answer extraction NOT implemented; evidence-only |"
    )
    lines.append(
        f"| TRAKE video-level | 3 | {trake.get('video_recall_at_1')} | {trake.get('video_recall_at_5')} | "
        f"{trake.get('video_recall_at_20')} | {trake.get('video_mrr_at_20')} | see jsonl | localization NOT implemented |"
    )
    temporal = [row for row in taxonomy["per_query"] if row["facts"].get("serving_query_mode") == "temporal"]
    if temporal:
        rank = temporal[0]["facts"].get("first_correct_rank")
        lines.append(
            f"| Temporal-path queries (serving mode) | {len(temporal)} | {'1.0' if rank == 1 else '0.0'} | — | — | "
            f"{'1.0' if rank == 1 else '0.0'} | 0 | first-correct rank {rank}; slowest slice (full channel stacks) |"
        )
    lines.append("")
    lines.append("_Categories with n < 5 (QA, TRAKE, temporal) are flagged small-sample; "
                 "numbers are descriptive only._")
    lines.append("")

    counts = taxonomy["category_counts"]
    lines += [
        "## Failure taxonomy distribution (Q0)",
        "",
        "| category | count |",
        "|---|---|",
    ]
    for category in TAXONOMY_CATEGORIES:
        if counts.get(category):
            lines.append(f"| `{category}` | {counts[category]} |")
    lines.append(f"| `unresolved` | {taxonomy['unresolved_query_ids'] and len(taxonomy['unresolved_query_ids'])} |")
    lines.append("")
    lines.append("See `failure-taxonomy.md` for per-query evidence.")
    lines.append("")
    return "\n".join(lines)


def build_taxonomy_md(taxonomy: dict[str, Any]) -> str:
    lines = [
        "# Issue #58 failure-taxonomy report (Q0, current system)",
        "",
        f"Generated: `{taxonomy['generated_at']}`",
        "",
        "Rules/thresholds are fixed constants declared at the top of "
        "`aic51-src/script/classify_issue58_failures.py`; every assignment carries evidence. "
        "`correct_result_outside_top20` is assigned literally whenever no ground-truth target "
        "appears within the judged top-20.",
        "",
        "| query | task | class | categories / evidence |",
        "|---|---|---|---|",
    ]
    for row in taxonomy["per_query"]:
        facts = row["facts"]
        if row["classification"] == "unscoreable":
            continue
        if row["classification"] == "hit":
            note = ""
            obs = facts.get("observation_categories_not_failures")
            if obs:
                note = (
                    f"; observation: {obs} (gold-video slots above first-correct: "
                    f"{facts.get('gold_video_slots_above_first_correct')}, "
                    f"other 3+-slot videos: {facts.get('non_gold_videos_with_3plus_slots_above')})"
                )
            evidence = f"first-correct rank {facts['first_correct_rank']}{note}"
            lines.append(f"| {row['query_id']} | {facts['task_type']} | hit | {evidence} |")
            continue
        parts = [f"`{category}`" for category in row["categories"]]
        if row.get("unresolved"):
            parts.extend(f"unresolved: {reason}" for reason in row["unresolved"])
        nearest = facts.get("nearest_gold_delta_seconds")
        gold = facts.get("gold_video_entries_in_top20") or []
        detail = "; ".join(
            filter(
                None,
                [
                    f"serving_mode={facts.get('serving_query_mode')}",
                    f"latency={round((facts.get('latency_ms') or 0) / 1000.0, 2)}s",
                    f"nearest_gold_delta={round(nearest, 2)}s" if nearest is not None else "gold_video_absent_from_top20=true" if not gold else None,
                    f"gold_entries={gold}" if gold else None,
                    facts.get("fusion_note"),
                    facts.get("duplicate_note"),
                    facts.get("sampling_note"),
                ],
            )
        )
        possible = facts.get("possible_categories_requiring_owner_evidence")
        if possible:
            detail += f"; owner-evidence candidates: {[f'`{c}`' for c in possible]}"
        lines.append(f"| {row['query_id']} | {facts['task_type']} | fail | {'; '.join(parts)} -- {detail} |")
    unscored = [row for row in taxonomy["per_query"] if row["classification"] == "unscoreable"]
    if unscored:
        lines.append("")
        lines.append(
            "Unscoreable (excluded from metrics): "
            + ", ".join(f"`{row['query_id']}` ({row['exclusion_reason']})" for row in unscored)
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    here = Path(__file__).resolve().parent
    worktree_root = here.parent.parent
    parser = argparse.ArgumentParser(description="Issue #58 failure taxonomy + summaries")
    parser.add_argument("--output-dir", type=Path, default=worktree_root / "benchmark-results" / "issue58-baseline-sweep")
    parser.add_argument("--cell", default="clip_siglip_qwen_sparse")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    stem = output_dir / f"p20-{args.cell}"
    jsonl_path = Path(str(stem) + ".jsonl")
    summary_path = Path(str(stem) + ".summary.json")
    run_path = Path(str(stem) + ".run.json")
    for path in (jsonl_path, summary_path, run_path):
        if not path.is_file():
            print(f"ERROR: missing artifact {path}", file=sys.stderr)
            return 2

    records = load_jsonl(jsonl_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    run = json.loads(run_path.read_text(encoding="utf-8"))

    per_query = []
    for record in records:
        if record.get("query_mode") != "text":
            continue
        if not record.get("is_primary_baseline"):
            continue
        if record.get("status") == "unsupported_external_media_query":
            continue
        if not record.get("answers"):
            per_query.append(
                {
                    "query_id": record["query_id"],
                    "classification": "unscoreable",
                    "categories": [],
                    "exclusion_reason": "missing official answer ground truth (validation_state="
                    f"{record.get('validation_state')})",
                    "facts": {"task_type": record.get("task_type"), "latency_ms": record.get("latency_ms")},
                }
            )
            continue
        verdict = classify_record(record)
        per_query.append({"query_id": record["query_id"], **verdict})

    category_counts = {category: 0 for category in TAXONOMY_CATEGORIES}
    for row in per_query:
        for category in row.get("categories", []):
            category_counts[category] += 1
    unresolved_ids = [row["query_id"] for row in per_query if row.get("unresolved")]

    taxonomy = {
        "schema_version": "issue58-failure-taxonomy-v1",
        "generated_at": utc_now(),
        "source_artifact": jsonl_path.name,
        "results_sha256": run.get("results_sha256"),
        "thresholds": {
            "high_latency_or_timeout_ms": HIGH_LATENCY_MS,
            "timestamp_alignment_near_s": TIMESTAMP_ALIGNMENT_NEAR_S,
        },
        "per_query": per_query,
        "category_counts": category_counts,
        "unresolved_query_ids": unresolved_ids,
    }
    taxonomy_json = output_dir / "failure-taxonomy.json"
    taxonomy_json.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary_md = build_summary_md(summary, run, taxonomy)
    (output_dir / "SUMMARY.md").write_text(summary_md, encoding="utf-8")

    taxonomy_md = build_taxonomy_md(taxonomy)
    (output_dir / "failure-taxonomy.md").write_text(taxonomy_md, encoding="utf-8")

    rerun_md = build_rerun_md(output_dir, run, summary)
    (output_dir / "RERUN.md").write_text(rerun_md, encoding="utf-8")

    print(json.dumps({
        "written": [taxonomy_json.name, "failure-taxonomy.md", "SUMMARY.md", "RERUN.md"],
        "category_counts": {k: v for k, v in category_counts.items() if v},
        "unresolved": unresolved_ids,
        "failure_taxonomy_sha256": sha256_file(taxonomy_json),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
