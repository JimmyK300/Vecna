#!/usr/bin/env python3
"""Score a completed, truth-free BM25 capture for the frozen dataset #17 sample.

This stage reads current canonical truth only after validating the completed
capture. It makes no network requests, rewrites, retrieval calls, or truth edits.
Raw provider order and observed main phrase-filter order remain separate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics

from analyze_reranker import load_scorer, read_json, read_jsonl, score_frozen, score_video, unique_index
from collect_sparse_visibility import digest, digest_json, dump
from preflight import TRUTH_SHA256


KS = (1, 5, 10, 20, 100)
SOURCE_REVIEW_SHA256 = "c3800092585e7c9f4e04d2ae3a78c8d3f050d4b0daa571285bbee7b3ef2ddd9d"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in rows), encoding="utf-8")


def verify_capture(root, capture):
    config_path = root / "outputs/source-visibility/sparse_config.json"
    queries_path = root / "outputs/source-visibility/sparse_queries.jsonl"
    config, queries = read_json(config_path), read_jsonl(queries_path)
    manifest_path = capture / "collection_manifest.json"
    rankings_path = capture / "sparse_rankings.jsonl"
    manifest, rows = read_json(manifest_path), read_jsonl(rankings_path)
    require(manifest["status"] == "complete" and manifest["rows_written"] == 38, "Capture must be complete before truth access")
    require(manifest["rankings_sha256"] == digest(rankings_path.read_bytes()), "Captured rankings checksum mismatch")
    require(manifest["queries_sha256"] == config["query_file_sha256"] == digest(queries_path.read_bytes()), "Capture query checksum mismatch")
    require(manifest["config_sha256"] == digest(config_path.read_bytes()), "Capture configuration checksum mismatch")
    require(manifest["collection"] == config["collection"], "Captured collection identity mismatch")
    require(manifest["code_identity"]["main_commit"] == config["main_commit"] and manifest["code_identity"]["source_lf_sha256"] == config["searcher_lf_sha256"], "Main method identity mismatch")
    require(manifest["ground_truth_read"] is False and manifest["collection_mutations"] is False and manifest["models_loaded"] is False, "Capture isolation declarations differ")
    require(len(rows) == len(queries) == 38, "Frozen sample row count changed")
    require(digest_json(queries) == config["query_projection_sha256"], "Query projection changed")
    sample_path = root / "outputs/dataset-audit/sample_manifest.json"
    require(digest(sample_path.read_bytes()) == config["frozen_sample_sha256"], "Frozen sample manifest changed")
    sample = read_json(sample_path)
    selected = [(channel, row["query_id"], row["query"]) for channel in ("ocr", "asr") for row in sample["selected"][channel]]
    require([(r["channel"], r["query_id"], r["query_text"]) for r in queries] == selected, "Capture does not use the original ordered sample")
    for row, query in zip(rows, queries):
        require(row["schema"] == "vecna82-sparse-visibility-row-v1", "Unknown capture row schema")
        require(all(row[key] == query[key] for key in query), "Captured query identity changed")
        require(row["query_text_sha256"] == digest(row["query_text"].encode("utf-8")), "Query text checksum mismatch")
        require(row["ground_truth_read"] is False and row["dense_models_loaded"] is False and row["visual_models_loaded"] is False, "Per-query isolation declarations differ")
        hits = row["raw_hits"]
        require(row["raw_hit_count"] == len(hits) <= 100, "Raw depth mismatch")
        require([h["raw_rank"] for h in hits] == list(range(1, len(hits) + 1)), "Raw ranks must be contiguous")
        require(len({h["frame_id"] for h in hits}) == len(hits), "Duplicate raw frame IDs")
        require(row["raw_call"]["effective_raw_limit"] == 100 and row["raw_call"]["filter"] == "" and row["raw_call"]["offset"] == 0 and row["raw_call"]["search_params"] == {"metric_type": "BM25"}, "Unexpected provider query state")
        eligible = sorted([h for h in hits if h["eligible_after_main_phrase_filter"]], key=lambda h: h["eligible_rank"])
        require([h["eligible_rank"] for h in eligible] == list(range(1, len(eligible) + 1)), "Eligible ranks must be contiguous")
        require([h["frame_id"] for h in eligible] == row["effective_frame_order"] and len(eligible) == row["eligible_hit_count"], "Observed main order differs from per-hit ranks")
        for hit in hits:
            require(hit["indexed_text_sha256"] == digest(hit["indexed_text"].encode("utf-8")), "Indexed text checksum mismatch")
            require(hit["frame_id"] == f"{hit['video_id']}#{str(hit['frame_idx']).zfill(len(hit['frame_id'].rsplit('#', 1)[1]))}", "Frame identity mismatch")
            require(math.isfinite(hit["bm25_score"]), "Non-finite BM25 score")
    return manifest, config, queries, rows, {
        "capture_manifest_sha256": digest(manifest_path.read_bytes()),
        "captured_rankings_sha256": digest(rankings_path.read_bytes()),
        "configuration_sha256": digest(config_path.read_bytes()),
        "queries_sha256": digest(queries_path.read_bytes()),
        "frozen_sample_sha256": digest(sample_path.read_bytes()),
    }


def candidates(hits, order):
    selected = hits if order == "raw" else sorted([h for h in hits if h["eligible_after_main_phrase_filter"]], key=lambda h: h["eligible_rank"])
    return [{"rank": i, "video_id": h["video_id"], "frame_id": h["frame_idx"], "capture_frame_id": h["frame_id"]} for i, h in enumerate(selected, 1)]


def target_membership(candidate, truth, scorer):
    """Any required target match, distinct from strict all-event query success."""
    if truth["truth_tier"] == "frozen_headless_benchmark_truth":
        if truth["task_type"] == "trake":
            targets = [event["proxy_window"] for event in truth["trake_event_truth"]]
        else:
            targets = truth["accepted_ranges"]
        matches = [scorer.video_frame_hit(candidate, truth["accepted_video_id"], target["start_frame"], target["end_frame"]) for target in targets]
    else:
        matches = [scorer.p3_target_hit(candidate, target) for group in truth["accepted_groups"] for target in group]
    return [i for i, hit in enumerate(matches) if hit]


def duplicate_statistics(hits, order):
    selected = hits if order == "raw" else sorted([h for h in hits if h["eligible_after_main_phrase_filter"]], key=lambda h: h["eligible_rank"])
    texts = Counter(h["indexed_text"] for h in selected if h["indexed_text"].strip())
    within_video = Counter((h["video_id"].casefold(), h["indexed_text"]) for h in selected if h["indexed_text"].strip())
    repeated = []
    for (video, text), count in sorted(within_video.items(), key=lambda pair: (-pair[1], pair[0])):
        if count > 1:
            group = [h for h in selected if h["video_id"].casefold() == video and h["indexed_text"] == text]
            repeated.append({"video_id": group[0]["video_id"], "count": count,
                             "ranks": [h["raw_rank"] if order == "raw" else h["eligible_rank"] for h in group],
                             "frame_ids": [h["frame_id"] for h in group], "indexed_text": text,
                             "indexed_text_sha256": digest(text.encode("utf-8"))})
    return {"hit_count": len(selected), "distinct_video_count": len({h["video_id"].casefold() for h in selected}),
            "nonempty_text_hit_count": sum(texts.values()), "unique_nonempty_text_count": len(texts),
            "exact_text_repeat_excess": sum(c - 1 for c in texts.values()),
            "same_video_exact_text_repeat_excess": sum(c - 1 for c in within_video.values()),
            "largest_same_video_exact_text_group": max(within_video.values(), default=0),
            "same_video_repeated_text_groups": repeated,
            "causal_limit": "Observed occupancy of the retained BM25 frame list; no deduplication counterfactual, visual-fusion effect, or transcription fidelity is established."}


def order_effect(capture):
    raw = [h for h in capture["raw_hits"] if h["eligible_after_main_phrase_filter"]]
    effective = sorted(raw, key=lambda h: h["eligible_rank"])
    moved = [{"frame_id": before["frame_id"], "raw_rank": before["raw_rank"], "eligible_rank": before["eligible_rank"], "bm25_score": before["bm25_score"]}
             for i, before in enumerate(raw, 1) if before["eligible_rank"] != i]
    same_scores = [h["bm25_score"] for h in raw] == [h["bm25_score"] for h in effective]
    return {"eligible_frame_order_changed": bool(moved), "moved_frame_count": len(moved),
            "raw_score_sequence_preserved": same_scores, "changes_confined_to_equal_bm25_scores": bool(moved) and same_scores,
            "moved_frames": moved,
            "source_explanation": "Pinned main collects frame IDs in a set, iterates that set into results, and sorts on final score alone. Tied scores retain that set iteration order; the host's observed output order is captured."}


def score_order(hits, order, truth, scorer):
    items = candidates(hits, order)
    by_id = {hit["frame_id"]: hit for hit in hits}
    frame = score_frozen(items, truth, scorer, depth=100)
    video = score_video(items, truth, scorer, depth=100)
    distinct, seen = [], set()
    for item in items:
        key = scorer.norm_video(item["video_id"])
        if key not in seen:
            seen.add(key)
            distinct.append({**item, "rank": len(distinct) + 1})
    distinct_video = score_video(distinct, truth, scorer, depth=100)
    mismatch = []
    matches = []
    accepted_videos = {scorer.norm_video(truth["accepted_video_id"])} if truth.get("accepted_video_id") else {scorer.norm_video(t["video_id"]) for g in truth["accepted_groups"] for t in g}
    for item in items:
        hit = by_id[item["capture_frame_id"]]
        targets = target_membership(item, truth, scorer)
        entry = {"rank": item["rank"], "frame_id": hit["frame_id"], "milvus_id": hit["milvus_id"],
                 "bm25_score": hit["bm25_score"], "indexed_text": hit["indexed_text"],
                 "indexed_text_sha256": hit["indexed_text_sha256"], "matching_target_indices": targets}
        if targets:
            matches.append(entry)
        elif len(mismatch) < 5:
            mismatch.append({**entry, "mismatch_type": "accepted_video_outside_current_targets" if scorer.norm_video(item["video_id"]) in accepted_videos else "outside_current_accepted_videos"})
    first_any = matches[0]["rank"] if matches else None
    return {"ranking_unit": "one indexed keyframe", "returned_depth": len(items),
            "frame_position_video": video, "distinct_video_within_retained_frame_pool": distinct_video,
            "frozen_range_or_event": frame, "first_any_target_rank": first_any,
            "any_target_hit": {f"R@{k}": first_any is not None and first_any <= k for k in KS},
            "video_hit": {f"R@{k}": video["first_success_rank"] is not None and video["first_success_rank"] <= k for k in KS},
            "strict_all_targets_hit": {f"R@{k}": bool(frame["target_first_ranks"]) and all(r is not None and r <= k for r in frame["target_first_ranks"]) for k in KS},
            "matching_candidates": matches, "nearest_candidates_outside_current_truth": mismatch,
            "observed_repeated_text": duplicate_statistics(hits, order)}


def index_projection_parity(root, hits, review):
    """Compare only retrieved rows overlapping already-pinned source artifacts."""
    comparisons = []
    cached = {}
    for artifact in review["bounded_artifacts"]:
        ref = artifact["source_ref"]
        path = root / ref["local"]
        require(digest(path.read_bytes()) == artifact["source_sha256"], "Pinned source artifact changed")
        source = read_json(path)
        cached[source["video_id"].casefold()] = (artifact, {int(f["frame_idx"]): f for f in source["frames"]})
    for hit in hits:
        if hit["video_id"].casefold() not in cached:
            continue
        artifact, frames = cached[hit["video_id"].casefold()]
        source = frames.get(hit["frame_idx"])
        comparisons.append({"frame_id": hit["frame_id"], "raw_rank": hit["raw_rank"], "eligible_rank": hit["eligible_rank"],
                            "source_path": artifact["source_ref"]["path"], "source_commit": artifact["source_ref"]["commit"],
                            "source_artifact_sha256": artifact["source_sha256"],
                            "projected_frame_present": source is not None,
                            "indexed_text_matches_projected_text": hit["indexed_text"] == source["text"] if source is not None else None,
                            "indexed_text_sha256": hit["indexed_text_sha256"],
                            "projected_text_sha256": digest(source["text"].encode("utf-8")) if source is not None else None})
    return {"scope": "Exact retrieved frame IDs from this case's pre-existing pinned video/channel artifacts only; other videos were not fetched.",
            "comparison_count": len(comparisons), "comparisons": comparisons,
            "index_membership_limit": "No target-directed index lookup was used. A target absent from top100 may still exist elsewhere in the index."}


def evaluate_rows(root, captured, truth, reviewed, scorer):
    result = []
    for capture in captured:
        qid, channel = capture["query_id"], capture["channel"]
        target, review = truth[qid], reviewed[(channel, qid)]
        require(target["scoreable"] is True and target["query"] == capture["query_text"] == review["canonical_query"], "Canonical truth/source-review query identity mismatch")
        raw = score_order(capture["raw_hits"], "raw", target, scorer)
        effective = score_order(capture["raw_hits"], "main_eligible", target, scorer)
        parity = index_projection_parity(root, capture["raw_hits"], review)
        if not capture["raw_hits"]:
            visibility = "raw_sparse_pool_empty"
        elif effective["frame_position_video"]["first_success_rank"] is None:
            visibility = "accepted_video_not_observed_in_main_eligible_top100"
        elif not effective["frozen_range_or_event"]["all_required_targets_present"]:
            visibility = "accepted_video_observed_but_current_required_targets_incomplete"
        else:
            visibility = "all_current_required_targets_observed_in_main_eligible_top100"
        result.append({"schema": "vecna82-sparse-visibility-scored-row-v1", "query_id": qid, "channel": channel,
                       "canonical_query": capture["query_text"], "query_text_sha256": capture["query_text_sha256"],
                       "truth_tier": target["truth_tier"], "truth_provisional": target["truth_tier"] != "frozen_headless_benchmark_truth",
                       "task_type": target["task_type"], "capture_state": capture["state"],
                       "native_query_state": capture["raw_call"], "ascii_double_quote_filter_active": capture["ascii_double_quote_filter_active"],
                       "raw": raw, "main_eligible": effective, "retrieval_visibility": visibility,
                       "ranking_order_effect": order_effect(capture),
                       "phrase_filter_effect": {"removed_count": len(capture["raw_hits"]) - capture["eligible_hit_count"],
                                                "raw_target_matches_removed": [h["frame_id"] for h in raw["matching_candidates"] if h["frame_id"] not in set(capture["effective_frame_order"])]},
                       "indexed_projection_parity": parity,
                       "source_review": {key: review.get(key) for key in ("review_status", "source_media_inspected", "latest_classification", "primary_failure", "stored_text_observation", "verified_artifact_excerpts")},
                       "source_media_reference": {key: review["media_review"].get(key) for key in ("artifact_relative_path", "artifact_sha256", "short_source_references", "source_to_artifact_comparison", "source_observation", "temporal_limit")},
                       "source_review_sha256": SOURCE_REVIEW_SHA256,
                       "truth_changed": False, "dense_visibility_audited": False,
                       "causal_limit": "Mechanical sparse visibility and observed text repetition are measured on this fixed sample. Source-image gaps stay anchor-specific; unheard ASR remains unverified. Sparse results alone do not explain saved Qwen/reranker outcomes or establish a repair."})
    return result


def summarize(rows):
    summary = {}
    for channel in ("ocr", "asr"):
        cohort = [r for r in rows if r["channel"] == channel]
        summary[channel] = {"query_channel_count": len(cohort), "provisional_truth_count": sum(r["truth_provisional"] for r in cohort),
                            "ascii_quoted_query_count": sum(r["ascii_double_quote_filter_active"] for r in cohort),
                            "visibility_counts": dict(sorted(Counter(r["retrieval_visibility"] for r in cohort).items())),
                            "phrase_removed_total": sum(r["phrase_filter_effect"]["removed_count"] for r in cohort),
                            "phrase_removed_any_target_query_ids": [r["query_id"] for r in cohort if r["phrase_filter_effect"]["raw_target_matches_removed"]]}
        summary[channel]["tie_order_effect"] = {"query_count_with_changed_eligible_order": sum(r["ranking_order_effect"]["eligible_frame_order_changed"] for r in cohort),
            "all_changed_orders_confined_to_equal_bm25_scores": all(not r["ranking_order_effect"]["eligible_frame_order_changed"] or r["ranking_order_effect"]["changes_confined_to_equal_bm25_scores"] for r in cohort),
            "first_target_rank_changes": [{"query_id": r["query_id"], "raw": r["raw"]["first_any_target_rank"], "main_eligible": r["main_eligible"]["first_any_target_rank"]} for r in cohort if r["raw"]["first_any_target_rank"] != r["main_eligible"]["first_any_target_rank"]]}
        for order in ("raw", "main_eligible"):
            counts = {metric: {f"R@{k}": sum(r[order][metric][f"R@{k}"] for r in cohort) for k in KS} for metric in ("video_hit", "any_target_hit", "strict_all_targets_hit")}
            counts["frozen_mixed_contract"] = {f"R@{k}": sum(r[order]["frozen_range_or_event"]["metrics"][f"R@{k}"] for r in cohort) for k in KS if k != 100}
            counts["frozen_mixed_contract"]["MRR@20_mean"] = statistics.fmean(r[order]["frozen_range_or_event"]["metrics"]["MRR@20"] for r in cohort)
            counts["raw_or_eligible_hits"] = sum(r[order]["returned_depth"] for r in cohort)
            counts["same_video_exact_text_repeat_excess"] = sum(r[order]["observed_repeated_text"]["same_video_exact_text_repeat_excess"] for r in cohort)
            counts["largest_same_video_exact_text_group"] = max((r[order]["observed_repeated_text"]["largest_same_video_exact_text_group"] for r in cohort), default=0)
            summary[channel][order] = counts
    comparisons = [c for row in rows for c in row["indexed_projection_parity"]["comparisons"]]
    summary["indexed_projection_parity"] = {"query_frame_comparisons": len(comparisons),
        "unique_channel_frame_comparisons": len({(row["channel"], c["frame_id"]) for row in rows for c in row["indexed_projection_parity"]["comparisons"]}),
        "matching": sum(c["indexed_text_matches_projected_text"] is True for c in comparisons),
        "mismatching": sum(c["indexed_text_matches_projected_text"] is False for c in comparisons),
        "projected_frame_missing": sum(c["projected_frame_present"] is False for c in comparisons)}
    return summary


def report(rows, summary, provenance):
    lines = ["# Frozen OCR/ASR sample: sparse BM25 visibility", "",
             "All 38 predeclared query/channel rows were searched independently against the existing 322,924-frame collection. Capture used exact canonical query strings and no truth, model loading, collection writes, or query rewrites. Scoring occurred after the completed ranking file was frozen and checksummed.", "",
             "This is a dataset #17 diagnostic. Each raw BM25 request retained 100 keyframes. Pinned main's exact ASCII-quote eligibility, 1.5 boost and maximum-score normalization ran on that retained pool. Main normally asks for 200 raw rows, or 500 for ASCII-quoted queries; this bounded capture records those native requests but fetches only 100. It therefore does not reproduce the complete production text-search candidate expansion.", "",
             "| Channel | Cases | Raw video @20 / @100 | Eligible video @20 / @100 | Eligible any target @20 / @100 | Eligible all targets @20 / @100 |", "|---|---:|---:|---:|---:|---:|"]
    for channel in ("ocr", "asr"):
        value = summary[channel]
        def cell(order, metric):
            return f"{value[order][metric]['R@20']} / {value[order][metric]['R@100']}"
        lines.append(f"| {channel.upper()} | {value['query_channel_count']} | {cell('raw', 'video_hit')} | {cell('main_eligible', 'video_hit')} | {cell('main_eligible', 'any_target_hit')} | {cell('main_eligible', 'strict_all_targets_hit')} |")
    lines += ["", "Video positions above remain keyframe positions, so repeated video frames consume slots. A separate distinct-video diagnostic is retained per query. Historical TRAKE requires all events; P3 retains its provisional fractional target contract in the JSON metrics. Any-target and strict-all columns are explicit supplemental diagnostics. These sample counts are not a full-benchmark score or an extraction failure rate.", "",
              "None of the 38 frozen canonical queries contains an ASCII double-quoted phrase. Main therefore removed no candidates through exact-phrase filtering; curly quotation marks do not activate that existing hard filter. The observed raw-to-main order differences are confined to equal BM25 scores. Main builds results by iterating a frame-ID set and then sorts by score alone, so tied candidates inherit set order. ASR any-target R@1 changed from 6/18 in SDK raw order to 4/18 in the captured main order; R@5 changed from 7/18 to 6/18. This observed tie behavior is separate from phrase eligibility or score boosting.", "",
              "| Query | Channel | ASCII phrase filter | Raw → eligible hits | Eligible first video | Eligible first target | Eligible all targets @100 | Same-video identical-text excess |", "|---|---|---|---:|---:|---:|---|---:|"]
    for row in rows:
        effective = row["main_eligible"]
        number = lambda value: "—" if value is None else str(value)
        lines.append(f"| {row['query_id']} | {row['channel']} | {'yes' if row['ascii_double_quote_filter_active'] else 'no'} | {row['raw']['returned_depth']} → {effective['returned_depth']} | {number(effective['frame_position_video']['first_success_rank'])} | {number(effective['first_any_target_rank'])} | {'yes' if effective['frozen_range_or_event']['all_required_targets_present'] else 'no'} | {effective['observed_repeated_text']['same_video_exact_text_repeat_excess']} |")
    lines += ["", "A dash means no match was observed within this retained pool. It does not prove that the frame or video is absent from the index. Full indexed text, BM25 scores, raw and eligible ranks, matching candidates, and the nearest five candidates outside current truth are retained per case in `sparse_visibility.jsonl`. P3 candidate mismatches are relative to provisional truth.", "",
              "Observed identical-text occupancy is recorded from actual retrieval candidates. It can motivate a deduplication experiment, but no causal effect on the Qwen baseline, reranker or fusion has been demonstrated. The 20 reviewed OCR stills remain representative anchors; all 18 captured ASR clips remain unheard. No CER/WER, native alignment verdict, truth repair or extraction fix is asserted.", "",
              f"Index/projected-text comparisons overlap only this sample's already pinned source videos: {summary['indexed_projection_parity']['query_frame_comparisons']} query/frame comparisons, including {summary['indexed_projection_parity']['matching']} matching, {summary['indexed_projection_parity']['mismatching']} mismatching and {summary['indexed_projection_parity']['projected_frame_missing']} absent projected-frame records. This is stored-text parity, not source transcription fidelity.", "",
              "Dense text visibility is not measured by this artifact. Sparse visibility completed independently of visual model availability.", "",
              f"Capture rankings SHA-256: `{provenance['captured_rankings_sha256']}`. Canonical truth SHA-256: `{TRUTH_SHA256}`. Source review SHA-256: `{SOURCE_REVIEW_SHA256}`. All file pins and collection identity are in `evaluation_manifest.json`.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/source-visibility/evaluation-v1"))
    args = parser.parse_args()
    root = args.root.resolve()
    capture = args.capture_dir if args.capture_dir.is_absolute() else root / args.capture_dir
    output = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    manifest, config, queries, captured, provenance = verify_capture(root, capture)
    truth_path = root / "inputs/canonical_truth.jsonl"
    require(digest(truth_path.read_bytes()) == TRUTH_SHA256, "Canonical truth checksum mismatch")
    truth = unique_index(read_jsonl(truth_path))
    reviewed_path = root / "outputs/dataset-audit/reviewed_audit.jsonl"
    require(digest(reviewed_path.read_bytes()) == SOURCE_REVIEW_SHA256, "Source review checksum mismatch")
    reviews = read_jsonl(reviewed_path)
    reviewed = {(r["channel"], r["query_id"]): r for r in reviews}
    require(len(reviewed) == len(reviews) == 38, "Source-review sample mismatch")
    scorer_path = root / "reference/evaluate_reranker_fusion.py"
    registry = read_json(root / "inputs/sources.json")
    scorer_entry = next(r for r in registry if r["local"] == "reference/evaluate_reranker_fusion.py")
    scorer_bytes = scorer_path.read_bytes()
    require(hashlib.sha1(b"blob " + str(len(scorer_bytes)).encode() + b"\0" + scorer_bytes).hexdigest() == scorer_entry["blob_sha"], "Frozen scorer Git blob mismatch")
    scorer = load_scorer(scorer_path)
    rows = evaluate_rows(root, captured, truth, reviewed, scorer)
    summary = summarize(rows)
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "sparse_visibility.jsonl", rows)
    dump(output / "summary.json", summary)
    (output / "SPARSE_VISIBILITY.md").write_text(report(rows, summary, provenance), encoding="utf-8")
    evaluation = {"schema": "vecna82-sparse-visibility-evaluation-v1", "status": "complete", **provenance,
                  "canonical_truth_sha256": TRUTH_SHA256, "source_review_sha256": SOURCE_REVIEW_SHA256,
                  "scorer_source": {**scorer_entry, "sha256": digest(scorer_bytes)}, "evaluator_sha256": digest(Path(__file__).read_bytes()),
                  "capture_manifest": manifest, "query_channel_count": len(rows),
                  "retrieval_complete_before_truth_join": True, "truth_changed": False,
                  "outputs": {name: digest((output / name).read_bytes()) for name in ("sparse_visibility.jsonl", "summary.json", "SPARSE_VISIBILITY.md")}}
    dump(output / "evaluation_manifest.json", evaluation)
    print(json.dumps({"output": str(output), "query_channel_rows": len(rows), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
