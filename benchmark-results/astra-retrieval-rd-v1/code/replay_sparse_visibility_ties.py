#!/usr/bin/env python3
"""Replay pinned main over frozen BM25 rows; no retrieval or truth access.

Set PYTHONHASHSEED before launching separate processes to inspect tie stability.
This reuses only the observed top100 response, without expanding the pool.
"""
import argparse
import copy
import json
import os
from pathlib import Path

from collect_sparse_visibility import capture_query, digest, dump, load_main_text_harness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--searcher-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.capture_dir / "collection_manifest.json").read_text(encoding="utf-8"))
    rankings_path = args.capture_dir / "sparse_rankings.jsonl"
    if manifest["status"] != "complete" or manifest["rankings_sha256"] != digest(rankings_path.read_bytes()):
        raise ValueError("Complete original rankings and matching checksum required")
    if os.environ.get("PYTHONHASHSEED") not in {"0", "1", "82"}:
        raise ValueError("Use an explicitly predeclared hash seed 0,1,82")
    harness, code = load_main_text_harness(args.searcher_source)
    results = []
    for original in [json.loads(line) for line in rankings_path.read_text(encoding="utf-8").splitlines() if line]:
        class FrozenClient:
            def search(self, collection, **kwargs):
                if collection != manifest["collection"]["name"] or kwargs["data"] != [original["raw_call"]["query_input"]] or kwargs["limit"] != 100:
                    raise ValueError("Replay query differs from frozen provider request")
                return [[{"id": h["milvus_id"], "distance": h["bm25_score"], "entity": {"frame_id": h["frame_id"], original["channel"]: h["indexed_text"]}} for h in original["raw_hits"]]]
        query = {key: original[key] for key in ("query_id", "channel", "query_text", "query_text_sha256")}
        replay = capture_query(harness, FrozenClient(), manifest["collection"]["name"], query)
        raw_score = {h["frame_id"]: h["bm25_score"] for h in original["raw_hits"]}
        if [raw_score[fid] for fid in replay["effective_frame_order"]] != [raw_score[fid] for fid in original["effective_frame_order"]]:
            raise ValueError("Replay changed more than equal-score order")
        results.append({"query_id": original["query_id"], "channel": original["channel"],
                        "effective_frame_order": replay["effective_frame_order"],
                        "order_differs_from_host": replay["effective_frame_order"] != original["effective_frame_order"],
                        "score_sequence_identical_to_host": True})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dump(args.output, {"schema": "vecna82-sparse-tie-replay-v1", "python_hash_seed": os.environ["PYTHONHASHSEED"],
                       "rankings_sha256": manifest["rankings_sha256"], "code_identity": code,
                       "replay_script_sha256": digest(Path(__file__).read_bytes()),
                       "ground_truth_read": False, "network_calls": 0, "models_loaded": False,
                       "row_count": len(results), "rows": results})
    print(json.dumps({"seed": os.environ["PYTHONHASHSEED"], "rows": len(results), "orders_differing_from_host": sum(r["order_differs_from_host"] for r in results)}))


if __name__ == "__main__":
    main()
