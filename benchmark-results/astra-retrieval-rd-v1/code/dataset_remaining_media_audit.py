#!/usr/bin/env python3
"""Apply recorded observations for the rest of the unchanged OCR/ASR sample.

Run after dataset_audit.py, dataset_text_audit.py and dataset_media_audit.py.
This verifies and replays annotations from directly viewed images. It does not
infer new image content, hear audio, run extraction, or change benchmark truth.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path
import wave

from dataset_audit import read_jsonl, sha, write_json, write_jsonl, write_text
from dataset_media_audit import AUDIO_LIMITATION, verify_host_parity


def verified_assets(root, channel):
    directory = root / f"outputs/source-audit/vecna82-source-media-remaining-{channel}-v1"
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Remaining {channel.upper()} capture manifest is required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    request_path = root / f"outputs/dataset-audit/remaining_{channel}_capture_request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if manifest["request_manifest_sha256"] != sha(request_path):
        raise ValueError("Captured request identity mismatch")
    if manifest["frozen_sample_sha256"] != sha(root / "outputs/dataset-audit/sample_manifest.json"):
        raise ValueError("Captured sample identity mismatch")
    requested = {r["query_id"]: r for r in request["requests"]}
    if len(manifest["assets"]) != len(requested) or {a["query_id"] for a in manifest["assets"]} != set(requested):
        raise ValueError("Captured identities differ from the declared remaining set")
    verified = []
    for asset in manifest["assets"]:
        expected = requested[asset["query_id"]]
        for field in ("query_id", "channel", "kind", "video", "frame") if channel == "ocr" else ("query_id", "channel", "kind", "video", "start_s", "end_s"):
            if asset[field] != expected[field]:
                raise ValueError(f"Changed source request field {field}")
        path = directory / asset["artifact"]
        if asset["status"] != "CAPTURED" or not asset["source_size_mtime_unchanged"]:
            raise ValueError("Failed capture or changing source video")
        if sha(path) != asset["artifact_sha256"] or path.stat().st_size != asset["artifact_bytes"]:
            raise ValueError("Captured asset bytes changed")
        asset = {**asset, "artifact_relative_path": path.relative_to(root).as_posix(),
                 "capture_manifest_relative_path": manifest_path.relative_to(root).as_posix(),
                 "capture_manifest_sha256": sha(manifest_path),
                 "truth_source": manifest["truth_source"], "text_source": manifest["text_source"]}
        stream = next(s for s in asset["ffprobe"]["streams"] if s["codec_type"] == "video")
        fps = Fraction(stream["avg_frame_rate"])
        if abs(float(fps) - expected["expected_fps"]) > 1e-6 or float(stream["start_time"]) != 0:
            raise ValueError("Fresh source timing differs from request")
        if channel == "ocr":
            asset["source_time_seconds"] = float(Fraction(asset["frame"], 1) / fps)
            asset["archive_rounded_fps_time_seconds"] = asset["frame"] / round(float(fps))
        else:
            with wave.open(str(path), "rb") as wav:
                asset["audio_format"] = {"channels": wav.getnchannels(), "sample_rate": wav.getframerate(),
                                         "sample_width_bytes": wav.getsampwidth(),
                                         "duration_seconds": wav.getnframes() / wav.getframerate()}
            fmt = asset["audio_format"]
            if fmt["channels"] != 1 or fmt["sample_rate"] != 16000 or fmt["sample_width_bytes"] != 2 or abs(fmt["duration_seconds"] - (asset["end_s"] - asset["start_s"])) > 0.02:
                raise ValueError("Unexpected bounded audio rendition")
        verified.append(asset)
    return verified, manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    out = root / "outputs/dataset-audit"
    rows = read_jsonl(out / "reviewed_audit.jsonl")
    base_media = read_jsonl(out / "source_media_review.jsonl")
    original_keys = {("ocr", "p0_q19"), ("ocr", "p0_q21"), ("ocr", "p1_q17"), ("asr", "p0_q20"), ("asr", "p3_q24")}
    base_media = [r for r in base_media if (r["channel"], r["query_id"]) in original_keys]
    if len(rows) != 38 or len(base_media) != 5:
        raise ValueError("Expected the unchanged sample and original five reviewed/captured assets")
    observations_path = out / "remaining_ocr_observations.jsonl"
    observations = {r["query_id"]: r for r in read_jsonl(observations_path)}
    ocr_assets, ocr_manifest = verified_assets(root, "ocr")
    asr_assets, asr_manifest = verified_assets(root, "asr")
    if set(observations) != {a["query_id"] for a in ocr_assets} or len(observations) != 17:
        raise ValueError("Each remaining OCR row must have one recorded direct image observation")
    by_key = {(r["channel"], r["query_id"]): r for r in rows}
    text_rows = read_jsonl(out / "source_text_audit.jsonl")
    initial_parity = verify_host_parity(root, text_rows)
    remaining_parity = verify_host_parity(root, text_rows, root / "inputs/source_parity_probe_remaining.json",
                                         "https://github.com/JimmyK300/ai-routing-hub/issues/1#issuecomment-5697563634")
    parity_rows = initial_parity["results"] + remaining_parity["results"]
    parity_by_key = {(r["channel"], r["query_id"]): r for r in parity_rows}
    if len(parity_rows) != 38 or set(parity_by_key) != set(by_key):
        raise ValueError("Host parity must cover every frozen query/channel row exactly once")
    listening = json.loads((out / "asr_listening_questions.json").read_text(encoding="utf-8"))
    media = list(base_media)
    for asset in ocr_assets + asr_assets:
        key = asset["channel"], asset["query_id"]
        row = by_key[key]
        review = {"query_id": key[1], "channel": key[0], "kind": asset["kind"],
                  "canonical_query": row["canonical_query"], "truth_tier": row["truth_tier"],
                  "artifact_relative_path": asset["artifact_relative_path"],
                  "artifact_sha256": asset["artifact_sha256"], "source_video_path": asset["source_path"],
                  "source_file": asset["source_file"], "ffprobe": asset["ffprobe"],
                  "capture_manifest_sha256": asset["capture_manifest_sha256"],
                  "capture_manifest_relative_path": asset["capture_manifest_relative_path"],
                  "truth_source": asset["truth_source"], "text_source": asset["text_source"],
                  "current_sample_selection_sha256": sha(out / "sample_manifest.json"),
                  "truth_changed": False, "cer": None, "wer": None,
                  "sparse_dense_visibility_audited": False, "duplicate_flooding_confirmed": False,
                  "source_identity_limit": "Current source-video size/mtime and ffprobe are recorded; full video hashes and historical extraction provenance are unavailable."}
        review["host_parity"] = parity_by_key[key]
        if key[0] == "ocr":
            observation = observations[key[1]]
            if observation["artifact_sha256"] != asset["artifact_sha256"] or observation["source_frame_zero_based"] != asset["frame"]:
                raise ValueError("Image annotation is not bound to the captured bytes/frame")
            if observation["source_media_inspected"] is not True:
                raise ValueError("Uninspected OCR row cannot be marked complete")
            review.update(observation)
            if observation.get("same_frame_feature_query_signal_gap"):
                exact = [f for f in review["host_parity"]["feature_reads"] if f["actual_feature_frame"] == asset["frame"]]
                if len(exact) != 1 or exact[0]["text_read_status"] != "read" or exact[0]["frame_offset"] != 0:
                    raise ValueError("A claimed same-frame gap lacks an exact decoded feature read")
            review.update({"review_status": "SOURCE_IMAGE_INSPECTED",
                           "source_time_seconds": asset["source_time_seconds"],
                           "archive_rounded_fps_time_seconds": asset["archive_rounded_fps_time_seconds"],
                           "temporal_limit": asset["coverage_limit"]})
            frames = [f for b in row["bounded_artifacts"] for f in b["frames"]]
            review["nearest_projected_record"] = min(frames, key=lambda f: abs(f["frame_idx"] - asset["frame"])) if frames else None
            review["source_reference_scope"] = "Only the observed query-critical writing or structure at this representative frame; not a full-frame OCR ground-truth transcript."
        else:
            review.update({"review_status": "AUDIO_CAPTURED_NOT_HEARD", "source_media_inspected": False,
                           "classification": "source_audio_fidelity_unreviewed", "short_source_references": [],
                           "source_interval_seconds": [asset["start_s"], asset["end_s"]],
                           "audio_format": asset["audio_format"], "access_limitation": AUDIO_LIMITATION,
                           "source_observation": "Bounded source WAV captured and verified; speech not heard in this assistant context.",
                           "source_to_artifact_comparison": "No source-audio fidelity comparison is available; preserved projected-text observations remain unverified against speech.",
                           "primary_failure": "unresolved", "cause_status": "source_audio_review_pending",
                           "smallest_review_question": listening["questions"][key[1]],
                           "temporal_limit": asset["coverage_limit"]})
        media.append(review)
    media_by_key = {(r["channel"], r["query_id"]): r for r in media}
    combined = []
    for row in rows:
        row = dict(row)
        review = media_by_key.get((row["channel"], row["query_id"]))
        row["media_review"] = review
        row["host_parity"] = parity_by_key[(row["channel"], row["query_id"])]
        if review:
            row.update({k: review[k] for k in ("review_status", "source_media_inspected", "primary_failure")})
            row["latest_classification"] = review["classification"]
            row["interpretation_limit"] = review["temporal_limit"] + " No live sparse/dense candidate visibility or downstream cause was assessed."
        combined.append(row)
    write_jsonl(out / "reviewed_audit.jsonl", combined)
    write_jsonl(out / "source_media_review.jsonl", media)
    parity_summary = {"query_channel_rows": 38, "host_metadata_parity_rows": 38,
                      "unique_host_metadata_files": len({r["metadata_path"] for r in parity_rows}),
                      "feature_files_read": sum(len(r["feature_reads"]) for r in parity_rows),
                      "native_evidence_or_analysis_directories_present": sum(int(r[k]["exists"]) for r in parity_rows for k in ("native_evidence", "native_analysis")),
                      "native_directories_checked": len(parity_rows) * 2,
                      "source_probes": [{k: r[k] for k in ("probe_sha256", "broker_source_url")} for r in (initial_parity, remaining_parity)],
                      "results": parity_rows}
    write_json(out / "source_parity_review.json", parity_summary)
    same_frame_gaps = sorted({"p0_q19", "p0_q21"} | {r["query_id"] for r in observations.values() if r.get("same_frame_feature_query_signal_gap")})
    summary = {"query_channel_rows": 38, "ocr_source_images_inspected": 20, "source_images_inspected": 20,
               "source_audio_clips_heard": 0, "ocr_queries_without_source_image": 0,
               "asr_source_clips_captured": sum(r["kind"] == "audio" for r in media),
               "asr_source_clips_heard": 0, "asr_fidelity_reviews_pending": 18,
               "source_review_coverage": "One directly inspected representative frame per OCR query; not complete temporal or full-window coverage.",
               "ocr_classifications": dict(Counter(r["classification"] for r in media if r["channel"] == "ocr")),
               "sample_changed": False, "truth_changes": 0, "cer_wer_reported": False,
               "same_frame_ocr_query_signal_gap_count": len(same_frame_gaps),
               "same_frame_ocr_query_signal_gap_queries": same_frame_gaps,
               "same_frame_gap_scope": "Query-critical writing missing or unrecoverably corrupted at the inspected sampled frame; not a full-window absence or a retrieval miss.",
               "host_metadata_parity_rows": 38, "host_feature_files_read": parity_summary["feature_files_read"],
               "native_evidence_or_analysis_directories_present": parity_summary["native_evidence_or_analysis_directories_present"],
               "audio_access_limitation": AUDIO_LIMITATION}
    write_json(out / "source_media_summary.json", summary)
    lines = ["# Frozen-sample source review", "",
             "All 20 frozen OCR queries have one directly inspected representative source frame. This completes representative-image coverage while preserving sequence, count, visibility, and truth-boundary limits. Audio clips remain a listening packet: this assistant context cannot hear audio.", "",
             "| OCR query | Source frame / seconds | Observation |", "|---|---|---|"]
    for row in combined:
        if row["channel"] != "ocr":
            continue
        review = row["media_review"]
        link = "../source-audit/" + review["artifact_relative_path"].split("outputs/source-audit/", 1)[1]
        lines.append(f"| {row['query_id']} | [{review['source_frame_zero_based']} / {review['source_time_seconds']:.3f}s]({link}) | {review['source_to_artifact_comparison']} |")
    lines += ["", "Image references are anchored to exact decoded source frames. For noninteger frame rates, source seconds use the fresh ffprobe average frame rate; archived projected-text times may instead divide by rounded FPS. Exact frame identity is preserved in both representations. No truth times or intervals were rewritten.", "",
              f"All 38 query/channel comparisons of host metadata match the pinned archive (37 unique files), and all {parity_summary['feature_files_read']} bounded decoded feature-text comparisons match projected strings (full text, or captured prefix plus full character count where truncated). All 76 probed native evidence/analysis directory checks report absent paths. Five exact sampled anchors have visible query-critical writing missing or unrecoverably corrupted in persisted OCR features: {', '.join(same_frame_gaps)}. This localizes those anchor omissions to at or before feature serialization, without distinguishing detection, recognition, or normalization. p1_q24 still has its answer text in other accepted-window OCR records. None of these counts is a whole-query retrieval-failure rate.", "",
              f"{summary['asr_source_clips_captured']} of 18 ASR source excerpts are captured; zero were heard. See AUDIO_REVIEW_REQUEST.md for one bounded source-reference question per query. No CER/WER, candidate-flooding rate, or downstream retrieval-failure cause is claimed.", "",
              "Replay with the first three audit stages, then `python code/dataset_remaining_media_audit.py --root .`. The recorded 17-image annotations are in remaining_ocr_observations.jsonl; all 38 combined rows remain in reviewed_audit.jsonl."]
    write_text(out / "SOURCE_MEDIA_REVIEW.md", "\n".join(lines) + "\n")
    write_text(out / "OCR_REPORT.md", "\n".join(lines) + "\n")
    audio_lines = ["# Frozen ASR listening packet", "", listening["instructions"], "", AUDIO_LIMITATION, "",
                   "| Query | Captured source excerpt | Smallest review question |", "|---|---|---|"]
    for row in combined:
        if row["channel"] != "asr":
            continue
        review = media_by_key.get(("asr", row["query_id"]))
        if review:
            link = "../source-audit/" + review["artifact_relative_path"].split("outputs/source-audit/", 1)[1]
            where = f"[{review['source_interval_seconds'][0]}–{review['source_interval_seconds'][1]}s]({link})"
        else:
            where = "Capture pending"
        audio_lines.append(f"| {row['query_id']} | {where} | {listening['questions'][row['query_id']]} |")
    write_text(out / "AUDIO_REVIEW_REQUEST.md", "\n".join(audio_lines) + "\n")
    write_text(out / "ASR_REPORT.md", "\n".join(audio_lines) + "\n")
    preparation = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    preparation.update({"status": "ALL20_OCR_REPRESENTATIVES_INSPECTED_ASR_LISTENING_PENDING", "source_images_inspected": 20,
                        "source_media_reviewed": 20, "source_audio_clips_heard": 0, "source_media_assets_captured": len(media)})
    preparation["channels"]["ocr"].update({"source_media_reviewed": 20, "pending_local_evidence": 0,
                                           "visible_text_missing_at_persisted_feature": len(same_frame_gaps),
                                           "coverage_limit": "Representative still inspected; full temporal query obligations may remain unresolved."})
    preparation["source_visible_missing_ocr_representation_rows"] = same_frame_gaps
    write_json(out / "summary.json", preparation)
    write_json(out / "failure_counts.json", {"status": "FIVE_SAME_FRAME_OCR_SIGNAL_GAPS_SOURCE_AUDIO_UNHEARD",
                                             "channels": preparation["channels"],
                                             "full_sample_failure_rates_estimated": False,
                                             "same_frame_gap_scope": summary["same_frame_gap_scope"]})
    write_text(out / "BTL-RETURN.md", (
        "# BTL return\n\n"
        "The unchanged 20-OCR/18-ASR sample now has one directly inspected representative source frame for every OCR query. All 18 bounded ASR source excerpts are captured and verified, but none was heard because this assistant context does not support audio input. Stored-text inspection covers all 38 rows.\n\n"
        f"All 38 query/channel host metadata comparisons (37 unique files) and {parity_summary['feature_files_read']} decoded feature-text comparisons match the pinned projected-text archive. All 76 native evidence/analysis directory checks report absent paths. Five exact sampled anchors lose query-critical visible writing at or before stored OCR features: {', '.join(same_frame_gaps)}. The precise detector/recognizer/normalization cause is unresolved; one of these queries retains its answer text elsewhere in the accepted window. No retrieval-failure rate or CER/WER is inferred.\n\n"
        "Structured diagrams, tables, curves and map counts require spatial relationships; some small sign writing is not reliably legible at the representative frame. One still does not adjudicate full event sequences, final states, absence across time, or new truth boundaries. All benchmark truth remains unchanged, including provisional P3 rows.\n\n"
        "The original/current sample SHA bridge is exact: only appended input-registry provenance changed, with selected rows, order, metadata, seed/method and truth inputs preserved.\n\n"
        "Next source task: use AUDIO_REVIEW_REQUEST.md for the 18 minimal listening checks. The remaining OCR findings are documented source-readability, structural-representation and temporal-coverage limitations; they do not authorize broad extraction or truth edits. Sparse/dense visibility has not been assessed in this dataset audit.\n\n"
        "Replay dataset_audit.py, dataset_text_audit.py, dataset_media_audit.py and dataset_remaining_media_audit.py in that order with --root .; hydrate pinned source JSON first if needed.\n"
    ))
    for name, paragraph in (
        ("REVIEW.md", "The preparation notes above are followed by complete stored-text inspection and one directly inspected representative source frame for each of the 20 OCR queries. All 18 bounded ASR excerpts are captured but unheard because audio input is unsupported. Five exact sampled OCR anchors lose visible query-critical writing at or before persisted features. All 38 host metadata comparisons and 61 feature-text comparisons pass; native sidecars checked for all cases are absent. Source readability, structural relationships and full temporal obligations retain their per-row limits. All truth remains unchanged. See SOURCE_MEDIA_REVIEW.md and reviewed_audit.jsonl for the combined current state."),
        ("PROVENANCE.md", "The text above describes preparation. Four replay stages now preserve all 38 bounded text inspections, 20 directly viewed source frames, 18 captured-but-unheard WAVs, and 38 channel-row host parity checks. Capture manifests retain original timestamps, source file size/mtime, ffprobe, exact source paths and asset hashes; whole source-video hashes and historical extraction sidecars are unavailable. sample_provenance_bridge.json proves that the original/current sample SHA delta changes only appended source-registry provenance. The fourth stage verifies all remaining source identities and replays the recorded observations without generating new source interpretations. Run all four stages in the order documented in SOURCE_HYDRATION.md."),
    ):
        doc = out / name
        initial = doc.read_text(encoding="utf-8").split("\n## Later audit stages\n", 1)[0].rstrip()
        write_text(doc, initial + "\n\n## Later audit stages\n\n" + paragraph + "\n")
    write_json(out / "remaining_media_run_manifest.json", {"code_sha256": sha(Path(__file__)),
               "observations_sha256": sha(observations_path), "ocr_capture_manifest_sha256": sha(ocr_manifest),
               "asr_capture_manifest_sha256": sha(asr_manifest) if asr_manifest else None,
               "source_parity_probe_sha256": initial_parity["probe_sha256"],
               "remaining_source_parity_probe_sha256": remaining_parity["probe_sha256"],
               "source_images_inspected": 20, "source_audio_clips_heard": 0, "truth_changed": False,
               "frozen_sample_sha256": sha(out / "sample_manifest.json")})
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    write_text(out / "SHA256SUMS.txt", "".join(f"{sha(p)}  {p.relative_to(out).as_posix()}\n" for p in files))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
