#!/usr/bin/env python3
"""Prepare remaining frozen-sample source captures, independent of retrieval scores."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dataset_audit import read_jsonl, sha, write_json
from dataset_text_audit import locators


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    out = root / "outputs/dataset-audit"
    rows = read_jsonl(out / "audit.jsonl")
    by_key = {(r["channel"], r["query_id"]): r for r in rows}
    probes = json.loads((out / "host_probe_requests.json").read_text(encoding="utf-8"))
    original_capture = json.loads((root / "outputs/source-audit/vecna82-source-media-review-v1/manifest.json").read_text(encoding="utf-8"))
    completed = {(r["channel"], r["query_id"]) for r in original_capture["assets"] if r["status"] == "CAPTURED"}
    if completed != {("ocr", "p0_q19"), ("ocr", "p0_q21"), ("ocr", "p1_q17"), ("asr", "p0_q20"), ("asr", "p3_q24")}:
        raise ValueError("Original five captured query/channel identities changed")
    if len(by_key) != 38 or probes["frozen_sample_sha256"] != sha(out / "sample_manifest.json"):
        raise ValueError("Unexpected frozen sample")
    for channel, expected_remaining in (("ocr", 17), ("asr", 16)):
        requests = []
        for probe in probes["requests"]:
            key = (probe["channel"], probe["query_id"])
            if probe["channel"] != channel or key in completed:
                continue
            row = by_key[key]
            windows = [w for w in locators(row) if w["video_id"] == probe["video_id"]]
            anchor = probe["probe_anchor_frames"][0]
            containing = [w for w in windows if w["start_frame"] <= anchor <= w["end_frame"]]
            if not containing:
                raise ValueError("Declared first anchor is outside the canonical window")
            request = {"query_id": probe["query_id"], "channel": channel,
                       "kind": "image" if channel == "ocr" else "audio",
                       "video": probe["video_relative_path"], "expected_fps": probe["known_fps"],
                       "canonical_query": row["canonical_query"], "truth_tier": row["truth_tier"],
                       "representative_anchor_frame": anchor,
                       "canonical_windows_preserved": windows,
                       "reason": "Complete one representative source observation for each remaining row in the frozen sample, using the first previously declared anchor; no retrieval-outcome selection."}
            if channel == "ocr":
                request["frame"] = anchor
                request["coverage_limit"] = "One source still can assess visible signal at this anchor; it does not establish a sequence, a count across time, first occurrence, or full-window visibility."
            else:
                window = containing[0]
                start, end = window["start_frame"] / probe["known_fps"], window["end_frame"] / probe["known_fps"]
                center = anchor / probe["known_fps"]
                if end - start <= 28:
                    start_s, end_s = max(0, start - 2), end + 2
                else:
                    start_s = min(max(start, center - 14), end - 28)
                    end_s = start_s + 28
                request.update({"start_s": round(start_s, 6), "end_s": round(end_s, 6),
                                "coverage_limit": "Representative 28-second excerpt, or a shorter full canonical window with two seconds of surrounding context. This prepares listening only; it does not establish complete speech coverage or a heard reference."})
            requests.append(request)
        if len(requests) != expected_remaining:
            raise ValueError("Remaining frozen-sample count changed")
        packet = {"schema": "vecna82-remaining-source-capture-v1", "channel": channel,
                  "frozen_sample_sha256": probes["frozen_sample_sha256"],
                  "truth_source": original_capture["truth_source"], "text_source": original_capture["text_source"],
                  "scope": f"Only the remaining {len(requests)} {channel.upper()} query/channel rows of the unchanged 20-OCR/18-ASR sample; no dataset writes or model runs.",
                  "selection_rule": "First previously declared probe anchor: first preserved submitted anchor within a canonical window, otherwise canonical window midpoint. ASR uses 28 seconds around that anchor fitted inside the containing window; windows <=28 seconds receive two seconds of surrounding context. No baseline/reranker outcome or extracted-text quality participates.",
                  "existing_capture_manifest_sha256": sha(root / "outputs/source-audit/vecna82-source-media-review-v1/manifest.json"),
                  "source_probe_requests_sha256": sha(out / "host_probe_requests.json"),
                  "requests": requests}
        target = out / f"remaining_{channel}_capture_request.json"
        write_json(target, packet)
        print(json.dumps({"path": str(target.relative_to(root)), "sha256": sha(target), "requested": len(requests),
                          "total_audio_seconds": round(sum(r.get("end_s", 0) - r.get("start_s", 0) for r in requests), 3)}))


if __name__ == "__main__":
    main()
