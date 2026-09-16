#!/usr/bin/env python3
"""Freeze dataset #16/#17 preparation from pinned evidence; perform no media review.

Only the Python standard library is required. Run from the packet root with:
    python code/dataset_audit.py --root .

Selection reads query-side capability fields only. Saved baseline outcomes are
attached after selection, never used to select or reclassify an audit case.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
import re
from typing import Any


TEMPORAL_IDS = (
    "p0_q22", "p0_q23", "p0_q24", "p1_q25",
    "p2_q29", "p2_q30", "p3_q21", "p3_q34",
)
EXPECTED_EXCLUDED = {"p0_q15", "p3_q09"}
SELECTION_SEED = "vecna-source-audit-v1"
QUERY_CAPABILITY_FIELDS = (
    "phase", "query_id", "task_type", "summary", "primary_challenge",
    "capability_tags", "evidence_needed",
)
TRUTH_FIELDS = (
    "accepted_video_id", "accepted_ranges", "accepted_groups",
    "trake_event_truth", "scoreability", "source_provenance",
    "truth_authority", "truth_tier", "truth_status", "notes",
    "current_identity_source", "historical_identity",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def object_hash(value: Any) -> str:
    return hashlib.sha256(json_bytes(value)).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(json_bytes(value))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_bytes("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_text(path: Path, value: str) -> None:
    path.write_bytes(value.encode("utf-8"))


def unique(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    result = {row[field]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate {field}")
    return result


def capability_id(row: dict[str, Any]) -> str:
    """Current display ordinals differ from preserved organizer source ordinals."""
    source_key = row["canonical_source_key"]
    match = re.fullmatch(r"query-(p[0-3])-(\d+)-[a-z]+", source_key)
    if match:
        return f"{match[1]}-q{int(match[2])}"
    match = re.fullmatch(r"(p3)_q(\d+)", source_key)
    if match:
        return f"{match[1]}-q{int(match[2])}"
    raise ValueError(f"Unrecognized canonical source identity: {source_key}")


def query_metadata(capability: dict[str, Any]) -> dict[str, Any]:
    return {field: capability[field] for field in QUERY_CAPABILITY_FIELDS}


def truth_copy(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in TRUTH_FIELDS if field in row}


def freeze_sample(eligible: list[dict[str, Any]], channel: str, limit: int) -> list[dict[str, Any]]:
    """Deterministic round robin over phase, task type, and combined OCR/ASR."""
    strata: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        cap = row["query_side_metadata"]
        combined = "combined_ocr_asr" if {"OCR", "ASR"} <= set(cap["capability_tags"]) else "single_text_channel"
        strata[(cap["phase"], cap["task_type"], combined)].append(row)
    queues = {}
    for key, rows in strata.items():
        queues[key] = deque(sorted(rows, key=lambda row: hashlib.sha256(
            f"{SELECTION_SEED}|{channel}|{row['query_id']}".encode("utf-8")).hexdigest()))
    selected = []
    while len(selected) < limit and any(queues.values()):
        for key in sorted(queues):
            if queues[key] and len(selected) < limit:
                selected.append(queues[key].popleft())
    return selected


def event_points(row: dict[str, Any]) -> list[dict[str, Any]]:
    events = row.get("trake_event_truth", [])
    if events:
        return [{"event_index": e["event_index"], "video_id": row["accepted_video_id"],
                 "frame": e["submitted_frame"], "truth_tier": e["truth_tier"],
                 "source_field": "trake_event_truth", "original_event": e} for e in events]
    result = []
    for group_index, group in enumerate(row.get("accepted_groups", [])):
        for index, locator in enumerate(group, 1):
            if locator.get("kind") == "point":
                result.append({"event_index": index, "group_index": group_index,
                               "video_id": locator["video_id"], "frame": locator["frame"],
                               "truth_tier": row["truth_tier"], "source_field": "accepted_groups",
                               "original_locator": locator})
    return result


def build_temporal(row: dict[str, Any], cap: dict[str, Any]) -> dict[str, Any]:
    events = event_points(row)
    source = row.get("source_provenance", {})
    provenance_frames = source.get("submitted_anchor_frames") if isinstance(source, dict) else None
    event_frames = [e["frame"] for e in events]
    flags = []
    if provenance_frames is not None and provenance_frames != event_frames:
        flags.append({"code": "provenance_anchor_list_differs_from_event_truth",
                      "provenance_frames": provenance_frames, "event_truth_frames": event_frames,
                      "interpretation": "Mechanical disagreement only; preserve both lists and trace exact source CSV/version before correction."})
    labels = re.findall(r"(?m)^\s*(E\d+)\b", row["query"])
    if len(labels) != len(set(labels)):
        flags.append({"code": "repeated_event_label_in_canonical_query", "labels": labels,
                      "interpretation": "Canonical wording preserved; event position and printed label are distinct."})
    if not events:
        flags.append({"code": "no_event_points_available"})
    return {
        "query_id": row["query_id"], "canonical_source_key": row["canonical_source_key"],
        "canonical_query": row["query"],
        "canonical_query_sha256": hashlib.sha256(row["query"].encode("utf-8")).hexdigest(),
        "task_type": row["task_type"], "current_truth_type": "ordered_event_points",
        "current_row_truth_tier": row["truth_tier"],
        "event_truth_tiers": sorted({e["truth_tier"] for e in events}),
        "scoreability_as_recorded": row.get("scoreability"), "scoreable_as_recorded": row["scoreable"],
        "canonical_truth_preserved": truth_copy(row), "events": events,
        "query_side_metadata": query_metadata(cap), "mechanical_flags": flags,
        "review_needed": True, "source_media_inspected": False,
        "event_order_status": "stored_order_only_not_source_motion_verified",
        "source_fps": None, "source_timebase_status": "unverified_in_this_packet",
        "review_status": "PENDING_LOCAL_SOURCE_EVIDENCE",
        "review_questions": [
            "Does each preserved frame show the intended query event in the stated video?",
            "Do source motion and the frames immediately before/after establish first occurrence and event order?",
            "What natural locator is supportable: point, interval, video only, or unresolved?",
        ],
        "notes": "Existing proxy windows are preserved as scoring proxies, not promoted to semantic event intervals. No truth proposal is made.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--limit-per-channel", type=int, default=20)
    args = parser.parse_args()
    root = args.root.resolve()
    out = root / "outputs" / "dataset-audit"
    if not 1 <= args.limit_per_channel <= 20:
        raise ValueError("Audit limit must be between 1 and 20")
    input_names = ["canonical_truth.jsonl", "canonical_truth.meta.json", "historical_manifest.json",
                   "original_truth_ledger.jsonl", "sources.json"] + [f"capability_p{p}.jsonl" for p in range(4)]
    input_paths = [root / "inputs" / name for name in input_names]
    input_hashes = {str(p.relative_to(root)): sha(p) for p in input_paths}
    truth = read_jsonl(root / "inputs/canonical_truth.jsonl")
    truth_by_id = unique(truth, "query_id")
    meta = json.loads((root / "inputs/canonical_truth.meta.json").read_text(encoding="utf-8"))
    if input_hashes["inputs/canonical_truth.jsonl"] != meta["projection"]["sha256"]:
        raise ValueError("Canonical projection SHA-256 does not match its pinned metadata")
    excluded = [row for row in truth if not row["scoreable"]]
    if len(truth) != 115 or len(truth) - len(excluded) != 113 or {r["query_id"] for r in excluded} != EXPECTED_EXCLUDED:
        raise ValueError("Expected exact 115/113 authority and known exclusions")
    capabilities = unique([r for p in range(4) for r in read_jsonl(root / f"inputs/capability_p{p}.jsonl")], "query_id")
    mapped = []
    for row in truth:
        cap = capabilities[capability_id(row)]
        if cap["phase"].upper() != row["canonical_round"]:
            raise ValueError(f"Phase mismatch for {row['query_id']}")
        mapped.append({"query_id": row["query_id"], "canonical_source_key": row["canonical_source_key"],
                       "scoreable": row["scoreable"], "query": row["query"],
                       "query_side_metadata": query_metadata(cap)})
    if len({r["query_side_metadata"]["query_id"] for r in mapped}) != 115:
        raise ValueError("Capability mapping must be one-to-one for all 115 current rows")
    eligible = {channel: [r for r in mapped if r["scoreable"] and channel.upper() in r["query_side_metadata"]["capability_tags"]]
                for channel in ("ocr", "asr")}
    selected = {channel: freeze_sample(rows, channel, args.limit_per_channel) for channel, rows in eligible.items()}
    selection = {
        "schema": "vecna82-dataset-audit-sample-v1", "frozen_before_source_inspection": True,
        "selection_seed": SELECTION_SEED, "limit_per_channel": args.limit_per_channel,
        "eligibility": "Current scoreable row with exact OCR or ASR capability tag, mapped by canonical source ordinal.",
        "selection_method": "Round robin over sorted (phase, capability task type, combined OCR+ASR status) strata; SHA-256 seed|channel|current query ID order within each stratum.",
        "selection_uses_baseline_outcomes": False, "selection_uses_source_media_or_extraction_quality": False,
        "metadata_fields_used": list(QUERY_CAPABILITY_FIELDS),
        "ignored_capability_fields": ["target_video", "ground_truth_status", "headless_video_rank", "headless_localization_rank", "headless_result", "failure_axis_if_wrong", "notes", "likely_corpus", "trake_event_coverage_at20"],
        "eligible_counts": {c: len(rows) for c, rows in eligible.items()},
        "selected_counts": {c: len(rows) for c, rows in selected.items()},
        "selected": selected,
        "eligible_query_ids": {c: [r["query_id"] for r in rows] for c, rows in eligible.items()},
        "input_sha256": input_hashes,
    }
    selection_hash = object_hash(selection)
    # The frozen selection is complete before any saved retrieval outcomes are read.
    score_path = root / "outputs/control-reproduction/per_query_scores.jsonl"
    scores = unique(read_jsonl(score_path), "query_id")
    if set(scores) != {r["query_id"] for r in truth if r["scoreable"]}:
        raise ValueError("Saved scoring output does not cover exactly the 113 scoreable identities")
    score_hash = sha(score_path)
    audit = []
    summaries = {}
    for channel, selected_rows in selected.items():
        for selected_row in selected_rows:
            query_id = selected_row["query_id"]
            row = truth_by_id[query_id]
            score = scores[query_id]
            audit.append({
                "query_id": query_id, "channel": channel, "canonical_source_key": row["canonical_source_key"],
                "canonical_query": row["query"], "query_side_metadata": selected_row["query_side_metadata"],
                "truth_tier": row["truth_tier"], "truth_preserved": truth_copy(row),
                "saved_baseline": score["baseline"], "saved_reranker": score["reranker"],
                "saved_scoring_family": score["family"], "sample_selection_sha256": selection_hash,
                "source_media_inspected": False, "source_interval": None, "reference_text": None,
                "artifact_text_raw": None, "artifact_text_normalized": None,
                "artifact_contains_required_signal": None, "sparse_rank": None, "dense_rank": None,
                "fusion_rank": None, "alignment_checked": False, "projection_duplicates_checked": False,
                "primary_failure": "unresolved", "secondary_failures": [], "repair_class": "needs_review",
                "review_status": "PENDING_LOCAL_SOURCE_EVIDENCE", "evidence_paths": [],
                "blocker": "This preparation packet contains no source videos, native OCR/ASR artifacts, or sparse/dense index responses; local dataset access has not been evaluated by this script.",
                "interpretation": "Saved Qwen/reranker status is an audit control only; it does not establish OCR/ASR route success or extraction failure.",
            })
        hits = sum(bool(scores[r["query_id"]]["baseline"]["recall"]["R@20"]) for r in selected_rows)
        summaries[channel] = {
            "eligible": len(eligible[channel]), "selected": len(selected_rows),
            "baseline_strict_success_controls": hits, "baseline_strict_misses": len(selected_rows) - hits,
            "source_media_reviewed": 0, "pending_local_evidence": len(selected_rows),
            "extraction_error_count": None, "alignment_error_count": None,
            "duplicate_flooding_count": None, "sparse_failure_count": None,
            "dense_failure_count": None, "fusion_failure_count": None,
        }
        if len(selected_rows) > 1 and (hits == 0 or hits == len(selected_rows)):
            raise ValueError(f"{channel} frozen sample lacks success/failure controls; report this gap instead of choosing cases post hoc")
    temporal = [build_temporal(truth_by_id[q], capabilities[capability_id(truth_by_id[q])]) for q in TEMPORAL_IDS]
    event_requests = []
    for row in temporal:
        for event in row["events"]:
            event_requests.append({
                "query_id": row["query_id"], "canonical_query": row["canonical_query"],
                "event_index": event["event_index"], "video_id": event["video_id"],
                "anchor_frame": event["frame"], "anchor_truth_tier": event["truth_tier"],
                "source_field": event["source_field"], "verify_fps_and_timebase_first": True,
                "initial_context_seconds_before": 15, "initial_context_seconds_after": 15,
                "request": "Return timestamp/frame-labelled filmstrip and motion clip as needed, with frames immediately before and after any proposed event boundary. Record and justify expansions.",
                "context_is_truth_interval": False, "use_retrieval_rankings_to_choose_media": False,
                "source_media_inspected": False,
            })
    excluded_rows = []
    for row in excluded:
        excluded_rows.append({"query_id": row["query_id"], "canonical_row_preserved": row,
                              "diagnosis": "No accepted current truth locator is present in the canonical projection.",
                              "source_reason_preserved": row.get("notes"), "source_media_inspected": False,
                              "still_excluded": True,
                              "next_question": "Can direct source/submission provenance establish an in-corpus locator without using retrieval output to choose truth?"})
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "sample_manifest.json", selection)
    write_jsonl(out / "capability_mapping.jsonl", mapped)
    write_jsonl(out / "audit.jsonl", audit)
    write_jsonl(out / "temporal_inventory.jsonl", temporal)
    write_jsonl(out / "temporal_evidence_requests.jsonl", event_requests)
    write_jsonl(out / "excluded_rows.jsonl", excluded_rows)
    write_json(out / "failure_counts.json", {"status": "NOT_ESTIMATED_PENDING_SOURCE_REVIEW", "channels": summaries})
    flag_counts = Counter(flag["code"] for row in temporal for flag in row["mechanical_flags"])
    summary = {
        "status": "PREPARATION_COMPLETE_SOURCE_REVIEW_PENDING", "canonical_rows": 115, "scoreable_rows": 113,
        "excluded_query_ids": sorted(EXPECTED_EXCLUDED), "sample_selection_sha256": selection_hash,
        "temporal_query_count": len(temporal), "temporal_event_count": len(event_requests),
        "temporal_mechanical_flags": dict(flag_counts), "channels": summaries,
        "unique_sampled_queries": len({r["query_id"] for r in audit}),
        "query_channel_audit_rows": len(audit), "source_media_reviewed": 0,
        "canonical_truth_changed": False, "models_run": False, "retrieval_indexes_queried": False,
    }
    write_json(out / "summary.json", summary)
    for channel in ("ocr", "asr"):
        s = summaries[channel]
        extra = "Inspect query-critical source text and its region; compare raw/normalized OCR, coordinates, persistence, and frame timing." if channel == "ocr" else "Listen to the query-critical speech interval; compare native transcript timing, segmentation, and frame projection duplication."
        write_text(out / f"{channel.upper()}_REPORT.md", (
            f"# {channel.upper()} audit preparation\n\n"
            f"Frozen {s['selected']} of {s['eligible']} eligible query cases. The outcome-independent sample contains "
            f"{s['baseline_strict_success_controls']} saved Qwen strict-R@20 successes and {s['baseline_strict_misses']} misses. "
            "These are visual-retrieval controls, not verified OCR/ASR route successes.\n\n"
            "No source media or extraction artifact was inspected; extraction and downstream failure counts remain unknown. "
            "Every audit row is explicitly unresolved.\n\n"
            f"Next: {extra} Then inspect original-query sparse and dense visibility separately, before attributing a failure to fusion or reranking. "
            "Do not change queries using observed answers. Do not regenerate the corpus.\n"
        ))
    table = "\n".join(f"| {r['query_id']} | {', '.join(str(e['frame']) for e in r['events'])} | {', '.join(f['code'] for f in r['mechanical_flags']) or 'none'} |" for r in temporal)
    write_text(out / "REVIEW.md", (
        "# Dataset issue preparation\n\n"
        "Canonical identity reproduces 115 rows, 113 scoreable, with p0_q15 and p3_q09 still excluded. "
        "The eight temporal controls preserve their existing event points, source provenance, and separate row/event truth tiers. "
        "All source-motion review remains pending.\n\n"
        "| Query | Stored event frames | Mechanical flags |\n|---|---|---|\n" + table + "\n\n"
        "The P2 provenance/event arrays disagree; inspect the exact source CSV and its version before correcting either list. "
        "The repeated E2 label in p0_q24 is preserved verbatim. "
        "P3 canonical truth contains point groups; this packet does not manufacture event intervals or import null-endpoint ranges from older experiment projections.\n\n"
        "The 15-second contexts in temporal_evidence_requests.jsonl are inspection windows only. Verify actual FPS/timebase before converting frame anchors into times. "
        "For motion-defined events, inspect transitions and event order; do not promote a still or a scoring proxy into an interval.\n\n"
        "The OCR/ASR sample is frozen using canonical source identity and query-side capability tags, stratified by phase, task, and combined text-channel status. "
        "Current display ordinals are not used as organizer ordinals. Baseline outcomes are attached only after selection. "
        "No extraction or ranking cause has yet been diagnosed.\n"
    ))
    write_text(out / "PROVENANCE.md", (
        "# Provenance\n\n"
        "Authority: JimmyK300/Vecna#34 PR80 lineage, canonical projection pinned by inputs/canonical_truth.meta.json; "
        "supporting work: official-dataset-control#16 and #17. Exact remote source repository/path/commit/blob identities remain in inputs/sources.json.\n\n"
        f"Canonical SHA-256: `{input_hashes['inputs/canonical_truth.jsonl']}`.\n\n"
        f"Frozen sample SHA-256: `{selection_hash}`.\n\n"
        "The sample reads only the explicit query-side metadata allowlist. Historical target-video and result columns are ignored. "
        "Saved visual Qwen/reranker scores are supplied by outputs/control-reproduction/per_query_scores.jsonl after selection. "
        "No live retrieval, model execution, source transcription, truth proposal, or canonical mutation occurs.\n\n"
        "Run: `python code/dataset_audit.py --root .`\n\n"
        "SHA256SUMS.txt binds every generated artifact except itself. run_manifest.json records code, input, and saved-score hashes. "
        "Generation contains no wall-clock timestamp or absolute runtime paths, so repeated runs over identical inputs produce identical bytes.\n"
    ))
    write_text(out / "BTL-RETURN.md", (
        "# BTL return\n\n"
        f"Preparation complete: 115/113 identity, eight temporal queries/{len(event_requests)} stored event points, "
        f"{len(audit)} OCR/ASR query-channel audit rows across {summary['unique_sampled_queries']} distinct queries.\n\n"
        "Supporting issues remain open at the source-evidence stage. Inspect exact P2 CSV provenance, then bounded event motion and query-critical OCR/ASR snippets. "
        "Only genuinely ambiguous event identity/boundary choices need semantic adjudication after the evidence is prepared.\n\n"
        "No truth promotion, retrieval tuning, corpus regeneration, or model rerun. All source-failure classifications remain unresolved.\n"
    ))
    if {str(p.relative_to(root)): sha(p) for p in input_paths} != input_hashes:
        raise ValueError("An immutable input changed during execution")
    if sha(score_path) != score_hash:
        raise ValueError("Saved scores changed during execution")
    write_json(out / "run_manifest.json", {
        "schema": "vecna82-dataset-audit-preparation-run-v1", "code_path": "code/dataset_audit.py",
        "code_sha256": sha(Path(__file__)), "input_sha256": input_hashes,
        "saved_scores_path": str(score_path.relative_to(root)), "saved_scores_sha256": score_hash,
        "frozen_selection_sha256": selection_hash, "input_hashes_unchanged": True,
        "source_media_inspected": False, "canonical_mutation": False,
    })
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    write_text(out / "SHA256SUMS.txt", "".join(f"{sha(p)}  {p.relative_to(out).as_posix()}\n" for p in files))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
