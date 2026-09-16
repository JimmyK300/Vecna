#!/usr/bin/env python3
"""Packet B scoring-only evaluation after a complete GT-blind provider export.

Selection policy is frozen before collection outcomes: maximum distinct-video
R@20, then distinct-video MRR@20, then R@1, then the declared fixed arm order.
This selects one descriptive global arm, never a per-query oracle or a deploy
policy. The same canonical scorer supplies separate frame-position video and
range/event diagnostics for comparison with Packet C.
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path

from analyze_reranker import (EXCLUDED, KS, METRICS, capability_key, load_scorer,
                              paired_bootstrap, percentile, read_json, read_jsonl,
                              score_frozen, score_video, unique_index, verify_sources)
from fusion_study import (ARMS, PROVIDERS, ContractError, _rank, current_scores,
                          digest_bytes, digest_json, nominal_weights, run as transform_run,
                          transform, validate_row)

LAYERS = ("distinct_video", "frame_position_video", "frozen_frame_range_event")
MATCHED_QWEN = "qwen_only_matched"
TEMPORAL = {"SEQ", "BOUND", "TRACK", "MOTION"}
VISUAL = {"VIS_OBJ", "VIS_ATTR", "VIS_EVENT", "SCENE", "ACT", "COUNT", "FINE", "SPATIAL", "MOTION", "TRACK"}
POLICY = {
    "schema": "vecna82-fusion-evaluation-policy-v1",
    "primary_layer": "distinct_video",
    "global_selection_order": ["maximum R@20", "maximum MRR@20", "maximum R@1", "fixed arm order"],
    "fixed_arm_order": list(ARMS),
    "bootstrap_seed": 82,
    "bootstrap_resamples": 10000,
    "comparison_controls": ["fusion_current_control", MATCHED_QWEN],
    "integration": "No production integration; select one descriptive global arm and disclose every regression.",
    "diagnostic_ablation": "Remove one already-computed provider contribution; freeze normalizers and candidate union. This is not recollection or an optimized weight.",
}


def aggregate(rows, layer, arm):
    values = [row["arms"][arm][layer] for row in rows]
    ranks = [value["first_success_rank"] for value in values if value["first_success_rank"] is not None]
    field = {"distinct_video": "distinct_video_rank_observed",
             "frame_position_video": "frame_position_video_rank_observed",
             "frozen_frame_range_event": "frozen_rank_observed"}[layer]
    retained_ranks = [row["arms"][arm][field] for row in rows if row["arms"][arm].get(field) is not None]
    return {"queries": len(values), "metrics": {
        metric: {"mean": statistics.fmean(value["metrics"][metric] for value in values) if values else None,
                 "sum": sum(value["metrics"][metric] for value in values)} for metric in METRICS},
        "median_correct_rank_observed_within20": statistics.median(ranks) if ranks else None,
        "median_correct_rank_observed_in_retained_list": statistics.median(retained_ranks) if retained_ranks else None,
        "unobserved_in_retained_list": len(values) - len(retained_ranks),
        "unobserved_within20": len(values) - len(ranks)}


def paired(rows, layer, arm, control, *, bootstrap=False):
    result = {"queries": len(rows), "arm": arm, "control": control, "metrics": {}}
    for metric in METRICS:
        deltas = [row["arms"][arm][layer]["metrics"][metric] - row["arms"][control][layer]["metrics"][metric]
                  for row in rows]
        rescues = [row["query_id"] for row, delta in zip(rows, deltas) if delta > 1e-12]
        regressions = [row["query_id"] for row, delta in zip(rows, deltas) if delta < -1e-12]
        result["metrics"][metric] = {
            "mean_delta": statistics.fmean(deltas) if deltas else None,
            "sum_delta": sum(deltas), "improved_query_ids": rescues, "regressed_query_ids": regressions,
            "improved_count": len(rescues), "regressed_count": len(regressions),
            "unchanged_count": len(rows) - len(rescues) - len(regressions),
        }
        if bootstrap:
            result["metrics"][metric]["bootstrap"] = paired_bootstrap(
                deltas, POLICY["bootstrap_seed"], POLICY["bootstrap_resamples"])
    return result


def select_global_arm(rows):
    metrics = {arm: aggregate(rows, "distinct_video", arm)["metrics"] for arm in ARMS}
    return max(ARMS, key=lambda arm: (metrics[arm]["R@20"]["sum"], metrics[arm]["MRR@20"]["sum"],
                                      metrics[arm]["R@1"]["sum"], -ARMS.index(arm)))


def score_arm(frames, videos, truth, scorer):
    result = {
        "distinct_video": score_video(videos, truth, scorer),
        "frame_position_video": score_video(frames, truth, scorer),
        "frozen_frame_range_event": score_frozen(frames, truth, scorer),
    }
    result["distinct_video_rank_observed"] = score_video(videos, truth, scorer, depth=100)["first_success_rank"]
    result["frame_position_video_rank_observed"] = score_video(frames, truth, scorer, depth=100)["first_success_rank"]
    pool = score_frozen(frames, truth, scorer, depth=100)
    result["frozen_rank_observed"] = pool["first_success_rank"]
    result["required_target_coverage_at_retained100"] = pool["target_coverage_at_depth"]
    result["all_required_targets_at_retained100"] = pool["all_required_targets_present"]
    result["correct_video_but_required_moment_missing"] = (
        result["distinct_video"]["metrics"]["R@20"] > 0 and not pool["all_required_targets_present"])
    return result


def matched_qwen_items(raw, config):
    frames = [dict(hit) for hit in raw["providers"]["qwen"]["hits"][:config["output_frame_k"]]]
    videos, seen = [], set()
    for frame in frames:
        if frame["video_id"] in seen:
            continue
        seen.add(frame["video_id"])
        videos.append({**frame, "frame_rank": frame["rank"], "rank": len(videos) + 1})
        if len(videos) == config["output_video_k"]:
            break
    return frames, videos


def contribution_ablations(raw, config, truth, scorer):
    maps = validate_row(raw, config)
    order, weights = raw["candidate_tie_order"], nominal_weights(config)
    result = {}
    for arm in ARMS:
        if arm == "fusion_current_control":
            scores, contributions = current_scores(maps, order, config)
        else:
            contributions = {fid: {provider: 0.0 for provider in PROVIDERS} for fid in order}
            for provider in PROVIDERS:
                normalized, _ = transform(maps[provider], arm)
                for fid, value in normalized.items():
                    contributions[fid][provider] = weights[provider] * value
            scores = {fid: sum(contributions[fid].values()) for fid in order}
        result[arm] = {}
        for provider in PROVIDERS:
            if weights[provider] == 0:
                continue
            removed = {fid: scores[fid] - contributions[fid][provider] for fid in order}
            _, videos = _rank(removed, contributions, order, config)
            result[arm][provider] = score_video(videos, truth, scorer)
    return result


def query_slices(row):
    tags = set(row["capability_tags"])
    groups = [f"phase:{row['phase']}", f"task:{row['task_type']}", f"truth:{row['effective_truth_basis']}",
              f"primary_challenge:{row['primary_challenge']}"]
    groups.extend("capability:" + tag for tag in sorted(tags))
    if "OCR" in tags:
        groups.append("requested:ocr_dependent_tag")
    if "ASR" in tags:
        groups.append("requested:asr_dependent_tag")
    if tags & TEMPORAL or row["task_type"] == "trake":
        groups.append("requested:temporal_or_trake")
    if tags & VISUAL and not tags & ({"OCR", "ASR"} | TEMPORAL):
        groups.append("requested:visual_without_text_or_temporal_tags")
    if tags & {"OCR", "ASR"} and tags & VISUAL:
        groups.append("requested:combined_visual_and_text_tags")
    if "NEG" in tags:
        groups.append("requested:hard_negative_tag")
    return groups


def evaluate(root: Path, rankings: Path, manifest: Path, config_path: Path, queries_path: Path, outdir: Path):
    if outdir.exists():
        raise ContractError("evaluation output exists; select a fresh immutable output directory")
    config = read_json(config_path)
    # Transform all queries before opening truth. The transform runner validates
    # complete collection identity, hashes, exact canonical IDs, and main replay.
    study_path = outdir / "study_results.jsonl"
    transform_proof = transform_run(rankings, config_path, queries_path, study_path, manifest)
    provenance = verify_sources(root, ["inputs/canonical_truth.jsonl", "reference/evaluate_reranker_fusion.py"]
                                + [f"inputs/capability_p{i}.jsonl" for i in range(4)])
    truth = unique_index(read_jsonl(root / "inputs/canonical_truth.jsonl"))
    caps = unique_index([row for i in range(4) for row in read_jsonl(root / f"inputs/capability_p{i}.jsonl")])
    raw_rows, study = unique_index(read_jsonl(rankings)), unique_index(read_jsonl(study_path))
    if len(truth) != 115 or set(raw_rows) != set(truth) or set(study) != set(truth):
        raise ContractError("evaluation requires exact 115-query join")
    if {query_id for query_id, row in truth.items() if not row.get("scoreable")} != EXCLUDED:
        raise ContractError("canonical 113-scoreable mapping changed")
    scorer = load_scorer(root / "reference/evaluate_reranker_fusion.py")
    rows = []
    for query_id in sorted(truth):
        target, raw, fused = truth[query_id], raw_rows[query_id], study[query_id]
        if target["query"] != raw["query_text"]:
            raise ContractError("scoring truth's canonical query text differs from collection")
        if not target["scoreable"]:
            continue
        cap = caps[capability_key(target)]
        row = {"query_id": query_id, "phase": target["canonical_round"], "task_type": target["task_type"],
               "truth_tier": target["truth_tier"],
               "effective_truth_basis": "+".join(sorted({event.get("truth_tier", "unspecified_event_truth")
                                                        for event in target.get("trake_event_truth", [])})) or target["truth_tier"],
               "capability_tags": cap["capability_tags"], "primary_challenge": cap["primary_challenge"],
               "query_text_sha256": raw["query_text_sha256"], "run_identity_sha256": raw["run_identity_sha256"],
               "arms": {}, "provider_diagnostics": {}}
        for arm in ARMS:
            row["arms"][arm] = score_arm(fused["arms"][arm]["frames"], fused["arms"][arm]["videos"], target, scorer)
            row["arms"][arm]["cpu_ns"] = fused["arms"][arm]["fusion_cpu_ns"]
            row["arms"][arm]["wall_ns"] = fused["arms"][arm]["fusion_wall_ns"]
            row["arms"][arm]["top1"] = fused["arms"][arm]["frames"][:1]
        qwen_frames, qwen_videos = matched_qwen_items(raw, config)
        row["arms"][MATCHED_QWEN] = score_arm(qwen_frames, qwen_videos, target, scorer)
        provider_union = {}
        for provider in PROVIDERS:
            items = raw["providers"][provider]["hits"]
            state = raw["providers"][provider]["state"]
            provider_score = score_video(items, target, scorer, depth=100)
            row["provider_diagnostics"][provider] = {
                "state": state, "candidate_count": len(items),
                "target_video_provider_rank": provider_score["first_success_rank"],
                "normalization": {arm: fused["arms"][arm]["normalization"].get(provider) for arm in ARMS[1:]},
            }
            if nominal_weights(config)[provider] > 0:
                provider_union.update({item["frame_id"]: item for item in items})
        union_items = [{**item, "rank": index} for index, item in enumerate(provider_union.values(), 1)]
        row["target_video_in_provider_union"] = score_video(union_items, target, scorer, depth=len(union_items))["first_success_rank"] is not None
        row["contribution_removal"] = contribution_ablations(raw, config, target, scorer)
        row["rank_deltas"] = {}
        for control in ("fusion_current_control", MATCHED_QWEN):
            row["rank_deltas"][control] = {}
            before = row["arms"][control]["distinct_video_rank_observed"]
            for arm in ARMS:
                after = row["arms"][arm]["distinct_video_rank_observed"]
                row["rank_deltas"][control][arm] = {
                    "before": before, "after": after,
                    "delta_after_minus_before": after - before if before is not None and after is not None else None,
                    "status": "both_observed" if before is not None and after is not None else
                              "rescue_into_retained_list" if after is not None else
                              "regression_out_of_retained_list" if before is not None else "both_unobserved",
                }
        rows.append(row)
    if len(rows) != 113:
        raise ContractError("not exactly 113 scored rows")
    all_arms = (*ARMS, MATCHED_QWEN)
    overall = {layer: {arm: aggregate(rows, layer, arm) for arm in all_arms} for layer in LAYERS}
    comparisons = {control: {arm: paired(rows, "distinct_video", arm, control, bootstrap=True)
                             for arm in ARMS if arm != control}
                   for control in ("fusion_current_control", MATCHED_QWEN)}
    groups = collections.defaultdict(list)
    for row in rows:
        for group in query_slices(row):
            groups[group].append(row)
    slices = {name: {"queries": len(group),
                     "overall": {layer: {arm: aggregate(group, layer, arm) for arm in all_arms} for layer in LAYERS},
                     "paired_vs_current": {arm: paired(group, "distinct_video", arm, "fusion_current_control") for arm in ARMS[1:]}}
              for name, group in sorted(groups.items())}
    best = select_global_arm(rows)
    removal = {}
    for arm in ARMS:
        removal[arm] = {}
        for provider in PROVIDERS:
            if nominal_weights(config)[provider] == 0:
                continue
            deltas = [row["contribution_removal"][arm][provider]["metrics"]["R@20"] -
                      row["arms"][arm]["distinct_video"]["metrics"]["R@20"] for row in rows]
            removal[arm][provider] = {"R@20_sum_delta": sum(deltas),
                                      "improved_query_ids": [row["query_id"] for row, d in zip(rows, deltas) if d > 0],
                                      "regressed_query_ids": [row["query_id"] for row, d in zip(rows, deltas) if d < 0]}
    best_comparison = comparisons["fusion_current_control"].get(best)
    decision = {"descriptive_best_global_arm": best, "production_integration": False,
                "comparison_scope": "four nonzero provider weights with inherited outer weights/current default alphas; actual availability is explicit",
                "weight_calibration_candidates": [provider for provider, data in removal[best].items() if data["R@20_sum_delta"] > 0],
                "weight_calibration_caveat": "Frozen-contribution removal is a diagnostic hypothesis; no weights were tuned or validated out of sample."}
    if best_comparison:
        best_r20 = best_comparison["metrics"]["R@20"]
        decision.update(
            evidence="positive_cohort_R20_interval" if best_r20["bootstrap"]["percentile_95_ci"][0] > 0 else "uncertain_cohort_gain",
            R20_regressions_preventing_unconditional_integration=best_r20["regressed_query_ids"],
            top1_regressions=best_comparison["metrics"]["R@1"]["regressed_query_ids"],
            warning="Winner and capability slices are exploratory on the same 113 queries; uncertainty is not adjusted for winner selection or multiple comparisons.")
    else:
        decision.update(evidence="no_alternative_wins_the_predeclared_global_order",
                        R20_regressions_preventing_unconditional_integration=[], top1_regressions=[])
    decision["requested_slice_R20_deltas"] = {
        name: (data["paired_vs_current"][best]["metrics"]["R@20"]["sum_delta"] if best != ARMS[0] else 0.0)
        for name, data in slices.items() if name.startswith("requested:")}
    decision["slice_regressions"] = [name for name, delta in decision["requested_slice_R20_deltas"].items() if delta < 0]
    if best == ARMS[0]:
        decision["benefit_scope"] = "no globally winning alternative under the declared selection order"
    elif best_comparison["metrics"]["R@20"]["sum_delta"] == 0:
        decision["benefit_scope"] = "rank-quality gain without a global R@20 gain"
    elif decision["slice_regressions"]:
        decision["benefit_scope"] = "aggregate R@20 gain with category regressions"
    else:
        decision["benefit_scope"] = "aggregate R@20 gain; overlapping category slices remain descriptive"
    summary = {"schema": "vecna82-packet-b-evaluation-v1", "policy": POLICY, "policy_sha256": digest_json(POLICY),
               "cohort": {"collected": 115, "scored": 113, "excluded": sorted(EXCLUDED)},
               "descriptive_best_global_arm": best, "decision": decision,
               "overall": overall, "paired_distinct_video": comparisons, "contribution_removal": removal,
               "provider_states": {provider: dict(collections.Counter(row["provider_diagnostics"][provider]["state"] for row in rows)) for provider in PROVIDERS},
               "candidate_generation_missing_video_query_ids": [row["query_id"] for row in rows if not row["target_video_in_provider_union"]],
               "latency": {arm: {clock: {"mean_ms": statistics.fmean(row["arms"][arm][clock] for row in rows) / 1e6,
                                         "p50_ms": percentile([row["arms"][arm][clock] for row in rows], .5) / 1e6,
                                         "p95_ms": percentile([row["arms"][arm][clock] for row in rows], .95) / 1e6}
                                  for clock in ("cpu_ns", "wall_ns")} for arm in ARMS},
               "contracts": {
                   "distinct_video": "Fuse frame hits, retain100 frames, then first unique video; primary Packet B layer.",
                   "frame_position_video": "Correct video at original frame-candidate positions, with duplicates; comparable unit to Packet C.",
                   "frozen_frame_range_event": "Pinned mixed historical range/provisional TRAKE/P3 target scorer, frame-only input; no timeline manufacture.",
                   "median_rank": "Both median among observed ranks within20 and median across the retained list are reported; misses are censored and counted separately.",
                   "truth": "Six historical TRAKE rows use provisional submission anchors; P3 source-text targets remain provisional. Not organizer gold.",
                   "simple_visual_slice": "Explicit proxy: visual tags without OCR/ASR or temporal tags. Existing annotations do not prove causal mechanisms.",
                   "uncertainty": "Ordinary paired-query bootstrap, seed82, 10000resamples. Shared videos/templates may violate independent-query assumptions; no held-out confirmation.",
                   "diagnoses": "Only candidate absence, rank changes and contribution effects are established. Outlier/semantic/extraction causes remain hypotheses without content inspection.",
               }, "transform_proof": transform_proof, "source_provenance": provenance,
               "evaluator_sha256": digest_bytes(Path(__file__).read_bytes())}
    for name, payload in (("summary.json", summary), ("slices.json", slices), ("policy.json", POLICY)):
        (outdir / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (outdir / "per_query.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows), encoding="utf-8")
    (outdir / "REPORT.md").write_text(render_report(summary), encoding="utf-8")
    return summary


def render_report(summary):
    best = summary["descriptive_best_global_arm"]
    lines = ["# Packet B fusion study", "", f"Descriptive global winner: `{best}`. Production integration remains off.", "",
             "115 queries were collected with exact main-transform replay; the pinned mapping scores113 and excludes p0_q15/p3_q09. The primary experiment assigns nonzero weights to four providers; actual availability remains explicit. Its top100 raw-provider surface is distinct from the historical UI pool and preserves native quote eligibility.", "",
             "| Arm | Video R@1 | R@5 | R@10 | R@20 | MRR@20 | Median observed retained rank |", "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, value in summary["overall"]["distinct_video"].items():
        metrics = value["metrics"]
        values = [f"{metrics[f'R@{k}']['sum']:g}/113" for k in KS]
        lines.append(f"| {arm} | " + " | ".join(values) + f" | {metrics['MRR@20']['mean']:.6f} | {value['median_correct_rank_observed_in_retained_list']} |")
    lines += ["", "Primary video ranks collapse duplicate videos after retaining100 fused frames. Separate frame-position video and frozen range/event scores are retained in summary.json so comparisons with Packet C do not mix ranking units.", "",
              "| Alternative vs current | R@20 rescues / regressions | R@20 delta (95% paired interval) | MRR@20 delta (95% paired interval) |", "|---|---:|---|---|"]
    for arm, comparison in summary["paired_distinct_video"]["fusion_current_control"].items():
        rec, mrr = comparison["metrics"]["R@20"], comparison["metrics"]["MRR@20"]
        def fmt(value):
            low, high = value["bootstrap"]["percentile_95_ci"]
            return f"{value['mean_delta']:+.4f} [{low:+.4f}, {high:+.4f}]"
        lines.append(f"| {arm} | {rec['improved_count']} / {rec['regressed_count']} | {fmt(rec)} | {fmt(mrr)} |")
    decision = summary["decision"]
    lines += ["", f"Evidence classification: `{decision['evidence']}`. Winner selection and capability slices use the same cohort; intervals are descriptive and unadjusted for selection/multiplicity.", "",
              "Benefit scope: " + decision["benefit_scope"] + ".", "",
              "Winner R@20 regressions: " + (", ".join(decision["R20_regressions_preventing_unconditional_integration"]) or "none") + ".",
              "Winner top1 regressions: " + (", ".join(decision["top1_regressions"]) or "none") + ".", "",
              "Provider contribution/removal evidence, full paired IDs, normalization diagnostics and category slices are retained. Removal keeps the normalizers and candidate union fixed; it suggests hypotheses without fitting weights. Candidate absence is a mechanical diagnosis; semantic, OCR/ASR extraction and outlier explanations remain unverified unless separately inspected.", "",
              "Six historical TRAKE rows use provisional submission anchors; P3 truth remains source-text provisional. No ordinary organizer-certified temporal metric is implied. No production retrieval, model training or corpus embeddings were changed.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--collection-manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--outdir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    summary = evaluate(root, args.rankings, args.collection_manifest,
                       args.config or root / "outputs/fusion/frozen_config.json",
                       args.queries or root / "outputs/fusion/queries.jsonl",
                       args.outdir or root / "outputs/fusion/evaluation")
    print(json.dumps({"cohort": summary["cohort"], "decision": summary["decision"]}, indent=2))


if __name__ == "__main__":
    main()
