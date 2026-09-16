#!/usr/bin/env python3
"""Evidence-qualified Packet A audit, independent of the legacy partial scorer.

Consumes frozen exported evidence. Never runs inference, changes a model cache,
or selects candidates from relevance labels. All derived artifacts are new.
"""
from __future__ import annotations

import argparse
from collections import Counter
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
        "budget_gate": "Parent-owned one-candidate float32 timing smoke with <=120s supervised cap before any sweep; no uncapped retry.",
        "candidate_selection_uses_ground_truth": False,
    }
    write_json(out / "summary.json", result)
    write_json(out / "processor_proof.json", processor)
    write_json(out / "matched_experiment_plan.json", plan)
    write_json(out / "cached_completion.json", coverage)
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
    if processor["status"] == "PASS":
        report += ["", "Processor inspection verified three distinct image patch groups in the supplied temporal order, with three image grids and all image tokens retained. Each batched patch chunk exactly equals processing that corresponding image alone. The contact sheet equals the three resized frames pasted left-to-right.", "", "| Input | Image grids | Image tokens | Sequence tokens |", "|---|---:|---:|---:|"]
        for mode, row in processor["proofs"].items():
            report.append(f"| {mode} | {len(row['image_grid_thw'])} | {sum(row['expected_image_tokens'])} | {row['sequence_length']} |")
        runtime = probe["runtime"]
        report += ["", f"This processor reconstruction uses torch `{runtime['torch']}` and transformers `{runtime['transformers']}` on `{runtime['cpu_capability']}`. Stage2a reported torch 2.4.1+cpu / transformers 4.57.1; Stage2b did not record versions. The current inspection proves delivery of ordered images, not learned temporal reasoning or exact reproduction of an unrecorded historical environment. Model identity is pinned by snapshot path and config hash; the processor-only probe does not hash or load weight bytes."]
    report += ["", "## Surface and metric limits", "",
        "All eight selected queries retain the same top-three candidate sets between the historical control and the current Qwen export. For `p3_q34`, ranks 2 and 3 swap. Reuse decoded frames by source video/frame identity; rank-coded candidate IDs and scores are not current-surface evidence.", "",
        "The legacy scorer permits different available-query denominators for each mode and scores incomplete candidate pools. It also leaves baseline `video_rank_in_pool` at zero. Its output must not be used for a paired conclusion. This audit requires all three candidates per compared mode before a query can count as paired.", "",
        "With only three candidates, R@5 and R@20 are invariant to reranking. Use paired pool R@1/rank and scoreable range/event evidence. Event hits remain submission-derived development proxies. No retrieval-quality metrics are emitted for this incomplete run.", "",
        "## Next executable step", "",
        "The matched plan pins the current eight-query top-three pool and keeps the same model revision. Run a parent-supervised, one-candidate CPU float32 timing smoke using matched 384×216 frames with a 120-second cap. It is timing-only and cannot update the old embedding cache. If feasible, run every primary arm with the same dtype/processor in a new cache and enforce complete paired coverage. If infeasible, keep Packet A inconclusive and defer further temporal inference on this host.", "",
        "No production retrieval code, existing cache, model family, or corpus index is changed.", ""]
    (out / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
    write_json(out / "run_manifest.json", {"experiment": "vecna82-packet-a-audit-v1", "status": result["status"],
        "command": "python code/temporal_audit.py --root .", "input_sources": evidence_sources,
        "native_processor_proof": processor["status"], "historical_embedding_cache_written": False,
        "inference_run_by_this_audit": False, "production_mutation": False})
    generated = sorted(path for path in out.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt")
    (out / "SHA256SUMS.txt").write_text("".join(f"{source(path)['sha256']}  {path.name}\n" for path in generated), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    result = audit(parser.parse_args().root)
    print(json.dumps({"status": result["status"], "processor_proof": result["native_input_support"]["current_processor_proof"],
                      "paired_query_count": len(result["coverage"]["paired_complete_query_ids"])}))


if __name__ == "__main__":
    main()
