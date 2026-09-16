#!/usr/bin/env python3
"""Inspect archived projected text only for the already-frozen dataset #17 sample.

This does not execute OCR, ASR, retrieval, or source-media review. A literal in
an extracted artifact is not evidence of transcription fidelity. The source
JSON bytes are checked against Git blob SHAs before use.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import subprocess

from dataset_audit import read_jsonl, sha, write_json, write_jsonl, write_text


# Assistant review of stored strings in the bounded canonical-locator windows.
# Excerpts are checked against preserved neighborhood text, not used for search.
# They are candidate observations, never manual source-media transcriptions.
REVIEWS = {
    ("ocr", "p0_q13"): ("partial_query_signal", ["năm 2024"], "Year/event backdrop fragments exist; the long quoted support-board phrase is not established by these two records."),
    ("ocr", "p0_q19"): ("no_nonempty_text_in_window", [], "No nonempty OCR frame record in the accepted window; whether decisive writing is visible requires pixels."),
    ("ocr", "p0_q21"): ("no_nonempty_text_in_window", [], "No nonempty OCR frame record in the accepted window; recipe title/200g visual evidence remains uninspected."),
    ("ocr", "p1_q17"): ("query_signal_present", ["remember", "gerund and to-infinitive"], "Stored OCR exposes the remember lesson despite substantial repeated/noisy text."),
    ("ocr", "p1_q18"): ("requires_visual_relation_verification", [], "Text exists, but the obligation is a colored three-level diagram; plain text cannot establish the layout."),
    ("ocr", "p1_q24"): ("candidate_answer_present", ["đèo tà pứa"], "A headline supplies a candidate pass name; source readability/fidelity still needs pixels."),
    ("ocr", "p1_q21"): ("requires_visual_relation_verification", [], "OCR includes broadcast clocks and noise; the final scale value is not established by text alone."),
    ("ocr", "p2_q15"): ("partial_query_signal", ["phân bố đô thị", "10493,2"], "Table words and numbers survive; row association, red/blue counts, and the comparative claim require pixels."),
    ("ocr", "p2_q26"): ("required_signal_not_established", [], "Window OCR is chiefly logos/noise; animal identity is not established through this text channel."),
    ("ocr", "p2_q25"): ("requires_visual_relation_verification", [], "Two nonempty OCR strings do not establish which pole number is absent over the first 16 seconds."),
    ("ocr", "p3_q04"): ("query_signal_present", ["i went to the museum last week", "i often played football"], "Both described English examples are available in stored OCR; full temporal sequence is unverified."),
    ("ocr", "p3_q02"): ("required_signal_not_established", [], "The one noisy OCR record does not establish class-number signs; provisional truth remains provisional."),
    ("ocr", "p3_q05"): ("candidate_answer_present", ["gồm 6 tỉnh"], "Stored slide OCR supplies a candidate province count; native source fidelity is unverified."),
    ("ocr", "p3_q35"): ("candidate_answer_present", ["(nhom 3)"], "OCR preserves a candidate group label and 2018 question text; the four-answer constraints still require direct verification."),
    ("ocr", "p0_q20"): ("partial_query_signal", ["nguyen trung truc"], "Name/poem fragments exist, but the requested full two lines are not recoverable faithfully from these records alone."),
    ("ocr", "p1_q03"): ("query_signal_present", ["london", "weigh-in 2024"], "London and weighing context survive; the animal/action sequence still requires pixels."),
    ("ocr", "p1_q23"): ("requires_visual_relation_verification", [], "Garbled labels/digits do not support counting map markers while excluding the legend."),
    ("ocr", "p2_q13"): ("required_signal_not_established", [], "Only one noisy record appears; the quoted SẮC CỔ text is not established by it."),
    ("ocr", "p2_q23"): ("required_signal_not_established", [], "Only one noisy record appears; the requested street name is not established in this window."),
    ("ocr", "p2_q24"): ("partial_query_signal", ["loài (ii)", "độ mặn"], "Question/axis language survives, but the graph optimum requires a visual relation rather than bag-of-words evidence."),
    ("asr", "p0_q02"): ("query_signal_present", ["với 5 thành viên mới", "vườn xoài"], "Tiger-birth context survives even though the saved visual baseline missed; phonetic fidelity is unverified."),
    ("asr", "p0_q19"): ("partial_query_signal", ["fana", "khánh hòa"], "Club/province context is present; the requested commune name is not established by the bounded window."),
    ("asr", "p1_q17"): ("query_signal_present", ["remember", "nhớ một cái việc gì đó đã xảy ra"], "Spoken remember usage distinction is represented in stored ASR."),
    ("asr", "p1_q24"): ("candidate_answer_present", ["đèo tà pứa"], "Stored speech contains a candidate pass name and landslide context."),
    ("asr", "p2_q26"): ("candidate_answer_present", ["chà bông cá hồi"], "Stored speech supplies a candidate topping identity in the plating window."),
    ("asr", "p2_q28"): ("candidate_answer_present", ["một con nghêu"], "Shellfish identity appears despite a saved visual-baseline miss; no source-audio fidelity claim."),
    ("asr", "p3_q04"): ("query_signal_present", ["i went to the museum last week", "quá khứ đơn"], "Examples and grammar explanation are represented in projected ASR."),
    ("asr", "p3_q08"): ("partial_query_signal", ["bà tôi thưởng"], "Grandmother/game-collection clue survives; the requested neon text is a separate visual obligation."),
    ("asr", "p3_q18"): ("candidate_answer_present", ["trường tiểu học công hải"], "Projected speech contains a candidate school identity; provisional truth and native spelling remain unverified."),
    ("asr", "p0_q16"): ("query_signal_present", ["năm 1975", "steven spielberg"], "Movie/year/shark context survives. The accepted window also spans unrelated following-news text."),
    ("asr", "p0_q20"): ("candidate_answer_fidelity_unverified", ["hỏa hùng nhật tảo quanh thiên địa"], "A poem-like answer string exists but source audio is needed to judge its words; no CER/WER is claimed."),
    ("asr", "p2_q23"): ("partial_query_signal", ["quán trọ", "mạnh thường quân"], "Lodging/donor context survives; the street name is not established in this bounded window."),
    ("asr", "p2_q21"): ("candidate_answer_present", ["cá sòng", "lá chanh", "1 cây sả"], "Species and ingredient context are present; this does not prove sparse/dense visibility or source fidelity."),
    ("asr", "p3_q06"): ("partial_query_signal", ["tô hoài", "vợ chồng a phủ"], "Author/work context survives; requested mountain-region answer is not established in this window."),
    ("asr", "p3_q14"): ("partial_query_signal", ["con đã biết bơi"], "Swimming interview is present, but the next grade is not established in this bounded window."),
    ("asr", "p0_q01"): ("query_signal_present", ["phi hành đoàn 4 người", "cực quan"], "Four-person private mission and aurora-like wording survive; the latter needs audio to judge transcription."),
    ("asr", "p3_q24"): ("candidate_answer_present", ["hai muỗng cà phê nước tương"], "Stored ASR contains a candidate soy-sauce quantity despite the saved visual-baseline miss."),
    ("asr", "p3_q05"): ("partial_query_signal", ["bắc trung bộ"], "Region context exists; the requested province count is not established by this bounded ASR window, while paired OCR contains a candidate count."),
}


def locators(row):
    truth = row["truth_preserved"]
    result = []
    for loc in truth.get("accepted_ranges", []):
        result.append({"video_id": truth["accepted_video_id"], "start_frame": loc["start_frame"],
                       "end_frame": loc["end_frame"], "source": "accepted_ranges", "original": loc})
    for group_index, group in enumerate(truth.get("accepted_groups", [])):
        for loc in group:
            start = loc["frame"] if loc["kind"] == "point" else loc["start"]
            end = loc["frame"] if loc["kind"] == "point" else loc["end"]
            result.append({"video_id": loc["video_id"], "start_frame": start, "end_frame": end,
                           "source": "accepted_groups", "group_index": group_index, "original": loc})
    if not result:
        raise ValueError(f"No bounded canonical locator: {row['query_id']}")
    return result


def hydrate_sources(root, registry, dataset_repo):
    """Restore only the 37 pinned JSON blobs; never edit the dataset checkout.

    The published run manifest supplies SHA-256, while the source registry pins
    commit:path and Git blob SHA. Existing bytes must already match; only absent
    cache files are created. All reads verify before the first write.
    """
    run_manifest = json.loads((root / "outputs/dataset-audit/source_text_run_manifest.json").read_text(encoding="utf-8"))
    expected_hashes = run_manifest["source_sha256"]
    expected_root = (root / "outputs/dataset-audit/source-artifacts").resolve()
    pending = []
    verified_existing = 0
    for ref in registry["files"]:
        if ref["repository"] != "JimmyK300/official-dataset-control":
            raise ValueError("Hydration supports only the pinned dataset repository")
        if not re.fullmatch(r"[a-f0-9]{40}", ref["commit"]) or not re.fullmatch(r"[a-f0-9]{40}", ref["blob_sha"]):
            raise ValueError("Hydration requires full commit and blob identities")
        if not ref["path"].startswith("derived/metadata/asr-ocr-text-v1/") or not ref["path"].endswith(".json"):
            raise ValueError("Hydration source path outside the bounded projected-text archive")
        target = (root / ref["local"]).resolve()
        if expected_root not in target.parents:
            raise ValueError("Hydration target escapes source-artifacts")
        expected_sha256 = expected_hashes[ref["local"]]
        if target.exists():
            content = target.read_bytes()
        else:
            result = subprocess.run(["git", "-C", str(dataset_repo), "show", f"{ref['commit']}:{ref['path']}"],
                                    check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise RuntimeError(f"Pinned Git blob unavailable: {ref['commit']}:{ref['path']}: " + result.stderr.decode("utf-8", errors="replace"))
            content = result.stdout
        blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
        if blob != ref["blob_sha"] or hashlib.sha256(content).hexdigest() != expected_sha256:
            raise ValueError(f"Hydration content mismatch: {ref['local']}")
        if target.exists():
            verified_existing += 1
        else:
            pending.append((target, content))
    for target, content in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(content)
    return {"verified_existing": verified_existing, "created": len(pending), "dataset_checkout_modified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dataset-repo", type=Path, help="Read missing source JSON from this existing Git checkout at the pinned commit; no fetch or checkout change.")
    parser.add_argument("--hydrate-only", action="store_true", help="Verify/restore the 37 source JSON files and stop before regenerating reports; requires --dataset-repo.")
    args = parser.parse_args()
    root = args.root.resolve()
    out = root / "outputs/dataset-audit"
    registry = json.loads((out / "source_artifact_registry.json").read_text(encoding="utf-8"))
    if args.hydrate_only and args.dataset_repo is None:
        parser.error("--hydrate-only requires --dataset-repo")
    if args.dataset_repo is not None:
        hydration = hydrate_sources(root, registry, args.dataset_repo.resolve())
        if args.hydrate_only:
            print(json.dumps(hydration, indent=2))
            return
    refs = {(r["channel"], r["video_id"]): r for r in registry["files"]}
    data = {}
    for key, ref in refs.items():
        path = root / ref["local"]
        content = path.read_bytes()
        blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
        if blob != ref["blob_sha"]:
            raise ValueError(f"Source Git blob mismatch: {path}")
        data[key] = json.loads(content)
    audit = read_jsonl(out / "audit.jsonl")
    if {(r["channel"], r["query_id"]) for r in audit} != set(REVIEWS):
        raise ValueError("Frozen sample and reviewed artifact rows differ")
    results = []
    host_requests = []
    for row in audit:
        channel, query_id = row["channel"], row["query_id"]
        windows = locators(row)
        bounded = []
        for video_id in sorted({w["video_id"] for w in windows}):
            datum = data[(channel, video_id)]
            video_windows = [w for w in windows if w["video_id"] == video_id]
            # Union membership avoids double-counting overlapping truth ranges.
            frames = [f for f in datum["frames"] if any(w["start_frame"] <= f["frame_idx"] <= w["end_frame"] for w in video_windows)]
            spans = [s for s in datum.get("segments", datum.get("spans", [])) if any(
                s["start_frame_idx"] <= w["end_frame"] and s["end_frame_idx"] >= w["start_frame"] for w in video_windows)]
            counts = Counter(f["text"] for f in frames)
            ref = refs[(channel, video_id)]
            bounded.append({"video_id": video_id, "source_ref": ref, "source_sha256": sha(root / ref["local"]),
                            "source_provider": datum["source"]["provider"], "timing": datum["timing"],
                            "windows": video_windows, "nonempty_frame_count": len(frames),
                            "unique_nonempty_text_count": len(counts),
                            "max_frames_sharing_identical_text": max(counts.values(), default=0),
                            "repeated_projection_frame_excess": len(frames) - len(counts),
                            "frames": frames, "overlapping_grouped_text": spans})
            # Two fixed diagnostic probe anchors; no target-text search is used.
            anchors = sorted({int((w["start_frame"] + w["end_frame"]) // 2) for w in video_windows})
            source = row["truth_preserved"].get("source_provenance", {})
            submitted = source.get("submitted_anchor_frames", []) if isinstance(source, dict) else []
            in_window = [f for f in submitted if any(w["start_frame"] <= f <= w["end_frame"] for w in video_windows)]
            anchors = list(dict.fromkeys(in_window[:1] + anchors))[:2]
            video_relative = PureWindowsPath(datum["timing"]["source_video_path"]).relative_to(PureWindowsPath("D:/Official-Dataset")).as_posix()
            host_requests.append({"query_id": query_id, "channel": channel, "video_id": video_id,
                                  "metadata_relative_path": ref["path"], "expected_metadata_sha256": sha(root / ref["local"]),
                                  "video_relative_path": video_relative,
                                  "feature_relative_dir": datum["source"]["features_root"] + "/" + video_id,
                                  "probe_anchor_frames": anchors, "known_fps": datum["timing"]["fps"],
                                  "native_evidence_relative_dir": f"provenance/evidence/{video_id}/{channel}",
                                  "native_analysis_relative_dir": f"provenance/analysis/{video_id}/{channel}"})
        status, excerpts, note = REVIEWS[(channel, query_id)]
        available_text = "\n".join(s["text"] for b in bounded for s in b["overlapping_grouped_text"])
        for excerpt in excerpts:
            if excerpt not in available_text:
                raise ValueError(f"Reviewed excerpt not present in bounded text: {channel}/{query_id}: {excerpt}")
        if status == "no_nonempty_text_in_window" and any(b["nonempty_frame_count"] for b in bounded):
            raise ValueError("Empty-window review contradicted by source JSON")
        results.append({"query_id": query_id, "channel": channel, "canonical_query": row["canonical_query"],
                        "truth_tier": row["truth_tier"], "sample_selection_sha256": row["sample_selection_sha256"],
                        "saved_baseline": row["saved_baseline"], "saved_reranker": row["saved_reranker"],
                        "review_status": "PROJECTED_TEXT_INSPECTED_SOURCE_MEDIA_PENDING",
                        "stored_text_observation": status, "verified_artifact_excerpts": excerpts,
                        "artifact_review_note": note, "bounded_artifacts": bounded,
                        "source_media_inspected": False, "native_transcript_or_boxes_available_in_archive": False,
                        "transcription_fidelity": "unverified", "primary_failure": "unresolved",
                        "sparse_dense_visibility_audited": False, "duplicate_flooding_confirmed": False,
                        "interpretation_limit": "Projected-text availability/replication are observable; extraction error, native alignment error, and downstream ranking cause require additional evidence."})
    write_jsonl(out / "source_text_audit.jsonl", results)
    write_json(out / "host_probe_requests.json", {"frozen_sample_sha256": audit[0]["sample_selection_sha256"], "requests": host_requests})
    summary = {"source_files": len(refs), "query_channel_rows": len(results), "source_media_reviewed": 0, "channels": {}}
    for channel in ("ocr", "asr"):
        subset = [r for r in results if r["channel"] == channel]
        projections = [b for r in subset for b in r["bounded_artifacts"]]
        summary["channels"][channel] = {
            "rows": len(subset), "observations": dict(Counter(r["stored_text_observation"] for r in subset)),
            "window_nonempty_frames": sum(b["nonempty_frame_count"] for b in projections),
            "window_unique_texts_sum": sum(b["unique_nonempty_text_count"] for b in projections),
            "repeated_projection_frame_excess": sum(b["repeated_projection_frame_excess"] for b in projections),
            "max_frames_sharing_one_text": max(b["max_frames_sharing_identical_text"] for b in projections),
            "confirmed_source_extraction_failures": None, "confirmed_retrieval_or_fusion_failures": None,
        }
    write_json(out / "source_text_summary.json", summary)
    lines = ["# Bounded projected-text audit", "", "All 38 frozen query/channel rows now have inspected stored text neighborhoods from 37 pinned per-video files. No pixels/audio or live sparse/dense ranking were inspected. Text availability does not establish extraction fidelity or a downstream failure cause.", "", "| Channel | Query | Nonempty frames / distinct strings | Artifact observation |", "|---|---|---:|---|"]
    for r in results:
        n = sum(b["nonempty_frame_count"] for b in r["bounded_artifacts"])
        u = sum(b["unique_nonempty_text_count"] for b in r["bounded_artifacts"])
        lines.append(f"| {r['channel']} | {r['query_id']} | {n} / {u} | {r['artifact_review_note']} |")
    lines += ["", "The duplicate counts describe repeated frame projections within accepted windows. They do not measure candidate-list flooding. Native WhisperX intervals and OCR boxes/confidences are absent from this metadata format; timestamps use rounded-FPS keyframe projection and identical strings are grouped across empty frames.", "", "Next direct checks: source pixels where OCR is absent/noisy; audio where candidate answers or questionable wording occur; exact sidecar discovery for retained native evidence; then sparse/dense visibility without answer-conditioned query rewriting. No broad re-extraction is authorized by this audit."]
    write_text(out / "SOURCE_TEXT_REVIEW.md", "\n".join(lines) + "\n")
    for channel in ("ocr", "asr"):
        subset = [r for r in results if r["channel"] == channel]
        channel_lines = [f"# {channel.upper()} bounded stored-text audit", "",
                         f"Inspected projected text neighborhoods for all {len(subset)} frozen {channel.upper()} cases. Source-media review and native alignment checks remain pending. Selection has not changed.", "",
                         "Saved Qwen/reranker results are visual-retrieval controls; they do not measure this text channel's ranking. No extraction or downstream failure cause is confirmed.", ""]
        for row in subset:
            channel_lines.append(f"- {row['query_id']}: {row['artifact_review_note']}")
        channel_lines += ["", "Exact frame records, grouped strings, source paths, blob/SHA-256 identities, and explicit observation limits are in source_text_audit.jsonl. Repeated projections are counted as a representation property, not proof of candidate flooding."]
        write_text(out / f"{channel.upper()}_REPORT.md", "\n".join(channel_lines) + "\n")
    write_text(out / "BTL-RETURN.md", (
        "# BTL return\n\n"
        "Canonical 115/113 reproduction and the frozen 20-OCR/18-ASR sample are complete. All 38 query/channel rows now have bounded stored-text inspection from 37 pinned per-video files. Eight temporal queries/31 event points retain unchanged truth and provenance.\n\n"
        "OCR has two accepted windows with no nonempty records; ASR projects 44 distinct per-window strings onto 456 frame records. These establish artifact availability/replication, not extraction fidelity or candidate flooding. Query/answer signals are preserved in multiple baseline misses.\n\n"
        "Next: capture the five bounded direct-media assets with code/capture_dataset_media.py, inspect them, verify host metadata/feature parity with code/dataset_source_probe.py, and inspect any existing native sidecars. Then audit sparse/dense visibility without answer-conditioned queries. No broad reprocessing, truth promotion, or retrieval tuning.\n\n"
        "Reproduce the complete local packet with python code/dataset_audit.py --root . followed by python code/dataset_text_audit.py --root .\n"
    ))
    preparation_summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    preparation_summary.update({"status": "PROJECTED_TEXT_AUDIT_COMPLETE_SOURCE_REVIEW_PENDING",
                                "projected_text_rows_inspected": len(results), "pinned_source_text_files": len(refs)})
    write_json(out / "summary.json", preparation_summary)
    write_json(out / "source_text_run_manifest.json", {"code_sha256": sha(Path(__file__)),
               "frozen_sample_sha256": audit[0]["sample_selection_sha256"],
               "registry_sha256": sha(out / "source_artifact_registry.json"),
               "source_sha256": {r["local"]: sha(root / r["local"]) for r in registry["files"]},
               "source_media_inspected": False, "no_retrieval_or_model_run": True})
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    write_text(out / "SHA256SUMS.txt", "".join(f"{sha(p)}  {p.relative_to(out).as_posix()}\n" for p in files))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
