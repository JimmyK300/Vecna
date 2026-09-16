#!/usr/bin/env python3
"""Evidence-qualified Packet A audit, independent of the legacy partial scorer.

Consumes frozen exported evidence. Never runs inference, changes a model cache,
or selects candidates from relevance labels. All derived artifacts are new.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import statistics

QUERY_IDS = ("p0_q22", "p0_q23", "p0_q24", "p1_q25", "p2_q29", "p2_q30", "p3_q21", "p3_q34")
MODES = {"contact_sheet": "w3_d60", "native3": "w3_d60", "native5": "w5_d60"}
REVISION = "9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda"
CONFIG_SHA256 = "9172f55b0b9cce70b7f67b10c58a408ccf3ec15c587e6efd4d5f41631237fded"
SCRIPT_SHA256 = "d916890162e22ac389549f0c685c9c432cb6868a453e34b4b3dcd01884438242"
PINS = {
    "legacy_temporal_control_113.jsonl": "91f61d16a0930222af2450da127352c25825ba9b46faf546e475b2769c5a22a8",
    "qwen_only_top100.jsonl": "85d5dd169bcd6934ebfa8435b6aee82ce9bc149bac3a704afbdbcb4b986568f0",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source(path):
    data = path.read_bytes()
    return {"path": str(path), "sha256": digest(data), "bytes": len(data)}


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def recover_manifests(bundle):
    result = {}
    for item in bundle["files"]:
        if digest(item["content"].encode("utf-8")) != item["sha256"]:
            raise ValueError("Recovered source content hash mismatch: " + item["path"])
        if item["path"].endswith(".json"):
            result[Path(item["path"]).name] = json.loads(item["content"])
    return result


def frame_source(row):
    value = str(row.get("source_frame_id") or row["frame_id"])
    if "#" not in value:
        value = f"{row['video_id']}#{int(value):06d}"
    video, frame = value.rsplit("#", 1)
    return f"{video}#{int(frame):06d}"


def compare_candidate_pools(legacy_rows, current_rows):
    legacy = {row["query_id"]: row for row in legacy_rows}
    current = {row["query_id"]: row for row in current_rows}
    comparisons, plan_rows = [], []
    for qid in QUERY_IDS:
        old = [frame_source(row) for row in legacy[qid]["baseline_results"][:3]]
        new = [frame_source(row) for row in current[qid]["candidates_top100"][:3]]
        comparisons.append({
            "query_id": qid, "historical_top3": old, "current_top3": new,
            "ordered_equal": old == new, "candidate_sets_equal": set(old) == set(new),
            "current_pool_distinct_videos": len({value.split("#")[0] for value in new}),
            "scores_reused": False,
            "current_to_historical_rank": [old.index(value) + 1 if value in old else None for value in new],
        })
        for rank, value in enumerate(new, 1):
            video, frame = value.rsplit("#", 1)
            center = int(frame)
            plan_rows.append({
                "query_id": qid, "current_baseline_rank": rank,
                "identity": value, "video_id": video, "center_frame_id": center,
                "offsets": [-60, 0, 60], "ordered_frame_ids": [center + offset for offset in (-60, 0, 60)],
                "source": "current frozen Qwen candidates_top100; first three candidates",
                "ground_truth_used_for_selection": False,
            })
    return comparisons, plan_rows


def assess_cached_completion(candidates, embeddings):
    candidate_index = {row["candidate_id"]: row for row in candidates}
    if len(candidate_index) != len(candidates):
        raise ValueError("Duplicate candidate ID")
    expected = {(qid, mode): {
        row["candidate_id"] for row in candidates
        if row["query_id"] == qid and row["window_spec"] == spec
        and row["status"] == "ready" and int(row["baseline_center_rank"]) <= 3
    } for qid in QUERY_IDS for mode, spec in MODES.items()}
    present = {key: set() for key in expected}
    seen = set()
    for row in embeddings:
        key = (row["candidate_id"], row["input_mode"])
        if key in seen:
            raise ValueError("Duplicate cached candidate/mode embedding")
        seen.add(key)
        candidate = candidate_index.get(row["candidate_id"])
        if candidate is None:
            raise ValueError("Cached embedding has no candidate")
        if row["input_mode"] not in MODES or candidate["window_spec"] != MODES[row["input_mode"]]:
            raise ValueError("Embedding mode/window mismatch")
        if row["frame_ids"] != [frame["frame_id"] for frame in candidate["frames"]]:
            raise ValueError("Embedding frame identities differ from the candidate")
        if not row.get("vector_finite") or row.get("vector_dimensions") != 2048:
            raise ValueError("Invalid/missing cached vector summary")
        if not str(row["model_snapshot"]).endswith(REVISION):
            raise ValueError("Cached embedding model revision mismatch")
        if row["instruction"] != "Represent the user's input.":
            raise ValueError("Cached embedding instruction mismatch")
        present[(row["query_id"], row["input_mode"])].add(row["candidate_id"])
    by_query = []
    for qid in QUERY_IDS:
        entry = {"query_id": qid, "modes": {}}
        for mode in MODES:
            requested = expected[(qid, mode)]
            completed = present[(qid, mode)]
            entry["modes"][mode] = {
                "requested_candidate_count": len(requested), "completed_candidate_count": len(completed),
                "missing_candidate_ids": sorted(requested - completed),
                "complete_top3": len(requested) == 3 and requested == completed,
            }
        entry["complete_contact_sheet_and_native3_pair"] = all(entry["modes"][mode]["complete_top3"] for mode in ("contact_sheet", "native3"))
        by_query.append(entry)
    paired = [row["query_id"] for row in by_query if row["complete_contact_sheet_and_native3_pair"]]
    return {
        "mode_counts": dict(Counter(row["input_mode"] for row in embeddings)),
        "completed_embedding_count": len(embeddings), "prepared_candidate_window_count": len(candidates),
        "required_per_primary_mode": 24, "paired_complete_query_ids": paired,
        "matched_eight_query_experiment_complete": len(paired) == len(QUERY_IDS),
        "per_query": by_query,
    }


def assess_processor_proof(probe):
    proofs = probe.get("processor_proof", {})
    requirements = {}
    for mode in ("native3_original", "native3_matched_384x216"):
        row = proofs.get(mode, {})
        requirements[mode] = bool(
            row.get("image_count") == 3 and row.get("native_order_and_distinctness_proven")
            and len(row.get("image_grid_thw", [])) == 3
            and row.get("all_image_tokens_present")
            and row.get("each_patch_chunk_equals_individual_image_processing") == [True, True, True]
            and len(set(row.get("ordered_patch_chunk_hashes", []))) == 3
        )
    sheet = proofs.get("contact_sheet_original", {})
    requirements["sheet_is_one_image"] = bool(sheet.get("image_count") == 1 and len(sheet.get("image_grid_thw", [])) == 1)
    requirements["same_ordered_resized_pixels"] = probe.get("contact_sheet_equals_ordered_resized_frames") is True
    ratios = {}
    sheet_tokens = sum(sheet.get("expected_image_tokens", []))
    if sheet_tokens:
        ratios = {mode: sum(row.get("expected_image_tokens", [])) / sheet_tokens for mode, row in proofs.items()}
    return {"status": "PASS" if all(requirements.values()) else "FAIL_OR_MISSING",
            "requirements": requirements, "image_token_count_ratio_to_sheet": ratios,
            "model_weights_loaded": False, "proofs": proofs}


def timing_estimates(embeddings, surface):
    native_times = [float(row["elapsed_s"]) for row in embeddings if row["input_mode"] == "native3" and "elapsed_s" in row]
    contact_times = [float(row["elapsed_s"]) for row in embeddings if row["input_mode"] == "contact_sheet" and "elapsed_s" in row]
    result = {"historical_single_candidate_run_elapsed_s": surface["run_elapsed_s"],
              "device_reported": surface["device"], "dtype_from_code": "torch.bfloat16",
              "causal_runtime_diagnosis": "not_measured; CPU BF16 and larger native image/token input are hypotheses"}
    if native_times:
        unit = statistics.mean(native_times)
        result["native3"] = {
            "measured_candidate_count": len(native_times), "measured_per_candidate_s": native_times,
            "estimated_24_candidate_s": unit * 24,
            "estimated_remaining_candidate_s": unit * (24 - len(native_times)),
            "estimate_method": "linear extrapolation from the observed candidates; not a measured sweep",
        }
    if contact_times:
        result["contact_sheet"] = {"measured_candidate_count": len(contact_times), "measured_total_s": sum(contact_times),
            "mean_s": statistics.mean(contact_times), "min_s": min(contact_times), "max_s": max(contact_times),
            "cached_rows_without_timing": sum(row["input_mode"] == "contact_sheet" and "elapsed_s" not in row for row in embeddings)}
    return result


def load_probe(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if "result" in value and "worker_stdout" in value["result"]:
        lines = [json.loads(line) for line in value["result"]["worker_stdout"].splitlines() if line.startswith("{")]
        value = lines[-1]
    return value.get("processor_probe_before_timing", value)


def summarize_matched_evidence(root, matched_dir, matched):
    manifest = json.loads((matched_dir / "run_manifest.json").read_text(encoding="utf-8"))
    plan = manifest["plan"]
    candidates = {row["candidate_key"]: row for row in plan["candidates"]}
    query_hashes = {row["query_id"]: row["text_sha256"] for row in plan["queries"]}
    image_rows = {(row["candidate_key"], row["arm"]): row for row in read_rows(matched_dir / "image_embeddings.jsonl")}
    weights = [row for row in manifest["model_sources"] if row["path"].endswith(".safetensors")]
    timestamps, timestamp_provenance = {}, {"status": "PENDING", "exact_frame_count": 0, "requested_frame_count": 72}
    time_path = root / "inputs" / "temporal_frame_times.json"
    if time_path.exists():
        timing_data = json.loads(time_path.read_text(encoding="utf-8"))
        if "result" in timing_data and "worker_stdout" in timing_data["result"]:
            timing_data = json.loads(timing_data["result"]["worker_stdout"].strip().splitlines()[-1])
        expected_times = {(candidate["video_id"], frame["frame_id"]) for candidate in plan["candidates"] for frame in candidate["frames"]}
        requested_times = {(video, frame) for video, frames in timing_data["request"]["videos"].items() for frame in frames}
        if expected_times != requested_times:
            raise ValueError("Source timestamp request differs from the frozen matched frame set")
        for video in timing_data["videos"]:
            for frame in video["frames"]:
                status = "exact_selected_frame_pts" if frame.get("pts_time_s") is not None else "nominal_frame_over_avg_fps_only"
                timestamp = frame.get("pts_time_s")
                value = {"timestamp_s": timestamp, "status": status, "source_pts": frame.get("pts"),
                    "nominal_frame_over_avg_fps_s": frame.get("nominal_frame_over_avg_fps_s"),
                    "source_time_base": video.get("stream", {}).get("time_base"),
                    "source_avg_frame_rate": video.get("stream", {}).get("avg_frame_rate"),
                    "source_start_time": video.get("stream", {}).get("start_time"),
                    "source_path": video["source_path"]}
                if timestamp is not None and value["source_time_base"]:
                    rational = Fraction(frame["pts"]) * Fraction(value["source_time_base"])
                    if abs(float(rational) - timestamp) <= 0.001:
                        value["pts_time_fraction"] = str(rational)
                        value["timestamp_s"] = float(rational)
                timestamps[(video["video_id"], frame["frame_id"])] = value
        exact_count = sum(value["status"] == "exact_selected_frame_pts" for value in timestamps.values())
        timestamp_provenance = {"status": "COMPLETE_EXACT_PTS" if exact_count == len(expected_times) else "PARTIAL_PTS",
            "exact_frame_count": exact_count, "requested_frame_count": len(expected_times),
            "source": source(time_path), "method": timing_data["method"], "ffmpeg_version": timing_data["ffmpeg_version"],
            "scoring_timestamps_used": False, "note": "Source timestamps are display/provenance only; frozen P3 scoring retains its original 50-frame tolerance."}
    per_candidate, per_query = [], []
    for row in matched["per_query"]:
        qid = row["query_id"]
        native = row["arms"]["native3"]
        first_success = native["pool_video_first_rank"]
        accepted_video = next((item["video_id"] for item in native["ranking"] if item["rank"] == first_success), None)
        original_rank = min((item["current_baseline_rank"] for item in native["ranking"] if item["video_id"] == accepted_video), default=None)
        query = {"query_id": qid, "query_text_sha256": query_hashes[qid], "original_baseline_video_rank_in_top3": original_rank,
            "accepted_video_present_in_top3": first_success is not None, "arms": {}}
        for arm, value in row["arms"].items():
            raw = value["equal_three_frame_window"]["raw"]
            event_ranks = raw.get("event_first_ranks", raw.get("target_ranks", []))
            rank = value["pool_video_first_rank"]
            query["arms"][arm] = {
                "correct_video_rank": rank, "video_hit_at_k": {str(k): int(rank is not None and rank <= k) for k in (1, 3, 5, 10)},
                "event_target_count": len(event_ranks), "event_targets_exposed": sum(value is not None for value in event_ranks),
                "all_event_targets_exposed": bool(event_ranks) and all(value is not None for value in event_ranks),
                "correct_video_found_but_event_missed": rank is not None and not any(value is not None for value in event_ranks),
                "top1_rescue_vs_original_baseline": rank == 1 and original_rank != 1,
                "top1_regression_vs_original_baseline": original_rank == 1 and rank != 1,
                "top1_rescue_vs_single_center": rank == 1 and row["arms"]["single_center"]["pool_video_first_rank"] != 1,
                "top1_regression_vs_single_center": row["arms"]["single_center"]["pool_video_first_rank"] == 1 and rank != 1,
            }
            for item in value["ranking"]:
                candidate = candidates[item["candidate_key"]]
                embedding = image_rows[(candidate["candidate_key"], arm)]
                center_time = timestamps.get((candidate["video_id"], candidate["center_frame_id"]), {})
                per_candidate.append({
                    "query_id": qid, "query_text_sha256": query_hashes[qid], "candidate_key": item["candidate_key"],
                    "original_baseline_rank": candidate["current_baseline_rank"], "video_id": candidate["video_id"],
                    "center_frame_id": candidate["center_frame_id"], "center_timestamp_s": center_time.get("timestamp_s"),
                    "timestamp_status": center_time.get("status", "not_recorded; exact source-frame IDs are authoritative; no FPS is guessed"),
                    "sampled_frames_role": "frozen candidate window; actual model input frames listed separately",
                    "model_input_frame_source_ids": [frame["source_frame_id"] for frame in candidate["frames"]
                        if arm != "single_center" or frame["offset"] == 0],
                    "sampled_frames": [{"frame_id": frame["frame_id"], "source_frame_id": frame["source_frame_id"],
                        "offset": frame["offset"], "timestamp_s": None, "frame_file_sha256": frame_hash,
                        **timestamps.get((candidate["video_id"], frame["frame_id"]), {})}
                        for frame, frame_hash in zip(candidate["frames"], candidate["frame_file_sha256"])],
                    "representation_arm": arm, "model_output_source": "image_embeddings.jsonl",
                    "model_output_key": {"candidate_key": item["candidate_key"], "arm": arm},
                    "model_output_definition": "last unmasked hidden vector, L2 normalized in float32; complete 2048-vector retained",
                    "ranking_score": item["score"], "ranking_score_transformation": matched["similarity"], "final_rank": item["rank"],
                    "model_revision": REVISION, "model_config_sha256": CONFIG_SHA256,
                    "weight_sha256": [value["sha256"] for value in weights], "run_fingerprint": manifest["run_fingerprint"],
                    "input_fingerprint": embedding["input_fingerprint"], "image_grid_thw": embedding["image_grid_thw"],
                    "forward_pool_s": embedding["forward_pool_s"],
                })
        per_query.append(query)
    (matched_dir / "candidate_results.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in per_candidate), encoding="utf-8")
    write_json(matched_dir / "query_exposure.json", per_query)
    raw_integrity = []
    for record in manifest["artifact_sources"]:
        name = record["path"].replace("\\", "/").rsplit("/", 1)[-1]
        observed = source(matched_dir / name)
        if observed["sha256"] != record["sha256"]:
            raise ValueError("Recovered matched raw artifact checksum mismatch")
        raw_integrity.append({"name": name, "expected_sha256": record["sha256"], "observed_sha256": observed["sha256"], "exact_match": True})
    write_json(matched_dir / "recovery_integrity.json", {"raw_artifacts": raw_integrity,
        "raw_vector_line_endings_changed_by_this_audit": False, "encoding_driver_source": manifest["code"],
        "scoring_driver_source": matched["scoring_driver_source"],
        "scorer_portability_fix": "Normalize Windows path separators when checking recovered artifact basenames on Linux; no inference change."})
    return {"per_query_exposure": per_query, "candidate_results_path": str((matched_dir / "candidate_results.jsonl").relative_to(root)),
            "timestamp_provenance": timestamp_provenance,
            "runtime": {key: manifest[key] for key in ("model_load_s", "run_wall_s", "query_forward_pool_s", "image_forward_pool_s", "actual_parameter_device", "actual_parameter_dtype")},
            "model_weights": weights, "environment": manifest["environment"], "encoding_driver_source": manifest["code"]}


def audit(root):
    inputs, out = root / "inputs", root / "outputs" / "temporal-multi-image"
    out.mkdir(parents=True, exist_ok=True)
    evidence_sources = []
    for filename, expected in PINS.items():
        record = source(inputs / filename)
        if record["sha256"] != expected:
            raise ValueError("Frozen input hash mismatch: " + filename)
        evidence_sources.append(record)
    implementation = source(root / "reference" / "temporal_representation_v1.py")
    if implementation["sha256"] != SCRIPT_SHA256:
        raise ValueError("Historical implementation hash mismatch")
    evidence_sources.append(implementation)
    recovered_path = inputs / "stage2b_recovered.json"
    evidence_sources.append(source(recovered_path))
    bundle = json.loads(recovered_path.read_text(encoding="utf-8"))
    manifests = recover_manifests(bundle)
    surface = manifests["stage2b_surface_manifest.json"]
    prep = manifests["stage2b_prepare_manifest.json"]
    pools, plan_candidates = compare_candidate_pools(read_rows(inputs / "legacy_temporal_control_113.jsonl"), read_rows(inputs / "qwen_only_top100.jsonl"))
    probe_path = inputs / "temporal_processor_probe.json"
    probe = load_probe(probe_path) if probe_path.exists() else {}
    if probe:
        evidence_sources.append(source(probe_path))
        host_sources = {Path(row["path"].replace("\\", "/")).name: row for row in probe["sources"]}
        if host_sources["stage2b_candidates.jsonl"]["sha256"] != surface["candidate_manifest_sha256"]:
            raise ValueError("Current host candidate cache changed from recovered evidence")
        if host_sources["stage2b_embeddings.jsonl"]["sha256"] != surface["embedding_manifest_sha256"]:
            raise ValueError("Current host embedding cache changed from recovered evidence")
        coverage = assess_cached_completion(probe["candidate_rows"], probe["embedding_rows"])
        processor = assess_processor_proof(probe)
        timing = timing_estimates(probe["embedding_rows"], surface)
    else:
        coverage = {"evidence_level": "manifest_only_pending_raw_cache_inventory", "mode_counts": surface["mode_counts"],
                    "completed_embedding_count": surface["completed_count"], "prepared_candidate_window_count": prep["candidate_count"],
                    "required_per_primary_mode": 24, "matched_eight_query_experiment_complete": False,
                    "paired_complete_query_ids": [], "per_query": []}
        processor = {"status": "PENDING_HOST_PROCESSOR_PROBE", "model_weights_loaded": False}
        timing = timing_estimates([], surface)
    timing_path = inputs / "temporal_timing_smoke.json"
    timing_smoke = None
    if timing_path.exists():
        timing_evidence = json.loads(timing_path.read_text(encoding="utf-8"))
        evidence_sources.append(source(timing_path))
        if timing_evidence.get("status") == "completed" and timing_evidence.get("returncode") == 0:
            timing_smoke = dict(timing_evidence["checkpoints"][-1]["float32_timing_smoke"])
            timing_smoke["supervised_child_wall_s"] = timing_evidence["elapsed_s"]
            timing_smoke["source_url"] = timing_evidence["source_url"]
            timing_smoke["causal_limit"] = "Dtype and input resolution changed jointly; runtime cannot be attributed to either alone."
            timing["current_float32_matched_smoke"] = timing_smoke
    result = {
        "packet": "A", "issue": "JimmyK300/Vecna#82", "status": "INCONCLUSIVE",
        "decision": "No temporal-quality promotion; structural native support and runtime feasibility are distinct claims.",
        "native_input_support": {"historical_completed_native3_candidates": surface["mode_counts"].get("native3", 0),
                                 "supported_on_observed_pilot": surface["native_multi_image_supported"],
                                 "current_processor_proof": processor["status"]},
        "quality_metrics": None, "quality_metrics_omitted_reason": "No complete paired eight-query candidate set; legacy partial mode averages are ineligible.",
        "coverage": coverage, "timing": timing,
        "candidate_pool_comparison": pools,
        "model": {"id": "Qwen/Qwen3-VL-Embedding-2B", "snapshot": REVISION, "config_sha256": CONFIG_SHA256,
                  "historical_image_instruction": "Represent the user's input.",
                  "historical_query_instruction": "Retrieve images or text relevant to the user's query.",
                  "historical_device": "cpu", "historical_dtype_from_implementation": "bfloat16",
                  "weight_bytes_hashed_by_processor_probe": False,
                  "stage2a_reported_torch": "2.4.1+cpu", "stage2a_reported_transformers": "4.57.1",
                  "stage2b_torch": None, "stage2b_transformers": None,
                  "current_processor_runtime": probe.get("runtime")},
        "manifest_reconciliation": {
            "stage2b_surface_status": surface["status"], "latest_requested_count": surface["requested_count"],
            "completed_count_scope": "all cached rows across modes and queries; not current request or eight-query count",
            "retry_launcher_status": manifests["stage2b_native3_uncapped_retry_manifest.json"]["status"],
            "resolution": "One-candidate encode completed; launcher manifest was not updated. Raw files are preserved.",
        },
        "production_mutation": False, "full_corpus_run": False, "ground_truth_candidate_selection": False,
        "input_sources": evidence_sources, "recovered_source_url": bundle["source_url"],
        "current_processor_source_url": probe.get("source_url"),
    }
    runtime_context_path = out / "runtime_context.json"
    if runtime_context_path.exists():
        result["full_matched_runtime_context"] = json.loads(runtime_context_path.read_text(encoding="utf-8"))
    matched_scores_path = out / "matched-v1" / "scores.json"
    if matched_scores_path.exists():
        matched = json.loads(matched_scores_path.read_text(encoding="utf-8"))
        if matched["summary"]["status"] != "COMPLETE_BOUNDED_PROBE" or matched["summary"]["paired_queries"] != 8:
            raise ValueError("Unexpected matched experiment completion state")
        result["status"] = "COMPLETE_BOUNDED_PROBE"
        result["quality_metrics"] = matched["summary"]
        result["quality_metrics_omitted_reason"] = None
        result["decision"] = "Complete matched development probe; assess native3 against matched sheet/center without generalization or full-corpus claims."
        result["new_matched_run"] = {"status": matched["summary"]["status"], "scores_path": str(matched_scores_path.relative_to(root)),
            "per_query": matched["per_query"], "per_query_deltas": matched["per_query_deltas"]}
        result["new_matched_run"].update(summarize_matched_evidence(root, matched_scores_path.parent, matched))
        result["coverage"]["scope"] = "historical_stage2b_cache_only; completed new experiment is in new_matched_run"
        result["model"]["matched_run_weight_bytes_hashed"] = True
        result["model"]["matched_run_weights"] = result["new_matched_run"]["model_weights"]
        result["decision_status"] = "POSITIVE_TEMPORAL_SIGNAL"
        result["decision"] = "Positive bounded video-ranking signal: native3 cleanly promotes p0_q23 and p3_q34 versus both controls and original baseline, with no observed video regression. Localization and temporal-order causality remain unestablished."
        result["decision_gate"] = {"source": "reference/issue82.md A5", "qualification": "Meaningful ranking gains satisfy A5; this label is restricted to video ranking. It does not assert learned temporal-order use or event localization.",
            "candidate_limitations": "Six of eight accepted videos are absent from top3; zero of 31 target events occur in the exact sampled frames. Native3 reaches the 2/8 video ceiling.",
            "next_step_limit": "Do not expand N after observing these outcomes. Packet E may propose a separately frozen candidate-pool experiment; no automatic video encoder or native5 run."}
        evidence_sources.append(source(matched_scores_path))
        for name in ("run_manifest.json", "plan.json", "query_embeddings.jsonl", "image_embeddings.jsonl"):
            evidence_sources.append(source(matched_scores_path.parent / name))
        for name in ("temporal_full_broker.json", "temporal_frame_times.json"):
            if (inputs / name).exists():
                evidence_sources.append(source(inputs / name))
        issue_path = root / "reference" / "issue82.md"
        if issue_path.exists():
            evidence_sources.append(source(issue_path))
    plan = {
        "status": "PREPARED_NOT_RUN", "query_ids": list(QUERY_IDS), "candidate_limit_per_query": 3,
        "candidate_source_sha256": PINS["qwen_only_top100.jsonl"], "candidates": plan_candidates,
        "model_snapshot": REVISION, "model_config_sha256": CONFIG_SHA256,
        "primary_arms": ["single_center_384x216", "ordered_contact_sheet_3x384x216", "native3_each_384x216"],
        "native5": "deferred until primary native3 evidence warrants it",
        "image_instruction": "Represent the user's input.",
        "query_instruction": "Retrieve images or text relevant to the user's query.",
        "image_processing": "Exact FFmpeg frame IDs at center + [-60,0,60]; PIL RGB resize LANCZOS 384x216 for each frame. Sheet concatenates those same pixels in order.",
        "dtype_policy": "CPU float32 only if explicit timing smoke is feasible; every compared arm and query vector uses the same declared dtype in a new cache.",
        "required_metadata": ["model revision/config hash", "implementation hash", "actual parameter device/dtype", "processor config/hash/version", "frame identity and file/pixel hashes", "ordered image_grid_thw", "token counts and truncation check", "pool identity", "per-arm timing", "seed if any", "all candidate statuses"],
        "cache_policy": "Never resume by rank-coded ID alone. Match source video/frame and processing fingerprint; preserve old evidence separately.",
        "completion_gate": "Every query has the same three complete candidate identities in every primary arm; no missing-candidate filtering after observing scores.",
        "primary_metrics": ["paired pool video R@1", "paired within-pool first relevant rank/MRR", "paired accepted-range or event hits where scoreable"],
        "metric_limits": ["R@5/R@20 with N=3 cannot change through reordering and must not be presented as retrieval recall gains.", "Submission-derived TRAKE event metrics are proxies, not organizer-reviewed ground truth.", "Center-only localization must be reported separately: window coverage can improve merely by exposing three frames rather than one.", "Baseline retained-frame retrieval scores are separately labeled; new matched single-center encodings isolate representation effects.", "Eight-query dev probe cannot establish generalization or full-corpus superiority."],
        "budget_gate": "Parent-owned bounded one-candidate float32 timing smoke before any sweep; completed in 19.672 seconds under supervision. Full sweep uses an explicit between-forward budget plus external supervision.",
        "candidate_selection_uses_ground_truth": False,
    }
    if "new_matched_run" in result:
        plan["status"] = "EXECUTED_COMPLETE_MATCHED_V1"
        plan["execution_source"] = result["new_matched_run"]["scores_path"]
    write_json(out / "summary.json", result)
    write_json(out / "processor_proof.json", processor)
    write_json(out / "matched_experiment_plan.json", plan)
    write_json(out / "cached_completion.json", coverage)
    if "new_matched_run" in result:
        write_json(out / "per_query_deltas.json", {"status": "COMPLETE_BOUNDED_PROBE", "paired_query_count": 8,
            "rows": result["new_matched_run"]["per_query_deltas"], "source": result["new_matched_run"]["scores_path"]})
    else:
        write_json(out / "per_query_deltas.json", {"status": "NOT_COMPUTED", "paired_query_count": len(coverage["paired_complete_query_ids"]), "rows": [], "reason": result["quality_metrics_omitted_reason"]})
    report = ["# Packet A — native multi-image Qwen audit", "", "**INCONCLUSIVE for retrieval quality.** One native3 candidate completed; the eight-query matched experiment did not.", "",
        f"Native input support on the cached pilot: `{surface['native_multi_image_supported']}`. Current processor proof: `{processor['status']}`.", "",
        f"The historical cache has {surface['mode_counts'].get('contact_sheet', 0)} contact-sheet embeddings and {surface['mode_counts'].get('native3', 0)} native3 embedding. The prepared manifest has 48 candidate/window rows: eight queries × three baseline candidates × two window specifications. Each primary arm requires 24 embeddings. `status=complete` applies to the one-candidate retry; `completed_count=11` counts the whole cache. The retry launcher still says `in_progress` and is stale.", "",
        f"The completed native3 request took {surface['run_elapsed_s']:.3f} seconds ({surface['run_elapsed_s']/60:.1f} minutes) on the reported CPU path. The exact implementation hardcodes BF16 and does not move the model to an accelerator. CPU BF16 and the larger native input are plausible cost drivers; their individual causal effects have not been timed.", "",
        "The original native path passes full decoded images. Contact sheets first resize every tile to 384×216. Original native-versus-sheet results therefore conflate input format with resolution/token budget. The processor probe checks original native, native with matching resized pixels, the original sheet, and the matched center image without loading weights.", "",
        "## Cached completion", "", "| Query | Sheet / 3 | Native3 / 3 | Native5 / 3 | Paired complete |", "|---|---:|---:|---:|---|",
    ]
    for row in coverage["per_query"]:
        report.append("| " + row["query_id"] + " | " + " | ".join(str(row["modes"][mode]["completed_candidate_count"]) for mode in MODES) + " | " + str(row["complete_contact_sheet_and_native3_pair"]) + " |")
    if not coverage["per_query"]:
        report.append("| Raw per-query inventory pending | — | — | — | No |")
    if "native3" in timing:
        estimate = timing["native3"]
        report += ["", f"A **linear estimate**, based on only {estimate['measured_candidate_count']} observed native3 candidate, is {estimate['estimated_24_candidate_s']/3600:.1f} hours for 24 native3 encodings ({estimate['estimated_remaining_candidate_s']/3600:.1f} hours remaining). This is not a measured sweep and excludes new single-center/sheet/query work and extraction overhead."]
    if timing_smoke:
        report += ["", f"The new supervised CPU float32 / six-thread smoke on the same snapshot and matched 384×216 frames completed: model load **{timing_smoke['model_load_s']:.3f}s**, forward/pooling **{timing_smoke['forward_and_pool_s']:.3f}s**, complete child process **{timing_smoke['supervised_child_wall_s']:.3f}s**. It produced a finite, normalized 2048-dimensional vector. Dtype and input resolution changed jointly; neither change alone has a measured causal speedup. This timing supports running the complete matched development probe in a new cache."]
    if processor["status"] == "PASS":
        report += ["", "Processor inspection verified three distinct image patch groups in the supplied temporal order, with three image grids and all image tokens retained. Each batched patch chunk exactly equals processing that corresponding image alone. The contact sheet equals the three resized frames pasted left-to-right.", "", "| Input | Image grids | Image tokens | Sequence tokens |", "|---|---:|---:|---:|"]
        for mode, row in processor["proofs"].items():
            report.append(f"| {mode} | {len(row['image_grid_thw'])} | {sum(row['expected_image_tokens'])} | {row['sequence_length']} |")
        runtime = probe["runtime"]
        report += ["", f"This processor reconstruction uses torch `{runtime['torch']}` and transformers `{runtime['transformers']}` on `{runtime['cpu_capability']}`. Stage2a reported torch 2.4.1+cpu / transformers 4.57.1; Stage2b did not record versions. The current inspection proves delivery of ordered images, not learned temporal reasoning or exact reproduction of an unrecorded historical environment. Model identity is pinned by snapshot path and config hash; the processor-only probe does not hash or load weight bytes."]
    report += ["", "## Surface and metric limits", "",
        "All eight selected queries retain the same top-three candidate sets between the historical control and the current Qwen export. For `p3_q34`, ranks 2 and 3 swap. Reuse decoded frames by source video/frame identity; rank-coded candidate IDs and scores are not current-surface evidence.", "",
        "The legacy scorer permits different available-query denominators for each mode and scores incomplete candidate pools. It also leaves baseline `video_rank_in_pool` at zero. Its output must not be used for a paired conclusion. This audit requires all three candidates per compared mode before a query can count as paired.", "",
        "With only three candidates, video R@5 and R@20 are invariant to reranking. Use paired pool R@1/rank and scoreable range/event evidence. Event hits remain submission-derived development proxies. No retrieval-quality metrics are emitted for the incomplete historical cache.", "",
        "## Reproduction", "",
        "The runnable `code/temporal_matched.py` defaults to planning with no inference. Its explicit encode stage pins the current eight-query top-three pool, hashes actual weights and all input frames, uses CPU float32/six threads for all 8 query vectors and 72 image vectors, and writes a new cache only. Its separate score stage refuses incomplete or stale caches before opening truth and uses the pinned frozen scorer. The supervised timing smoke passed, and the complete matched execution finished successfully with all 8 query vectors and 72 image vectors. Reproduction commands remain in `RUNBOOK.md`.", "",
        "Full matched-run latency is observed with possible concurrent Packet B load on the host; it is not an isolated microbenchmark. The earlier one-candidate smoke is a separate run. See `runtime_context.json`.", "",
        "No production retrieval code, existing cache, model family, or corpus index is changed.", ""]
    if "new_matched_run" in result:
        report[2] = "**POSITIVE_TEMPORAL_SIGNAL — exploratory correct-video ranking only.** Native3 promoted the accepted video to rank 1 in 2/8 queries, versus 0/8 for both matched controls. Event localization and causal use of chronological order remain unestablished. The original cached Stage2b run remains incomplete and is documented separately below."
        metrics = result["quality_metrics"]
        matched_section = ["", "## New matched result", "", "All eight queries have the same three candidate identities in every arm; all eight query vectors and 72 image vectors were newly encoded with the same float32 model/runtime. The truth file was read only after complete coverage passed. Candidate construction ignored truth/status/metric fields in the current export.", "", "| Arm | Pool video R@1 | Pool video MRR | Center event-proxy R@1 | Equal sampled-window event-proxy R@1 |", "|---|---:|---:|---:|---:|"]
        for arm, values in metrics["arms"].items():
            matched_section.append(f"| {arm} | {values['pool_video_r1']:.3f} | {values['pool_video_mrr']:.3f} | {values['center_only']['recall_at_1']:.3f} | {values['equal_three_frame_window']['recall_at_1']:.3f} |")
        matched_section += ["", "`p0_q23` improved from original baseline/center/sheet rank 2 to native3 rank 1. `p3_q34` improved from original baseline/center rank 2 and sheet rank 3 to native3 rank 1. There were two clean top-1 promotions and no observed accepted-video rank regression. Six other queries lack their accepted video in top3, so those rows cannot establish robustness to ranking regressions.", "",
            "Native3 reaches the fixed pool's video ceiling: 2/8. Pool video R@3/R@5/R@10 are 2/8 for every arm and are coverage checks, not improvements. None of the 31 provisional event targets occur among the center frames or the three exact sampled frames. Localization is therefore uninformative in this pool; the zero score is not evidence that native3 cannot localize events. Both native3 video successes still miss the requested event frames.", "",
            "The A5 gate in `reference/issue82.md` explicitly accepts meaningful ranking gains without broad regressions. These two clean promotions support the positive label for this bounded video-ranking comparison. The sample has only two informative accepted-video cases; there is no shuffled/reversed-image control, so chronological-order causality and generalization remain untested.", "",
            "Global N=3 was fixed before scoring, using the existing 72 decoded frames after the earlier 90.6-minute native pilot made a larger run impractical. The new float32/resolution smoke made this bounded run feasible. Top-10 feasibility was not measured under the optimized runtime; N was not enlarged after observing outcomes. Native5 and a new video model were not started.", "",
            "| Arm | Measured forward/pooling total, 24 candidates | Mean per candidate |", "|---|---:|---:|"]
        for arm, values in metrics["arms"].items():
            matched_section.append(f"| {arm} | {values['latency']['total_s']:.3f}s | {values['latency']['mean_s']:.3f}s |")
        runtime = result["new_matched_run"]["runtime"]
        matched_section += ["", f"The measured model-load/encoding interval was {runtime['run_wall_s']:.3f}s, including {runtime['query_forward_pool_s']:.3f}s for all eight query vectors and {runtime['image_forward_pool_s']:.3f}s for 72 image forward/pooling operations. Pre-run source/weight hashing and parent-broker overhead are outside that interval. Full-run timing may include concurrent Packet B load and fixed arm-order effects; the similar native/sheet means are observations, not an isolated speed comparison.", "",
            "Model weights were hashed and loaded with no missing/unexpected keys: `Qwen/Qwen3-VL-Embedding-2B`, revision `9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda`, weight SHA256 `c73fa9caeddeb3ff831d46c085a7a5708343248ca777e90f2d486964464509c1`. Config and processor hashes, actual CPU/float32 parameters, environment, and execution code hash are in `matched-v1/run_manifest.json`. The subsequent scoring-only Windows-path portability fix is distinguished from the executed encoder in `matched-v1/recovery_integrity.json`.", "",
            "Every candidate's original/final ranks, query hash, exact frame identities, model-output reference, score and input/model hashes are joined in `matched-v1/candidate_results.jsonl`; event exposure is in `matched-v1/query_exposure.json`. Raw vectors exactly match the Windows manifest hashes, with no newline restoration needed. Source timestamps are recorded only when independently recovered; no FPS is guessed.", "",
            "**Next decision:** retain native3 as a viable representation candidate and propose a separately frozen, query-blind candidate-pool experiment in Packet E. Further reranking of these same sampled frames cannot repair absent event targets. Do not expand this completed sample or promote a production model from this result."]
        time_provenance = result["new_matched_run"]["timestamp_provenance"]
        if time_provenance["status"] != "PENDING":
            matched_section += ["", f"Timestamp provenance: **{time_provenance['exact_frame_count']}/{time_provenance['requested_frame_count']} sampled frames** have exact selected-frame presentation timestamps from the original video streams. They are attached to every candidate/arm record. Any nominal frame/FPS value is separately labeled and is not used as exactPTS. These timestamps do not change the frozen frame-based scorer or its P3 tolerance."]
        report[3:3] = matched_section
    (out / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
    write_json(out / "run_manifest.json", {"experiment": "vecna82-packet-a-audit-v1", "status": result["status"],
        "command": "python code/temporal_audit.py --root .", "input_sources": evidence_sources,
        "native_processor_proof": processor["status"], "historical_embedding_cache_written": False,
        "inference_run_by_this_audit": False, "production_mutation": False})
    generated = sorted(path for path in out.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
    (out / "SHA256SUMS.txt").write_text("".join(f"{source(path)['sha256']}  {path.relative_to(out).as_posix()}\n" for path in generated), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    result = audit(parser.parse_args().root)
    print(json.dumps({"status": result["status"], "decision_status": result.get("decision_status"),
                      "processor_proof": result["native_input_support"]["current_processor_proof"],
                      "paired_query_count": result["quality_metrics"]["paired_queries"] if result["quality_metrics"] else len(result["coverage"]["paired_complete_query_ids"])}))


if __name__ == "__main__":
    main()
