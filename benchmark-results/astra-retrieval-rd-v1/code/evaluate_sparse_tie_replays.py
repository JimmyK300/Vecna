#!/usr/bin/env python3
"""Score three predeclared, retrieval-free main-method tie replays."""
import argparse
import json
from pathlib import Path

from analyze_reranker import load_scorer, read_json, read_jsonl, score_frozen, unique_index
from collect_sparse_visibility import digest, dump
from evaluate_sparse_visibility import require, verify_capture
from preflight import TRUTH_SHA256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    capture = root / "outputs/source-visibility/sparse-v1"
    manifest, _, _, captured, provenance = verify_capture(root, capture)
    out = root / "outputs/source-visibility/tie-replay-v1"
    docs = {seed: read_json(out / f"seed-{seed}.json") for seed in (0, 1, 82)}
    for seed, doc in docs.items():
        require(doc["python_hash_seed"] == str(seed) and doc["rankings_sha256"] == manifest["rankings_sha256"] and doc["row_count"] == 38, "Unexpected tie replay identity")
        require(doc["ground_truth_read"] is False and doc["network_calls"] == 0 and doc["models_loaded"] is False, "Replay isolation declarations differ")
        require(doc["code_identity"]["selected_ast_sha256"] == manifest["code_identity"]["selected_ast_sha256"], "Replay main source differs")
        require([(r["channel"], r["query_id"]) for r in doc["rows"]] == [(r["channel"], r["query_id"]) for r in captured], "Replay sample order differs")
    truth_path = root / "inputs/canonical_truth.jsonl"
    require(digest(truth_path.read_bytes()) == TRUTH_SHA256, "Canonical truth checksum differs")
    truth = unique_index(read_jsonl(truth_path))
    scorer = load_scorer(root / "reference/evaluate_reranker_fusion.py")
    rows = []
    for i, capture_row in enumerate(captured):
        by_id = {h["frame_id"]: h for h in capture_row["raw_hits"]}
        orders = {"host": capture_row["effective_frame_order"], **{str(seed): doc["rows"][i]["effective_frame_order"] for seed, doc in docs.items()}}
        scores = {}
        for label, order in orders.items():
            require(len(order) == len(set(order)) and set(order) == set(orders["host"]), "Replay changed eligible candidate membership")
            require([by_id[f]["bm25_score"] for f in order] == [by_id[f]["bm25_score"] for f in orders["host"]], "Replay altered nontied score order")
            items = [{"rank": rank, "video_id": by_id[fid]["video_id"], "frame_id": by_id[fid]["frame_idx"]} for rank, fid in enumerate(order, 1)]
            scores[label] = score_frozen(items, truth[capture_row["query_id"]], scorer, depth=100)
        rows.append({"query_id": capture_row["query_id"], "channel": capture_row["channel"],
                     "truth_tier": truth[capture_row["query_id"]]["truth_tier"], "scores": scores,
                     "distinct_effective_orders_across_host_and_seeds": len({tuple(order) for order in orders.values()}),
                     "equal_scores_and_membership_preserved": True})
    totals = {}
    for channel in ("ocr", "asr"):
        cohort = [r for r in rows if r["channel"] == channel]
        totals[channel] = {label: {"range_or_event_R@1": sum(r["scores"][label]["metrics"]["R@1"] for r in cohort),
                                  "range_or_event_R@5": sum(r["scores"][label]["metrics"]["R@5"] for r in cohort),
                                  "range_or_event_R@20": sum(r["scores"][label]["metrics"]["R@20"] for r in cohort),
                                  "MRR@20_mean": sum(r["scores"][label]["metrics"]["MRR@20"] for r in cohort) / len(cohort)} for label in ("host", "0", "1", "82")}
    proof = {"schema": "vecna82-sparse-tie-proof-v1", "predeclared_seeds": [0, 1, 82], **provenance,
             "replay_sha256": {str(seed): digest((out / f"seed-{seed}.json").read_bytes()) for seed in docs},
             "truth_sha256": TRUTH_SHA256, "evaluator_sha256": digest(Path(__file__).read_bytes()),
             "query_channel_count": len(rows), "rows_with_process_seed_order_variation": sum(r["distinct_effective_orders_across_host_and_seeds"] > 1 for r in rows),
             "all_candidate_membership_and_score_sequences_preserved": True, "totals": totals, "rows": rows,
             "interpretation": "Observed current-main order depends on Python string hash seed within exact-score ties. This is reproducibility evidence, not a seeded retrieval arm or a tuned seed recommendation."}
    dump(out / "tie_proof.json", proof)
    lines = ["# Current-main text ranking tie proof", "",
             "The completed 38-row BM25 responses were replayed through the same pinned main text method in three local processes with predeclared PYTHONHASHSEED=0,1,82. Replays read no truth, ran no models and made no network/retrieval calls. Scoring joined unchanged canonical truth after these outputs were frozen.", "",
             f"All {proof['rows_with_process_seed_order_variation']} query/channel rows have different effective orders across the host and these seeds. Every replay preserves the identical candidate membership and complete BM25 score sequence. Main builds a frame-ID set, iterates it into results, and sorts by final score alone; equal-score groups therefore retain process-dependent set order.", "",
             "| Channel | Order | Frozen range/event R@1 | R@5 | R@20 | MRR@20 |", "|---|---|---:|---:|---:|---:|"]
    for channel, entries in totals.items():
        for label, value in entries.items():
            lines.append(f"| {channel.upper()} | {label} | {value['range_or_event_R@1']:g} | {value['range_or_event_R@5']:g} | {value['range_or_event_R@20']:g} | {value['MRR@20_mean']:.6f} |")
    lines += ["", "The numbers describe this fixed diagnostic sample and its frozen truth, including provisional P3 rows. They do not select a preferred seed or claim a retrieval improvement. A stable tie policy would improve repeatability; its choice and resulting ranking change require explicit review. No production ranking code was changed here.", ""]
    (out / "TIE_PROOF.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"rows_with_order_variation": proof["rows_with_process_seed_order_variation"], "totals": totals}, indent=2))


if __name__ == "__main__":
    main()
