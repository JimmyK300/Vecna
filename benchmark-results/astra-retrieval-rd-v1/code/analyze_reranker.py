#!/usr/bin/env python3
"""Audit retained reranker utility, without model inference or production changes.

Uses the pinned scorer in ../reference. Missing reranker hits are censored at
the retained top 20. All joins are explicit; no text/ordinal fuzzy matching.
Run: python code/analyze_reranker.py --root .
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import math
import random
import re
import statistics
from pathlib import Path

KS = (1, 5, 10, 20)
METRICS = tuple(f"R@{k}" for k in KS) + ("MRR@20",)
EXCLUDED = {"p0_q15", "p3_q09"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def unique_index(rows, field="query_id"):
    result = {}
    for row in rows:
        key = row[field]
        if key in result:
            raise ValueError(f"duplicate {field}: {key}")
        result[key] = row
    return result


def capability_key(truth):
    key = truth["canonical_source_key"]
    match = re.fullmatch(r"query-(p[012])-(\d+)-(?:kis|qa|trake)", key)
    if not match:
        match = re.fullmatch(r"(p3)_q(\d+)", key)
    if not match:
        raise ValueError(f"unknown capability join key: {key}")
    return f"{match[1]}-q{int(match[2])}"


def load_scorer(path):
    spec = importlib.util.spec_from_file_location("pinned_frozen_scorer", path)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    return scorer


def identity(item, scorer):
    return (scorer.norm_video(item["video_id"]), scorer.frame_id(item))


def validate_candidates(base_items, rerank_items, scorer):
    """Check each retained item against its exact original baseline rank.

    Video/frame identity alone is insufficient because timeline candidates can
    share their first frame. Preserve the exact ranking-unit lineage.
    """
    base = scorer.ranked(base_items)
    rerank = scorer.ranked(rerank_items)
    for label, rows, expected in (("baseline", base, len(base)), ("reranker", rerank, len(rerank))):
        if [r["_rank"] for r in rows] != list(range(1, expected + 1)):
            raise ValueError(f"{label} candidate ranks must be contiguous from 1")
    if len(base) > 100 or len(rerank) > 20:
        raise ValueError("unsupported retained ranking depth")
    by_rank = {item["_rank"]: item for item in base}
    restored, used = [], set()
    for item in rerank:
        original = item.get("original_baseline_rank")
        if original not in by_rank or original in used:
            raise ValueError(f"missing or duplicate original baseline rank: {original}")
        source = by_rank[original]
        if identity(source, scorer) != identity(item, scorer):
            raise ValueError(f"candidate identity mismatch at original rank {original}")
        used.add(original)
        fixed = dict(item)
        if "time_line" in source:
            fixed["time_line"] = source["time_line"]
        elif "timeline" in source:
            fixed["timeline"] = source["timeline"]
        restored.append(fixed)
    return restored


def score_frozen(items, truth, scorer, depth=20):
    """Maintain frozen mixed range/event semantics; extend only pool diagnostics.

    Historical TRAKE requires every event. P3 averages per-target recall and
    uses its first target for RR. The depth-100 extension is an explicitly
    labelled candidate-coverage diagnostic, never the official MRR score.
    """
    historical = truth.get("truth_tier") == "frozen_headless_benchmark_truth"
    rows = [r for r in scorer.ranked(items) if r["_rank"] <= depth]
    if historical:
        raw = scorer.historical_score(rows, truth)
        if truth["task_type"] == "trake":
            target_ranks = raw["event_first_ranks"]
            first = raw["first_all_events_rank"]
            recall = {f"R@{k}": float(bool(target_ranks) and all(scorer.hit_at(r, k) for r in target_ranks)) for k in KS}
            pool_coverage = float(bool(target_ranks) and all(r is not None for r in target_ranks))
        else:
            first = raw["first_correct_rank"]
            target_ranks = [first]
            recall = {f"R@{k}": float(scorer.hit_at(first, k)) for k in KS}
            pool_coverage = float(first is not None)
        family = "historical_trake" if truth["task_type"] == "trake" else "historical_range"
    else:
        targets = [target for group in truth.get("accepted_groups", []) for target in group]
        if not targets:
            raise ValueError(f"scored P3 row lacks targets: {truth['query_id']}")
        target_ranks = []
        for target in targets:
            target_ranks.append(next((r["_rank"] for r in rows if scorer.p3_target_hit(r, target)), None))
        first = scorer.first_rank(target_ranks)
        recall = {f"R@{k}": sum(scorer.hit_at(r, k) for r in target_ranks) / len(target_ranks) for k in KS}
        pool_coverage = sum(r is not None for r in target_ranks) / len(target_ranks)
        family = "p3_fractional_trake" if truth["task_type"] == "trake" else "p3_range"
    return {
        "family": family, "retained_depth": depth, "first_success_rank": first,
        "rank_status": "observed" if first is not None else f"not_observed_within_{depth}",
        "target_first_ranks": target_ranks, "metrics": {**recall, "MRR@20": scorer.reciprocal(first)},
        "target_coverage_at_depth": sum(r is not None for r in target_ranks) / len(target_ranks),
        "frozen_contract_coverage_at_depth": pool_coverage,
        "all_required_targets_present": bool(target_ranks) and all(r is not None for r in target_ranks),
    }


def score_video(items, truth, scorer, depth=20):
    videos = {scorer.norm_video(truth["accepted_video_id"])} if truth.get("accepted_video_id") else {
        scorer.norm_video(t["video_id"]) for g in truth.get("accepted_groups", []) for t in g
    }
    first = next((r["_rank"] for r in scorer.ranked(items) if r["_rank"] <= depth and scorer.norm_video(r["video_id"]) in videos), None)
    return {"first_success_rank": first, "retained_depth": depth,
            "rank_status": "observed" if first is not None else f"not_observed_within_{depth}",
            "metrics": {**{f"R@{k}": float(scorer.hit_at(first, k)) for k in KS}, "MRR@20": scorer.reciprocal(first)}}


def percentile(values, quantile):
    ordered = sorted(values)
    if not ordered:
        return None
    point = (len(ordered) - 1) * quantile
    lo, hi = math.floor(point), math.ceil(point)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (point - lo)


def paired_bootstrap(deltas, seed, resamples):
    if not deltas:
        return None
    rng = random.Random(seed)
    n = len(deltas)
    samples = [sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)]
    return {"mean_delta": statistics.fmean(deltas), "percentile_95_ci": [percentile(samples, .025), percentile(samples, .975)],
            "resamples": resamples, "seed": seed, "unit": "paired query", "method": "ordinary nonparametric percentile bootstrap"}


def exact_discordance_p(improved, regressed):
    n = improved + regressed
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(improved, regressed) + 1)) / (2 ** n)) if n else 1.0


def comparison(rows, layer, bootstrap=0, seed=82):
    result = {"count": len(rows), "baseline": {}, "reranker": {}, "paired": {}}
    for metric in METRICS:
        before = [r[layer]["baseline"]["metrics"][metric] for r in rows]
        after = [r[layer]["reranker"]["metrics"][metric] for r in rows]
        deltas = [b - a for a, b in zip(before, after)]
        for name, values in (("baseline", before), ("reranker", after)):
            result[name][metric] = {"mean": statistics.fmean(values) if values else None, "sum": sum(values)}
        improved = [r["query_id"] for r, d in zip(rows, deltas) if d > 1e-12]
        regressed = [r["query_id"] for r, d in zip(rows, deltas) if d < -1e-12]
        info = {"mean_delta": statistics.fmean(deltas) if deltas else None, "sum_delta": sum(deltas),
                "improved_count": len(improved), "regressed_count": len(regressed), "unchanged_count": len(rows)-len(improved)-len(regressed),
                "improved_query_ids": improved, "regressed_query_ids": regressed}
        if metric != "MRR@20" and all(x in (0, 1) for x in before + after):
            info["exact_two_sided_mcnemar_p"] = exact_discordance_p(len(improved), len(regressed))
        if bootstrap:
            info["bootstrap"] = paired_bootstrap(deltas, seed, bootstrap)
        result["paired"][metric] = info
    return result


def classification(row):
    if not row["scoreable"]:
        return {"retrieval_evidence": "unresolved_truth_gate", "semantic_cause": "unresolved", "reason": "No scoreable frozen truth; ranking change has no verified correctness label."}
    pool = row["candidate_pool"]
    if not row["baseline_candidate_count"]:
        evidence = "empty_candidate_pool"
    elif pool["video_first_rank_at_100"] is None:
        evidence = "accepted_video_absent_from_top100"
    elif not pool["all_required_targets_present"]:
        evidence = "required_range_or_events_missing_from_top100"
    else:
        evidence = "all_required_targets_available_in_top100"
    changes = []
    for layer in ("video", "frozen"):
        for k in KS:
            delta = row[layer]["reranker"]["metrics"][f"R@{k}"] - row[layer]["baseline"]["metrics"][f"R@{k}"]
            if delta:
                changes.append(f"{layer}_{'rescue' if delta > 0 else 'regression'}_at_{k}")
        rr_delta = row[layer]["reranker"]["metrics"]["MRR@20"] - row[layer]["baseline"]["metrics"]["MRR@20"]
        if rr_delta:
            changes.append(f"{layer}_mrr_{'improvement' if rr_delta > 0 else 'regression'}")
    if not changes:
        changes = ["rank_order_change_without_recall_change" if row["ranking_changed"] else "ranking_unchanged"]
    return {"retrieval_evidence": evidence, "observed_effects": changes, "semantic_cause": "unresolved_without_frame_or_clip_review",
            "capability_labels_are": "pre-existing query annotations, not diagnosed causes",
            "metadata_loss_effect": row["timeline_diagnostic"]["changes_frozen_metrics"]}


def summarize_latency(reranker_doc, logfile, cohort):
    rows = reranker_doc["per_query"]
    measured = [float(r["rerank_latency_ms"]) for r in rows]
    active = [float(r["rerank_latency_ms"]) for r in rows if r["reranked_candidates_top20"]]
    cohort_active = [float(r["rerank_latency_ms"]) for r in rows if r["query_id"] in cohort and r["reranked_candidates_top20"]]
    def stats(values):
        return {"count": len(values), "mean_ms": statistics.fmean(values), "p50_ms": percentile(values, .5),
                "p95_ms": percentile(values, .95), "min_ms": min(values), "max_ms": max(values), "sum_seconds": sum(values)/1000}
    text = logfile.read_text(encoding="utf-8")
    pattern = r"\[(\d+)/115\] Processing (p\d_q\d+) \(candidate count=(\d+)\)\.\.\.(.*?)(?=\n\[\d+/115\] Processing|\Z)"
    parsed = {}
    for _, query_id, count, chunk in re.findall(pattern, text, flags=re.S):
        latency = re.search(r"Rerank complete in ([\d.]+)s", chunk)
        parsed[query_id] = {"candidate_count": int(count), "printed_seconds": float(latency[1]) if latency else None}
    discrepancies = []
    for row in rows:
        logged = parsed.get(row["query_id"], {})
        if logged.get("printed_seconds") is not None and abs(logged["printed_seconds"] * 1000-row["rerank_latency_ms"]) > 5.001:
            discrepancies.append(row["query_id"])
    return {
        "all_exported_queries_including_one_empty_pool": stats(measured),
        "actual_nonempty_reranks": stats(active), "scoreable_nonempty_reranks": stats(cohort_active),
        "first_nonempty_query_ms": active[0], "subsequent_nonempty_queries": stats(active[1:]),
        "stored_summary_mean_ms": reranker_doc["qwen3_vl_reranker_top100"]["avg_rerank_latency_ms"],
        "stored_summary_matches_all115_mean_to_0_1ms": round(statistics.fmean(measured), 1) == reranker_doc["qwen3_vl_reranker_top100"]["avg_rerank_latency_ms"],
        "stored_summary_matches_nonempty_mean_to_0_1ms": round(statistics.fmean(active), 1) == reranker_doc["qwen3_vl_reranker_top100"]["avg_rerank_latency_ms"],
        "parsed_log_queries": len(parsed), "printed_completed_latencies": sum(x["printed_seconds"] is not None for x in parsed.values()),
        "log_json_discrepancy_query_ids": discrepancies,
        "load_duration_ms": None, "model_load_vs_steady_state": "Log states one model load before query loop, but has no timed load interval; first query is not a measured cold-load latency.",
        "measurement_scope": "Stored per-query rerank wall time for the 100-candidate input; no baseline search latency or end-to-end user latency recorded here.",
        "runtime_evidence": "stdout names AMD RX 6900 XT / DirectML. Comparison JSON reports repeat_interleave CPU fallback from a separately cited stderr log; not remeasured.",
        "quantiles": "linear interpolation at (n-1)*p",
    }


def audit_legacy_video_control(legacy, current_rows, truth, base, scorer):
    """Explain #79 video-control drift without substituting its candidate run."""
    previous = unique_index(legacy)
    current = unique_index([r for r in current_rows if r["scoreable"]])
    if set(previous) != set(current):
        raise ValueError("legacy/current video cohorts differ")
    comparisons, per_query = [], []
    for q in sorted(current):
        old = previous[q]
        # Score both old and current candidates against the identical canonical
        # video target; verify the legacy truth does not change this result.
        old_score = score_video(old["baseline_results"], truth[q], scorer)
        if old_score != score_video(old["baseline_results"], old, scorer):
            raise ValueError(f"legacy/canonical video truth differs: {q}")
        def candidate_signature(items):
            return [(identity(item, scorer), scorer.candidate_frames(item)) for item in scorer.ranked(items) if item["_rank"] <= 20]
        changed = candidate_signature(old["baseline_results"]) != candidate_signature(base[q]["candidates_top100"])
        comparisons.append({"query_id": q, "video": {"baseline": old_score, "reranker": current[q]["video"]["baseline"]}})
        per_query.append({"query_id": q, "legacy_baseline_source": old["baseline_source"], "baseline_candidate_order_or_identity_changed": changed,
                          "legacy_video_first_rank": old_score["first_success_rank"],
                          "current_video_first_rank": current[q]["video"]["baseline"]["first_success_rank"],
                          "video_metrics_changed": old_score["metrics"] != current[q]["video"]["baseline"]["metrics"]})
    raw = comparison(comparisons, "video")
    temporal = [r for r in current.values() if r["task_type"] == "trake"]
    return {"explanation": "Legacy #79 control candidates are 78 frozen_headless_vnext_scored_combined + 35 p3_qwen_only_v1. They differ from this packet's current Qwen-only export. Same canonical video targets and scoring definition reproduce both sets; do not pair the legacy baseline with this reranker.",
            "counts_by_legacy_source": dict(collections.Counter(r["baseline_source"] for r in legacy)),
            "top20_candidate_order_or_identity_changed_queries": sum(r["baseline_candidate_order_or_identity_changed"] for r in per_query),
            "identical_video_truth_and_metric_definition": True,
            "legacy_baseline": raw["baseline"], "current_baseline": raw["reranker"],
            "paired_current_minus_legacy": raw["paired"], "per_query": per_query,
            "exact8_temporal_query_ids": [r["query_id"] for r in temporal],
            "exact8_temporal_current_video": comparison(temporal, "video"),
            "exact8_temporal_current_frozen": comparison(temporal, "frozen")}


def verify_sources(root, paths):
    source_rows = read_json(root / "inputs/sources.json")
    by_local = {x["local"]: x for x in source_rows}
    verified = []
    for relative in paths:
        payload = (root / relative).read_bytes()
        sha = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
        expected = by_local[relative]["blob_sha"]
        if sha != expected:
            raise ValueError(f"Git blob mismatch: {relative}")
        verified.append({**by_local[relative], "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "git_blob_verified": True})
    return verified


def run(root, outdir, resamples=10000):
    root, outdir = Path(root).resolve(), Path(outdir).resolve()
    paths = [f"inputs/{name}" for name in ("canonical_truth.jsonl", "original_truth_ledger.jsonl", "historical_manifest.json",
             "qwen_only_top100.jsonl", "qwen3_vl_reranker_2b_top100.json", "comparison_qwen_vs_reranker.json", "reranker.stdout.log",
             "capability_p0.jsonl", "capability_p1.jsonl", "capability_p2.jsonl", "capability_p3.jsonl", "legacy_temporal_control_113.jsonl")] + ["reference/evaluate_reranker_fusion.py"]
    provenance = verify_sources(root, paths)
    scorer = load_scorer(root / "reference/evaluate_reranker_fusion.py")
    truth = unique_index(read_jsonl(root / "inputs/canonical_truth.jsonl"))
    old_truth = unique_index(read_jsonl(root / "inputs/original_truth_ledger.jsonl"))
    base = unique_index(read_jsonl(root / "inputs/qwen_only_top100.jsonl"))
    rerank_doc = read_json(root / "inputs/qwen3_vl_reranker_2b_top100.json")
    rerank = unique_index(rerank_doc["per_query"])
    stored = read_json(root / "outputs/control-reproduction/controls.json")
    stored_scores = unique_index(stored["per_query"])
    caps = unique_index([r for phase in range(4) for r in read_jsonl(root / f"inputs/capability_p{phase}.jsonl")])
    historical_records = read_json(root / "inputs/historical_manifest.json")["records"]
    hist = {(r["operational_phase"], r["raw_query_id"]): r for r in historical_records}
    if len(hist) != len(historical_records):
        raise ValueError("duplicate historical join key")
    if not len(truth) == 115 or not set(truth) == set(base) == set(rerank) == set(old_truth):
        raise ValueError("exports must have identical 115 unique query IDs")
    if {q for q, r in truth.items() if not r.get("scoreable")} != EXCLUDED:
        raise ValueError("unexpected excluded scoreability set")
    rows, proof, timeline_rows = [], [], []
    for query_id in sorted(truth):
        t, b, r = truth[query_id], base[query_id], rerank[query_id]
        if t["query"] != b["query"] or b["query"] != r["query"] or t["canonical_source_key"] != b["canonical_source_key"]:
            raise ValueError(f"query identity/text drift: {query_id}")
        cap = caps[capability_key(t)]
        if t["scoreable"] and t["canonical_round"] != "P3":
            h = scorer.join_historical(b, hist)
            if not h or any(t.get(k) != h.get(k) for k in ("accepted_video_id", "accepted_ranges", "trake_event_truth", "task_type")):
                raise ValueError(f"canonical and historical scoring truth differ: {query_id}")
        elif t["canonical_round"] == "P3":
            if any(t.get(k) != old_truth[query_id].get(k) for k in ("accepted_groups", "task_type", "scoreable")):
                raise ValueError(f"canonical and original P3 scoring truth differ: {query_id}")
        bi, ri = b["candidates_top100"], r["reranked_candidates_top20"]
        restored = validate_candidates(bi, ri, scorer)
        baseranks = [x.get("rank", i+1) for i, x in enumerate(bi)]
        baseline_top20 = [(i, identity(c, scorer)) for i, c in zip(baseranks, bi) if i <= 20]
        reranked_top20 = [(c["original_baseline_rank"], identity(c, scorer)) for c in scorer.ranked(ri)]
        changed = baseline_top20 != reranked_top20
        lost_timeline = sum(bool(source.get("time_line", source.get("timeline"))) and not bool(retained.get("time_line", retained.get("timeline")))
                            for source, retained in zip(restored, scorer.ranked(ri)))
        duplicated = len(bi)-len({identity(c, scorer) for c in bi})
        proof.append({"query_id": query_id, "baseline_candidates": len(bi), "retained_reranker_candidates": len(ri),
                      "verified_original_rank_identity_links": len(ri), "all_retained_candidates_in_baseline_pool": True,
                      "baseline_duplicate_video_frame_keys": duplicated,
                      "baseline_candidates_with_timeline": sum(bool(c.get("time_line", c.get("timeline"))) for c in bi),
                      "retained_candidates_losing_timeline": lost_timeline,
                      "retained_original_baseline_ranks": [c["original_baseline_rank"] for c in scorer.ranked(ri)]})
        row = {"query_id": query_id, "canonical_source_key": t["canonical_source_key"], "phase": t["canonical_round"],
               "task_type": t["task_type"], "truth_tier": t["truth_tier"], "scoreable": t["scoreable"],
               "effective_truth_basis": "+".join(sorted({e.get("truth_tier", "unspecified_event_truth") for e in t.get("trake_event_truth", [])})) or t["truth_tier"],
               "capability_source_query_id": cap["query_id"], "primary_challenge": cap["primary_challenge"],
               "capability_tags": cap["capability_tags"], "query_summary": cap["summary"],
               "baseline_candidate_count": len(bi), "retained_reranker_candidate_count": len(ri), "ranking_changed": changed,
               "baseline_top1": identity(bi[0], scorer) if bi else None, "reranker_top1": identity(ri[0], scorer) if ri else None,
               "timeline_diagnostic": {"retained_candidates_losing_timeline": lost_timeline, "changes_frozen_metrics": False}}
        if t["scoreable"]:
            row["frozen"] = {"baseline": score_frozen(bi, t, scorer), "reranker": score_frozen(ri, t, scorer)}
            row["video"] = {"baseline": score_video(bi, t, scorer), "reranker": score_video(ri, t, scorer)}
            row["matched_timeline"] = {"baseline": row["frozen"]["baseline"], "reranker": score_frozen(restored, t, scorer)}
            row["frame_only"] = {"baseline": score_frozen([{k: v for k, v in c.items() if k not in ("time_line", "timeline")} for c in bi], t, scorer), "reranker": row["frozen"]["reranker"]}
            pool = score_frozen(bi, t, scorer, 100)
            frame_pool = score_frozen([{k: v for k, v in c.items() if k not in ("time_line", "timeline")} for c in bi], t, scorer, 100)
            row["candidate_pool"] = {"video_first_rank_at_100": score_video(bi, t, scorer, 100)["first_success_rank"],
                                     "target_first_ranks_at_100": pool["target_first_ranks"],
                                     "all_required_targets_present": pool["all_required_targets_present"],
                                     "frozen_contract_coverage_at_100": pool["frozen_contract_coverage_at_depth"],
                                     "target_coverage_at_100": pool["target_coverage_at_depth"],
                                     "first_frame_only_coverage_at_100": frame_pool["frozen_contract_coverage_at_depth"],
                                     "coverage_ceiling_note": "Observed pool coverage, not reranker rank >20 or an achievable production oracle."}
            for layer in ("frozen", "video", "matched_timeline", "frame_only"):
                row[layer]["delta"] = {m: row[layer]["reranker"]["metrics"][m] - row[layer]["baseline"]["metrics"][m] for m in METRICS}
            row["timeline_diagnostic"]["changes_frozen_metrics"] = row["matched_timeline"]["reranker"]["metrics"] != row["frozen"]["reranker"]["metrics"]
            row["timeline_diagnostic"]["changes_baseline_metrics_if_frame_only"] = row["frame_only"]["baseline"]["metrics"] != row["frozen"]["baseline"]["metrics"]
            for arm in ("baseline", "reranker"):
                actual = row["frozen"][arm]["metrics"]
                expected = stored_scores[query_id][arm]
                if any(abs(actual[f"R@{k}"] - expected["recall"][f"R@{k}"]) > 1e-12 for k in KS) or abs(actual["MRR@20"]-expected["reciprocal_rank"]) > 1e-12:
                    raise ValueError(f"frozen scorer reproduction differs: {query_id} {arm}")
        row["classification"] = classification(row)
        rows.append(row)
        if proof[-1]["baseline_candidates_with_timeline"]:
            timeline_rows.append(row)
    scored = [r for r in rows if r["scoreable"]]
    if len(scored) != 113 or set(stored_scores) != {r["query_id"] for r in scored}:
        raise ValueError("expected exact 113-query scored join")
    overall = {layer: comparison(scored, layer, resamples if layer in ("video", "frozen") else 0) for layer in ("video", "frozen", "matched_timeline", "frame_only")}
    legacy_audit = audit_legacy_video_control(read_jsonl(root / "inputs/legacy_temporal_control_113.jsonl"), rows, truth, base, scorer)
    slices = {}
    for dimension in ("phase", "truth_tier", "effective_truth_basis", "task_type", "primary_challenge", "capability_tags", "score_family"):
        groups = collections.defaultdict(list)
        for row in scored:
            keys = row["capability_tags"] if dimension == "capability_tags" else [row["frozen"]["baseline"]["family"] if dimension == "score_family" else row[dimension]]
            for key in keys:
                groups[key].append(row)
        slices[dimension] = {key: {layer: comparison(value, layer) for layer in ("video", "frozen")} for key, value in sorted(groups.items())}
    classifications = collections.Counter(r["classification"]["retrieval_evidence"] for r in rows)
    metrics_changed = [r["query_id"] for r in scored if any(r["frozen"]["delta"].values()) or any(r["video"]["delta"].values())]
    timelines = {"status": "diagnostic_only; original frozen comparison remains authoritative",
                 "restoration": "Reattach original baseline time_line at verified original_baseline_rank; preserve the retained reranker order and its 20-row truncation.",
                 "affected_queries": [r["query_id"] for r in timeline_rows],
                 "reranker_metrics_changed_queries": [r["query_id"] for r in timeline_rows if r["timeline_diagnostic"]["changes_frozen_metrics"]],
                 "baseline_frame_only_metrics_changed_queries": [r["query_id"] for r in timeline_rows if r["timeline_diagnostic"].get("changes_baseline_metrics_if_frame_only")],
                 "per_query": timeline_rows}
    summary = {
        "schema": "vecna82/packet-c-retained-reranker-audit-v1", "cohort": {"exported": 115, "scored": 113, "excluded": sorted(EXCLUDED)},
        "contracts": {"video": "First candidate rank containing any accepted target video; candidate positions retain duplicates; not deduplicated-video ranking.",
                      "frozen": "72 historical ranges + 6 strict all-event TRAKE + 35 P3 source-text provisional targets (including 2 fractional TRAKE). QA scores retrieval location, not answer accuracy.",
                      "truth_status": "Frozen historical benchmark truth is a development control, not organizer gold; historical TRAKE windows use provisional submission anchors. effective_truth_basis slices expose these proxy tiers separately.",
                      "range_boundary": "inclusive", "p3_point_tolerance": "50 frames (25 FPS * 2 seconds), frozen setting, not video-specific measured FPS",
                      "retention": "114 reranker rows retain top20, one empty row; positions beyond20 unavailable and never imputed.",
                      "uncertainty": "Paired query bootstrap describes this 113-query cohort under query-resampling assumptions; shared videos/templates can violate independence. No held-out validation, no multiplicity-adjusted slice inference.",
                      "slices": "Capability join uses canonical phase and source query number, not reordered current query ordinal. Overlapping tags are descriptive and are not a deployable selection rule."},
        "verification": {"exact_113_join": True, "all_115_texts_match_between_truth_baseline_reranker": True,
                         "canonical_scoring_truth_matches_historical_and_original_p3": True,
                         "every_frozen_per_query_metric_matches_pinned_control_reproduction": True,
                         "all_retained_candidates_match_original_baseline_rank": True,
                         "verified_retained_candidate_links": sum(p["verified_original_rank_identity_links"] for p in proof)},
        "ranking_changes": {"all115_top20_order_changed": sum(r["ranking_changed"] for r in rows),
                            "all115_top1_identity_changed": sum(r["baseline_top1"] != r["reranker_top1"] for r in rows),
                            "scored113_any_reported_metric_changed": len(metrics_changed), "metric_changed_query_ids": metrics_changed},
        "overall": overall, "classifications": dict(classifications),
        "legacy_video_control_audit": {key: legacy_audit[key] for key in ("explanation", "counts_by_legacy_source", "top20_candidate_order_or_identity_changed_queries", "identical_video_truth_and_metric_definition", "legacy_baseline", "current_baseline")},
        "candidate_ceiling": {"video_present_in_top100_queries": sum(r["candidate_pool"]["video_first_rank_at_100"] is not None for r in scored),
                              "all_required_targets_present_in_top100_queries": sum(r["candidate_pool"]["all_required_targets_present"] for r in scored),
                              "frozen_coverage_sum_at100": sum(r["candidate_pool"]["frozen_contract_coverage_at_100"] for r in scored),
                              "empty_pool_query_ids": [r["query_id"] for r in scored if not r["baseline_candidate_count"]]},
        "recommendation": {"policy": "operator_opt_in_experimental", "always_on": False,
                           "reason": "R@20 gains coexist with R@1/R@10 regressions and small aggregate MRR change; roughly 28 seconds per nonempty rerank is a material interactive cost. Candidate and timeline evidence is incomplete beyond retained20.",
                           "conditional_automatic_policy": "Not justified by post-hoc capability slices; no truth-independent gate has held-out evidence.",
                           "next_bounded_work": "Preserve full candidate metadata and all100 scores in a future experiment; evaluate a preregistered latency budget and truth-independent trigger on held-out queries before enabling automatic reranking.",
                           "production_changes_in_this_packet": "none"},
    }
    latency = summarize_latency(rerank_doc, root / "inputs/reranker.stdout.log", {r["query_id"] for r in scored})
    if latency["log_json_discrepancy_query_ids"]:
        raise ValueError("latency stdout/JSON mismatch")
    outdir.mkdir(parents=True, exist_ok=True)
    for name, data in (("summary.json", summary), ("slices.json", slices), ("candidate_subset_proof.json", proof),
                       ("timeline_diagnostic.json", timelines), ("latency.json", latency), ("provenance.json", provenance),
                       ("legacy_video_control_audit.json", legacy_audit)):
        (outdir / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, data in (("per_query.jsonl", rows), ("changed_queries.jsonl", [r for r in rows if r["ranking_changed"]])):
        (outdir / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data), encoding="utf-8")
    report = render_report(summary, latency, slices, timelines)
    (outdir / "REPORT.md").write_text(report, encoding="utf-8")
    return summary


def render_report(summary, latency, slices, timeline):
    frozen, video = summary["overall"]["frozen"], summary["overall"]["video"]
    resamples = frozen["paired"]["R@1"]["bootstrap"]["resamples"]
    lines = ["# Packet C: retained Qwen3-VL reranker utility", "",
             "Recommendation: keep reranking experimental and operator opt-in. The retained result improves R@20 while regressing R@1/R@10; the MRR difference is small and latency is about 28 seconds per query. No automatic conditional gate has been validated.", "",
             "The exact 113-query join and every frozen per-query score reproduce. P0–P2 contain 72 accepted-range and 6 strict all-event TRAKE cases; P3 contains 35 provisional source-text cases, including 2 fractional TRAKE cases. Historical TRAKE windows are submission-anchor proxies; frozen benchmark truth is a development control, not organizer gold. Excluded: p0_q15 and p3_q09. QA measures retrieval location, not answer correctness.", "",
             "| Metric | Frozen baseline | Frozen reranker | Paired gain/loss queries | Delta, percentage points (95% bootstrap CI) |", "|---|---:|---:|---:|---:|"]
    for metric in METRICS:
        paired = frozen["paired"][metric]
        lo, hi = paired["bootstrap"]["percentile_95_ci"]
        display = lambda arm: f"{frozen[arm][metric]['mean']:.6f}" if metric == "MRR@20" else f"{frozen[arm][metric]['sum']:g}/113"
        lines.append(f"| {metric} | {display('baseline')} | {display('reranker')} | +{paired['improved_count']} / −{paired['regressed_count']} | {paired['mean_delta']*100:+.2f} [{lo*100:+.2f}, {hi*100:+.2f}] |")
    lines += ["", f"MRR deltas are shown ×100 in the last column; bootstrap uses {resamples:,} paired-query resamples, seed 82. These are descriptive uncertainty estimates for this cohort, with no held-out or multiplicity-adjusted claims. Shared videos and near-duplicate query templates may violate independent-query assumptions.", "",
              "| Diagnostic layer | Baseline R@1 / R@5 / R@10 / R@20 | Reranker R@1 / R@5 / R@10 / R@20 | Baseline → reranker MRR@20 |", "|---|---|---|---|"]
    for name, label in (("video", "Video presence, candidate positions"), ("frozen", "Frozen range/event contract"), ("matched_timeline", "Diagnostic: original timelines restored"), ("frame_only", "Diagnostic: first frame only in both arms")):
        value = summary["overall"][name]
        fmt = lambda arm: " / ".join(f"{value[arm][f'R@{k}']['sum']:g}" for k in KS)
        lines.append(f"| {label} | {fmt('baseline')} | {fmt('reranker')} | {value['baseline']['MRR@20']['mean']:.6f} → {value['reranker']['MRR@20']['mean']:.6f} |")
    lines += ["", "Video scoring accepts any target video at its candidate rank and keeps duplicates; it does not prove localization or ordered-event success.", "",
              "The older #79 video control used 78 historical Headless candidates plus 35 prior P3 Qwen candidates. With the identical video metric and truth, those inputs reproduce 57/70/76/83, whereas the current Qwen-only export gives 59/69/76/82. Candidate order or identity differs on 105/113 rows. This is an input-run difference, not a metric substitution; details are in legacy_video_control_audit.json. On the exact eight TRAKE cases, current video R@20 is 6/8 → 7/8 while frozen event success/recall remains zero in both arms.", "",
              f"Candidate audit: all {summary['verification']['verified_retained_candidate_links']} retained rows match the baseline pool at their exact original rank and video/frame identity. Only the top20 is retained despite the filename containing top100. Missing reranker targets are censored at20; the unavailable 21–100 positions are never reconstructed.", "",
              f"The baseline top100 contains the accepted video for {summary['candidate_ceiling']['video_present_in_top100_queries']}/113 queries and all required range/event targets for {summary['candidate_ceiling']['all_required_targets_present_in_top100_queries']}/113. An empty pool at p2_q17 is an upstream absence, not a reranking regression. Query-level pool diagnoses and every changed ranking are retained in per_query.jsonl and changed_queries.jsonl. Semantic causes remain unresolved without frame/clip review; capability tags are annotations rather than explanations.", "",
              "Six queries carry baseline timelines that the reranker export drops: " + ", ".join(timeline["affected_queries"]) + ". Timelines are restored solely for a matched-evidence diagnostic using exact original-rank links. This is not a production repair or a replacement for frozen controls.",
              "Restoration changes retained reranker metrics for: " + (", ".join(timeline["reranker_metrics_changed_queries"]) or "none") + ". Removing timelines from the baseline changes metrics for: " + (", ".join(timeline["baseline_frame_only_metrics_changed_queries"]) or "none") + ".", "",
              "In p3_q36 the baseline timeline hits the accepted range at rank1, while its first-frame-only rank is14. The retained reranker hits at rank2 in either diagnostic. Removing baseline evidence would flip this query's MRR regression into an improvement, so frozen and matched-timeline comparisons retain the original regression.", "",
              "| Phase | n | Frozen baseline → reranker R@20 | MRR change |", "|---|---:|---:|---:|"]
    for phase, value in slices["phase"].items():
        f = value["frozen"]
        lines.append(f"| {phase} | {f['count']} | {f['baseline']['R@20']['sum']:g} → {f['reranker']['R@20']['sum']:g} | {f['paired']['MRR@20']['mean_delta']:+.6f} |")
    active = latency["actual_nonempty_reranks"]
    lines += ["", "Capability, truth-tier, task-type and score-family slices are in slices.json. Canonical source numbers join the capability records; current query ordinals cannot be used after task-type regrouping. Overlapping capability slices are exploratory, with no oracle-based routing recommendation.", "",
              f"Latency: {active['count']} nonempty reranks average {active['mean_ms']/1000:.3f}s; p50 {active['p50_ms']/1000:.3f}s; p95 {active['p95_ms']/1000:.3f}s. All 115 exported rows include one zero-latency empty pool; their mean is {latency['all_exported_queries_including_one_empty_pool']['mean_ms']/1000:.3f}s. The stored 27,973.2ms average includes that empty pool. The first query takes {latency['first_nonempty_query_ms']/1000:.3f}s; subsequent nonempty queries average {latency['subsequent_nonempty_queries']['mean_ms']/1000:.3f}s. The log says the model loads once, but supplies no timed load interval, so cold-load overhead cannot be recovered. JSON timing agrees with the rounded stdout durations. These are rerank costs, not end-to-end or baseline-search costs.", "",
              "Next experiment: preserve all100 scores and original timelines, then preregister a latency budget and a truth-independent trigger for held-out evaluation. Existing post-hoc gains do not justify always-on deployment.", "",
              "Reproduce from the evidence packet root:", "", "```bash", "python code/analyze_reranker.py --root . --out-dir outputs/reranker --bootstrap-resamples 10000", "python -m unittest discover -s tests -p test_reranker_analysis.py -v", "```", "",
              "Inputs are Git-blob verified against inputs/sources.json; provenance.json records pinned commits and SHA-256. The pinned scorer and control reproduction remain separate. No weights, model calls or production defaults changed.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--bootstrap-resamples", type=int, default=10000)
    args = parser.parse_args()
    if args.bootstrap_resamples < 1:
        parser.error("bootstrap-resamples must be positive")
    summary = run(args.root, args.out_dir or args.root / "outputs/reranker", args.bootstrap_resamples)
    print(json.dumps({"verification": summary["verification"], "recommendation": summary["recommendation"]["policy"]}, indent=2))


if __name__ == "__main__":
    main()
