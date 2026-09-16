#!/usr/bin/env python3
"""Freeze truth-free sparse-audit inputs from the existing query-side sample."""
import argparse
import json
from pathlib import Path

from collect_sparse_visibility import MAIN_SHA, SEARCHER_SHA256, digest, digest_json, dump


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    sample_path = root / "outputs/dataset-audit/sample_manifest.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    if sample["selected_counts"] != {"ocr": 20, "asr": 18}:
        raise ValueError("Unexpected frozen sample sizes")
    rows = [{"query_id": r["query_id"], "channel": channel, "query_text": r["query"],
             "query_text_sha256": digest(r["query"].encode("utf-8"))}
            for channel in ("ocr", "asr") for r in sample["selected"][channel]]
    if len({(r["channel"], r["query_id"]) for r in rows}) != 38:
        raise ValueError("Duplicate selected query/channel identity")
    out = root / "outputs/source-visibility"
    out.mkdir(parents=True, exist_ok=True)
    query_path = out / "sparse_queries.jsonl"
    query_path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    identity_path = root / "outputs/fusion/live-smoke-v1/collection_manifest.json"
    collection = json.loads(identity_path.read_text(encoding="utf-8"))["identity"]["collection"]
    config = {"schema": "vecna82-sparse-visibility-config-v1", "provider_depth": 100,
              "query_file_sha256": digest(query_path.read_bytes()), "query_projection_sha256": digest_json(rows),
              "frozen_sample_sha256": digest(sample_path.read_bytes()), "expected_query_channel_count": 38,
              "per_channel_counts": {"ocr": 20, "asr": 18}, "collection": collection,
              "collection_identity_source": "Verified metadata preflight of the recorded fusion smoke; the subsequent visual query failed independently.",
              "collection_identity_evidence_sha256": digest(identity_path.read_bytes()),
              "main_commit": MAIN_SHA, "searcher_lf_sha256": SEARCHER_SHA256,
              "provider_fields": {"ocr": "ocr_sparse", "asr": "asr_sparse"},
              "metric": "BM25", "server_filter": "", "offset": 0,
              "effective_semantics": "Execute main's exact text component with alpha=0, no dense extractor, one canonical text formulation, native ASCII-quote cleaning/eligibility/1.5 boost/max normalization. Cap the single raw request at100 and retain the native requested200/500 limit as evidence.",
              "forbidden_capture_inputs": ["truth", "accepted_video", "accepted_frame", "answer", "query_rewrite", "retrieval_outcome"],
              "scope": "Dataset #17 diagnostic only; independent of the blocked visual-fusion collector and its frozen weights. No index writes, collection load/release, or models."}
    config_path = out / "sparse_config.json"
    dump(config_path, config)
    print(json.dumps({"queries": str(query_path.relative_to(root)), "queries_sha256": digest(query_path.read_bytes()),
                      "config": str(config_path.relative_to(root)), "config_sha256": digest(config_path.read_bytes()),
                      "query_channel_rows": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
