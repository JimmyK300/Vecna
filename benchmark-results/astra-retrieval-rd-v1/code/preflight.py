#!/usr/bin/env python3
"""Freeze Vecna #82's saved control; never call a model or alter rankings.

Run from any directory: python code/preflight.py [--root DIR] [--check].
The checked-in source pins are the authority, not whichever files happen to
exist on the local inference host. Optional broker observations describe host
readiness separately; their absence never prevents saved-ranking analysis.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
VECNA_MAIN = "95d63a6abf10c598e0e54af7d2071bedbe542d1e"
TRUTH_REF = "f0b0f4707ceab91ba7e266f72fa982dce3ae1c4b"
DATASET_REF = "1f1ad1baef1e1d31817f6c5a12d4d94133611038"
TRUTH_SHA256 = "63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f"
QUERY_SHA256 = "bd15d05f6c8f00597cced4f50914547ca0b3de75a9e57ee262a4f4ba292485aa"
EXCLUDED = {"p0_q15", "p3_q09"}
PHASE_COUNTS = {"P0": 24, "P1": 25, "P2": 30, "P3": 36}
EXPECTED_IDS = {f"{p.lower()}_q{i:02d}" for p, n in PHASE_COUNTS.items() for i in range(1, n + 1)}
EVAL_PATH = "evaluation/headless-current-p0-p1-p2-p3-qwen-only-top100-v0/"
ARCHIVE_PATH = "experiments/vecna-reranker-fusion-v1-20260914/"

# local path, repository, immutable commit, repository path, Git blob SHA-1.
PINNED_SOURCES = [
    ("inputs/canonical_truth.jsonl", "JimmyK300/Vecna", TRUTH_REF, "benchmark-results/issue34-current-115/ground_truth_current_115.jsonl", "7a1ea48bff3d33336ff37f3fb51da699c4e701c0"),
    ("inputs/canonical_truth.meta.json", "JimmyK300/Vecna", TRUTH_REF, "benchmark-results/issue34-current-115/ground_truth_current_115.meta.json", "33a8ef21dc9f76539b3fc73c12c8da2b5ed2ed56"),
    ("reference/build_issue34_current_115_truth.py", "JimmyK300/Vecna", TRUTH_REF, "aic51-src/script/build_issue34_current_115_truth.py", "c11838cc259f28afef1d40a486deb6d342f26d9d"),
    ("inputs/historical_manifest.json", "JimmyK300/Vecna", "e0981b9022723f0a8bb20d4ccb108f725f4f2e50", "benchmark-results/headless-vnext-p0-p1-p2-v1/manifest.json", "396fcc70df9a0af14e705720104f38bb2dd47828"),
    ("inputs/qwen_only_top100.jsonl", "JimmyK300/official-dataset-control", DATASET_REF, EVAL_PATH + "qwen_only_top100.jsonl", "207476ce2f6ba6121e1a5255448138c702b47fb1"),
    ("inputs/qwen3_vl_reranker_2b_top100.json", "JimmyK300/official-dataset-control", DATASET_REF, EVAL_PATH + "qwen3_vl_reranker_2b_top100.json", "71b751c36cbf5cab6611b10ab5edf391ee078e0f"),
    ("inputs/comparison_qwen_vs_reranker.json", "JimmyK300/official-dataset-control", DATASET_REF, EVAL_PATH + "comparison_qwen_vs_reranker.json", "b9ab1328a7ee9f7339e69ba24fc5edcc59657d1a"),
    ("inputs/original_truth_ledger.jsonl", "JimmyK300/official-dataset-control", DATASET_REF, EVAL_PATH + "ground_truth_current_115.jsonl", "797fe9ef462fffa32e86af4419f0fb69e916293b"),
    ("inputs/reranker.stdout.log", "JimmyK300/official-dataset-control", DATASET_REF, EVAL_PATH + "reranker.stdout.log", "f8a506439d813d780e44db1288ac95efa373bf06"),
    ("reference/evaluate_reranker_fusion.py", "JimmyK300/official-dataset-control", DATASET_REF, ARCHIVE_PATH + "code/aic51-src/script/evaluate_reranker_fusion.py", "1c47b0abe5d81730e33f10d9c33d627d50cae58c"),
    ("inputs/previous_controls.json", "JimmyK300/official-dataset-control", DATASET_REF, ARCHIVE_PATH + "artifacts/controls/controls.json", "e52e2afc351afac0fc6cf32cd89540a45f1bfb6e"),
    ("inputs/temporal_surface.json", "JimmyK300/official-dataset-control", DATASET_REF, "experiments/temporal-sequence-retrieval-v1/surface_manifest.json", "84e1b7efbb28f814d682fd389924c60ca99a7208"),
    ("inputs/temporal_control_manifest.json", "JimmyK300/official-dataset-control", DATASET_REF, "experiments/temporal-sequence-retrieval-v1/control_manifest.json", "28cc572e6baf01f1382b39cdc872b975b402f99e"),
    ("inputs/capability_p0.jsonl", "JimmyK300/official-dataset-control", DATASET_REF, "evaluation/queries/benchmark/capability-decomposition-v0/p0.jsonl", "2e56403a52c4fc49d2aadb87196bef646ed5556e"),
    ("inputs/capability_p1.jsonl", "JimmyK300/official-dataset-control", DATASET_REF, "evaluation/queries/benchmark/capability-decomposition-v0/p1.jsonl", "a2668984dc020619989efcf6c146e0ed6300a535"),
    ("inputs/capability_p2.jsonl", "JimmyK300/official-dataset-control", DATASET_REF, "evaluation/queries/benchmark/capability-decomposition-v0/p2.jsonl", "80ecd87d9ddb8b44033c07f11193bb53593d0117"),
    ("inputs/capability_p3.jsonl", "JimmyK300/official-dataset-control", DATASET_REF, "evaluation/queries/benchmark/capability-decomposition-v0/p3.jsonl", "1e28904f7f8537592e4617b8f16e55c4df81e02c"),
]
OPTIONAL_PINNED_SOURCES = [
    ("inputs/legacy_temporal_control_113.jsonl", "JimmyK300/official-dataset-control", DATASET_REF, "experiments/temporal-sequence-retrieval-v1/control_113.jsonl", "12cd9b33fec74ace71c6dabd1d83b2b593ac0b8d"),
]


class PreflightError(RuntimeError):
    """An input or asserted identity failed closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def json_hash(value: Any) -> str:
    return sha256(canonical_json(value))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_sources(root: Path) -> list[dict]:
    recorded = read_json(root / "inputs/sources.json")
    fields = ("local", "repository", "commit", "path", "blob_sha")
    known = {row[0]: dict(zip(fields, row)) for row in PINNED_SOURCES + OPTIONAL_PINNED_SOURCES}
    required = {row[0] for row in PINNED_SOURCES}
    actual_names = [source["local"] for source in recorded]
    require(len(actual_names) == len(set(actual_names)) and required <= set(actual_names), "Source registry differs from the reviewed immutable pins")
    require(all(source == known.get(source["local"]) for source in recorded), "Source registry differs from the reviewed immutable pins")
    require(all(not (root / row[0]).is_file() or row[0] in actual_names for row in OPTIONAL_PINNED_SOURCES),
            "Optional source exists without its reviewed registry pin")
    expected = [known[row[0]] for row in PINNED_SOURCES + OPTIONAL_PINNED_SOURCES if row[0] in actual_names]
    checked = []
    for source in expected:
        raw = (root / source["local"]).read_bytes()
        blob_sha = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        require(blob_sha == source["blob_sha"], f"Git blob mismatch: {source['local']}")
        checked.append({**source, "bytes": len(raw), "sha256": sha256(raw), "git_blob_verified": True})
    return checked


def load_reference(root: Path, filename: str):
    spec = importlib.util.spec_from_file_location("vecna82_" + filename.replace(".", "_"), root / "reference" / filename)
    require(spec is not None and spec.loader is not None, f"Cannot load reference {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def query_index(rows: list[dict], label: str) -> dict[str, dict]:
    ids = [row.get("query_id") for row in rows]
    require(len(ids) == len(set(ids)), f"Duplicate query identity: {label}")
    require(set(ids) == EXPECTED_IDS, f"115-query identity mismatch: {label}")
    require(all(isinstance(row.get("query"), str) and row["query"].strip() for row in rows), f"Missing query text: {label}")
    return {row["query_id"]: row for row in rows}


def verify_queries(canonical: list[dict], **surfaces: list[dict]) -> dict:
    index = query_index(canonical, "canonical truth")
    text_projection = [{"query_id": qid, "query": index[qid]["query"]} for qid in sorted(index)]
    require(json_hash(text_projection) == QUERY_SHA256, "Canonical query-text hash mismatch")
    require(dict(Counter(row["canonical_round"] for row in canonical)) == PHASE_COUNTS, "Phase counts changed")
    excluded = {row["query_id"] for row in canonical if not row.get("scoreable")}
    require(excluded == EXCLUDED, f"Scoreability exclusions changed: {sorted(excluded)}")
    for label, rows in surfaces.items():
        other = query_index(rows, label)
        require(all(index[qid]["query"] == other[qid]["query"] for qid in index), f"Exact query-text mismatch: {label}")
    return {"total": 115, "scoreable": 113, "excluded_ids": sorted(EXCLUDED),
            "excluded_source_keys": {qid: index[qid].get("canonical_source_key") for qid in sorted(EXCLUDED)},
            "phase_counts": PHASE_COUNTS, "scoreable_phase_counts": {p: sum(r["canonical_round"] == p and r["scoreable"] for r in canonical) for p in PHASE_COUNTS},
            "query_text_sha256": QUERY_SHA256,
            "query_text_encoding": "UTF-8 compact sorted-key JSON list of {query_id,query}, ordered by query_id; exact text; no normalization",
            "scoreable_ids": sorted(EXPECTED_IDS - EXCLUDED), "all_surface_query_ids_and_text_equal": True}


def verify_projection(root: Path, canonical: list[dict]) -> dict:
    builder = load_reference(root, "build_issue34_current_115_truth.py")
    historical_raw = (root / "inputs/historical_manifest.json").read_bytes()
    ledger_raw = (root / "inputs/original_truth_ledger.jsonl").read_bytes()
    _, historical = builder.parse_vecna_manifest(historical_raw)
    rebuilt = builder.build_projection(builder.parse_current_ledger(ledger_raw), historical)
    require(rebuilt == canonical, "Canonical truth differs from the provenance-backed historical/P3 projection")
    encoded = builder.encode_jsonl(rebuilt)
    require(encoded == (root / "inputs/canonical_truth.jsonl").read_bytes(), "Canonical truth byte encoding changed")
    require(sha256(encoded) == TRUTH_SHA256, "Canonical truth hash mismatch")
    meta = read_json(root / "inputs/canonical_truth.meta.json")
    require(meta == builder.metadata(vecna_raw=historical_raw, odc_raw=ledger_raw, output_raw=encoded), "Canonical truth metadata does not reproduce")
    historical_rows = [r for r in rebuilt if r["truth_tier"] == "frozen_headless_benchmark_truth"]
    require(len(historical_rows) == 78, "Historical truth inventory changed")
    return {"canonical_path": "inputs/canonical_truth.jsonl", "canonical_sha256": TRUTH_SHA256,
            "projection_reproduced_byte_for_byte": True, "historical_count": 78, "p3_provisional_count": 35,
            "historical_range_count": 72, "historical_trake_count": 6, "p3_trake_count": 2,
            "join": "(canonical_round, canonical_source_key), supported by source provenance; query text checked separately",
            "historical_truth_sha256": sha256(historical_raw), "p3_and_identity_ledger_sha256": sha256(ledger_raw),
            "historical_projection_semantic_sha256": json_hash(historical_rows),
            "p3_projection_semantic_sha256": json_hash([r for r in rebuilt if r["canonical_round"] == "P3"]),
            "truth_limitations": ["Six historical TRAKE rows retain submission-derived event-window proxies.", "35 scoreable P3 rows retain provisional source-text truth requiring corpus validation."]}


def candidate_identity(candidate: dict) -> tuple[str, int]:
    return candidate["video_id"], int(str(candidate["frame_id"]).rsplit("#", 1)[-1])


def verify_candidates(baseline: list[dict], reranker: list[dict]) -> dict:
    base = query_index(baseline, "baseline")
    rerank = query_index(reranker, "reranker")
    empty = []
    duplicate_occurrences = {"baseline": {}, "reranker": {}}
    for qid in sorted(base):
        left, right = base[qid]["candidates_top100"], rerank[qid]["reranked_candidates_top20"]
        require(len(left) in (0, 100) and len(right) == (20 if left else 0), f"Candidate depth changed: {qid}")
        if not left:
            empty.append(qid)
        require([c["rank"] for c in left] == list(range(1, len(left) + 1)), f"Baseline ranks invalid: {qid}")
        require([c["rank"] for c in right] == list(range(1, len(right) + 1)), f"Reranker ranks invalid: {qid}")
        # Duplicate hits are part of the frozen retrieval evidence. Do not
        # deduplicate here: that would change the scorer's rank semantics.
        for arm, items in (("baseline", left), ("reranker", right)):
            extra = len(items) - len({candidate_identity(c) for c in items})
            if extra:
                duplicate_occurrences[arm][qid] = extra
        for candidate in right:
            rank = candidate["original_baseline_rank"]
            require(isinstance(rank, int) and 1 <= rank <= len(left), f"Invalid original baseline rank: {qid}")
            require(candidate_identity(candidate) == candidate_identity(left[rank - 1]), f"Reranker candidate outside frozen baseline mapping: {qid}")
            require(math.isfinite(candidate["reranker_score"]), f"Nonfinite reranker score: {qid}")
        require(all(math.isfinite(c["distance"]) for c in left), f"Nonfinite baseline score: {qid}")
    require(empty == ["p2_q17"], f"Empty-provider query inventory changed: {empty}")
    return {"baseline_input_depth": 100, "reranker_input_depth": 100, "reranker_saved_output_depth": 20,
            "query_rows": 115, "nonempty_query_rows": 114, "empty_query_ids": empty,
            "empty_queries_remain_in_denominator": True, "reranked_candidates_verified_in_frozen_pool": 2280,
            "duplicate_occurrences_preserved": duplicate_occurrences,
            "full_top100_reranker_scores_saved": False,
            "limitation": "Saved top20 cannot support a new blend requiring scores for all100 candidates."}


def reproduce_controls(root: Path, canonical: list[dict], baseline: list[dict], reranker: list[dict]) -> dict:
    scorer = load_reference(root, "evaluate_reranker_fusion.py")
    base, rerank = query_index(baseline, "baseline"), query_index(reranker, "reranker")
    per_query = []
    for truth in canonical:
        if not truth["scoreable"]:
            continue
        qid = truth["query_id"]
        source = "p3" if truth["canonical_round"] == "P3" else "historical"
        t = {**truth, "_source": source}
        a = scorer.score_query(base[qid]["candidates_top100"], t)
        b = scorer.score_query(rerank[qid]["reranked_candidates_top20"], t)
        truth_key = qid if source == "p3" else truth["historical_identity"]["canonical_query_id"]
        per_query.append({"query_id": qid, "family": a["family"], "truth_key": truth_key, "baseline": a, "reranker": b})
    previous = read_json(root / "inputs/previous_controls.json")
    require(per_query == previous["per_query"], "Canonical scoring disagrees with saved per-query control evidence")
    controls = {arm: scorer.aggregate([row[arm] for row in per_query]) for arm in ("baseline", "reranker")}
    require(controls == previous["controls"], "Recomputed controls disagree with frozen controls")
    return {"status": "reproduced_from_canonical_truth_and_saved_rankings", "metrics": controls,
            "per_query_semantic_sha256": json_hash(per_query), "per_query_count": len(per_query),
            "scoring_contract": previous["scoring_contract"],
            "historical_trake_note": "Strict all-events coverage; P3 retains its own fractional event metric."}


def legacy_checksum_reconciliation(root: Path) -> dict:
    previous = read_json(root / "inputs/previous_controls.json")["inputs"]
    result = {}
    for key, filename in (("historical_manifest", "historical_manifest.json"), ("p3_comparison", "comparison_qwen_vs_reranker.json")):
        raw = (root / "inputs" / filename).read_bytes()
        require(sha256(raw.replace(b"\n", b"\r\n")) == previous[key]["sha256"], f"Legacy CRLF hash mismatch: {key}")
        result[key] = {"status": "line_endings_only", "git_lf_sha256": sha256(raw), "legacy_raw_sha256": previous[key]["sha256"]}
    raw = (root / "inputs/qwen3_vl_reranker_2b_top100.json").read_bytes()
    result["reranker"] = {"git_lf_sha256": sha256(raw), "canonical_json_sha256": json_hash(json.loads(raw)),
                          "legacy_raw_sha256": previous["reranker"]["sha256"],
                          "status": "legacy_host_bytes_not_yet_reconciled",
                          "archive_git_blob_sha": "71b751c36cbf5cab6611b10ab5edf391ee078e0f",
                          "archive_path": ARCHIVE_PATH + "inputs/" + EVAL_PATH + "qwen3_vl_reranker_2b_top100.json"}
    identity_path = root / "inputs/host_reranker_identity.json"
    if identity_path.is_file():
        evidence = read_json(identity_path)
        require(evidence["raw_sha256"] == previous["reranker"]["sha256"], "Host reranker no longer matches archived raw checksum")
        require(evidence["lf_sha256"] == sha256(raw), "Host reranker LF-normalized bytes differ from pinned Git bytes")
        require(evidence["canonical_json_sha256"] == json_hash(json.loads(raw)), "Host/Git reranker JSON identity differs")
        result["reranker"].update(status="line_endings_only_host_lf_normalization_and_json_verified", source_url=evidence["source_url"], evidence_sha256=sha256(identity_path.read_bytes()))
    comparison = read_json(root / "inputs/comparison_qwen_vs_reranker.json")
    result["older_comparison_recorded_reranker_checksum"] = {
        "sha256": comparison["inputs"]["reranker"]["sha256"], "status": "older_byte_identity_unverified",
        "scope": "Stored P3 metrics are reproduced exactly; this older input checksum is not claimed to identify current raw bytes."}
    return result


def host_observations(root: Path) -> dict:
    path = root / "inputs/host_preflight.json"
    if not path.is_file():
        return {"status": "not_observed", "loaded_model_index_parity": "unverified"}
    evidence = read_json(path)
    result = evidence["result"]
    require(result["task_id"] == "vecna82-authority-runtime-preflight-20260916" and result["status"] == "success", "Host preflight did not complete")
    require(result["base_commit"] == VECNA_MAIN and result["final_head"] == VECNA_MAIN, "Broker workspace identity changed")
    require(result["changed_paths"] == [] and result["scope_violations"] == [], "Read-only broker preflight changed repository paths")
    models, repositories = [], []
    for line in result["worker_stdout"].splitlines():
        if line.startswith("MODEL_SNAPSHOT "):
            models.append(json.loads(line[len("MODEL_SNAPSHOT "):]))
        elif line.startswith('{"repo":'):
            repositories.append(json.loads(line))
    historical = read_json(root / "inputs/temporal_surface.json")
    revision = historical["model_snapshot"].replace("\\", "/").rsplit("/", 1)[-1]
    matching = [model for model in models if model["path"].endswith("/" + revision)]
    require(len(matching) == 1, "The frozen embedding-model snapshot is not uniquely observed on the host")
    configs = [item for item in matching[0]["files"] if item["path"].endswith("/config.json")]
    require(len(configs) == 1 and configs[0].get("sha256") == historical["model_config_sha256"],
            "Host embedding-model config differs from the frozen temporal surface")
    return {"status": "snapshot_config_files_observed", "source_url": evidence["source_url"],
            "evidence_path": "inputs/host_preflight.json", "evidence_sha256": sha256(path.read_bytes()),
            "model_snapshots": models, "repository_observations": repositories,
            "repository_status_note": "git_status is a process exit code, not evidence that the checkout is clean.",
            "frozen_embedding_snapshot_config_identity_verified": True,
            "loaded_model_index_parity": "unverified", "weight_file_hashes": "not_observed"}


def baseline_lineage(root: Path, canonical: list[dict], baseline: list[dict]) -> dict:
    path = root / "inputs/legacy_temporal_control_113.jsonl"
    if not path.is_file():
        return {"status": "legacy_temporal_control_not_loaded", "current_control_authority": "inputs/qwen_only_top100.jsonl"}
    legacy = read_jsonl(path)
    require(len(legacy) == 113 and {row["query_id"] for row in legacy} == EXPECTED_IDS - EXCLUDED,
            "Legacy temporal control does not have the same113 scoreable identities")
    truth = {row["query_id"]: row for row in canonical}
    require(all(row["query_text"] == truth[row["query_id"]]["query"] for row in legacy), "Legacy control query text differs")
    old = {row["query_id"]: row for row in legacy}
    current = query_index(baseline, "baseline")
    hits = lambda rows, n: [candidate_identity(c) for c in sorted(rows, key=lambda x: x["rank"])[:n]]
    differences = [qid for qid in sorted(old) if hits(old[qid]["baseline_results"], 20) != hits(current[qid]["candidates_top100"], 20)]
    temporal_ids = ["p0_q22", "p0_q23", "p0_q24", "p1_q25", "p2_q29", "p2_q30", "p3_q21", "p3_q34"]
    temporal = {}
    for qid in temporal_ids:
        left, right = hits(old[qid]["baseline_results"], 3), hits(current[qid]["candidates_top100"], 3)
        temporal[qid] = {"top3_candidate_set_equal": set(left) == set(right), "top3_order_equal": left == right}
    return {"status": "resolved_distinct_baseline_lineages", "legacy_path": "inputs/legacy_temporal_control_113.jsonl",
            "legacy_sha256": sha256(path.read_bytes()), "legacy_baseline_sources": dict(Counter(row["baseline_source"] for row in legacy)),
            "same_113_query_ids_and_text": True, "top20_order_or_membership_differs_count": len(differences),
            "top20_changed_query_ids": differences, "temporal_top3_candidate_identity": temporal,
            "packet_authority": {"B_and_C": "current115 Qwen top100 export", "A": "new matched run required; legacy cached scores are not the current baseline"},
            "reuse_boundary": "Frame caches may be reused only after exact video/frame/decoder/transform identity; legacy scores are not globally interchangeable."}


def build_manifest(root: Path) -> dict:
    sources = verify_sources(root)
    canonical = read_jsonl(root / "inputs/canonical_truth.jsonl")
    baseline = read_jsonl(root / "inputs/qwen_only_top100.jsonl")
    reranker = read_json(root / "inputs/qwen3_vl_reranker_2b_top100.json")["per_query"]
    ledger = read_jsonl(root / "inputs/original_truth_ledger.jsonl")
    query = verify_queries(canonical, baseline=baseline, reranker=reranker, original_ledger=ledger)
    truth = verify_projection(root, canonical)
    candidates = verify_candidates(baseline, reranker)
    controls = reproduce_controls(root, canonical, baseline, reranker)
    historical_surface = read_json(root / "inputs/temporal_surface.json")
    return {"schema": "vecna82-control-manifest-v1", "issue": "JimmyK300/Vecna#82",
            "authority": {"vecna_main_at_start": VECNA_MAIN, "truth_projection_ref": TRUTH_REF,
                          "dataset_main_at_start": DATASET_REF, "local_checkout_is_not_truth_authority": True},
            "source_manifest_sha256": sha256((root / "inputs/sources.json").read_bytes()), "sources": sources,
            "preflight_code_sha256": sha256(Path(__file__).read_bytes()), "query_surface": query, "truth_surface": truth,
            "candidate_surface": candidates, "controls": controls,
            "baseline_lineage": baseline_lineage(root, canonical, baseline),
            "legacy_checksum_reconciliation": legacy_checksum_reconciliation(root),
            "model_index_surface": {
                "baseline_model": "Qwen/Qwen3-VL-Embedding-2B", "reranker_model": "Qwen/Qwen3-VL-Reranker-2B",
                "historical_temporal_surface": historical_surface,
                "historical_surface_status": "saved_experiment_evidence; not a current loaded-model or index proof",
                "host_observations": host_observations(root),
                "collection_row_count": None, "index_fingerprint": None, "active_vector_text_fields": None,
                "current_package_versions": None,
                "query_transformation_gates": {"required_off": ["query_expansion", "translation", "reranking", "yolo_text_transformation"],
                                              "status": "pending_exact_export_code_config_and_run_evidence_for_new_retrieval"}},
            "packet_readiness": {
                "0_saved_control": {"status": "verified", "retrieval_results_changed": False},
                "A_native_multi_image": {"status": "requires_packet_A_runtime_and_matched_candidate_manifest", "blocker": "Installed native-image support, matched representations and bounded inference proof are separate gates."},
                "B_provider_fusion": {"status": "requires_packet_B_provider_manifest", "blocker": "Frozen raw per-provider lists, exact current fusion replay and model/index transformation parity are separate gates."},
                "C_saved_reranker": {"status": "ready", "scope": "Saved candidates, existing reranker scores and archived latency only; no new inference."},
                "D_failure_ledger": {"status": "ready_for_saved_control_and_C_evidence", "limit": "A/B failures or pending evidence must remain explicit, not inferred."},
                "E_next_proposal": {"status": "requires_failure_ledger"}},
            "invariants": {"ground_truth_role": "scoring_only", "query_text_transformed_here": False,
                           "new_model_inference": False, "production_changes": False, "full_corpus_reembedding": False}}


def provenance_text(manifest: dict) -> str:
    checks = manifest["legacy_checksum_reconciliation"]
    return f"""# Vecna #82 control provenance

The saved control is reproducible: 115 exact query identities/texts, 113
scoreable rows, exclusions `p0_q15` and `p3_q09`. `p2_q17` has no saved
candidates and remains in the denominator. All {len(manifest['sources'])} source Git blobs are verified
against embedded immutable pins before any reference code is imported.

- Vecna main at inspection: `{VECNA_MAIN}`.
- Canonical truth projection ref: `{TRUTH_REF}` (PR #80).
- Dataset main at inspection: `{DATASET_REF}`.
- Canonical truth SHA-256: `{TRUTH_SHA256}`.
- Exact query-text SHA-256: `{QUERY_SHA256}`.

The canonical projection is rebuilt byte-for-byte from 78 historical rows and
the original 115-row identity/P3 ledger. Joining uses provenance-backed source
identity; exact query text is an additional check. Six historical TRAKE rows
retain submission-derived event proxies; 35 P3 rows retain provisional
source-text truth. Historical TRAKE is scored by strict all-events coverage;
P3 preserves its existing fractional event semantics.

Direct scoring of canonical truth and saved candidates reproduces every frozen
per-query control and the aggregates: baseline R@20 **68/113**, reranker
R@20 **76/113**; MRR@20 **0.4243397949150161 → 0.4320209888728889**.
The input pool is top100, while the reranker artifact stores only its top20.
Every one of the 2,280 saved reranker candidates maps to the same query's
baseline pool and recorded original rank. No new retrieval or inference runs.

Historical-manifest and comparison raw-checksum differences are fully explained
by CRLF versus LF. Reranker reconciliation is
`{checks['reranker']['status']}`. The archive copy and current dataset file share
Git blob `71b751c36cbf5cab6611b10ab5edf391ee078e0f`; the optional broker identity
record proves host LF-normalized bytes and canonical JSON equal the Git copy.
The older comparison's separate reranker checksum remains an unverified older
byte identity; its stored P3 metrics reproduce exactly and are not used as truth.

Local model snapshot/config observations are recorded separately from historical
package versions. Snapshot presence does not establish the model actually loaded
for a run, full weights, collection contents, current package versions, or disabled
query transformations. Packet A and Packet B must supply their own remaining
runtime/provider evidence. Their readiness does not block Packet C's saved-data
analysis. Local checkout HEADs never override pinned truth authority.

The optional #79 temporal control contains the same113 query identities but a
different baseline lineage: 78 frozen historical results plus35 P3-only results.
It is recorded separately in `baseline_lineage`; cached temporal scores cannot
be substituted for the current115-export control. Packet A needs a matched run;
exact frame-cache identity may permit reuse without claiming score parity.

Reproduce with `python code/preflight.py`; verify generated artifacts without
rewriting with `python code/preflight.py --check`. Run regression checks with
`python -m unittest discover -s tests -p test_preflight.py -v`.

All paths, hashes, model/config observations, readiness limits and source URLs are
in `control_manifest.json`. Source locations are relative to this experiment root.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="fail if generated artifacts are absent or stale")
    args = parser.parse_args()
    try:
        manifest = build_manifest(args.root.resolve())
        artifacts = {"control_manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                     "PROVENANCE.md": provenance_text(manifest)}
        for filename, text in artifacts.items():
            path = args.root / "outputs" / filename
            raw = text.encode("utf-8")
            if args.check:
                require(path.is_file() and path.read_bytes() == raw, f"Missing or stale generated artifact: {path}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        print(f"Verified {len(manifest['sources'])} pinned blobs; 115 exact queries; 113 scoreable; canonical truth and per-query controls reproduce.")
        return 0
    except (PreflightError, ValueError, KeyError, OSError) as exc:
        print(f"PREFLIGHT_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
