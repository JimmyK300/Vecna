#!/usr/bin/env python3
"""Score a completed fixed-sample BGE dense capture after immutable capture.

Reuses the identical frozen scorer and source/text comparison rules as sparse.
No retrieval, new model, query selection or rewriting, repair, or truth edit.
"""
import argparse
import json
import math
from pathlib import Path

from analyze_reranker import load_scorer, read_json, read_jsonl, unique_index
from collect_dense_visibility import TEXT_EMBEDDING_SHA256
from collect_sparse_visibility import digest, digest_json, dump
from evaluate_sparse_visibility import SOURCE_REVIEW_SHA256, index_projection_parity, order_effect, require, score_order, verify_capture, write_jsonl
from preflight import TRUTH_SHA256


def cosine_keys(value):
    """Reuse score arithmetic while preserving the explicit cosine field name."""
    if isinstance(value, dict):
        return {key.replace("bm25", "cosine"): cosine_keys(child) for key, child in value.items()}
    if isinstance(value, list):
        return [cosine_keys(child) for child in value]
    return value


def score_dense_order(hits, order, truth, scorer):
    adapted = [{**h, "bm25_score": h["cosine_score"]} for h in hits]
    result = cosine_keys(score_order(adapted, order, truth, scorer))
    result["observed_repeated_text"]["causal_limit"] = "Observed occupancy of the retained dense keyframe list; no deduplication counterfactual, visual-fusion effect or transcription fidelity is established."
    return result


def verify_dense(root, capture):
    _, _, queries, _, sample_pins = verify_capture(root, root / "outputs/source-visibility/sparse-v1")
    manifest_path = capture / "collection_manifest.json"
    rankings_path = capture / "dense_rankings.jsonl"
    config_path = root / "outputs/source-visibility/dense_config.json"
    manifest, rows, config = read_json(manifest_path), read_jsonl(rankings_path), read_json(config_path)
    require(manifest["schema"] == "vecna82-dense-visibility-run-v1" and manifest["status"] == "complete" and manifest["rows_written"] == len(rows) == 38, "Dense capture must be complete before scoring")
    require(manifest["rankings_sha256"] == digest(rankings_path.read_bytes()), "Dense rankings checksum mismatch")
    require(manifest["config_sha256"] == digest(config_path.read_bytes()) and manifest["queries_sha256"] == config["query_file_sha256"] == sample_pins["queries_sha256"], "Dense query/config checksum mismatch")
    require(manifest["collection"] == config["collection"], "Dense collection metadata identity mismatch")
    require(manifest["ground_truth_read"] is False and manifest["collection_mutations"] is False and manifest["visual_models_loaded"] is False, "Dense capture isolation differs")
    require(manifest["collector_sha256"] == digest((root / "code/collect_dense_visibility.py").read_bytes()), "Dense collector bytes differ from the locally frozen executable")
    require(manifest["code_identity"]["main_commit"] == config["main_commit"] and manifest["code_identity"]["source_lf_sha256"] == config["searcher_lf_sha256"], "Main search source mismatch")
    model = manifest["model_identity"]
    require(model["snapshot_revision"] == config["model"]["snapshot_revision"] and model["repository"] == "BAAI/bge-m3" and model["source_lf_sha256"] == TEXT_EMBEDDING_SHA256, "Dense model/source identity mismatch")
    require(model["checkpoint_parameter_audit"]["all_active_encoder_parameters_equal_cached_checkpoint"] is True and not model["core_encoder_missing_keys"] and not model["core_encoder_unexpected_keys"], "Dense active encoder loading was not verified")
    require(model["runtime_semantics"]["device"] == "cpu" and model["runtime_semantics"]["compute_type"] == "float32" and model["runtime_semantics"]["max_length"] == 1024, "Unexpected dense compute semantics")
    configured_files = {f["relative_path"]: f for f in config["model"]["files"]}
    measured_files = {f["relative_path"]: f for f in model["files"]}
    require(len(configured_files) == len(config["model"]["files"]) == len(measured_files) == len(model["files"]) and set(configured_files) == set(measured_files), "Dense consumed-input inventory is duplicate or incomplete")
    for name, expected in configured_files.items():
        observed = measured_files[name]
        require(observed["bytes"] == expected["bytes"] and observed["mtime_ns"] == expected["mtime_ns"] and observed["size_and_mtime_stable_after_loading"] is True, "Dense consumed-file metadata changed")
        require(len(observed["sha256"]) == 64 and all(c in "0123456789abcdef" for c in observed["sha256"]), "Dense consumed file lacks measured SHA256")
        require(not expected.get("sha256") or observed["sha256"] == expected["sha256"], "Dense consumed file differs from its pre-run SHA256 pin")
        require(not expected.get("content_addressed_sha256") or observed["sha256"] == expected["content_addressed_sha256"], "Dense consumed file differs from content address")
        require(observed["digest_pin_scope"] == expected["digest_pin_scope"], "Dense checksum provenance scope changed")
    loading = model["loading_info"]
    require(not loading.get("mismatched_keys") and not loading.get("error_msgs"), "Dense loading diagnostic contains mismatches or errors")
    require(not [k for k in loading.get("missing_keys", []) if not k.startswith("pooler.")], "Dense loading diagnostic contains a missing active encoder weight")
    require(not [k for k in loading.get("unexpected_keys", []) if not k.startswith(("pooler.", "lm_head.", "cls."))], "Dense loading diagnostic contains an unexpected active encoder weight")
    parameter_audit = model["checkpoint_parameter_audit"]
    parameters = parameter_audit["parameters"]
    require(bool(parameters) and len(parameters) == parameter_audit["active_parameter_tensor_count"] == len({p["parameter"] for p in parameters}), "Dense checkpoint parameter audit is empty or inconsistent")
    require(digest_json(parameters) == parameter_audit["parameter_mapping_sha256"], "Dense checkpoint parameter-audit checksum mismatch")
    require(sum(p["elements"] for p in parameters) == parameter_audit["active_parameter_elements"] <= model["trainable_parameter_elements"], "Dense active-parameter element count mismatch")
    require(all(p["equal_after_declared_dtype_cast"] is True and p["elements"] == math.prod(p["shape"]) and p["checkpoint_file"] in measured_files for p in parameters), "Dense parameter audit lacks exact equality or file/shape consistency")
    for registry in manifest["index_registry_records"]:
        if registry["exists"]:
            require(digest((capture / registry["artifact_relative_path"]).read_bytes()) == registry["sha256"], "Recovered dense index registry bytes mismatch")
            require(registry["index_state"] != "mutating", "Index was mutating")
    for row, query in zip(rows, queries):
        require(row["schema"] == "vecna82-dense-visibility-row-v1" and all(row[k] == query[k] for k in query), "Dense query projection differs from frozen sample")
        require(row["ground_truth_read"] is False and row["visual_models_loaded"] is False, "Dense row isolation differs")
        hits = row["raw_hits"]
        require(len(hits) == row["raw_hit_count"] <= 100 and [h["raw_rank"] for h in hits] == list(range(1, len(hits) + 1)), "Dense raw ranks/depth mismatch")
        require(len({h["frame_id"] for h in hits}) == len(hits), "Duplicate dense frame IDs")
        # The frozen collector checks the exact two-key request before calling
        # MilvusClient. The SDK may add its empty nested params mapping in place;
        # the collector records that same dictionary after the call returns.
        allowed_params = ({"nprobe": 32, "metric_type": "COSINE"}, {"nprobe": 32, "metric_type": "COSINE", "params": {}})
        require(row["raw_call"]["effective_raw_limit"] == 100 and row["raw_call"]["filter"] == "" and row["raw_call"]["offset"] == 0 and row["raw_call"]["anns_field"] == row["channel"] + "_dense" and row["raw_call"]["search_params"] in allowed_params, "Undeclared dense request state")
        eligible = sorted([h for h in hits if h["eligible_after_main_phrase_filter"]], key=lambda h: h["eligible_rank"])
        require(len(eligible) == row["eligible_hit_count"] and [h["eligible_rank"] for h in eligible] == list(range(1, len(eligible) + 1)) and [h["frame_id"] for h in eligible] == row["effective_frame_order"], "Dense effective rank order mismatch")
        require(row["query_embedding"]["dimension"] == 1024 and abs(row["query_embedding"]["l2_norm"] - 1) <= 0.00001, "Invalid dense query embedding")
        for hit in hits:
            require(hit["indexed_text_sha256"] == digest(hit["indexed_text"].encode("utf-8")), "Indexed dense candidate text checksum mismatch")
            require(math.isfinite(hit["cosine_score"]), "Non-finite dense provider score")
            require(hit["frame_id"] == f"{hit['video_id']}#{str(hit['frame_idx']).zfill(len(hit['frame_id'].rsplit('#', 1)[1]))}", "Dense frame identity mismatch")
    return manifest, config, rows, {"capture_manifest_sha256": digest(manifest_path.read_bytes()), "captured_rankings_sha256": digest(rankings_path.read_bytes()),
                                   "configuration_sha256": digest(config_path.read_bytes()), "queries_sha256": sample_pins["queries_sha256"], "frozen_sample_sha256": sample_pins["frozen_sample_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--capture-dir", type=Path, default=Path("outputs/source-visibility/dense-v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/source-visibility/dense-evaluation-v1"))
    args = parser.parse_args()
    root = args.root.resolve()
    capture = args.capture_dir if args.capture_dir.is_absolute() else root / args.capture_dir
    out = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    manifest, config, captured, pins = verify_dense(root, capture)
    truth_path, review_path = root / "inputs/canonical_truth.jsonl", root / "outputs/dataset-audit/reviewed_audit.jsonl"
    require(digest(truth_path.read_bytes()) == TRUTH_SHA256 and digest(review_path.read_bytes()) == SOURCE_REVIEW_SHA256, "Frozen truth/source-review identity differs")
    truth = unique_index(read_jsonl(truth_path))
    reviewed = {(r["channel"], r["query_id"]): r for r in read_jsonl(review_path)}
    sparse_path = root / "outputs/source-visibility/evaluation-v1/sparse_visibility.jsonl"
    scorer = load_scorer(root / "reference/evaluate_reranker_fusion.py")
    sparse_manifest_path = root / "outputs/source-visibility/evaluation-v1/evaluation_manifest.json"
    sparse_manifest = read_json(sparse_manifest_path)
    sparse_rows = read_jsonl(sparse_path)
    sparse = {(r["channel"], r["query_id"]): r for r in sparse_rows}
    _, _, _, sparse_captured, sparse_pins = verify_capture(root, root / "outputs/source-visibility/sparse-v1")
    require(sparse_manifest["status"] == "complete" and sparse_manifest["outputs"]["sparse_visibility.jsonl"] == digest(sparse_path.read_bytes()), "Sparse comparison output is not bound to its completed evaluation manifest")
    require(sparse_manifest["captured_rankings_sha256"] == sparse_pins["captured_rankings_sha256"] and sparse_manifest["canonical_truth_sha256"] == TRUTH_SHA256 and sparse_manifest["source_review_sha256"] == SOURCE_REVIEW_SHA256, "Sparse comparison capture/truth/source identity differs")
    require(len(sparse) == len(sparse_rows) == 38 and set(sparse) == {(r["channel"], r["query_id"]) for r in captured}, "Sparse comparison query/channel set differs")
    for original in sparse_captured:
        previous = sparse[(original["channel"], original["query_id"])]
        target = truth[original["query_id"]]
        require(previous["canonical_query"] == original["query_text"] == target["query"] and previous["query_text_sha256"] == original["query_text_sha256"], "Sparse comparison canonical query changed")
        for order in ("raw", "main_eligible"):
            require(previous[order] == score_order(original["raw_hits"], order, target, scorer), "Sparse comparison does not reproduce its frozen capture scores")
    rows = []
    for row in captured:
        key = (row["channel"], row["query_id"])
        target, review = truth[row["query_id"]], reviewed[key]
        require(row["query_text"] == target["query"] == review["canonical_query"] and target["scoreable"], "Dense canonical text/truth join mismatch")
        raw = score_dense_order(row["raw_hits"], "raw", target, scorer)
        effective = score_dense_order(row["raw_hits"], "main_eligible", target, scorer)
        sparse_effective = sparse[key]["main_eligible"]
        dense_hit = effective["frozen_range_or_event"]["all_required_targets_present"]
        sparse_hit = sparse_effective["frozen_range_or_event"]["all_required_targets_present"]
        if not row["raw_hits"]:
            state = "raw_dense_pool_empty"
        elif effective["frame_position_video"]["first_success_rank"] is None:
            state = "accepted_video_not_observed_in_dense_field_top100_under_declared_encoder"
        elif not dense_hit:
            state = "accepted_video_observed_but_current_targets_incomplete_in_dense_field_top100"
        else:
            state = "all_current_targets_observed_in_dense_field_top100"
        adapted = {**row, "raw_hits": [{**h, "bm25_score": h["cosine_score"]} for h in row["raw_hits"]]}
        rows.append({"schema": "vecna82-dense-visibility-scored-row-v1", "query_id": row["query_id"], "channel": row["channel"],
                     "canonical_query": row["query_text"], "query_text_sha256": row["query_text_sha256"],
                     "capture_state": row["state"],
                     "truth_tier": target["truth_tier"], "truth_provisional": target["truth_tier"] != "frozen_headless_benchmark_truth",
                     "raw": raw, "main_eligible": effective, "retrieval_visibility": state,
                     "native_query_state": row["raw_call"], "query_embedding": row["query_embedding"],
                     "sdk_search_params_note": "Frozen collector enforces COSINE/nprobe32 before the SDK call; the recorded dictionary is observed after the SDK may add an empty params mapping in place. This proves the main-call arguments, not independently verified effective server nprobe.",
                     "ascii_double_quote_filter_active": row["ascii_double_quote_filter_active"],
                     "ranking_order_effect": cosine_keys(order_effect(adapted)),
                     "indexed_projection_parity": index_projection_parity(root, row["raw_hits"], review),
                     "sparse_comparison": {"sparse_first_video_rank": sparse_effective["frame_position_video"]["first_success_rank"],
                                           "sparse_first_target_rank": sparse_effective["first_any_target_rank"],
                                           "sparse_all_targets_at100": sparse_hit, "dense_all_targets_at100": dense_hit,
                                           "coverage_class": "both" if sparse_hit and dense_hit else "sparse_only" if sparse_hit else "dense_only" if dense_hit else "neither"},
                     "source_review": {k: review.get(k) for k in ("review_status", "source_media_inspected", "latest_classification", "primary_failure")},
                     "source_media_reference": {k: review["media_review"].get(k) for k in ("artifact_relative_path", "artifact_sha256", "short_source_references", "source_to_artifact_comparison")},
                     "source_review_sha256": SOURCE_REVIEW_SHA256, "truth_changed": False,
                     "corpus_query_encoder_compatibility": "unresolved; schema dimensions, current query model and indexed text do not establish historical stored-vector encoder identity",
                     "causal_limit": "Source fidelity remains separately assessed. Dense target absence is only absence from this retained pool under this declared current encoder; it does not prove compatible-index failure, extraction error, historical Qwen/reranker cause or a repair."})
    summary = {}
    for channel in ("ocr", "asr"):
        cohort = [r for r in rows if r["channel"] == channel]
        value = {"query_channel_count": len(cohort), "provisional_truth_count": sum(r["truth_provisional"] for r in cohort),
                 "queries_truncated_at1024_tokens": [r["query_id"] for r in cohort if r["query_embedding"]["truncation_applied"]],
                 "coverage_comparison_at100": {name: sum(r["sparse_comparison"]["coverage_class"] == name for r in cohort) for name in ("both", "sparse_only", "dense_only", "neither")}}
        for order in ("raw", "main_eligible"):
            value[order] = {metric: {f"R@{k}": sum(r[order][metric][f"R@{k}"] for r in cohort) for k in (1, 5, 10, 20, 100)} for metric in ("video_hit", "any_target_hit", "strict_all_targets_hit")}
            value[order]["same_video_exact_text_repeat_excess"] = sum(r[order]["observed_repeated_text"]["same_video_exact_text_repeat_excess"] for r in cohort)
        summary[channel] = value
    comparisons = [c for r in rows for c in r["indexed_projection_parity"]["comparisons"]]
    summary["indexed_projection_parity"] = {"comparisons": len(comparisons), "matching": sum(c["indexed_text_matches_projected_text"] is True for c in comparisons),
                                           "mismatching": sum(c["indexed_text_matches_projected_text"] is False for c in comparisons), "missing_projected_frames": sum(c["projected_frame_present"] is False for c in comparisons)}
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "dense_visibility.jsonl", rows)
    dump(out / "summary.json", summary)
    lines = ["# Frozen OCR/ASR sample: dense BGE-M3 visibility", "",
             "The existing cached BGE-M3 checkpoint encoded all 38 frozen canonical query/channel rows through pinned main's PyTorch CPU float32, CLS, L2-normalized, 1024-token path. Every active encoder parameter was compared with the cached checkpoint before queries ran. Raw COSINE top100 and main eligibility/boost/max normalization were retained separately; no visual model, truth-directed query, new model, extraction, index mutation or fusion change was used.", "",
             "The current query checkpoint is identified and verified. Historical stored-vector encoder/index-generation compatibility remains unresolved. Target absence therefore means absent from this dense field's retained100 under this declared encoder; it does not establish an extraction error or failure of a proven compatible dense index. Source-image observations and the 18 unheard ASR clips retain their separate limits.", "",
             "| Channel | Cases | Eligible video @20 / @100 | Eligible any target @20 / @100 | All targets @100: both / sparse only / dense only / neither |", "|---|---:|---:|---:|---:|"]
    for channel in ("ocr", "asr"):
        value = summary[channel]
        effective = value["main_eligible"]
        coverage = value["coverage_comparison_at100"]
        lines.append(f"| {channel.upper()} | {value['query_channel_count']} | {effective['video_hit']['R@20']} / {effective['video_hit']['R@100']} | {effective['any_target_hit']['R@20']} / {effective['any_target_hit']['R@100']} | " + " / ".join(str(coverage[n]) for n in ("both", "sparse_only", "dense_only", "neither")) + " |")
    lines += ["", "These are sample visibility counts at keyframe positions, including provisional P3 truth. The sparse/dense overlap counts compare independent candidate pools and are not a fusion score. Main's normal raw pool expansion to200/500 was not fetched. Full ranks, query vectors' checksums, token counts/truncation, indexed text, nearest candidates outside current truth, source parity, and repeated-text occupancy are in `dense_visibility.jsonl`.", "",
              "| Query | Channel | Dense first video | Dense first target | Sparse first target | Coverage at100 |", "|---|---|---:|---:|---:|---|"]
    for row in rows:
        show = lambda v: "—" if v is None else str(v)
        lines.append(f"| {row['query_id']} | {row['channel']} | {show(row['main_eligible']['frame_position_video']['first_success_rank'])} | {show(row['main_eligible']['first_any_target_rank'])} | {show(row['sparse_comparison']['sparse_first_target_rank'])} | {row['sparse_comparison']['coverage_class']} |")
    lines += ["", "No CER/WER, source transcript, truth promotion, model repair or extraction fix is asserted. Existing source gaps remain anchor-specific, even if another candidate in the accepted window is retrieved.", "",
              f"Current cached revision: `{manifest['model_identity']['snapshot_revision']}`. Rankings SHA-256: `{pins['captured_rankings_sha256']}`. Model loading, all consumed-file hashes and checkpoint parameter proof are in the capture manifest and `model_initialization.json`; lineage and checksum qualifications are preserved there.", ""]
    (out / "DENSE_VISIBILITY.md").write_text("\n".join(lines), encoding="utf-8")
    dump(out / "evaluation_manifest.json", {"schema": "vecna82-dense-visibility-evaluation-v1", "status": "complete", **pins,
         "canonical_truth_sha256": TRUTH_SHA256, "source_review_sha256": SOURCE_REVIEW_SHA256, "sparse_scored_rows_sha256": digest(sparse_path.read_bytes()),
         "sparse_evaluation_manifest_sha256": digest(sparse_manifest_path.read_bytes()), "sparse_comparison_rescored_from_verified_capture": True,
         "evaluator_sha256": digest(Path(__file__).read_bytes()), "capture_manifest": manifest, "retrieval_complete_before_truth_join": True, "truth_changed": False,
         "outputs": {name: digest((out / name).read_bytes()) for name in ("dense_visibility.jsonl", "summary.json", "DENSE_VISIBILITY.md")}})
    print(json.dumps({"output": str(out), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
