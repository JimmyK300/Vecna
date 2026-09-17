import statistics
from evaluate_e import ROOT, PARENT, write
from analyze_reranker import read_json, read_jsonl, unique_index, load_scorer, paired_bootstrap
from analyze_fusion_headroom import coverage
from evaluate_fusion_study import score_arm, aggregate, paired, LAYERS


def evaluate(rankings, out, arm):
    # Save blind rankings before loading truth.
    write(out / "rankings.jsonl", rankings, True)
    truth = unique_index(read_jsonl(PARENT / "inputs/canonical_truth.jsonl"))
    scorer = load_scorer(PARENT / "reference/evaluate_reranker_fusion.py")
    rows = []
    names = ("control", arm)
    for result in rankings:
        qid = result["query_id"]
        target = truth[qid]
        if not target["scoreable"]:
            continue
        rows.append({"query_id": qid, "truth_tier":target["truth_tier"], "task_type":target["task_type"],
            "arms": {a: score_arm(result["arms"][a]["frames"],result["arms"][a]["videos"],target,scorer) for a in names},
            "coverage": {a: coverage(result["arms"][a]["frames"],target,scorer) for a in names}})
    assert len(rows)==113
    write(out / "per_query.jsonl", rows, True)
    summary={"metrics": {layer:{a:aggregate(rows,layer,a) for a in names} for layer in LAYERS},
        "paired": {layer:paired(rows,layer,arm,"control",bootstrap=True) for layer in LAYERS}, "coverage":{}}
    for field in ("all_required_targets_present","target_coverage","accepted_video_present"):
        b=[r["coverage"]["control"][field] for r in rows]
        a=[r["coverage"][arm][field] for r in rows]
        d=[y-x for x,y in zip(b,a)]
        summary["coverage"][field]={"control_sum":sum(b),"arm_sum":sum(a),"control_mean":statistics.fmean(b),"arm_mean":statistics.fmean(a),
            "rescues":[r["query_id"] for r,v in zip(rows,d) if v>0],"regressions":[r["query_id"] for r,v in zip(rows,d) if v<0],
            "bootstrap":paired_bootstrap(d,82,10000)}
    p=summary["paired"]["distinct_video"]["metrics"]
    target_delta=summary["coverage"]["all_required_targets_present"]["bootstrap"]["mean_delta"]
    positive=p["R@20"]["mean_delta"]>0 and p["MRR@20"]["mean_delta"]>=0 and target_delta>=0
    negative=p["R@20"]["mean_delta"]<0 or target_delta<0
    summary["verdict"]="POSITIVE" if positive else "NEGATIVE" if negative else "INCONCLUSIVE"
    summary["promoted"]=positive
    return summary
