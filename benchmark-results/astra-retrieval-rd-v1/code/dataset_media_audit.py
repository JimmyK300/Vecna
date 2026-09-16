#!/usr/bin/env python3
"""Apply bounded source-image observations to the unchanged #17 audit sample.

Observations below were recorded after viewing the three captured JPEGs. They
are fixed review annotations, not output from OCR, ASR, or a retrieval model.
Two source WAVs were captured, but this assistant context rejects audio input;
there is no heard reference or ASR fidelity assessment for those clips.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from fractions import Fraction
import json
from pathlib import Path
import wave

from dataset_audit import object_hash, read_jsonl, sha, truth_copy, write_json, write_jsonl, write_text


EXPECTED_ASSETS = {
    "p0_q21": "9528ac6fba3652b7c169b8229fe568a459af70d46bbc97db83f0e83a0c32cedc",
    "p0_q19": "19cc56fef73a66606c768b3a23d1d30b1b5e1496d415b197f410114cf5b088e0",
    "p1_q17": "0acc462af6b8fd07124429ea400cef15de49bf0106f32bb5d5400b4813e23bf3",
    "p0_q20": "0360218142ae4b7e2d678d88f2b557e2f83f1ab14fee5d7ca6528f335dee4684",
    "p3_q24": "5d6582ca61cc9b5751e5ae26cfa68a39449a505ea68c2431893dacb969eaf529",
}

# Short references transcribed from visible source pixels. These do not alter
# canonical query text, accepted ranges, benchmark answers, or truth tiers.
IMAGE_REVIEWS = {
    "p0_q21": {
        "classification": "source_visible_text_missing_at_persisted_ocr_feature",
        "short_source_references": ["Nhân bánh cuốn", "200 gr"],
        "reference_confidence": "moderate: small, tilted and soft recipe print; only title and quantity transcribed",
        "source_observation": "A person holds a printed recipe sheet. Its visible title reads Nhân bánh cuốn, and an ingredient line contains 200 gr. Query-critical print is present at this source anchor.",
        "source_to_artifact_comparison": "The canonical accepted window has zero nonempty OCR frame records. The existing exact-frame 001788/ocr.npy also decodes to an empty string, and host metadata matches the pinned archive. Missing sampled-file availability and JSON-only export loss are ruled out at this anchor; signal is already absent at persisted OCR features.",
        "primary_failure": "missing_query_critical_ocr_representation_at_inspected_source_anchor",
        "cause_status": "at_or_before_persisted_ocr_feature_detection_recognition_normalization_unresolved",
        "remaining_check": "The inspected native evidence and analysis directories do not exist. Exact detector/recognizer/normalization attribution requires separate retained historical evidence or a future bounded diagnostic; preserve current truth and avoid broad re-extraction.",
    },
    "p0_q19": {
        "classification": "source_visible_text_missing_at_persisted_ocr_feature",
        "short_source_references": ["Xã Giang Ly, huyện Khánh Vĩnh, tỉnh Khánh Hoà"],
        "reference_confidence": "high: location line legible on the event banner",
        "source_observation": "The gift-distribution scene has an event banner with the commune, district and province. The displayed commune is Giang Ly.",
        "source_to_artifact_comparison": "The existing exact-frame 001745/ocr.npy is empty, as is the accepted OCR window; host metadata matches the pinned archive. The readable location line is therefore missing at or before persisted OCR features. Saved visual retrieval succeeds at R@20, so this text-channel gap is not evidence of an overall retrieval miss.",
        "primary_failure": "missing_query_critical_ocr_representation_at_inspected_source_anchor",
        "cause_status": "at_or_before_persisted_ocr_feature_detection_recognition_normalization_unresolved",
        "remaining_check": "Both native sidecar directories are absent. The still establishes the banner at one time only; identifying the precise lost processing stage needs additional evidence and does not justify a truth-range change.",
    },
    "p1_q17": {
        "classification": "source_query_signal_also_present_in_archived_ocr",
        "short_source_references": ["remember", "V-ing", "to-V", "Remember to call me when you arrive!"],
        "reference_confidence": "high: large clear teaching slide",
        "source_observation": "A teacher in a pink áo dài and glasses appears beside a remember lesson branching to V-ing and to-V, with usage explanations and examples.",
        "source_to_artifact_comparison": "The accepted window has 23 nonempty frame records and 14 distinct strings. The nearest stored record is frame 17169, 17 frames (0.68 seconds) after the inspected source frame, and contains the remember lesson and call-me example. This is neighborhood agreement, not a same-frame OCR accuracy measurement.",
        "primary_failure": "none_established_for_query_critical_signal",
        "cause_status": "query_critical_signal_represented_fidelity_not_quantified",
        "remaining_check": "Only needed for a broader fidelity study: compare existing same-frame region evidence and native OCR output. No repair is suggested by this positive control.",
    },
}

AUDIO_LIMITATION = "Audio emission returned: audio content omitted because you do not support audio input. No source clip was heard in this assistant context."


def verify_sample_bridge(root, capture_manifest, rows):
    """Reconstruct and hash the first freeze; permit only the proven registry append."""
    sample_path = root / "outputs/dataset-audit/sample_manifest.json"
    current = json.loads(sample_path.read_text(encoding="utf-8"))
    current_hash = sha(sample_path)
    capture_hash = capture_manifest["frozen_sample_sha256"]
    if current_hash != rows[0]["sample_selection_sha256"]:
        raise ValueError("Current sample bytes and audit-row identities differ")
    reconstructed = copy.deepcopy(current)
    registry = json.loads((root / "inputs/sources.json").read_text(encoding="utf-8"))
    appended = [r for r in registry if r["local"] == "inputs/legacy_temporal_control_113.jsonl"]
    if capture_hash != current_hash:
        if len(registry) != 18 or len(appended) != 1:
            raise ValueError("Unrecognized source-registry change since media capture")
        prior_registry = [r for r in registry if r["local"] != appended[0]["local"]]
        reconstructed["input_sha256"]["inputs/sources.json"] = object_hash(prior_registry)
        if object_hash(reconstructed) != capture_hash:
            raise ValueError("Capture/current sample mismatch is not solely the verified registry append")
    ordered_selection = [(channel, item) for channel in ("ocr", "asr") for item in reconstructed["selected"][channel]]
    if [(c, item["query_id"]) for c, item in ordered_selection] != [(r["channel"], r["query_id"]) for r in rows]:
        raise ValueError("Ordered selected query/channel rows changed")
    canonical = {r["query_id"]: r for r in read_jsonl(root / "inputs/canonical_truth.jsonl")}
    scores_path = root / "outputs/control-reproduction/per_query_scores.jsonl"
    scores = {r["query_id"]: r for r in read_jsonl(scores_path)}
    run_manifest = json.loads((root / "outputs/dataset-audit/run_manifest.json").read_text(encoding="utf-8"))
    if sha(scores_path) != run_manifest["saved_scores_sha256"]:
        raise ValueError("Saved score bytes changed since preparation")
    identity_rows = []
    for (_, selected), row in zip(ordered_selection, rows):
        query_id = row["query_id"]
        if selected["query"] != row["canonical_query"] or selected["query_side_metadata"] != row["query_side_metadata"]:
            raise ValueError("Selected query text or metadata changed")
        if row["truth_preserved"] != truth_copy(canonical[query_id]):
            raise ValueError("Truth/video/window identities changed")
        if row["saved_baseline"] != scores[query_id]["baseline"] or row["saved_reranker"] != scores[query_id]["reranker"]:
            raise ValueError("Saved control outcome statuses differ")
        identity_rows.append({"channel": row["channel"], "query_id": query_id,
                              "query_text_sha256": object_hash(row["canonical_query"]),
                              "truth_identity_sha256": object_hash(row["truth_preserved"]),
                              "saved_baseline": row["saved_baseline"], "saved_reranker": row["saved_reranker"]})
    bridge = {"capture_sample_sha256": capture_hash, "current_sample_sha256": current_hash,
              "reconstructed_capture_sample_sha256": object_hash(reconstructed),
              "only_changed_field": "input_sha256.inputs/sources.json" if capture_hash != current_hash else None,
              "prior_registry_sha256": reconstructed["input_sha256"]["inputs/sources.json"],
              "current_registry_sha256": current["input_sha256"]["inputs/sources.json"],
              "appended_registry_source": appended[0] if appended else None,
              "selection_seed": current["selection_seed"], "selection_method": current["selection_method"],
              "ordered_selection_and_query_metadata_unchanged": True, "canonical_truth_unchanged": True,
              "saved_score_bytes_sha256": sha(scores_path),
              "saved_statuses_verified_against_unchanged_pinned_control_inputs": True,
              "interpretation": "Full manifest hash changed only because an unused supporting source entry was appended. Matching the reconstructed original full SHA proves selection, query metadata, seed, method, and all other manifest inputs unchanged. Saved statuses are verified against the preparation's pinned score bytes; they do not participate in selection.",
              "ordered_identity_rows": identity_rows}
    return bridge, reconstructed


def verify_host_parity(root, text_rows, path=None, source_url=None):
    path = path or root / "inputs/source_parity_probe.json"
    probe = json.loads(path.read_text(encoding="utf-8"))
    by_key = {(r["channel"], r["query_id"]): r for r in text_rows}
    if probe["frozen_sample_sha256"] != text_rows[0]["sample_selection_sha256"]:
        raise ValueError("Host parity probe used a different selected sample")
    results = []
    for row in probe["results"]:
        audit = by_key[(row["channel"], row["query_id"])]
        bound = next(b for b in audit["bounded_artifacts"] if b["video_id"] == row["video_id"])
        if row["metadata_sha256"] != bound["source_sha256"] or not row["metadata_matches_pinned_archive"]:
            raise ValueError("Host/archive metadata parity changed")
        source = json.loads((root / bound["source_ref"]["local"]).read_text(encoding="utf-8"))
        frames = {f["frame_idx"]: f["text"] for f in source["frames"]}
        checks = []
        for feature in row["feature_reads"]:
            if feature.get("text_read_status") != "read":
                raise ValueError("A declared host feature did not decode")
            projected = frames.get(feature["actual_feature_frame"], "")
            matches = projected.startswith(feature["text"]) if feature["text_truncated"] else projected == feature["text"]
            if not matches or len(projected) != feature["text_chars"]:
                raise ValueError("Feature text disagrees with archived projection")
            checks.append({**feature, "projected_text_matches": True,
                           "comparison_scope": "captured prefix plus full character count" if feature["text_truncated"] else "full decoded text"})
        results.append({**row, "feature_projection_checks": checks})
    return {"probe_sha256": sha(path), "broker_source_url": probe.get("broker_source_url", source_url),
            "query_channel_rows": len(results), "feature_files_read": sum(len(r["feature_reads"]) for r in results),
            "host_metadata_parity_rows": len(results),
            "native_evidence_or_analysis_directories_present": sum(int(r[k]["exists"]) for r in results for k in ("native_evidence", "native_analysis")),
            "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    out = root / "outputs/dataset-audit"
    media_dir = root / "outputs/source-audit/vecna82-source-media-review-v1"
    manifest_path = media_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    text_rows = read_jsonl(out / "source_text_audit.jsonl")
    original_rows = read_jsonl(out / "audit.jsonl")
    by_key = {(r["channel"], r["query_id"]): r for r in text_rows}
    truth_by_key = {(r["channel"], r["query_id"]): r["truth_preserved"] for r in original_rows}
    if len(by_key) != 38 or len(original_rows) != 38:
        raise ValueError("Frozen 38-row sample changed")
    if {a["query_id"] for a in manifest["assets"]} != set(EXPECTED_ASSETS):
        raise ValueError("Captured media set differs from the declared five assets")
    if len(manifest["assets"]) != len(EXPECTED_ASSETS):
        raise ValueError("Duplicate captured media entry")
    sample_bridge, reconstructed_sample = verify_sample_bridge(root, manifest, original_rows)
    host_parity = verify_host_parity(root, text_rows)
    parity_by_key = {(r["channel"], r["query_id"]): r for r in host_parity["results"]}
    if manifest["truth_source"]["sha256"] != sha(root / "inputs/canonical_truth.jsonl"):
        raise ValueError("Captured media uses different canonical truth")

    reviews = []
    for asset in manifest["assets"]:
        query_id, channel = asset["query_id"], asset["channel"]
        text_row = by_key[(channel, query_id)]
        path = media_dir / asset["artifact"]
        digest = sha(path)
        if digest != EXPECTED_ASSETS[query_id] or digest != asset["artifact_sha256"]:
            raise ValueError(f"Media content mismatch: {path}")
        if path.stat().st_size != asset["artifact_bytes"] or asset["status"] != "CAPTURED":
            raise ValueError(f"Media capture metadata mismatch: {path}")
        if not asset["source_size_mtime_unchanged"]:
            raise ValueError(f"Source video changed during capture: {query_id}")
        video_stream = next(s for s in asset["ffprobe"]["streams"] if s["codec_type"] == "video")
        fps = Fraction(video_stream["avg_frame_rate"])
        if fps != 25 or video_stream["r_frame_rate"] != "25/1" or float(video_stream["start_time"]) != 0:
            raise ValueError(f"Unexpected source frame timebase: {query_id}")
        review = {
            "query_id": query_id, "channel": channel, "kind": asset["kind"],
            "canonical_query": text_row["canonical_query"], "truth_tier": text_row["truth_tier"],
            "truth_preserved": truth_by_key[(channel, query_id)],
            "sample_selection_sha256": manifest["frozen_sample_sha256"],
            "artifact_relative_path": path.relative_to(root).as_posix(), "artifact_sha256": digest,
            "source_video_path": asset["source_path"], "source_file": asset["source_file"],
            "ffprobe": asset["ffprobe"], "capture_manifest_sha256": sha(manifest_path),
            "truth_source": manifest["truth_source"], "text_source": manifest["text_source"],
            "source_video_full_hash_computed": False,
            "source_identity_limit": "Source-video bytes/mtime and ffprobe are captured; whole video content hashes were not computed.",
            "sparse_dense_visibility_audited": False, "duplicate_flooding_confirmed": False,
            "truth_changed": False, "cer": None, "wer": None,
            "host_parity": parity_by_key[(channel, query_id)],
            "current_sample_selection_sha256": original_rows[0]["sample_selection_sha256"],
        }
        if asset["kind"] == "image":
            review.update(IMAGE_REVIEWS[query_id])
            review.update({"review_status": "SOURCE_IMAGE_INSPECTED", "source_media_inspected": True,
                           "inspection_method": "assistant visual inspection of recovered JPEG via view_image",
                           "source_frame_zero_based": asset["frame"],
                           "source_time_seconds": float(Fraction(asset["frame"], 1) / fps),
                           "frame_identity_method": asset["frame_identity_method"],
                           "temporal_limit": "One inspected frame cannot establish visibility throughout the accepted range, first occurrence, or exact event boundaries."})
            records = [f for b in text_row["bounded_artifacts"] for f in b["frames"]]
            if query_id in ("p0_q19", "p0_q21") and records:
                raise ValueError("An empty-window source comparison is no longer valid")
            if query_id in ("p0_q19", "p0_q21"):
                exact_feature = [f for f in review["host_parity"]["feature_reads"] if f["actual_feature_frame"] == asset["frame"]]
                if len(exact_feature) != 1 or exact_feature[0]["text"] != "" or exact_feature[0]["frame_offset"] != 0:
                    raise ValueError("Exact sampled-frame empty OCR evidence changed")
            if query_id == "p1_q17":
                nearest = min(records, key=lambda f: abs(f["frame_idx"] - asset["frame"]))
                if nearest["frame_idx"] != 17169 or "remember to call me when you arrive!" not in nearest["text"]:
                    raise ValueError("Positive control neighborhood changed")
                review["nearest_projected_record"] = nearest
        else:
            with wave.open(str(path), "rb") as wav:
                duration = wav.getnframes() / wav.getframerate()
                audio_format = {"channels": wav.getnchannels(), "sample_rate": wav.getframerate(),
                                "sample_width_bytes": wav.getsampwidth(), "duration_seconds": duration}
            if audio_format != {"channels": 1, "sample_rate": 16000, "sample_width_bytes": 2,
                                "duration_seconds": asset["end_s"] - asset["start_s"]}:
                raise ValueError("Audio rendition differs from capture request")
            review.update({"review_status": "AUDIO_CAPTURED_NOT_HEARD", "source_media_inspected": False,
                           "classification": "source_audio_fidelity_unreviewed", "short_source_references": [],
                           "reference_confidence": "not applicable: no heard reference",
                           "source_interval_seconds": [asset["start_s"], asset["end_s"]],
                           "audio_format": audio_format, "access_limitation": AUDIO_LIMITATION,
                           "source_observation": "The requested source interval was captured and its SHA-256 and WAV format/duration were verified. Its speech content was not reviewed.",
                           "source_to_artifact_comparison": "No comparison can be established without hearing the source. The existing stored-text observation remains provisional.",
                           "primary_failure": "unresolved", "cause_status": "source_audio_review_pending",
                           "remaining_check": "An audio-capable reviewer should transcribe only the query-critical phrase in this existing bounded WAV, then compare it with the preserved stored text.",
                           "temporal_limit": "Clip intervals are source playback seconds; projected ASR frame ranges are not native word timestamps."})
            review["smallest_review_question"] = (
                "What exact two poem lines are spoken in this 215–233 second excerpt? Transcribe only those lines."
                if query_id == "p0_q20" else
                "What quantity and unit of soy sauce are spoken in this 98–126 second excerpt? Transcribe only that short phrase.")
        reviews.append(review)

    review_by_key = {(r["channel"], r["query_id"]): r for r in reviews}
    reviewed_rows = []
    for row in text_rows:
        final_row = dict(row)
        review = review_by_key.get((row["channel"], row["query_id"]))
        final_row["media_review"] = review
        final_row["host_parity"] = parity_by_key.get((row["channel"], row["query_id"]))
        if review:
            final_row.update({k: review[k] for k in ("review_status", "source_media_inspected", "primary_failure")})
            final_row["latest_classification"] = review["classification"]
            final_row["interpretation_limit"] = ("For the two empty OCR anchors, signal is already absent in existing exact-frame features; detector, recognizer, normalization, and prior historical source identity remain unresolved. No retrieval-stage cause is established. " + review["temporal_limit"])
            if review["source_media_inspected"]:
                final_row["transcription_fidelity"] = "query_critical_source_image_reference_only_no_accuracy_rate"
        else:
            final_row["latest_classification"] = row["stored_text_observation"]
        reviewed_rows.append(final_row)
    write_jsonl(out / "source_media_review.jsonl", reviews)
    write_jsonl(out / "reviewed_audit.jsonl", reviewed_rows)
    write_json(out / "sample_provenance_bridge.json", sample_bridge)
    write_json(out / "captured_sample_manifest_reconstructed.json", reconstructed_sample)
    write_json(out / "source_parity_review.json", host_parity)
    summary = {
        "query_channel_rows": len(reviewed_rows), "sample_changed": False,
        "captured_assets": len(reviews), "source_images_inspected": len(IMAGE_REVIEWS),
        "source_audio_clips_heard": 0, "audio_clips_captured_unheard": 2,
        "ocr_visible_source_text_missing_from_archived_window": 2,
        "ocr_missing_signal_at_exact_persisted_feature": 2,
        "ocr_source_and_projected_query_signal_controls": 1,
        "classifications": dict(Counter(r["classification"] for r in reviews)),
        "remaining_source_inspection": {"ocr_queries": 17, "asr_queries": 18},
        "specific_extractor_failure_cause_confirmed": False,
        "sparse_dense_visibility_audited": False, "retrieval_failure_cause_confirmed": False,
        "truth_changes": 0, "cer_wer_reported": False, "audio_access_limitation": AUDIO_LIMITATION,
        "host_parity_query_channel_rows": host_parity["query_channel_rows"],
        "host_feature_files_read": host_parity["feature_files_read"],
        "native_evidence_or_analysis_directories_present": host_parity["native_evidence_or_analysis_directories_present"],
    }
    write_json(out / "source_media_summary.json", summary)

    lines = ["# Bounded source-media review", "",
             "Three recovered source images were viewed. Both empty OCR windows contain query-critical writing at the inspected source anchors; the teaching-slide control has matching query signal in stored OCR. Two audio intervals were captured and verified but could not be heard in this model context. The frozen 20-OCR/18-ASR sample and canonical truth are unchanged.", "",
             "| Query/channel | Source evidence | Bounded finding |", "|---|---|---|"]
    for review in reviews:
        relative = "../source-audit/vecna82-source-media-review-v1/" + Path(review["artifact_relative_path"]).name
        where = (f"frame {review['source_frame_zero_based']} / {review['source_time_seconds']:.2f}s" if review["kind"] == "image"
                 else f"{review['source_interval_seconds'][0]}–{review['source_interval_seconds'][1]}s; captured, unheard")
        refs = "; ".join(f"“{r}”" for r in review["short_source_references"])
        finding = review["source_to_artifact_comparison"]
        lines.append(f"| {review['query_id']} / {review['channel']} | [{where}]({relative}) | {refs + '. ' if refs else ''}{finding} |")
    lines += ["", "Frames use exact zero-based decoded ffmpeg selection. All five source videos report 25/1 nominal and average frame rates, zero start time, and video timebase 1/12800. The two WAVs are mono 16 kHz PCM renditions, with durations 18 and 28 seconds. The source manifest records file byte size, mtime, ffprobe, exact capture commands, and asset hashes; full source-video hashes were intentionally not computed.", "",
              "The recipe print is small, tilted and soft, so its short title/quantity reference has moderate confidence; the commune banner and grammar slide are clear. No CER/WER is calculated. Native OCR boxes/confidences and WhisperX word intervals are not present in the projected-text archive.", "",
              "The host probe narrows both OCR gaps to at or before persisted OCR features: exact sampled files 001745/ocr.npy and 001788/ocr.npy exist and decode to empty strings. Their host metadata equals the pinned archive. This rules out absent sampled-feature files and JSON-only export loss at the inspected anchors. Detection, recognition, normalization, and historical extraction provenance remain unresolved; all 16 native evidence/analysis directories checked across eight query/channel rows are absent. The 13 bounded feature reads agree with archived projections (12 full strings and one captured prefix plus full length). Current index visibility was not inspected.", "",
              "A missing archived OCR signal does not itself prove a retrieval miss: p0_q19 is a saved visual-baseline success. One still also cannot establish first occurrence, visibility throughout the accepted window, or any new truth interval.", "",
              AUDIO_LIMITATION + " No poem wording or soy-sauce quantity has been promoted to a heard source reference. p3_q24 retains its provisional truth tier.", "",
              "The capture manifest retains the original sample SHA d3727ab9…, while the current packet/probe use b4fd9442…. Reconstructing the original 17-entry input registry and changing only its digest reproduces d3727ab9… exactly. The additional source entry is legacy_temporal_control_113.jsonl; selected rows, order, texts, metadata, seed/method and all truth inputs are unchanged. The explicit reconstruction and current score-status checks are in sample_provenance_bridge.json.", "",
              "Next checks use the existing captured WAVs with an audio-capable reviewer. Any exact OCR-stage attribution needs additional retained evidence or a separately bounded diagnostic, because the probed native sidecars are absent. Audit sparse/dense candidate visibility without answer-conditioned queries. No broad re-extraction, truth edits, or model tuning occurred.", "",
              "Replay after the first two audit stages with `python code/dataset_media_audit.py --root .`. All 38 combined rows are in `reviewed_audit.jsonl`; the five media records preserve short source references, confidence, provenance, and unresolved checks in `source_media_review.jsonl`."]
    write_text(out / "SOURCE_MEDIA_REVIEW.md", "\n".join(lines) + "\n")
    audio_lines = ["# Two bounded audio checks", "",
                   "Both source WAVs are captured and SHA-256 verified. This assistant context cannot receive audio input, so no heard source references exist. An audio-capable reviewer only needs to answer the two questions below; the canonical truth remains unchanged.", "",
                   "| Query | Source interval | Smallest review question |", "|---|---|---|"]
    for review in reviews:
        if review["kind"] == "audio":
            relative = "../source-audit/vecna82-source-media-review-v1/" + Path(review["artifact_relative_path"]).name
            audio_lines.append(f"| {review['query_id']} | [{review['source_interval_seconds'][0]}–{review['source_interval_seconds'][1]}s]({relative}) | {review['smallest_review_question']} |")
    audio_lines += ["", "Return the heard phrase, any uncertain words, and approximate phrase onset/offset within the excerpt. Compare it with the preserved projected text only after recording the source reference. Native word intervals are unavailable, and p3_q24 truth remains provisional. No full-video listening, new ASR run, or truth edit is needed for these two checks."]
    write_text(out / "AUDIO_REVIEW_REQUEST.md", "\n".join(audio_lines) + "\n")
    for channel in ("ocr", "asr"):
        subset = [r for r in reviewed_rows if r["channel"] == channel]
        channel_lines = [f"# {channel.upper()} bounded dataset audit", "",
                         f"All {len(subset)} frozen {channel.upper()} cases have projected-text inspection. " +
                         ("Three source images were inspected: two visible-text gaps in archived OCR and one positive signal control. Seventeen source-image reviews remain." if channel == "ocr" else
                          "Two source audio clips were recovered, but the assistant context does not support audio input. All 18 ASR source-fidelity reviews remain pending."), "",
                         "The sample and truth remain unchanged. No particular extractor or retrieval-stage cause has been established; no CER/WER or candidate-flooding metric is claimed.", ""]
        for row in subset:
            review = row["media_review"]
            note = review["source_to_artifact_comparison"] if review else row["artifact_review_note"]
            channel_lines.append(f"- {row['query_id']}: {note}")
        channel_lines += ["", "See reviewed_audit.jsonl for all combined classifications, SOURCE_MEDIA_REVIEW.md for direct source findings, and source_text_audit.jsonl for complete bounded stored strings and source identities."]
        write_text(out / f"{channel.upper()}_REPORT.md", "\n".join(channel_lines) + "\n")
    preparation_summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    preparation_summary.update({"status": "PROJECTED_TEXT_COMPLETE_THREE_SOURCE_IMAGES_REVIEWED_AUDIO_ACCESS_LIMITED",
                                "source_images_inspected": 3, "source_audio_clips_heard": 0,
                                "source_media_reviewed": 3,
                                "source_media_assets_captured": 5,
                                "source_visible_missing_ocr_representation_rows": ["p0_q19", "p0_q21"]})
    preparation_summary["channels"]["ocr"].update({"source_media_reviewed": 3, "pending_local_evidence": 17,
                                                    "visible_text_missing_at_persisted_feature": 2})
    write_json(out / "summary.json", preparation_summary)
    write_json(out / "failure_counts.json", {"status": "TWO_OCR_FEATURE_GAPS_OBSERVED_SPECIFIC_STAGE_CAUSES_UNRESOLVED",
                                             "channels": preparation_summary["channels"],
                                             "full_sample_failure_rates_estimated": False})
    for name, paragraph in (
        ("REVIEW.md", "The preparation notes above are followed by complete stored-text inspection and three source-image inspections. Two visible-text omissions are already present in exact-frame OCR feature files; host metadata matches the pinned archive. Three JPEGs were inspected, two captured WAVs remain unheard because audio input is unsupported, and all temporal truth remains unchanged. See SOURCE_MEDIA_REVIEW.md and reviewed_audit.jsonl for the current combined state."),
        ("PROVENANCE.md", "The text above describes the preparation stage. Later stages preserve the pinned projected text and captured host evidence, including capture timestamps and Windows source paths from the original evidence. The third stage records short references from three directly viewed images, verifies five media hashes plus eight channel-row host parity checks, and records the explicit unsupported-audio-input limitation. sample_provenance_bridge.json proves that the original/current sample SHA delta changes only the appended source-registry provenance. Reproduce all stages in order as documented in SOURCE_HYDRATION.md; no new timestamps or source interpretations are created during replay."),
    ):
        doc = out / name
        initial = doc.read_text(encoding="utf-8").split("\n## Later audit stages\n", 1)[0].rstrip()
        write_text(doc, initial + "\n\n## Later audit stages\n\n" + paragraph + "\n")
    write_text(out / "BTL-RETURN.md", (
        "# BTL return\n\n"
        "Canonical 115/113 reproduction and the frozen 20-OCR/18-ASR sample are complete. All 38 query/channel rows have bounded stored-text inspection from 37 pinned per-video files. Eight temporal queries/31 event points retain unchanged truth and provenance.\n\n"
        "Five bounded source assets were captured and their hashes verified. Three JPEGs were inspected: p0_q19 has a clear Giang Ly commune banner and p0_q21 has a recipe title/200 gr line despite empty exact-frame OCR features and archived windows; p1_q17 has source/archived agreement on the remember lesson. All eight probed host metadata files match the pinned archive, and all 13 feature reads agree with projected text. Loss is at or before OCR feature serialization for the two empty cases; detector/recognizer/normalization and retrieval-stage causes remain unresolved. Native sidecar directories checked for these cases are absent.\n\n"
        "Both source WAVs are ready but unheard: this assistant context rejects audio input. No poem or soy-sauce phrase was source-transcribed, and no CER/WER was computed. The full sample still needs 17 OCR source reviews and 18 ASR source-fidelity reviews. No truth promotion or dataset repair occurred.\n\n"
        "The first and current sample-manifest SHA values differ only because a legacy-control source was appended to the input registry. Exact SHA reconstruction proves selected rows, order, query metadata, seed/method and truth inputs unchanged; score statuses match the pinned preparation output.\n\n"
        "Next: have an audio-capable reviewer inspect only the two captured query-critical excerpts; then audit sparse/dense visibility without answer-conditioned query rewriting. Precise OCR-stage attribution needs additional retained evidence or a separate bounded diagnostic; broad extraction is not justified by these five assets.\n\n"
        "Reproduce the packet with python code/dataset_audit.py --root ., then python code/dataset_text_audit.py --root ., then python code/dataset_media_audit.py --root .\n"
    ))
    write_json(out / "source_media_run_manifest.json", {
        "code_sha256": sha(Path(__file__)), "frozen_sample_sha256": manifest["frozen_sample_sha256"],
        "capture_manifest_sha256": sha(manifest_path), "text_audit_sha256": sha(out / "source_text_audit.jsonl"),
        "source_parity_probe_sha256": host_parity["probe_sha256"],
        "current_sample_sha256": sample_bridge["current_sample_sha256"],
        "sample_bridge_sha256": sha(out / "sample_provenance_bridge.json"),
        "review_annotation_basis": "three directly viewed JPEGs; explicit unsupported-audio-input result",
        "media_artifact_sha256": {r["artifact_relative_path"]: r["artifact_sha256"] for r in reviews},
        "source_images_inspected": 3, "source_audio_clips_heard": 0,
        "no_retrieval_or_model_run": True, "truth_changed": False,
    })
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    write_text(out / "SHA256SUMS.txt", "".join(f"{sha(p)}  {p.relative_to(out).as_posix()}\n" for p in files))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
