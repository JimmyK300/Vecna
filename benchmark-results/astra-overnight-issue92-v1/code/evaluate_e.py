"""Exact parent replay then frozen E1; all admission rankings saved before truth loads."""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent / "astra-retrieval-rd-v1"
sys.path.insert(0, str(PARENT / "code"))
from fusion_study import validate_row, current_scores, _rank, digest_bytes, digest_json
from analyze_fusion_headroom import PINNED, RAW_SHA, MANIFEST_SHA, RUN_ID, coverage
from analyze_reranker import read_json, read_jsonl, unique_index, load_scorer, paired_bootstrap
from evaluate_fusion_study import score_arm, aggregate, paired, LAYERS
from admission import balanced_admission


def write(path, value, lines=False):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        if lines:
            for row in value:
                f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        else:
            f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    out = ROOT / "outputs" / "packet-e"
    out.mkdir(parents=True, exist_ok=False)
    pins = {**PINNED,
        "outputs/fusion/capture-full115-v1/provider_rankings.jsonl": RAW_SHA,
        "outputs/fusion/capture-full115-v1/collection_manifest.json": MANIFEST_SHA,
        "outputs/fusion/evaluation/study_results.jsonl": "ba47bd96eb842d0bb57811e247cbd2ea29de8794c5dd3b289dce24a3032c10b1"}
    for name, sha in pins.items():
        assert digest_bytes((PARENT / name).read_bytes()) == sha, name
    write(ROOT / "control_manifest.json", {"parent_commit": read_json(ROOT / "config.json")["parent_commit"],
        "parent_root": str(PARENT), "sha256": pins, "exclusions": ["p0_q15", "p3_q09"], "run_identity": RUN_ID})
    config = read_json(PARENT / "outputs/fusion/frozen_config.json")
    raw = unique_index(read_jsonl(PARENT / "outputs/fusion/capture-full115-v1/provider_rankings.jsonl"))
    study = unique_index(read_jsonl(PARENT / "outputs/fusion/evaluation/study_results.jsonl"))
    assert set(raw) == set(study) and len(raw) == 115
    results = []
    for qid in sorted(raw):
        row = raw[qid]
        assert row["run_identity_sha256"] == RUN_ID
        assert study[qid]["provider_input_sha256"] == digest_json(row)
        maps = validate_row(row, config)
        order = row["candidate_tie_order"]
        start = time.perf_counter_ns()
        scores, contributions = current_scores(maps, order, config)
        cf, cv = _rank(scores, contributions, order, config)
        control_ns = time.perf_counter_ns() - start
        saved = study[qid]["arms"]["fusion_current_control"]
        assert cf == saved["frames"] and cv == saved["videos"]
        start = time.perf_counter_ns()
        es, ec = current_scores(maps, order, config)
        admitted = balanced_admission(row)
        membership = set(admitted)
        ef, ev = _rank(es, ec, [fid for fid in order if fid in membership], config)
        arm_ns = time.perf_counter_ns() - start
        assert len(ef) == len(cf) == min(100, len(order))
        assert all(f["score"] == scores[f["frame_id"]] for f in ef)
        results.append({"query_id": qid, "input_sha256": digest_json(row), "admission_order": admitted,
            "membership_changed": membership != {f["frame_id"] for f in cf},
            "arms": {"control": {"frames": cf, "videos": cv}, "e1": {"frames": ef, "videos": ev}},
            "same_session_wall_ns": {"control": control_ns, "e1": arm_ns},
            "candidate_union_count": len(order)})
    assert any(r["membership_changed"] for r in results), "no changed sets"
    write(out / "rankings.jsonl", results, True)
    # Only now open immutable evaluation truth.
    truth = unique_index(read_jsonl(PARENT / "inputs/canonical_truth.jsonl"))
    assert set(truth) == set(raw)
    assert {q for q,t in truth.items() if not t["scoreable"]} == {"p0_q15", "p3_q09"}
    scorer = load_scorer(PARENT / "reference/evaluate_reranker_fusion.py")
    rows = []
    for result in results:
        qid = result["query_id"]
        target = truth[qid]
        assert target["query"] == raw[qid]["query_text"]
        if not target["scoreable"]:
            continue
        rows.append({"query_id": qid, "phase": target["canonical_round"], "task_type": target["task_type"],
            "truth_tier": target["truth_tier"],
            "arms": {arm: score_arm(r["frames"], r["videos"], target, scorer) for arm,r in result["arms"].items()},
            "coverage": {arm: coverage(r["frames"], target, scorer) for arm,r in result["arms"].items()}})
    assert len(rows) == 113
    write(out / "per_query.jsonl", rows, True)
    metrics = {layer: {arm: aggregate(rows, layer, arm) for arm in ("control", "e1")} for layer in LAYERS}
    assert metrics["distinct_video"]["control"]["metrics"]["R@20"]["sum"] == 87
    summary = {"cohort": {"collected": 115, "scored": 113}, "metrics": metrics,
        "paired": {layer: paired(rows, layer, "e1", "control", bootstrap=True) for layer in LAYERS}, "coverage": {}}
    for field in ("all_required_targets_present", "target_coverage", "accepted_video_present"):
        before = [r["coverage"]["control"][field] for r in rows]
        after = [r["coverage"]["e1"][field] for r in rows]
        deltas = [b-a for a,b in zip(before, after)]
        summary["coverage"][field] = {"control_sum": sum(before), "e1_sum": sum(after),
            "control_mean": statistics.fmean(before), "e1_mean": statistics.fmean(after),
            "rescues": [r["query_id"] for r,d in zip(rows,deltas) if d>0],
            "regressions": [r["query_id"] for r,d in zip(rows,deltas) if d<0],
            "bootstrap": paired_bootstrap(deltas,82,10000)}
    complete = summary["coverage"]["all_required_targets_present"]
    frac = summary["coverage"]["target_coverage"]["bootstrap"]["mean_delta"]
    video = summary["coverage"]["accepted_video_present"]
    positive = len(complete["rescues"])>=2 and not complete["regressions"] and frac>0 and not video["regressions"]
    negative = not complete["rescues"] or (frac<=0 and bool(complete["regressions"]))
    summary["verdict"] = "POSITIVE" if positive else "NEGATIVE" if negative else "INCONCLUSIVE"
    summary["selected_for_next_family"] = "e1" if positive else "control"
    summary["workload"] = {"new_provider_calls": 0, "new_inference_calls": 0, "query_variants": 0,
        "queries_replayed": 115, "max_admitted_frames": 100, "membership_changed_queries": sum(r["membership_changed"] for r in results),
        "same_session_wall_ns_total": {arm: sum(r["same_session_wall_ns"][arm] for r in results) for arm in ("control","e1")}}
    summary["slices"] = {f"{field}:{value}": {layer: {arm: aggregate([r for r in rows if r[field]==value],layer,arm) for arm in ("control","e1")} for layer in LAYERS}
        for field in ("phase","task_type","truth_tier") for value in sorted({r[field] for r in rows})}
    write(out / "summary.json", summary)
    write(out / "hashes.json", {str(p.relative_to(ROOT)): digest_bytes(p.read_bytes()) for p in list((ROOT/"code").glob("*.py"))+[ROOT/"config.json",ROOT/"control_manifest.json",out/"rankings.jsonl",out/"per_query.jsonl",out/"summary.json"]})
    print(json.dumps({k:summary[k] for k in ("verdict","coverage","workload")},indent=2))


if __name__ == "__main__":
    main()
