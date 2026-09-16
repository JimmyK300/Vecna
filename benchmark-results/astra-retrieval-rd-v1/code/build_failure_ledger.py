#!/usr/bin/env python3
"""Reconstructed Packet D ledger; saved evidence only, no models or retrieval.

Recovered from the reviewed source/read/patch record after scratch became
unavailable. New source hashes identify this reconstruction. Host tests and
generation must run before any final-result claim.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import importlib.util
import json
import math
from pathlib import Path

FUSION_ARMS = ("fusion_current_control", "fusion_rrf", "fusion_minmax_sum", "fusion_robust_z_sum", "fusion_softmax_sum")
MATCHED_QWEN = "qwen_only_matched"
FUSION_EVALUATION = "outputs/fusion/evaluation"
LOADER_PROVENANCE = "outputs/reranker/loader-provenance-evidence/findings.json"
COMPARISON_SCOPE = {
    "packet_c_baseline": "Historical saved Qwen HTTP candidates in inputs/qwen_only_top100.jsonl; paired with C's saved reranker output.",
    "packet_b_baseline": "Fresh raw-provider Qwen candidates from the same collection identity as B's five fusion transforms; stored as qwen_only_matched.",
    "cross_packet": "Descriptive query-level comparison across different captures and candidate surfaces. Neither candidate identity nor collection conditions are held fixed between B and C.",
    "frozen_evidence": "The pinned range/event scorer is shared. C frozen scores retain original HTTP timeline evidence; B supplies frame-only candidates. Comparable score labels do not establish identical evidence.",
    "pipeline": "No fusion-to-reranker pipeline or causal interaction was tested.",
    "runtime": "Historical C rank evidence does not certify a fresh model loader or corpus extraction lineage. A defect in a later runtime cannot be transferred to C without run-bound evidence.",
}
TAXONOMY = ("none", "candidate_generation_missing_video", "candidate_generation_missing_event", "visual_semantic_confusion",
    "fine_detail_attribute_failure", "ocr_extraction_failure", "ocr_retrieval_failure", "asr_extraction_failure",
    "asr_retrieval_failure", "fusion_calibration_failure", "fusion_duplicate_flooding", "reranker_regression",
    "temporal_representation_failure", "temporal_localization_failure", "ground_truth_weak_or_provisional", "query_ambiguous", "unresolved")
HYDRATE = (
    "python code/hydrate_fusion_capture.py --root .\n"
    "python code/fusion_study_storage.py rebuild --rankings outputs/fusion/capture-full115-v1/provider_rankings.jsonl "
    "--config outputs/fusion/frozen_config.json --queries outputs/fusion/queries.jsonl "
    "--collection-manifest outputs/fusion/capture-full115-v1/collection_manifest.json "
    "--sidecar outputs/fusion/evaluation/study_timings.json --output outputs/fusion/evaluation/study_results.jsonl"
)

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]

def index(rows, key="query_id"):
    found = {}
    for row in rows:
        identity = row[key]
        if identity in found:
            raise ValueError(f"duplicate {key}: {identity}")
        found[identity] = row
    return found

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def require(value, message):
    if not value:
        raise ValueError(message)

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def load_audit(root):
    return load_module("ledger_reranker_audit", root / "code/analyze_reranker.py")

def load_visibility(root, truth, sample, audit, scorer):
    return load_module("ledger_visibility", root / "code/visibility_ledger.py").load(root, truth, sample, audit, scorer)

def fusion_evidence(path, truth, audit, scorer, selection_path=None, evaluated_path=None):
    """A completed evaluation can never silently regress to null/partial."""
    path = Path(path)
    selection_path = Path(selection_path) if selection_path else path.parent / "summary.json"
    evaluated_path = Path(evaluated_path) if evaluated_path else path.parent / "per_query.jsonl"
    if not path.exists():
        if selection_path.exists() or evaluated_path.exists():
            raise ValueError("Packet B evaluation artifacts exist but study_results.jsonl is absent. Hydrate outputs/fusion/evaluation/study_results.jsonl before regenerating D; completed B evidence must not be replaced with null. From the experiment root, run:\n" + HYDRATE)
        return {"status": "NOT_RUN", "best_global_arm": None, "per_query": {}, "reason": "All Packet B study/evaluation artifacts are absent."}
    if selection_path.exists() != evaluated_path.exists():
        raise ValueError("Packet B study has only one evaluation artifact: the completed evaluation bundle is partially restored. Restore both summary.json and per_query.jsonl before regenerating D; partial completed evidence must not become null. Hydration command:\n" + HYDRATE)
    if not selection_path.exists():
        return {"status": "EVALUATION_PENDING", "best_global_arm": None, "per_query": {}, "reason": "Raw fusion output exists and both evaluation artifacts are absent."}
    selection = read_json(selection_path)
    selected = selection.get("descriptive_best_global_arm")
    require(selected in FUSION_ARMS, "B evaluation has no supported descriptive_best_global_arm")
    raw = index(read_jsonl(path))
    require(set(raw) == set(truth) and len(raw) == 115, "Completed B evaluation has a partial or foreign study cohort; restore the exact 115-row study before regenerating D")
    for q, row in raw.items():
        require(row.get("query_text_sha256") == hashlib.sha256(truth[q]["query"].encode()).hexdigest(), f"fusion/canonical query text mismatch: {q}")
        require(set(row.get("arms", {})) == set(FUSION_ARMS), f"Completed B evaluation has missing or foreign study arms: {q}")
    identities = {row.get("run_identity_sha256") for row in raw.values()}
    require(len(identities) == 1, "B transformed rows do not share one collection identity")
    run_identity = next(iter(identities))
    require(isinstance(run_identity, str) and len(run_identity) == 64 and all(c in "0123456789abcdef" for c in run_identity), "B collection identity must be a SHA256 value")
    proof = selection.get("transform_proof") or {}
    require(proof.get("output_sha256") == sha256(path), "B summary transform_proof does not bind the actual study SHA256")
    require(proof.get("run_identity_sha256") == run_identity, "B summary transform_proof run identity differs from study rows")
    require(proof.get("queries") == 115 and proof.get("arms") == list(FUSION_ARMS) and proof.get("ground_truth_read") is False, "B summary transform proof cohort/arm/isolation mismatch")
    provider_path = path.parent.parent / "capture-full115-v1/provider_rankings.jsonl"
    require(provider_path.exists(), "Completed B evaluation requires raw provider rankings for matched-Qwen rescoring. Hydrate the capture with:\n" + HYDRATE)
    require(proof.get("rankings_sha256") == sha256(provider_path), "B raw-provider SHA256 differs from transform proof")
    config_path = path.parent.parent / "frozen_config.json"
    config = read_json(config_path)
    config_digest = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    require(proof.get("config_sha256") == config_digest, "B transform configuration digest differs")
    require(config["output_frame_k"] == config["output_video_k"] == 100 and config["visual_providers"] == ["qwen", "siglip"] and config["ocr_alpha"] == config["asr_alpha"] == 0 and config["ocr_weight"] > 0 and config["asr_weight"] > 0, "B observed-pool overlay requires the fixed four active providers and retained100")
    active_providers = ("qwen", "siglip", "ocr_sparse", "asr_sparse")
    providers = index(read_jsonl(provider_path))
    require(set(providers) == set(truth), "B raw-provider cohort must preserve exact115 IDs")
    for q, exported in providers.items():
        require(exported.get("run_identity_sha256") == run_identity and exported.get("query_text_sha256") == raw[q]["query_text_sha256"] and exported.get("query_text") == truth[q]["query"], f"B raw-provider query/run identity mismatch: {q}")
        if "provider_input_sha256" in raw[q]:
            actual = hashlib.sha256(json.dumps(exported, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            require(raw[q]["provider_input_sha256"] == actual, f"B study/raw-provider row digest mismatch: {q}")
    scores = {}
    for q, row in raw.items():
        if not truth[q]["scoreable"]:
            continue
        scores[q] = {}
        exported = providers[q]
        union = {}
        for provider in active_providers:
            observed = exported["providers"][provider]
            hits = observed["hits"]
            require(observed["state"] in {"ok", "empty"} and len(hits) <= 100 and [int(h["rank"]) for h in hits] == list(range(1, len(hits) + 1)), f"B active provider state/depth/rank mismatch: {q} {provider}")
            require(len({h["frame_id"] for h in hits}) == len(hits), f"B active provider duplicate IDs: {q} {provider}")
            for hit in hits:
                video, number = str(hit["frame_id"]).rsplit("#", 1)
                require(video == hit["video_id"] and number.isdigit(), f"B active provider frame/video mismatch: {q} {provider}")
                union[hit["frame_id"]] = hit
        tie_order = exported["candidate_tie_order"]
        require(set(union) == set(tie_order) and len(tie_order) == len(union), f"B active union differs from captured tie order: {q}")
        scores[q]["active_provider_union"] = pool_coverage([union[fid] for fid in tie_order], truth[q], audit, scorer)
        for name in FUSION_ARMS:
            arm = row["arms"][name]
            require("frames" in arm and "videos" in arm, f"fusion arm has no frame/video result arrays: {q} {name}")
            for field in ("frames", "videos"):
                require([int(r["rank"]) for r in arm[field]] == list(range(1, len(arm[field]) + 1)), f"fusion {field} ranks are not contiguous: {q} {name}")
            scores[q][name] = {"frozen": audit.score_frozen(arm["frames"], truth[q], scorer),
                "candidate_position_video": audit.score_video(arm["frames"], truth[q], scorer),
                "deduplicated_video": audit.score_video(arm["videos"], truth[q], scorer), "frame_candidate_count": len(arm["frames"]),
                "retained_frame_pool": pool_coverage(arm["frames"], truth[q], audit, scorer),
                "analysis_video_representatives": pool_coverage(arm["videos"], truth[q], audit, scorer)}
    require(len(scores) == 113, "Fusion scoreable cohort must be exactly113")
    evaluated = index(read_jsonl(evaluated_path))
    require(set(evaluated) == set(scores), "B per-query evaluation does not contain the exact 113 scoreable IDs")
    layers = {"frozen": "frozen_frame_range_event", "candidate_position_video": "frame_position_video", "deduplicated_video": "distinct_video"}
    for q, reported in evaluated.items():
        require(reported.get("query_text_sha256") == raw[q]["query_text_sha256"] and reported.get("run_identity_sha256") == run_identity, f"B scored/transformed identity mismatch: {q}")
        require(set(reported.get("arms", {})) == set(FUSION_ARMS) | {MATCHED_QWEN}, f"B scored row lacks the five arms and separate matched Qwen: {q}")
        for arm in FUSION_ARMS:
            for local, b_layer in layers.items():
                require(reported["arms"][arm].get(b_layer) == scores[q][arm][local], f"B per-query score disagrees with D rescoring: {q} {arm} {b_layer}")
        matched = reported["arms"][MATCHED_QWEN]
        qwen = providers[q]["providers"]["qwen"]
        frames = qwen["hits"]
        require(qwen["state"] in {"ok", "empty"} and len(frames) == qwen["raw_hit_count"] <= 100 and [int(f["rank"]) for f in frames] == list(range(1, len(frames) + 1)), f"B raw-Qwen rank/state/depth mismatch: {q}")
        require(len({f["frame_id"] for f in frames}) == len(frames), f"B raw-Qwen duplicate frame IDs: {q}")
        videos, seen_videos = [], set()
        for frame in frames:
            fid = str(frame["frame_id"])
            video, number = fid.rsplit("#", 1)
            require(video == frame["video_id"] and number.isdigit(), f"B raw-Qwen frame/video identity mismatch: {q}")
            if frame["video_id"] not in seen_videos:
                seen_videos.add(frame["video_id"])
                videos.append({**frame, "rank": len(videos) + 1})
        independent = {"frozen_frame_range_event": audit.score_frozen(frames, truth[q], scorer),
            "frame_position_video": audit.score_video(frames, truth[q], scorer),
            "distinct_video": audit.score_video(videos, truth[q], scorer)}
        require(all(matched.get(k) == value for k, value in independent.items()), f"B matched-Qwen scores do not reproduce from raw candidates: {q}")
        observed_frozen = audit.score_frozen(frames, truth[q], scorer, depth=100)
        observed_ranks = {"distinct_video_rank_observed": audit.score_video(videos, truth[q], scorer, depth=100)["first_success_rank"],
            "frame_position_video_rank_observed": audit.score_video(frames, truth[q], scorer, depth=100)["first_success_rank"],
            "frozen_rank_observed": observed_frozen["first_success_rank"],
            "required_target_coverage_at_retained100": observed_frozen["target_coverage_at_depth"],
            "all_required_targets_at_retained100": observed_frozen["all_required_targets_present"]}
        require(all(matched.get(k) == value for k, value in observed_ranks.items()), f"B matched-Qwen retained100 evidence does not reproduce: {q}")
        for b_layer in layers.values():
            value = matched.get(b_layer, {})
            require(value.get("retained_depth") == 20 and set(value.get("metrics", {})) == set(audit.METRICS), f"B matched Qwen lacks the declared top20 scoring layer: {q} {b_layer}")
        scores[q][MATCHED_QWEN] = {local: matched[b_layer] for local, b_layer in layers.items()}
        scores[q][MATCHED_QWEN]["retained100"] = {field: matched.get(field) for field in ("distinct_video_rank_observed", "frame_position_video_rank_observed", "frozen_rank_observed", "required_target_coverage_at_retained100", "all_required_targets_at_retained100")}
        scores[q][MATCHED_QWEN]["run_identity_sha256"] = run_identity
        scores[q][MATCHED_QWEN]["retained_frame_pool"] = pool_coverage(frames, truth[q], audit, scorer)
    def aggregate(layer):
        return {name: {metric: math.fsum(scores[q][name][layer]["metrics"][metric] for q in scores) / len(scores) for metric in audit.METRICS} for name in FUSION_ARMS}
    frozen_aggregate, video_aggregate = aggregate("frozen"), aggregate("deduplicated_video")
    winner = max(FUSION_ARMS, key=lambda arm: (video_aggregate[arm]["R@20"], video_aggregate[arm]["MRR@20"], video_aggregate[arm]["R@1"], -FUSION_ARMS.index(arm)))
    require(selected == winner, f"B selected global arm disagrees with declared video objective: {selected} vs {winner}")
    return {"status": "EVALUATED", "best_global_arm": selected, "count": len(scores), "per_query": scores,
        "aggregate_frozen_mean_metrics": frozen_aggregate, "aggregate_deduplicated_video_mean_metrics": video_aggregate,
        "selection_rule": "Verify B global distinct-video R20, then MRR20, then R1, then fixed FUSION_ARMS order; frozen range/event performance remains separate.",
        "selection_qualification": "Exploratory development selection after comparing five global arms; no per-query oracle or held-out superiority claim.",
        "rank_comparison_boundary": "B/C candidate surfaces, captures and timeline evidence differ; cross-packet comparisons are descriptive.",
        "matched_qwen_status": "EVALUATED", "run_identity_sha256": run_identity,
        "matched_qwen_mean_metrics": {local: {metric: math.fsum(scores[q][MATCHED_QWEN][local]["metrics"][metric] for q in scores) / len(scores) for metric in audit.METRICS} for local in layers},
        "source_sha256": sha256(path), "selection_source_sha256": sha256(selection_path), "evaluated_source_sha256": sha256(evaluated_path),
        "transform_proof": proof, "raw_provider_source_sha256": sha256(provider_path), "configuration_source_sha256": sha256(config_path),
        "active_providers": list(active_providers),
        "matched_qwen_verification": "All113 raw-Qwen controls independently rescored in three top20 layers and retained100 diagnostics."}

def pool_coverage(items, truth, audit, scorer):
    ranked = [{**item, "rank": i} for i, item in enumerate(items, 1)]
    frozen = audit.score_frozen(ranked, truth, scorer, depth=len(ranked))
    bits = [rank is not None for rank in frozen["target_first_ranks"]]
    return {"candidate_count": len(ranked), "accepted_video_present": audit.score_video(ranked, truth, scorer, depth=len(ranked))["first_success_rank"] is not None,
        "target_present": bits, "required_target_count": len(bits), "present_target_count": sum(bits),
        "target_coverage": frozen["target_coverage_at_depth"], "all_required_targets_present": frozen["all_required_targets_present"]}

def observed_pool_evidence(c, b_query=None, selected_arm=None):
    historical = {"accepted_video_present": c["candidate_pool"]["video_first_rank_at_100"] is not None,
        "target_present": [rank is not None for rank in c["candidate_pool"]["target_first_ranks_at_100"]],
        "scope": "Historical C saved HTTP Qwen top100; original timeline evidence retained."}
    pools = {"historical_c_qwen_top100": historical}
    if b_query:
        pools["fresh_b_active_provider_union"] = b_query["active_provider_union"]
        pools["fresh_b_selected_global_top100"] = b_query[selected_arm]["retained_frame_pool"]
        pools["fresh_b_matched_qwen_top100"] = b_query[MATCHED_QWEN]["retained_frame_pool"]
    lengths = {len(pool["target_present"]) for pool in pools.values()}
    require(len(lengths) == 1, "Observed C/B pool target identities differ")
    n = next(iter(lengths))
    bits = [any(pool["target_present"][i] for pool in pools.values()) for i in range(n)]
    return {"pools": pools, "any_accepted_video_present": any(pool["accepted_video_present"] for pool in pools.values()),
        "combined_target_present": bits, "all_required_targets_observed": bool(bits) and all(bits),
        "scope": "Observed saved-pool coverage across historical C and fresh B captures. This is a diagnostic OR of target presence, not an attainable ranking, corpus-wide absence claim, or matched intervention. Sparse/dense source-visibility diagnostics remain separate."}

def remaining_failure(pool_evidence, remaining):
    if not remaining:
        return "none"
    if not pool_evidence["any_accepted_video_present"]:
        return "candidate_generation_missing_video"
    if not pool_evidence["all_required_targets_observed"]:
        return "candidate_generation_missing_event"
    return "unresolved"

def baseline_failure(c):
    if c["frozen"]["baseline"]["metrics"]["R@20"] == 1:
        return "none"
    if c["candidate_pool"]["video_first_rank_at_100"] is None:
        return "candidate_generation_missing_video"
    if not c["candidate_pool"]["all_required_targets_present"]:
        return "candidate_generation_missing_event"
    return "unresolved"

def weak_truth(c):
    basis = c["effective_truth_basis"]
    weak = c["truth_tier"] != "frozen_headless_benchmark_truth" or basis == "provisional_submission_anchor"
    return {"truth_tier": c["truth_tier"], "effective_truth_basis": basis, "provisional_or_proxy": weak, "organizer_gold": False,
            "main_failure_cause_established": False,
            "qualification": "Source-text truth awaits corpus validation or event truth is a submission-anchor proxy." if weak else "Historical development benchmark truth; not organizer gold."}

def smallest_test(primary, row):
    if primary == "candidate_generation_missing_video":
        return "Check whether an independent provider supplies the accepted video in its frozen top100; preserve the historical Qwen miss as a control."
    if primary == "candidate_generation_missing_event":
        if row["task_type"] == "trake":
            return "Resolve remaining source-review event/contact questions and version any accepted truth update before new event metrics; retain the current proxy score separately."
        return "Inspect the accepted range and retained frames from its video to distinguish a missing moment from a weak locator before changing ranking."
    if primary == "none" and row["reranker_regression"]:
        return "Review promoted and displaced retained candidates at the regressed cutoff; preserve the successful baseline output."
    if primary == "none":
        return "Keep this query as a success control; its frozen top20 outcome does not justify a corrective retrieval experiment."
    channels = row["dataset_audit"]["channels"]
    if any(x.get("review_status") == "AUDIO_CAPTURED_NOT_HEARD" for x in channels.values()):
        return "Listen to the captured ASR excerpt and record a source reference before judging transcription fidelity; keep source observations separate from downstream retrieval causes."
    if channels:
        return "Test the recorded source-feature finding against independent provider visibility; an OCR gap alone does not establish the cause of a retrieval miss."
    return "Inspect the first relevant baseline candidate within top100 and higher-ranked negatives; test one cause only after source review."

def dataset_join(audit_rows, sample, expected_ids):
    by_query = collections.defaultdict(dict)
    selected = {(r["query_id"], channel) for channel, rows in sample["selected"].items() for r in rows}
    seen = set()
    fields = ("review_status", "source_media_inspected", "primary_failure", "evidence_paths", "alignment_checked",
              "artifact_contains_required_signal", "sparse_rank", "dense_rank", "fusion_rank")
    for row in audit_rows:
        key = (row["query_id"], row["channel"])
        require(key not in seen and row["query_id"] in expected_ids, f"Duplicate/excluded dataset query/channel audit: {key}")
        seen.add(key)
        by_query[key[0]][key[1]] = {k: row[k] for k in fields}
    require(seen == selected and len(seen) == 38 and len(by_query) == 30, "Dataset audit must preserve the frozen38 pairs across30 queries")
    return by_query

def attach_dataset_reviews(dataset, reviewed_rows, truth):
    expected = {(q, channel) for q, channels in dataset.items() for channel in channels}
    seen = set()
    for reviewed in reviewed_rows:
        q, channel = reviewed["query_id"], reviewed["channel"]
        key = (q, channel)
        require(key not in seen and key in expected, f"Duplicate or unselected source-audit row: {key}")
        seen.add(key)
        require(reviewed["canonical_query"] == truth[q]["query"], f"Source-audit canonical query mismatch: {key}")
        target = dataset[q][channel]
        target["preparation_review_status"] = target["review_status"]
        target["preparation_source_media_inspected"] = target["source_media_inspected"]
        target["review_status"] = reviewed["review_status"]
        target["source_media_inspected"] = reviewed["source_media_inspected"]
        media = reviewed.get("media_review") or {}
        target["source_review"] = {
            "path": "outputs/dataset-audit/reviewed_audit.jsonl", "query_id": q, "channel": channel,
            "classification": reviewed["latest_classification"], "source_primary_failure": reviewed["primary_failure"],
            "interpretation_limit": reviewed["interpretation_limit"], "media_review_status": media.get("review_status"),
            "cause_status": media.get("cause_status"), "artifact_relative_path": media.get("artifact_relative_path"),
            "artifact_sha256": media.get("artifact_sha256"), "sparse_dense_visibility_audited": reviewed["sparse_dense_visibility_audited"],
            "transcription_fidelity": reviewed["transcription_fidelity"], "downstream_failure_cause_established": False,
            "preparation_field_scope": "Legacy alignment and rank fields remain preparation checks; source observations do not fill unavailable live ranks.",
        }
        require(not (channel == "asr" and reviewed["review_status"] == "AUDIO_CAPTURED_NOT_HEARD" and reviewed["source_media_inspected"]), "Unheard ASR capture must not be counted as source-media listening")
    require(seen == expected, "Reviewed source audit must cover the exact38 selected pairs")
    return dataset

def temporal_review_join(reviewed_rows, truth, temporal_inventory, canonical_sha256):
    expected = {f"{row['query_id']}:e{event['event_index']}": event for row in temporal_inventory for event in row["events"]}
    reviewed = index(reviewed_rows, "anchor_id")
    require(len(expected) == 31 and set(reviewed) == set(expected), "Temporal source review must preserve exactly31 requested anchors")
    by_query = collections.defaultdict(list)
    for aid, row in reviewed.items():
        q, prior = row["query_id"], row["prior_anchor"]
        require(row["canonical_query"] == truth[q]["query"] and row["canonical_source"]["sha256"] == canonical_sha256, f"Temporal review canonical identity mismatch: {aid}")
        require(prior["point_frame"] == expected[aid]["frame"] and prior["video_id"] == expected[aid]["video_id"], f"Temporal review changed its preserved anchor: {aid}")
        policy = row["metric_policy"]
        require(policy["evaluation_use"] == "REVIEW_ONLY_NOT_SCORING_INPUT" and not any(policy[k] for k in ("canonical_truth_replaced", "existing_scoring_contract_changed", "truth_tier_promoted", "new_temporal_iou_eligibility", "new_event_order_metric_eligibility")), "Temporal source proposals must not alter scoring")
        require(row["review_status"] == "SOURCE_MEDIA_REVIEWED" and row["source_media_inspected"] is True, f"Temporal source media was not reviewed: {aid}")
        by_query[q].append({k: row[k] for k in ("anchor_id", "event_index", "event_text_exact", "prior_anchor", "prior_point_disposition", "proposed_locator", "event_decision", "video_decision", "order_decision", "review", "metric_policy", "source_media_inspected", "review_status")})
    return {q: {"status": "SOURCE_MEDIA_REVIEWED", "source": "outputs/temporal-truth-review/proposed_truth.reviewed.jsonl",
                "anchors": sorted(rows, key=lambda row: row["event_index"]), "canonical_scoring_changed": False}
            for q, rows in by_query.items()}

def build_rows(truth, crows, dataset, temporal_summary, temporal_inventory, fusion, temporal_reviews=None, visibility=None):
    temporal_reviews = temporal_reviews or {}
    scoreable = {q for q, t in truth.items() if t["scoreable"]}
    require(len(truth) == 115 and len(scoreable) == 113 and set(truth) - scoreable == {"p0_q15", "p3_q09"}, "Canonical115/113 cohort differs")
    c = index(crows)
    require(scoreable <= set(c) and not (set(c) - set(truth)), "Packet C lacks the exact scoreable cohort")
    temporal_coverage = index(temporal_summary["coverage"]["per_query"])
    temporal_pool = index(temporal_summary["candidate_pool_comparison"])
    inventory = index(temporal_inventory)
    matched_run = temporal_summary.get("new_matched_run") or {}
    matched_rows = index(matched_run.get("per_query", []))
    expected_temporal = {q for q in scoreable if truth[q]["task_type"] == "trake"}
    require(set(temporal_coverage) == set(temporal_pool) == set(inventory) == expected_temporal and len(expected_temporal) == 8, "Packet A/dataset temporal coverage must preserve exact eight TRAKE IDs")
    require(not matched_rows or set(matched_rows) == expected_temporal, "Matched temporal results must preserve exact eight TRAKE IDs")
    output = []
    for q in sorted(scoreable):
        source, t = c[q], truth[q]
        require(source["canonical_source_key"] == t["canonical_source_key"] and source["task_type"] == t["task_type"], f"Packet C identity mismatch: {q}")
        base, rerank = source["frozen"]["baseline"], source["frozen"]["reranker"]
        best = fusion["per_query"].get(q, {}).get(fusion["best_global_arm"])
        matched_b = fusion["per_query"].get(q, {}).get(MATCHED_QWEN)
        regression_metrics = [m for m, delta in source["frozen"]["delta"].items() if delta < -1e-12]
        observed = {"baseline": base["metrics"]["R@20"] == 1, "reranker": rerank["metrics"]["R@20"] == 1}
        if best is not None:
            observed["best_fusion"] = best["frozen"]["metrics"]["R@20"] == 1
        remaining = not any(observed.values())
        pool_evidence = observed_pool_evidence(source, fusion["per_query"].get(q), fusion["best_global_arm"])
        primary = remaining_failure(pool_evidence, remaining)
        channels = dataset.get(q, {})
        temporal = q in expected_temporal
        row = {
            "query_id": q, "canonical_source_key": t["canonical_source_key"], "phase": source["phase"], "task_type": source["task_type"],
            "truth_tier": source["truth_tier"], "capability_tags": source["capability_tags"], "query_category": source["primary_challenge"],
            "baseline_rank": base["first_success_rank"], "best_fusion_rank": best["frozen"]["first_success_rank"] if best else None,
            "reranker_rank": rerank["first_success_rank"], "baseline_source": "PACKET_C_HISTORICAL_SAVED_HTTP_QWEN",
            "cross_packet_comparison_status": "DESCRIPTIVE_DIFFERENT_CAPTURES" if best else "PENDING_PACKET_B",
            "matched_b_qwen_rank": matched_b["frozen"]["first_success_rank"] if matched_b else None,
            "matched_b_qwen": {"arm": MATCHED_QWEN, "source": FUSION_EVALUATION + "/per_query.jsonl", **matched_b} if matched_b else None,
            "matched_b_qwen_status": "EVALUATED" if matched_b else fusion["status"],
            "rank_semantics": {"metric": "frozen range/event contract", "depth": 20, "baseline": base["rank_status"], "reranker": rerank["rank_status"],
                "best_fusion": best["frozen"]["rank_status"] if best else fusion["status"],
                "null_meaning": "Not observed within retained20 if evaluated; unavailable arm if status NOT_RUN/INCOMPLETE. No ranks21-100 are imputed."},
            "baseline_video_rank": source["video"]["baseline"]["first_success_rank"], "reranker_video_rank": source["video"]["reranker"]["first_success_rank"],
            "best_fusion_video_rank": best["candidate_position_video"]["first_success_rank"] if best else None,
            "best_fusion_deduplicated_video_rank": best["deduplicated_video"]["first_success_rank"] if best else None,
            "best_fusion": {"global_arm": fusion["best_global_arm"], "metrics": best["frozen"]["metrics"]} if best else None,
            "best_fusion_status": fusion["status"],
            "temporal_experiment_status": matched_run.get("status", temporal_summary["status"]) if temporal else "NOT_IN_TEMPORAL_SUBSET",
            "primary_failure": primary, "baseline_primary_failure": baseline_failure(source),
            "secondary_failures": ["reranker_regression"] if regression_metrics else [],
            "reranker_regression": bool(regression_metrics), "reranker_regression_metrics": regression_metrics,
            "truth_qualification": weak_truth(source), "observed_success_at20": observed, "remaining_miss_after_observed_arms": remaining,
            "candidate_ceiling": source["candidate_pool"],
            "observed_pool_evidence": pool_evidence,
            "primary_failure_scope": "Remaining miss diagnosed only against observed historical-C top100 and fresh-B active-provider union/current100; target presence leads to unresolved ranking. No corpus/model extraction cause is inferred.",
            "candidate_ceiling_scope": "Packet C historical saved HTTP Qwen top100 only; separate from B's fresh raw-provider pool and matched Qwen control.",
            "dataset_audit": {"selected_channels": sorted(channels), "channels": channels, "selection_is_not_causal_evidence": True,
                "status": "SOURCE_REVIEW_ATTACHED" if any("source_review" in x for x in channels.values()) else "SELECTED_FOR_SOURCE_REVIEW" if channels else "NOT_SELECTED"},
            "source_visibility": {"status": "SEPARATE_EVIDENCE_ATTACHED" if visibility and q in visibility["per_query"] else "NOT_SELECTED" if not channels else "EVIDENCE_NOT_LOADED",
                "channels": visibility["per_query"].get(q, {}) if visibility else {}, "changes_primary_failure": False, "included_in_observed_arm_union": False,
                "scope": "Independent retained-top100 OCR/ASR provider observations; no extraction diagnosis, compatibility claim or fusion/reranker intervention is inferred."},
            "temporal_evidence": {
                "cached_completion": temporal_coverage[q], "candidate_pool_comparison": temporal_pool[q],
                "quality_metrics_available": temporal_summary["quality_metrics"] is not None,
                "new_matched_run": matched_rows.get(q), "new_matched_run_status": matched_run.get("status"), "new_matched_run_scores_path": matched_run.get("scores_path"),
                "motion_review_status": temporal_reviews[q]["status"] if q in temporal_reviews else inventory[q]["review_status"],
                "preparation_motion_review_status": inventory[q]["review_status"], "source_truth_proposals": temporal_reviews.get(q),
                "mechanical_flags": inventory[q]["mechanical_flags"], "stored_event_count": len(inventory[q]["events"]), "event_truth_tiers": inventory[q]["event_truth_tiers"],
                "baseline_target_coverage_at20": base["target_coverage_at_depth"], "reranker_target_coverage_at20": rerank["target_coverage_at_depth"],
                "best_fusion_target_coverage_at20": best["frozen"]["target_coverage_at_depth"] if best else None,
            } if temporal else None,
            "evidence": {
                "packet_c": {"path": "outputs/reranker/per_query.jsonl", "query_id": q}, "canonical_truth": {"path": "inputs/canonical_truth.jsonl", "query_id": q},
                "baseline_frozen_metrics": base["metrics"], "reranker_frozen_metrics": rerank["metrics"],
                "baseline_video_metrics": source["video"]["baseline"]["metrics"], "reranker_video_metrics": source["video"]["reranker"]["metrics"],
                "ranking_classification": source["classification"], "timeline_diagnostic": source["timeline_diagnostic"], "historical_c_frame_only": source["frame_only"],
                "fusion_source": FUSION_EVALUATION + "/study_results.jsonl" if best else None,
                "matched_b_qwen_source": FUSION_EVALUATION + "/per_query.jsonl" if matched_b else None,
                "dataset_source": "outputs/dataset-audit/audit.jsonl" if channels else None,
                "temporal_source": "outputs/temporal-multi-image/summary.json" if temporal else None,
            },
        }
        row["next_smallest_test"] = smallest_test(primary, row)
        require(primary in TAXONOMY and all(x in TAXONOMY for x in row["secondary_failures"]), f"Uncontrolled failure label: {q}")
        output.append(row)
    return output

def matched_b_contrasts(fusion):
    if fusion["status"] != "EVALUATED":
        return {"status": "NOT_COMPUTED_PENDING_FUSION", "layers": None}
    selected = fusion["best_global_arm"]
    layers = {}
    for layer in ("frozen", "candidate_position_video", "deduplicated_video"):
        metrics = {}
        for metric in ("R@1", "R@5", "R@10", "R@20", "MRR@20"):
            deltas = {q: arms[selected][layer]["metrics"][metric] - arms[MATCHED_QWEN][layer]["metrics"][metric] for q, arms in fusion["per_query"].items()}
            metrics[metric] = {"sum_delta": math.fsum(deltas.values()), "mean_delta": math.fsum(deltas.values()) / len(deltas),
                "improved_query_ids": sorted(q for q, d in deltas.items() if d > 1e-12),
                "regressed_query_ids": sorted(q for q, d in deltas.items() if d < -1e-12)}
        layers[layer] = metrics
    return {"status": "EVALUATED", "selected_arm": selected, "control": MATCHED_QWEN, "run_identity_sha256": fusion["run_identity_sha256"], "layers": layers,
        "scope": "B transforms and raw Qwen share one fresh provider collection. These are within-B contrasts; C's saved reranker is not part of this matched experiment. Global selection remains exploratory."}

def summarize(rows, fusion, visibility=None):
    remaining = [r for r in rows if r["remaining_miss_after_observed_arms"]]
    primary_counts = dict(collections.Counter(r["primary_failure"] for r in rows))
    def counts(subset):
        return {"count": len(subset), "remaining_misses": sum(r["remaining_miss_after_observed_arms"] for r in subset),
                "primary_failure_counts": dict(collections.Counter(r["primary_failure"] for r in subset))}
    by_capability = {tag: counts([r for r in rows if tag in r["capability_tags"]]) for tag in sorted({tag for r in rows for tag in r["capability_tags"]})}
    by_category = {cat: counts([r for r in rows if r["query_category"] == cat]) for cat in sorted({r["query_category"] for r in rows})}
    interaction = {"status": "NOT_COMPUTED_PENDING_FUSION", "fusion_improved_mrr_but_reranker_regressed": None,
        "reranker_improved_mrr_but_fusion_did_not": None, "fusion_R20_rescues": None, "reranker_R20_rescues_fusion_did_not": None,
        "comparison_scope": "DESCRIPTIVE_CROSS_RUN_HISTORICAL_REFERENCE",
        "definition": "These legacy-named sets compare B fresh fusion scores with C's historical HTTP Qwen reference, while C reranker deltas are paired within C. Capture/candidate surfaces and timeline evidence differ. No matched B/C intervention or fusion-to-reranker pipeline was tested."}
    if fusion["status"] == "EVALUATED":
        for key in ("fusion_improved_mrr_but_reranker_regressed", "reranker_improved_mrr_but_fusion_did_not", "fusion_R20_rescues", "reranker_R20_rescues_fusion_did_not"):
            interaction[key] = []
        interaction["status"] = "EVALUATED"
        for row in rows:
            b, r, f = row["evidence"]["baseline_frozen_metrics"], row["evidence"]["reranker_frozen_metrics"], row["best_fusion"]["metrics"]
            if f["MRR@20"] > b["MRR@20"] + 1e-12 and r["MRR@20"] < b["MRR@20"] - 1e-12:
                interaction["fusion_improved_mrr_but_reranker_regressed"].append(row["query_id"])
            if r["MRR@20"] > b["MRR@20"] + 1e-12 and f["MRR@20"] <= b["MRR@20"] + 1e-12:
                interaction["reranker_improved_mrr_but_fusion_did_not"].append(row["query_id"])
            if b["R@20"] == 0 and f["R@20"] == 1:
                interaction["fusion_R20_rescues"].append(row["query_id"])
            if b["R@20"] == 0 and r["R@20"] == 1 and f["R@20"] < 1:
                interaction["reranker_R20_rescues_fusion_did_not"].append(row["query_id"])
    temporal = [r for r in rows if r["task_type"] == "trake"]
    anchors = [a for row in temporal for a in (row["temporal_evidence"].get("source_truth_proposals") or {}).get("anchors", [])]
    pool_temporal = [r["query_id"] for r in temporal if r["candidate_ceiling"]["video_first_rank_at_100"] is not None and not r["candidate_ceiling"]["all_required_targets_present"]]
    observed_temporal = [r["query_id"] for r in temporal if (r["baseline_video_rank"] is not None or r["reranker_video_rank"] is not None or r["best_fusion_video_rank"] is not None) and r["remaining_miss_after_observed_arms"]]
    return {
        "schema": "vecna82-failure-ledger-v1", "status": "COMPLETE_WITH_QUALIFIED_SOURCE_DIAGNOSES" if fusion["status"] == "EVALUATED" else "LEDGER_READY_FUSION_PENDING",
        "cohort": {"scoreable_queries": len(rows), "excluded_query_ids": ["p0_q15", "p3_q09"]}, "comparison_scope": COMPARISON_SCOPE,
        "primary_failure_scope": "Remaining misses after the descriptive success union are classified against observed C historical top100 plus fresh B active-provider union/current100. Missing-video/event labels describe absence from those saved pools only. Existing target evidence leaves ranking unresolved. Baseline failure and candidate ceiling remain historical-C-only; no extraction or corpus-wide absence cause is inferred.",
        "taxonomy": list(TAXONOMY), "taxonomy_extension": "none explicitly represents success; missing_event includes missing accepted ranges for non-TRAKE queries.",
        "primary_failure_counts": primary_counts, "baseline_primary_failure_counts": dict(collections.Counter(r["baseline_primary_failure"] for r in rows)),
        "remaining_misses": len(remaining), "remaining_miss_query_ids": [r["query_id"] for r in remaining],
        "reranker_regression_query_ids": [r["query_id"] for r in rows if r["reranker_regression"]],
        "counts_by_capability": by_capability, "counts_by_query_category": by_category,
        "capability_warning": "Overlapping query-side labels describe requirements; they do not diagnose visual/OCR/ASR causes.",
        "confirmed_recurring_obstructions": {k: v for k, v in primary_counts.items() if k.startswith("candidate_generation_")},
        "mechanism_limit": "Saved evidence establishes pool absence and score movement; extraction, calibration, representation and temporal reasoning causes require further evidence.",
        "fusion": {k: v for k, v in fusion.items() if k != "per_query"}, "arm_interactions": interaction, "matched_b_contrasts": matched_b_contrasts(fusion),
        "source_visibility": {"status": "SEPARATE_EVIDENCE_ATTACHED" if visibility else "EVIDENCE_NOT_LOADED", "providers": visibility["providers"] if visibility else None,
            "changes_primary_failure": False, "included_in_observed_arm_union": False,
            "scope": "Independent frozen38 query/channel evidence overlays; no benchmark score, causal failure label or observed-arm union is changed."},
        "cross_run_qwen_baseline_differences": {
            "status": "DESCRIPTIVE_DIFFERENT_CAPTURES" if fusion["status"] == "EVALUATED" else "NOT_COMPUTED_PENDING_FUSION",
            "historical_c_frozen_vs_fresh_b_frame_only_changed_query_ids": [r["query_id"] for r in rows if r["matched_b_qwen"] is not None and r["evidence"]["baseline_frozen_metrics"] != r["matched_b_qwen"]["frozen"]["metrics"]] if fusion["status"] == "EVALUATED" else None,
            "scope": "Differences can reflect collection, candidate surface and timeline evidence; they do not isolate model or ranking changes."},
        "temporal": {"count": len(temporal), "experiment_status_counts": dict(collections.Counter(r["temporal_experiment_status"] for r in temporal)),
            "correct_video_in_top100_but_required_event_missing": pool_temporal,
            "correct_video_observed_at20_but_event_contract_unsatisfied": observed_temporal,
            "interpretation": "At least one required event remains missing; this does not imply every event is absent or prove a representation failure."},
        "truth": {"provisional_or_proxy_query_ids": [r["query_id"] for r in rows if r["truth_qualification"]["provisional_or_proxy"]],
            "mainly_truth_limited_query_ids": None, "mainly_truth_limited_status": "NOT_ESTABLISHED_BY_SOURCE_REVIEW" if anchors else "NOT_ESTABLISHED_WITHOUT_SOURCE_REVIEW",
            "explanation": "41 queries use P3 provisional text or historical event proxies. Source review does not by itself establish truth quality as the dominant retrieval-miss cause.",
            "source_review": {"reviewed_queries": sum(bool(r["temporal_evidence"].get("source_truth_proposals")) for r in temporal), "reviewed_anchors": len(anchors),
                "proposed_locator_counts": dict(collections.Counter(a["proposed_locator"]["kind"] for a in anchors)),
                "first_occurrence_claims": sum(a["event_decision"]["first_occurrence_verified"] is True for a in anchors),
                "canonical_scoring_changed": False, "scope": "Proposal overlay only; representative points do not certify first occurrence, completion or the full sequence."}},
        "dataset_audit": {"selected_query_channel_rows": sum(len(r["dataset_audit"]["selected_channels"]) for r in rows),
            "unique_selected_queries": sum(bool(r["dataset_audit"]["selected_channels"]) for r in rows),
            "source_media_reviewed_rows": sum(x["source_media_inspected"] for r in rows for x in r["dataset_audit"]["channels"].values()),
            "source_review_status_counts": dict(collections.Counter(x["review_status"] for r in rows for x in r["dataset_audit"]["channels"].values())),
            "source_images_inspected_ocr": sum(x["source_media_inspected"] for r in rows for c, x in r["dataset_audit"]["channels"].items() if c == "ocr"),
            "source_audio_heard_asr": sum(x["source_media_inspected"] for r in rows for c, x in r["dataset_audit"]["channels"].items() if c == "asr"),
            "source_audio_captured_not_heard_asr": sum(x["review_status"] == "AUDIO_CAPTURED_NOT_HEARD" for r in rows for c, x in r["dataset_audit"]["channels"].items() if c == "asr")},
    }

def report(summary):
    lines = ["# Packet D: unified 113-query failure ledger", "",
        f"{summary['cohort']['scoreable_queries']} scoreable queries are preserved; {summary['remaining_misses']} miss the frozen top20 contract across the observed arms. Fusion status: {summary['fusion']['status']}.", "",
        "| Primary outcome after observed arms | Queries |", "|---|---:|"]
    lines += [f"| {label} | {count} |" for label, count in sorted(summary["primary_failure_counts"].items())]
    lines += ["", "The success count is a descriptive union across saved arms, not a deployed system score or routing policy. The ledger retains each historical baseline failure and reranker regression even when another arm succeeds. The candidate ceiling describes C's historical Qwen pool; it does not imply that other providers cannot rescue the query.", "",
        "C's historical saved HTTP Qwen output is paired with its saved reranker result. B uses a fresh raw-provider collection and preserves its own matched Qwen control separately. Candidate identities, collection conditions and timeline evidence differ across B/C, so their comparisons are descriptive. No sequential fusion-to-reranker system was tested.", "",
        "Ranks use the pinned frozen localization/event scorer at20. Original C timeline evidence is preserved, while B has frame-only candidates. Candidate-position video and deduplicated-video ranks remain separate. Missing observed ranks are censored; unavailable arms are null, with explicit status.", ""]
    if summary.get("runtime_provenance"):
        lines += ["Historical C metrics remain literal saved-rank evidence. Historical package versions, tensor equality and corpus extraction/index lineage remain unverified. A later loader defect and its repair do not retroactively establish C or corpus validity; see the separately pinned C loader-provenance companion.", ""]
    if summary["fusion"]["status"] == "EVALUATED":
        lines += [f"B's one global development selection is {summary['fusion']['best_global_arm']}, verified by distinct-video R20, then MRR20, then R1 and fixed arm order. The selection is exploratory after comparing five arms, with no per-query oracle.", ""]
        for key, label in (
            ("fusion_improved_mrr_but_reranker_regressed", "B fusion exceeds C historical MRR while C reranker regresses against its paired baseline"),
            ("reranker_improved_mrr_but_fusion_did_not", "C reranker improves MRR while B does not exceed the historical baseline"),
            ("reranker_R20_rescues_fusion_did_not", "C reranker R20 rescues with a miss in B's separate fusion capture")):
            lines += [label + ": " + (", ".join(summary["arm_interactions"][key]) or "none") + "."]
        matched = summary["matched_b_contrasts"]["layers"]["frozen"]["R@20"]
        lines += ["", "Within B's own collection, selected fusion R20 improvements versus fresh Qwen: " + (", ".join(matched["improved_query_ids"]) or "none") + ".",
            "Within that B collection, R20 regressions versus fresh Qwen: " + (", ".join(matched["regressed_query_ids"]) or "none") + ".", ""]
    else:
        lines += ["Fusion interactions remain null until the full study and evaluation are available. Missing fusion is not a failed score. Existing completed B artifacts cannot be silently replaced by partial/null evidence.", ""]
    visibility = summary.get("source_visibility") or {}
    if visibility.get("providers"):
        lines += ["| Provider | Channel | Cases | Eligible video @100 | All current targets @100 | Same-video exact-text repeat excess / retained candidates |",
            "|---|---|---:|---:|---:|---:|"]
        for mode, provider in visibility["providers"].items():
            if provider["status"] != "EVALUATED":
                lines += [f"| {mode} | - | {provider['status']} | - | - | - |"]
                continue
            for channel, value in provider["channels"].items():
                layer = value["main_eligible"]
                lines += [f"| {mode} | {channel.upper()} | {value['query_channel_count']} | {layer['video_hit']['R@100']} | {layer['strict_all_targets_hit']['R@100']} | {layer['same_video_exact_text_repeat_excess']} / {layer['retained_candidates']} |"]
        lines += ["", "These are independent sample-pool visibility counts, including provisional truth. Raw and main-eligible orders remain separate. Video rank uses frame positions; any-target visibility, strict all-target visibility and the full frozen range/event score are distinct. MRR remains capped at20. None of these observations changes D's causal labels or observed-arm union.", "",
            "Sparse host/seed tie replays preserve membership and score sequences but may change ranks and rank metrics. Every observed order is retained without selecting a seed. Dense evidence preserves declared query-model identity and unresolved historical stored-vector compatibility; the exact SDK-added empty params mapping is recorded without claiming independently verified server nprobe.", ""]
    lines += ["Temporal correct-video top100 cases with a missing required event: " + (", ".join(summary["temporal"]["correct_video_in_top100_but_required_event_missing"]) or "none") + ".",
        "Temporal correct-video top20 cases with an unsatisfied event contract: " + (", ".join(summary["temporal"]["correct_video_observed_at20_but_event_contract_unsatisfied"]) or "none") + ".", "",
        f"Source evidence includes {summary['dataset_audit']['source_images_inspected_ocr']} OCR images inspected, {summary['dataset_audit']['source_audio_captured_not_heard_asr']} ASR excerpts captured but unheard, and {summary['dataset_audit']['source_audio_heard_asr']} ASR excerpts heard. Preparation rank fields remain separate from source judgements.", "",
        f"Temporal source proposals cover {summary['truth']['source_review']['reviewed_anchors']} anchors: " + ", ".join(f"{k}={v}" for k, v in sorted(summary["truth"]["source_review"]["proposed_locator_counts"].items())) + ". Canonical truth, prior anchors and metric eligibility are unchanged.",
        "Truth qualifies 41 queries:35 provisional P3 cases and6 historical TRAKE submission-anchor proxies. The mainly-truth-limited set remains null because source review does not establish dominant retrieval cause.", "",
        "Counts by capability/category, exact ranks, source evidence and one next-smallest test per query are in failure_ledger.jsonl and summary.json. All consumed-file SHA256 values appear in provenance.json.", "",
        "Replay after hydrating the final packet artifacts:", "", "    python -m unittest discover -s tests -p 'test_*ledger.py' -v",
        "    python code/build_failure_ledger.py --root . --require-complete", ""]
    return "\n".join(lines)

def run(root, outdir, require_complete=False):
    root, outdir = Path(root).resolve(), Path(outdir).resolve()
    paths = ["inputs/canonical_truth.jsonl", "outputs/control_manifest.json", "outputs/reranker/per_query.jsonl", "outputs/reranker/provenance.json",
        "outputs/dataset-audit/audit.jsonl", "outputs/dataset-audit/sample_manifest.json", "outputs/dataset-audit/temporal_inventory.jsonl",
        "outputs/temporal-multi-image/summary.json", "code/analyze_reranker.py", "code/visibility_ledger.py", "reference/evaluate_reranker_fusion.py"]
    optional_paths = ("outputs/dataset-audit/reviewed_audit.jsonl", "outputs/temporal-truth-review/proposed_truth.reviewed.jsonl",
        LOADER_PROVENANCE, "outputs/reranker/LOADER_PROVENANCE_LIMIT.md", "reference/issue82.md")
    paths += [p for p in optional_paths if (root / p).exists()]
    before = {p: sha256(root / p) for p in paths}
    truth = index(read_jsonl(root / "inputs/canonical_truth.jsonl"))
    canonical_ids = {q for q, t in truth.items() if t["scoreable"]}
    controls = read_json(root / "outputs/control_manifest.json")
    require(controls["controls"]["per_query_count"] == 113, "Packet0 does not confirm the113-query control")
    crows = read_jsonl(root / "outputs/reranker/per_query.jsonl")
    c_sources = index(read_json(root / "outputs/reranker/provenance.json"), "local")
    require(c_sources["inputs/canonical_truth.jsonl"]["sha256"] == before["inputs/canonical_truth.jsonl"], "Packet C scores use a different canonical truth snapshot")
    sample = read_json(root / "outputs/dataset-audit/sample_manifest.json")
    dataset = dataset_join(read_jsonl(root / "outputs/dataset-audit/audit.jsonl"), sample, canonical_ids)
    if "outputs/dataset-audit/reviewed_audit.jsonl" in before:
        dataset = attach_dataset_reviews(dataset, read_jsonl(root / "outputs/dataset-audit/reviewed_audit.jsonl"), truth)
    temporal_summary = read_json(root / "outputs/temporal-multi-image/summary.json")
    inventory = read_jsonl(root / "outputs/dataset-audit/temporal_inventory.jsonl")
    temporal_reviews = temporal_review_join(read_jsonl(root / "outputs/temporal-truth-review/proposed_truth.reviewed.jsonl"), truth, inventory, before["inputs/canonical_truth.jsonl"]) if "outputs/temporal-truth-review/proposed_truth.reviewed.jsonl" in before else {}
    audit = load_audit(root)
    scorer = audit.load_scorer(root / "reference/evaluate_reranker_fusion.py")
    visibility = load_visibility(root, truth, sample, audit, scorer)
    for path, observed in visibility["inputs_sha256"].items():
        require(path not in before or before[path] == observed, f"Visibility input changed while joining: {path}")
        if path not in before:
            paths.append(path)
            before[path] = observed
    for additional in ("outputs/fusion/capture-full115-v1/provider_rankings.jsonl", "outputs/fusion/frozen_config.json"):
        if (root / additional).exists():
            paths.append(additional)
            before[additional] = sha256(root / additional)
    for name in ("study_results.jsonl", "summary.json", "per_query.jsonl"):
        path = FUSION_EVALUATION + "/" + name
        if (root / path).exists():
            paths.append(path)
            before[path] = sha256(root / path)
    fusion = fusion_evidence(root / FUSION_EVALUATION / "study_results.jsonl", truth, audit, scorer)
    rows = build_rows(truth, crows, dataset, temporal_summary, inventory, fusion, temporal_reviews, visibility)
    summary = summarize(rows, fusion, visibility)
    if LOADER_PROVENANCE in before:
        loader = read_json(root / LOADER_PROVENANCE)
        summary["runtime_provenance"] = {
            "status": loader["status"], "historical_c_affected_by_current_defect": loader["historical_c_affected_by_current_defect"],
            "historical_c_rank_metrics": loader["historical_c_rank_metrics"],
            "corpus_feature_loader_provenance": loader["corpus_feature_loader_provenance"]["status"],
            "synthesis_policy": loader["synthesis_policy"], "source": LOADER_PROVENANCE, "source_sha256": before[LOADER_PROVENANCE],
            "scope": "Provenance snapshot; a current-runtime defect concerns the inspected attempt, not every future B run."}
    if require_complete:
        require(fusion["status"] == "EVALUATED", "Final D requires completed Packet B evaluation")
        require(all(p["status"] == "EVALUATED" for p in visibility["providers"].values()), "Final D requires completed sparse and dense evidence")
        require(summary["truth"]["source_review"]["reviewed_anchors"] == 31 and summary["dataset_audit"]["source_images_inspected_ocr"] == 20 and summary["dataset_audit"]["source_audio_captured_not_heard_asr"] == 18, "Final D requires completed bounded source reviews")
        require(LOADER_PROVENANCE in before and all(row["temporal_experiment_status"] == "COMPLETE_BOUNDED_PROBE" for row in rows if row["task_type"] == "trake"), "Final D requires current C provenance and completed Packet A")
    after = {p: sha256(root / p) for p in paths}
    require(before == after, "An input changed during ledger generation; regenerate after its producer finishes")
    provenance = {"schema": "vecna82-failure-ledger-provenance-v1", "inputs_sha256": after, "generator_sha256": sha256(Path(__file__)),
        "authority": "JimmyK300/Vecna#82 Packet D; canonical truth and Packet0 control manifest",
        "selection_rule": "Verify B global distinct-video R20/MRR20/R1 and fixed arm order; no per-query tuning",
        "input_refresh": "Regenerate after A/B/source/visibility evidence changes; all consumed bytes checked before/after.",
        "reconstruction": "Source reconstructed after the scratch outage; this generator hash identifies the recovered implementation.",
        "require_complete": require_complete}
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "failure_ledger.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in rows), encoding="utf-8")
    for name, value in (("summary.json", summary), ("provenance.json", provenance)):
        (outdir / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    (outdir / "REPORT.md").write_text(report(summary), encoding="utf-8")
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--require-complete", action="store_true", help="Fail unless B, A and both visibility providers are complete.")
    args = parser.parse_args()
    result = run(args.root, args.out_dir or args.root / "outputs/failure-ledger", args.require_complete)
    print(json.dumps({k: result[k] for k in ("status", "primary_failure_counts", "remaining_misses")}, indent=2))
