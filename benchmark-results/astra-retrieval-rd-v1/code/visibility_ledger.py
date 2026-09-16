"""Read-only Packet D source-visibility overlay, reconstructed after scratch loss.

No retrieval/model imports are required. Manifest identities and retained-pool
metrics are checked before attaching evidence. This is a reconstruction with new
hashes, not a claim of byte equality with the unavailable scratch source.
"""
from __future__ import annotations
import collections
import hashlib
import json
import math
from pathlib import Path

BASE = "outputs/source-visibility"
LAYOUTS = {
    "sparse": {"evaluation": BASE + "/evaluation-v1", "capture": BASE + "/sparse-v1"},
    "dense": {"evaluation": BASE + "/dense-evaluation-v1", "capture": BASE + "/dense-v1"},
}
KS = (1, 5, 10, 20, 100)
TIE_SEEDS = (0, 1, 82)
LIMIT = "Independent retained-top100 visibility evidence only. Repeated text, target absence and sparse/dense differences do not establish extraction, compatible-index or historical Qwen/reranker causes. These observations do not change the ledger's primary failure or observed-arm success union."

def require(value, message):
    if not value:
        raise ValueError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def stable_digest(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode())

def valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

def pair_index(rows):
    found = {}
    for row in rows:
        key = (row["query_id"], row["channel"])
        require(key not in found, f"Duplicate visibility query/channel: {key}")
        found[key] = row
    return found

class Reader:
    def __init__(self, root):
        self.root, self.hashes = Path(root), {}

    def raw(self, relative):
        payload = (self.root / relative).read_bytes()
        value = digest(payload)
        require(relative not in self.hashes or self.hashes[relative] == value, f"Visibility input changed: {relative}")
        self.hashes[relative] = value
        return payload

    def json(self, relative):
        return json.loads(self.raw(relative))

    def jsonl(self, relative):
        return [json.loads(line) for line in self.raw(relative).decode().splitlines() if line.strip()]

    def bind(self, relative, expected):
        self.raw(relative)
        require(self.hashes[relative] == expected, f"Visibility checksum mismatch: {relative}")

    def unchanged(self):
        require(all(digest((self.root / p).read_bytes()) == h for p, h in self.hashes.items()), "Visibility input changed during join")

def validate_dense_model(model, config):
    specified = {entry["relative_path"]: entry for entry in config["model"]["files"]}
    files = {entry["relative_path"]: entry for entry in model["files"]}
    require(len(files) == len(model["files"]) == len(specified) and set(files) == set(specified), "Dense consumed-file audit inventory differs")
    for name, observed in files.items():
        expected = specified[name]
        require(observed["bytes"] == expected["bytes"] and observed["mtime_ns"] == expected["mtime_ns"] and observed["size_and_mtime_stable_after_loading"] is True and valid_sha(observed["sha256"]), "Dense consumed-file audit metadata differs")
        for field in ("sha256", "content_addressed_sha256"):
            if expected.get(field):
                require(observed["sha256"] == expected[field], "Dense consumed-file audit checksum differs")
        require(observed["digest_pin_scope"] == expected.get("digest_pin_scope", "checksum_verified_against_identity_probe"), "Dense consumed-file checksum qualification differs")
    require(model["snapshot_top_level_files"] == config["model"]["snapshot_top_level_files"], "Dense snapshot inventory differs")
    loading = model["loading_info"]
    require(not loading.get("mismatched_keys") and not loading.get("error_msgs"), "Dense loading audit contains mismatches or errors")
    require([key for key in loading.get("missing_keys", []) if not key.startswith("pooler.")] == model["core_encoder_missing_keys"] == [] and [key for key in loading.get("unexpected_keys", []) if not key.startswith(("pooler.", "lm_head.", "cls."))] == model["core_encoder_unexpected_keys"] == [], "Dense core loading audit differs")
    parameter_audit = model["checkpoint_parameter_audit"]
    records = parameter_audit["parameters"]
    require(len(records) == parameter_audit["active_parameter_tensor_count"] > 0 and stable_digest(records) == parameter_audit["parameter_mapping_sha256"], "Dense parameter audit digest/count differs")
    require(len({row["parameter"] for row in records}) == len({row["checkpoint_key"] for row in records}) == len(records), "Dense parameter audit mapping is not unique")
    require(all(row["equal_after_declared_dtype_cast"] is True and row["checkpoint_file"] == config["model"]["checkpoint_file"] and math.prod(row["shape"]) == row["elements"] > 0 for row in records), "Dense parameter audit contains unequal or inconsistent tensors")
    require(sum(row["elements"] for row in records) == parameter_audit["active_parameter_elements"] and parameter_audit["all_active_encoder_parameters_equal_cached_checkpoint"] is True, "Dense parameter audit totals differ")

def compact_order(layer, selected, truth, audit, scorer):
    candidates = [{"rank": i, "video_id": h["video_id"], "frame_id": h["frame_idx"]} for i, h in enumerate(selected, 1)]
    frozen = audit.score_frozen(candidates, truth, scorer, depth=100)
    video = audit.score_video(candidates, truth, scorer, depth=100)
    distinct, seen = [], set()
    for candidate in candidates:
        key = scorer.norm_video(candidate["video_id"])
        if key not in seen:
            seen.add(key)
            distinct.append({**candidate, "rank": len(distinct) + 1})
    distinct_video = audit.score_video(distinct, truth, scorer, depth=100)
    require(layer["returned_depth"] == len(selected), "Visibility depth differs from captured pool")
    require(layer["frozen_range_or_event"] == frozen and layer["frame_position_video"] == video and layer["distinct_video_within_retained_frame_pool"] == distinct_video, "Visibility metrics do not reproduce from captured ranks")
    first_any = min((r for r in frozen["target_first_ranks"] if r is not None), default=None)
    require(layer["first_any_target_rank"] == first_any, "Visibility any-target rank mismatch")
    hits = {
        "video_hit": {f"R@{k}": video["first_success_rank"] is not None and video["first_success_rank"] <= k for k in KS},
        "any_target_hit": {f"R@{k}": first_any is not None and first_any <= k for k in KS},
        "strict_all_targets_hit": {f"R@{k}": bool(frozen["target_first_ranks"]) and all(r is not None and r <= k for r in frozen["target_first_ranks"]) for k in KS},
    }
    require(all(layer[name] == value for name, value in hits.items()), "Visibility hit indicators mismatch")
    texts = collections.Counter(h["indexed_text"] for h in selected if h["indexed_text"].strip())
    within_video = collections.Counter((h["video_id"].casefold(), h["indexed_text"]) for h in selected if h["indexed_text"].strip())
    repeats = {
        "hit_count": len(selected), "distinct_video_count": len({h["video_id"].casefold() for h in selected}),
        "nonempty_text_hit_count": sum(texts.values()), "unique_nonempty_text_count": len(texts),
        "exact_text_repeat_excess": sum(v - 1 for v in texts.values()),
        "same_video_exact_text_repeat_excess": sum(v - 1 for v in within_video.values()),
        "largest_same_video_exact_text_group": max(within_video.values(), default=0),
    }
    require(all(layer["observed_repeated_text"][k] == v for k, v in repeats.items()), "Visibility repeated-text counts mismatch")
    return {"returned_depth": len(selected), "frame_position_video": video, "distinct_video_within_retained_frame_pool": distinct_video,
            "frozen_range_or_event": frozen, "first_any_target_rank": first_any, **hits, "observed_repeated_text": repeats}

def join_rows(mode, scored_rows, captured_rows, queries, truth, sample_pairs, source_review_sha, provenance, audit, scorer):
    scored, captured, query_index = pair_index(scored_rows), pair_index(captured_rows), pair_index(queries)
    require(set(scored) == set(captured) == set(query_index) == sample_pairs and len(scored) == 38, "Visibility rows must preserve the exact frozen 38 query/channel pairs")
    require(list(scored) == list(captured) == list(query_index), "Visibility ordered query/channel projection differs")
    result = {}
    score_key = "bm25_score" if mode == "sparse" else "cosine_score"
    for key, row in scored.items():
        q, channel = key
        raw, query, target = captured[key], query_index[key], truth[q]
        expected_hash = digest(target["query"].encode())
        require(target["scoreable"] and row["canonical_query"] == raw["query_text"] == query["query_text"] == target["query"], f"Visibility canonical text mismatch: {key}")
        require(row["query_text_sha256"] == raw["query_text_sha256"] == query["query_text_sha256"] == expected_hash, f"Visibility canonical hash mismatch: {key}")
        require(row["schema"] == f"vecna82-{mode}-visibility-scored-row-v1" and raw["schema"] == f"vecna82-{mode}-visibility-row-v1", "Unexpected visibility schema")
        require(row["truth_changed"] is False and row["truth_tier"] == target["truth_tier"] and row["source_review_sha256"] == source_review_sha, "Visibility truth/source-review identity mismatch")
        require(raw["ground_truth_read"] is False and raw["visual_models_loaded"] is False, "Visibility capture isolation mismatch")
        if mode == "sparse":
            require(raw["dense_models_loaded"] is False, "Sparse visibility unexpectedly loaded a dense model")
        require(row["capture_state"] == raw["state"] and raw["state"] in {"ok", "empty"}, "Visibility capture state mismatch")
        hits = raw["raw_hits"]
        require(raw["raw_hit_count"] == len(hits) <= 100 and [h["raw_rank"] for h in hits] == list(range(1, len(hits) + 1)), "Visibility raw rank/depth mismatch")
        require(len({h["frame_id"] for h in hits}) == len(hits), "Duplicate visibility frame IDs")
        for hit in hits:
            video, frame = hit["frame_id"].rsplit("#", 1)
            require(video == hit["video_id"] and frame.isdigit() and int(frame) == hit["frame_idx"], "Visibility frame identity mismatch")
            require(hit["indexed_text_sha256"] == digest(hit["indexed_text"].encode()) and math.isfinite(hit[score_key]), "Visibility text hash or score mismatch")
        eligible = sorted((h for h in hits if h["eligible_after_main_phrase_filter"]), key=lambda h: h["eligible_rank"])
        require(len(eligible) == raw["eligible_hit_count"] and [h["eligible_rank"] for h in eligible] == list(range(1, len(eligible) + 1)) and [h["frame_id"] for h in eligible] == raw["effective_frame_order"], "Visibility main order mismatch")
        require(raw["state"] == ("ok" if eligible else "empty"), "Visibility success/empty state disagrees with main-eligible candidates")
        call = raw["raw_call"]
        allowed_params = [{"metric_type": "BM25"}] if mode == "sparse" else [{"metric_type": "COSINE", "nprobe": 32}, {"metric_type": "COSINE", "nprobe": 32, "params": {}}]
        require(call["anns_field"] == channel + "_" + mode and call["effective_raw_limit"] == 100 and call["filter"] == "" and call["offset"] == 0 and call["search_params"] in allowed_params and row["native_query_state"] == call, "Visibility provider request mismatch")
        require(row["ascii_double_quote_filter_active"] == raw["ascii_double_quote_filter_active"], "Visibility phrase-filter state mismatch")
        if mode == "dense":
            embedding = row["query_embedding"]
            require(embedding == raw["query_embedding"] and embedding["dimension"] == 1024 and math.isfinite(embedding["l2_norm"]) and abs(embedding["l2_norm"] - 1) <= 0.00001, "Dense visibility query-vector evidence mismatch")
            require(row["corpus_query_encoder_compatibility"].startswith("unresolved"), "Dense visibility must preserve unresolved historical corpus compatibility")
        raw_eligible = [h for h in hits if h["eligible_after_main_phrase_filter"]]
        moved = sum(h["eligible_rank"] != i for i, h in enumerate(raw_eligible, 1))
        same_scores = [h[score_key] for h in raw_eligible] == [h[score_key] for h in eligible]
        effect = row["ranking_order_effect"]
        require(effect["eligible_frame_order_changed"] == bool(moved) and effect["moved_frame_count"] == moved and effect["raw_score_sequence_preserved"] == same_scores and effect[f"changes_confined_to_equal_{'bm25' if mode == 'sparse' else 'cosine'}_scores"] == (bool(moved) and same_scores), "Visibility tie observation mismatch")
        result[key] = {
            "status": "EVALUATED", "query_text_sha256": expected_hash, "query_id": q, "channel": channel,
            "provider": channel + "_" + mode, "provider_state": "success_output" if eligible else "success_empty",
            "provider_state_scope": "Captured main-eligible output; raw provider occupancy is reported separately.",
            "raw_provider_state": "success_output" if hits else "success_empty", "capture_state": raw["state"],
            "truth_tier": target["truth_tier"], "retrieval_visibility": row["retrieval_visibility"], "native_query_state": call,
            "request_provenance_note": "Declared pinned-main request. The post-call SDK mapping may additionally contain empty params; effective server nprobe is not independently verified." if mode == "dense" else None,
            "ascii_double_quote_filter_active": row["ascii_double_quote_filter_active"],
            "raw": compact_order(row["raw"], hits, target, audit, scorer),
            "main_eligible": compact_order(row["main_eligible"], eligible, target, audit, scorer),
            "ranking_order_effect": {k: v for k, v in effect.items() if k != "moved_frames"},
            "process_seed_tie_replay": None,
            "indexed_projection_parity": {k: v for k, v in row["indexed_projection_parity"].items() if k != "comparisons"},
            "query_embedding": row.get("query_embedding"),
            "corpus_query_encoder_compatibility": row.get("corpus_query_encoder_compatibility", "Sparse text-function observations do not establish dense vector lineage."),
            "provenance": provenance, "causal_limit": LIMIT,
        }
    return result

def tie_replay(reader, captured_rows, truth, provenance, code_identity, audit, scorer):
    base = BASE + "/tie-replay-v1"
    path = base + "/tie_proof.json"
    if not (reader.root / path).exists():
        return {"status": "REPLAY_NOT_AVAILABLE", "evidence": None}, {}
    proof = reader.json(path)
    require(proof["schema"] == "vecna82-sparse-tie-proof-v1" and proof["predeclared_seeds"] == list(TIE_SEEDS) and proof["query_channel_count"] == 38, "Sparse tie replay contract mismatch")
    for key in ("capture_manifest_sha256", "captured_rankings_sha256", "configuration_sha256", "queries_sha256", "frozen_sample_sha256"):
        require(proof[key] == provenance[key], "Sparse tie replay provenance mismatch: " + key)
    require(proof["truth_sha256"] == provenance["canonical_truth_sha256"], "Sparse tie replay truth mismatch")
    reader.bind("code/evaluate_sparse_tie_replays.py", proof["evaluator_sha256"])
    captured, expected = pair_index(captured_rows), pair_index(proof["rows"])
    require(list(expected) == list(captured), "Sparse tie replay query/channel ordering mismatch")
    seeds, seed_paths = {}, {}
    for seed in TIE_SEEDS:
        label = str(seed)
        seed_path = base + f"/seed-{label}.json"
        reader.bind(seed_path, proof["replay_sha256"][label])
        replay = reader.json(seed_path)
        require(replay["schema"] == "vecna82-sparse-tie-replay-v1" and replay["python_hash_seed"] == label and replay["row_count"] == 38 and replay["rankings_sha256"] == provenance["captured_rankings_sha256"], "Sparse seed replay identity mismatch")
        require(replay["code_identity"] == code_identity and replay["ground_truth_read"] is False and replay["models_loaded"] is False and replay["network_calls"] == 0, "Sparse seed replay source/isolation mismatch")
        reader.bind("code/replay_sparse_visibility_ties.py", replay["replay_script_sha256"])
        seeds[label] = pair_index(replay["rows"])
        require(list(seeds[label]) == list(captured), "Sparse seed replay ordered cohort mismatch")
        seed_paths[label] = {"path": seed_path, "sha256": reader.hashes[seed_path]}
    joined, variation = {}, 0
    for key, capture in captured.items():
        by_id = {h["frame_id"]: h for h in capture["raw_hits"]}
        host_order = capture["effective_frame_order"]
        orders = {"host": host_order, **{label: rows[key]["effective_frame_order"] for label, rows in seeds.items()}}
        host_scores = [by_id[f]["bm25_score"] for f in host_order]
        scores = {}
        for label, order in orders.items():
            require(len(order) == len(set(order)) and set(order) == set(host_order), "Sparse tie replay candidate membership changed")
            require([by_id[f]["bm25_score"] for f in order] == host_scores, "Sparse tie replay score sequence changed")
            candidates = [{"rank": i, "video_id": by_id[f]["video_id"], "frame_id": by_id[f]["frame_idx"]} for i, f in enumerate(order, 1)]
            scores[label] = audit.score_frozen(candidates, truth[key[0]], scorer, depth=100)
            if label != "host":
                replayed = seeds[label][key]
                require(replayed["order_differs_from_host"] == (order != host_order) and replayed["score_sequence_identical_to_host"] is True, "Sparse seed replay declarations differ from observed ranks")
        distinct_orders = len({tuple(order) for order in orders.values()})
        variation += distinct_orders > 1
        recorded = expected[key]
        require(recorded["scores"] == scores and recorded["truth_tier"] == truth[key[0]]["truth_tier"] and recorded["equal_scores_and_membership_preserved"] is True and recorded["distinct_effective_orders_across_host_and_seeds"] == distinct_orders, "Sparse tie proof does not reproduce")
        joined[key] = {"status": "VERIFIED", "predeclared_seeds": list(TIE_SEEDS), "distinct_effective_orders_across_host_and_seeds": distinct_orders,
                       "candidate_membership_preserved": True, "score_sequences_preserved": True, "frozen_range_or_event_by_observed_order": scores,
                       "proof_path": path, "proof_sha256": reader.hashes[path], "seed_artifacts": seed_paths, "selection": None,
                       "scope": "Parallel reproducibility observations; no preferred seed, extra retrieval arm, or change to the ledger success union."}
    require(proof["rows_with_process_seed_order_variation"] == variation and proof["all_candidate_membership_and_score_sequences_preserved"] is True, "Sparse tie proof totals mismatch")
    return {"status": "VERIFIED", "query_channel_count": len(joined), "rows_with_process_seed_order_variation": variation,
            "predeclared_seeds": list(TIE_SEEDS), "proof_path": path, "proof_sha256": reader.hashes[path], "seed_artifacts": seed_paths, "selection": None}, joined

def load_provider(reader, mode, truth, sample, audit, scorer):
    layout = LAYOUTS[mode]
    eval_dir, capture_dir = layout["evaluation"], layout["capture"]
    manifest_path = eval_dir + "/evaluation_manifest.json"
    if not (reader.root / manifest_path).exists():
        return {"status": "EVALUATION_NOT_AVAILABLE", "evidence": None, "evaluation_manifest": manifest_path,
                "reason": "No completed evaluated evidence is available; no zero score or failure is imputed."}, {}
    evaluation = reader.json(manifest_path)
    if evaluation.get("status") != "complete":
        return {"status": "EVALUATION_INCOMPLETE", "evidence": None, "evaluation_manifest": manifest_path,
                "evaluation_manifest_sha256": reader.hashes[manifest_path]}, {}
    require(evaluation["schema"] == f"vecna82-{mode}-visibility-evaluation-v1" and evaluation["truth_changed"] is False and evaluation["retrieval_complete_before_truth_join"] is True, "Visibility evaluation contract mismatch")
    scored_path = eval_dir + f"/{mode}_visibility.jsonl"
    capture_path, rankings_path = capture_dir + "/collection_manifest.json", capture_dir + f"/{mode}_rankings.jsonl"
    config_path, queries_path = BASE + f"/{mode}_config.json", BASE + "/sparse_queries.jsonl"
    bindings = {
        capture_path: evaluation["capture_manifest_sha256"], rankings_path: evaluation["captured_rankings_sha256"],
        config_path: evaluation["configuration_sha256"], queries_path: evaluation["queries_sha256"],
        "inputs/canonical_truth.jsonl": evaluation["canonical_truth_sha256"],
        "outputs/dataset-audit/sample_manifest.json": evaluation["frozen_sample_sha256"],
        "outputs/dataset-audit/reviewed_audit.jsonl": evaluation["source_review_sha256"],
        f"code/evaluate_{mode}_visibility.py": evaluation["evaluator_sha256"],
    }
    bindings.update({eval_dir + "/" + name: value for name, value in evaluation["outputs"].items()})
    if evaluation.get("scorer_source"):
        bindings[evaluation["scorer_source"]["local"]] = evaluation["scorer_source"]["sha256"]
    for path, expected in bindings.items():
        reader.bind(path, expected)
    capture, config, queries = reader.json(capture_path), reader.json(config_path), reader.jsonl(queries_path)
    require(capture == evaluation["capture_manifest"] and capture["status"] == "complete" and capture["rows_written"] == 38, "Visibility completed capture identity mismatch")
    require(capture["rankings_sha256"] == reader.hashes[rankings_path] and capture["queries_sha256"] == config["query_file_sha256"] == reader.hashes[queries_path] and capture["config_sha256"] == reader.hashes[config_path], "Visibility capture checksum chain mismatch")
    require(capture["collection"] == config["collection"] and capture["collection_mutations"] is False and capture["ground_truth_read"] is False, "Visibility collection/isolation mismatch")
    require(config["query_projection_sha256"] == stable_digest(queries), "Visibility query projection mismatch")
    require(config["frozen_sample_sha256"] == evaluation["frozen_sample_sha256"], "Visibility configuration/sample identity mismatch")
    require(capture["code_identity"]["main_commit"] == config["main_commit"] and capture["code_identity"]["source_lf_sha256"] == config["searcher_lf_sha256"], "Visibility pinned main source identity mismatch")
    reader.bind("code/collect_" + mode + "_visibility.py", capture["collector_sha256"])
    main_bytes = reader.raw("outputs/fusion/source/searcher_main.py")
    require(digest(main_bytes.replace(b"\r\n", b"\n")) == config["searcher_lf_sha256"], "Visibility pinned main source bytes mismatch")
    selected_order = [(row["query_id"], channel, row["query"]) for channel in ("ocr", "asr") for row in sample["selected"][channel]]
    require([(row["query_id"], row["channel"], row["query_text"]) for row in queries] == selected_order, "Visibility frozen sample order/text mismatch")
    selected = {(row["query_id"], channel) for channel, rows in sample["selected"].items() for row in rows}
    require(len(selected) == 38 and collections.Counter(channel for _, channel in selected) == {"ocr": 20, "asr": 18}, "Visibility frozen sample changed")
    if mode == "dense":
        model = capture["model_identity"]
        validate_dense_model(model, config)
        initialization = reader.json(capture_dir + "/model_initialization.json")
        require(initialization.get("status") == "verified" and {k: v for k, v in initialization.items() if k != "status"} == model, "Dense initialization artifact differs from capture manifest")
        require(capture["visual_models_loaded"] is False and model["repository"] == config["model"]["repository"] == "BAAI/bge-m3" and model["snapshot_revision"] == config["model"]["snapshot_revision"], "Dense visibility model identity mismatch")
        require(model["runtime_semantics"]["device"] == "cpu" and model["runtime_semantics"]["compute_type"] == "float32" and model["runtime_semantics"]["max_length"] == 1024, "Dense visibility compute semantics mismatch")
        text_source = reader.raw(BASE + "/source/text_embedding_main.py")
        require(digest(text_source.replace(b"\r\n", b"\n")) == model["source_lf_sha256"] == config["text_embedding_lf_sha256"], "Dense visibility text encoder source bytes mismatch")
        for registry in capture["index_registry_records"]:
            if registry["exists"]:
                require(registry["index_state"] != "mutating", "Dense visibility index was mutating")
                reader.bind(capture_dir + "/" + registry["artifact_relative_path"], registry["sha256"])
        sparse_path = LAYOUTS["sparse"]["evaluation"] + "/sparse_visibility.jsonl"
        require(reader.hashes.get(sparse_path) == evaluation["sparse_scored_rows_sha256"], "Dense visibility sparse-comparison provenance was not independently verified")
    else:
        require(capture["models_loaded"] is False, "Sparse visibility unexpectedly loaded models")
    provenance = {"evaluation_manifest": manifest_path, "evaluation_manifest_sha256": reader.hashes[manifest_path],
                  "capture_manifest": capture_path, "capture_manifest_sha256": reader.hashes[capture_path],
                  "scored_rows": scored_path, "scored_rows_sha256": reader.hashes[scored_path],
                  "captured_rankings": rankings_path, "captured_rankings_sha256": reader.hashes[rankings_path],
                  "configuration": config_path, "configuration_sha256": reader.hashes[config_path],
                  "query_projection": queries_path, "queries_sha256": reader.hashes[queries_path], "frozen_sample_sha256": evaluation["frozen_sample_sha256"],
                  "canonical_truth_sha256": evaluation["canonical_truth_sha256"], "source_review_sha256": evaluation["source_review_sha256"]}
    captured_rows = reader.jsonl(rankings_path)
    rows = join_rows(mode, reader.jsonl(scored_path), captured_rows, queries, truth, selected, evaluation["source_review_sha256"], provenance, audit, scorer)
    ties = {"status": "NOT_PART_OF_DENSE_CAPTURE", "evidence": None}
    if mode == "sparse":
        ties, replay_rows = tie_replay(reader, captured_rows, truth, provenance, capture["code_identity"], audit, scorer)
        for pair, row in rows.items():
            row["process_seed_tie_replay"] = replay_rows.get(pair, {"status": ties["status"], "evidence": None})
    return {"status": "EVALUATED", "query_channel_count": len(rows), "collection": capture["collection"],
            "model_identity": capture.get("model_identity"), "index_generation_identity": capture.get("index_generation_identity"),
            "process_seed_tie_replay": ties, "provenance": provenance, "causal_limit": LIMIT}, rows

def load(root, truth, sample, audit, scorer):
    reader, providers, rows_by_mode = Reader(root), {}, {}
    for mode in LAYOUTS:
        providers[mode], rows_by_mode[mode] = load_provider(reader, mode, truth, sample, audit, scorer)
        if providers[mode]["status"] == "EVALUATED":
            providers[mode]["channels"] = {}
            for channel in ("ocr", "asr"):
                selected = [row for (q, c), row in rows_by_mode[mode].items() if c == channel]
                value = {"query_channel_count": len(selected), "provider_state_counts": dict(collections.Counter(row["provider_state"] for row in selected)),
                         "raw_provider_state_counts": dict(collections.Counter(row["raw_provider_state"] for row in selected)),
                         "main_order_changed_rows": sum(row["ranking_order_effect"]["eligible_frame_order_changed"] for row in selected)}
                for order in ("raw", "main_eligible"):
                    value[order] = {metric: {f"R@{k}": sum(row[order][metric][f"R@{k}"] for row in selected) for k in KS} for metric in ("video_hit", "any_target_hit", "strict_all_targets_hit")}
                    value[order].update({"retained_candidates": sum(row[order]["returned_depth"] for row in selected),
                                         "same_video_exact_text_repeat_excess": sum(row[order]["observed_repeated_text"]["same_video_exact_text_repeat_excess"] for row in selected)})
                providers[mode]["channels"][channel] = value
    joined = collections.defaultdict(dict)
    for channel, selected in sample["selected"].items():
        for row in selected:
            q = row["query_id"]
            joined[q][channel] = {mode: rows_by_mode[mode].get((q, channel), {"status": providers[mode]["status"], "evidence": None}) for mode in LAYOUTS}
    reader.unchanged()
    return {"schema": "vecna82-ledger-source-visibility-v1", "providers": providers, "per_query": dict(joined),
            "inputs_sha256": reader.hashes, "causal_limit": LIMIT}
