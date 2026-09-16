#!/usr/bin/env python3
"""Reproduce saved-set coverage headroom; this constructs no admission arm.

The first-unique-video layer is Packet B's analysis projection. These counts do
not establish a serving defect or a loss in historical Packet C's timelines.
"""
from __future__ import annotations
import argparse
import json
import statistics
from pathlib import Path
from analyze_reranker import EXCLUDED, load_scorer, read_json, read_jsonl, score_frozen, score_video, unique_index
from fusion_study import ContractError, PROVIDERS, _rank, current_scores, digest_bytes, digest_json, nominal_weights, run_identity_digest, validate_config, validate_row

RUN_ID = "f0d32893564111064d47f6f2f72f7b03dbb14ebbfbb3d05c48e49e30ef165755"
PINNED = {
    "code/analyze_reranker.py": "2b9b2624fda6582c1ba894ecb8ec39e90b27d9d6258f8c75676773bb36bd2bb1",
    "code/fusion_study.py": "57ded10b78c0a6649008d15e61882e3b52d2eb0b5cf63b57a7133a6a9da2a292",
    "outputs/fusion/frozen_config.json": "ff7a6f817579a2ba65572734016d51164f454a9d5012177841a458bbdca34b1a",
    "outputs/fusion/queries.jsonl": "3b91dfe26a893192a497a964d3a9ea5f50c595fdaabad000cbc60fc602be0d1a",
    "inputs/canonical_truth.jsonl": "63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f",
    "reference/evaluate_reranker_fusion.py": "82cbc5d7f5b6309f747165f8f278d4c3b66e9db83092c1808d2f72d1f8e76316",
}
RAW_SHA = "d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82"
MANIFEST_SHA = "01333a2ce910605b537a90aa6897938103aaf1728048d216af350d26bde756d8"
LAYERS = ("active_provider_union", "current_pre_collapse100", "first_video_analysis_representatives")


def require(condition, message):
    if not condition:
        raise ContractError(message)


def file_proof(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": digest_bytes(data)}


def coverage(items, truth, scorer):
    # Rank positions do not affect set membership; override inherited ranks so
    # depth includes every element, including provider-union elements after100.
    ranked = [{**item, "rank": rank} for rank, item in enumerate(items, 1)]
    frozen = score_frozen(ranked, truth, scorer, depth=len(ranked))
    bits = [rank is not None for rank in frozen["target_first_ranks"]]
    return {
        "candidate_count": len(ranked),
        "accepted_video_present": score_video(ranked, truth, scorer, depth=len(ranked))["first_success_rank"] is not None,
        "target_present": bits,
        "required_target_count": len(bits),
        "present_target_count": sum(bits),
        "target_coverage": frozen["target_coverage_at_depth"],
        "all_required_targets_present": frozen["all_required_targets_present"],
    }


def aggregate(rows, layer):
    values = [row["layers"][layer] for row in rows]
    return {
        "queries": len(values),
        "video_queries": sum(value["accepted_video_present"] for value in values),
        "complete_target_queries": sum(value["all_required_targets_present"] for value in values),
        "mean_target_coverage": statistics.fmean(value["target_coverage"] for value in values),
    }


def analyze(root, rankings, collection_manifest, study_path, summary_path, output):
    require(not output.exists(), "headroom output exists; use a fresh immutable path")
    proof = {}
    for name, expected in PINNED.items():
        proof[name] = file_proof(root / name)
        require(proof[name]["sha256"] == expected, "pinned source/input differs: " + name)
    raw_proof, manifest_proof = file_proof(rankings), file_proof(collection_manifest)
    require(raw_proof["sha256"] == RAW_SHA, "not the exact frozen raw capture")
    require(manifest_proof["sha256"] == MANIFEST_SHA, "not the exact frozen collection manifest")
    summary, manifest = read_json(summary_path), read_json(collection_manifest)
    config = validate_config(read_json(root / "outputs/fusion/frozen_config.json"))
    require(manifest["status"] == "complete" and manifest["rows_written"] == 115, "incomplete capture")
    require(run_identity_digest(manifest) == manifest["run_identity_sha256"] == RUN_ID, "run identity mismatch")
    study_proof = file_proof(study_path)
    transform_proof = summary["transform_proof"]
    require(transform_proof["output_sha256"] == study_proof["sha256"], "summary/study hash mismatch")
    require(transform_proof["run_identity_sha256"] == RUN_ID and transform_proof["rankings_sha256"] == RAW_SHA, "foreign transform inputs")
    require(transform_proof["config_sha256"] == digest_json(config), "foreign transform configuration")
    require(transform_proof["queries"] == 115 and transform_proof["ground_truth_read"] is False, "incomplete/nonblind transform")
    require(summary["cohort"] == {"collected": 115, "scored": 113, "excluded": sorted(EXCLUDED)}, "cohort differs")
    require(summary["descriptive_best_global_arm"] == "fusion_current_control", "this diagnostic names the globally selected current control")
    truth = unique_index(read_jsonl(root / "inputs/canonical_truth.jsonl"))
    raw, study = unique_index(read_jsonl(rankings)), unique_index(read_jsonl(study_path))
    require(len(truth) == 115 and set(raw) == set(study) == set(truth), "not the exact115-query join")
    require({qid for qid, row in truth.items() if not row["scoreable"]} == EXCLUDED, "scoreable mapping differs")
    scorer = load_scorer(root / "reference/evaluate_reranker_fusion.py")
    active = [name for name in PROVIDERS if nominal_weights(config)[name] > 0]
    require(active == ["qwen", "siglip", "ocr_sparse", "asr_sparse"], "active provider set changed")
    rows = []
    for qid in sorted(truth):
        target, exported, fused = truth[qid], raw[qid], study[qid]
        require(target["query"] == exported["query_text"], "canonical query text mismatch")
        require(exported["query_text_sha256"] == digest_bytes(target["query"].encode("utf-8")), "query hash mismatch")
        require(exported["run_identity_sha256"] == fused["run_identity_sha256"] == RUN_ID, "mixed query identities")
        require(fused["provider_input_sha256"] == digest_json(exported), "study row not bound to raw row")
        require(fused["query_text_sha256"] == exported["query_text_sha256"], "study query hash mismatch")
        maps = validate_row(exported, config)
        order = exported["candidate_tie_order"]
        scores, contributions = current_scores(maps, order, config)
        frames, videos = _rank(scores, contributions, order, config)
        control = fused["arms"]["fusion_current_control"]
        require(frames == control["frames"] and videos == control["videos"], "current saved ranking does not replay")
        union = {item["frame_id"]: item for provider in active for item in exported["providers"][provider]["hits"]}
        require(set(union) == set(order) and len(union) == len(order), "active union/tie-order mismatch")
        require({item["frame_id"] for item in frames} <= set(union), "retained frames outside union")
        if not target["scoreable"]:
            continue
        layers = {
            "active_provider_union": coverage([union[fid] for fid in order], target, scorer),
            "current_pre_collapse100": coverage(frames, target, scorer),
            "first_video_analysis_representatives": coverage(videos, target, scorer),
        }
        provider_coverage = {provider: coverage(exported["providers"][provider]["hits"], target, scorer) for provider in active}
        bits = layers["active_provider_union"]["target_present"]
        require(bits == [any(provider_coverage[p]["target_present"][i] for p in active) for i in range(len(bits))], "provider target OR differs from union")
        previous = bits
        for layer in LAYERS[1:]:
            current = layers[layer]["target_present"]
            require(len(current) == len(previous) and all(not present or previous[i] for i, present in enumerate(current)), "target presence nesting violated")
            previous = current
        rows.append({
            "query_id": qid, "query_text_sha256": exported["query_text_sha256"],
            "run_identity_sha256": RUN_ID, "phase": target["canonical_round"], "task_type": target["task_type"],
            "truth_tier": target["truth_tier"], "layers": layers, "providers": provider_coverage,
        })
    require(len(rows) == 113, "not113 scored headroom rows")
    def ids(predicate):
        return [row["query_id"] for row in rows if predicate(row["layers"])]
    complete = ids(lambda x: x[LAYERS[0]]["all_required_targets_present"] and not x[LAYERS[1]]["all_required_targets_present"])
    partial = ids(lambda x: x[LAYERS[0]]["target_coverage"] > x[LAYERS[1]]["target_coverage"] and not x[LAYERS[0]]["all_required_targets_present"])
    result = {
        "schema": "vecna82-saved-set-headroom-v1", "status": "complete", "new_arm_constructed": False,
        "scope": "Mechanical saved-set ceilings; analysis representatives do not establish serving or historical-C timeline loss.",
        "cohort": {"collected": 115, "scored": 113, "excluded": sorted(EXCLUDED)},
        "run_identity_sha256": RUN_ID, "control": "fusion_current_control", "active_providers": active,
        "inputs": {**proof, "rankings": raw_proof, "collection_manifest": manifest_proof,
                   "study": study_proof, "summary": file_proof(summary_path)},
        "code": file_proof(Path(__file__)),
        "overall": {layer: aggregate(rows, layer) for layer in LAYERS},
        "complete_target_admission_headroom_query_ids": complete,
        "additional_partial_target_admission_headroom_query_ids": partial,
        "video_admission_headroom_query_ids": ids(lambda x: x[LAYERS[0]]["accepted_video_present"] and not x[LAYERS[1]]["accepted_video_present"]),
        "video_absent_from_union_query_ids": ids(lambda x: not x[LAYERS[0]]["accepted_video_present"]),
        "incomplete_targets_in_union_query_ids": ids(lambda x: not x[LAYERS[0]]["all_required_targets_present"]),
        "analysis_projection_target_coverage_loss_query_ids": ids(lambda x: x[LAYERS[1]]["target_coverage"] > x[LAYERS[2]]["target_coverage"]),
        "analysis_projection_complete_target_loss_query_ids": ids(lambda x: x[LAYERS[1]]["all_required_targets_present"] and not x[LAYERS[2]]["all_required_targets_present"]),
        "per_query": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--collection-manifest", type=Path, required=True)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.root, args.rankings, args.collection_manifest, args.study, args.summary, args.output)
    print(json.dumps({key: result[key] for key in ("status", "cohort", "run_identity_sha256", "overall", "complete_target_admission_headroom_query_ids", "additional_partial_target_admission_headroom_query_ids")}, indent=2))


if __name__ == "__main__":
    main()
