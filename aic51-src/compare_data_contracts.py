"""Compare two filesystem/Milvus contract reports without changing either side."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _content_hashes_available(report: dict[str, Any]) -> bool:
    return bool(report.get("content_hashing"))


def _config_features(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("config", {}).get("features", {}) or {}


def _video_entries(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        entry["id"]: entry
        for entry in report.get("videos", {}).get("videos", [])
        if "id" in entry
    }


def _manifest_decision(
    baseline_manifest: str | None,
    candidate_manifest: str | None,
    structural_match: bool,
    content_hashes_available: bool,
    reuse_reason: str,
    verify_reason: str,
    rerun_reason: str,
) -> dict[str, str]:
    if (
        content_hashes_available
        and baseline_manifest
        and candidate_manifest
    ):
        if baseline_manifest == candidate_manifest:
            return {"decision": "reuse", "reason": reuse_reason}
        return {"decision": "reprocess", "reason": rerun_reason}
    if structural_match:
        return {"decision": "verify", "reason": verify_reason}
    return {"decision": "reprocess", "reason": rerun_reason}


def compare_sources(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, dict[str, str]]:
    baseline_videos = _video_entries(baseline)
    candidate_videos = _video_entries(candidate)
    content_hashes_available = _content_hashes_available(baseline) and _content_hashes_available(candidate)
    decisions: dict[str, dict[str, str]] = {}

    for video_id in sorted(set(baseline_videos) | set(candidate_videos)):
        old = baseline_videos.get(video_id)
        new = candidate_videos.get(video_id)
        if old is None:
            decisions[video_id] = {
                "decision": "new_input",
                "reason": "Video is present only in the candidate report.",
            }
            continue
        if new is None:
            decisions[video_id] = {
                "decision": "missing_input",
                "reason": "Video is absent from the candidate report.",
            }
            continue

        structural_match = (
            old.get("relative_path") == new.get("relative_path")
            and old.get("bytes") == new.get("bytes")
        )
        decisions[video_id] = _manifest_decision(
            old.get("sha256"),
            new.get("sha256"),
            structural_match,
            content_hashes_available,
            "Video content hash matches.",
            "Video path and size match, but content hashing was not enabled.",
            "Video path, size, or content differs.",
        )
    return decisions


def compare_keyframes(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    source_decisions: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    old_videos = baseline.get("keyframes", {}).get("videos", {}) or {}
    new_videos = candidate.get("keyframes", {}).get("videos", {}) or {}
    content_hashes_available = _content_hashes_available(baseline) and _content_hashes_available(candidate)
    decisions: dict[str, dict[str, str]] = {}

    for video_id in sorted(set(old_videos) | set(new_videos)):
        old = old_videos.get(video_id)
        new = new_videos.get(video_id)
        if old is None or new is None:
            decisions[video_id] = {
                "decision": "reextract",
                "reason": "Keyframe directory is missing on one side.",
            }
            continue
        if source_decisions.get(video_id, {}).get("decision") in {
            "reprocess",
            "missing_input",
        }:
            decisions[video_id] = {
                "decision": "reextract",
                "reason": "Source video is not reusable.",
            }
            continue

        structural_match = (
            old.get("frame_ids") == new.get("frame_ids")
            and old.get("file_sizes") == new.get("file_sizes")
            and old.get("image_dimensions") == new.get("image_dimensions")
        )
        decisions[video_id] = _manifest_decision(
            old.get("manifest_sha256"),
            new.get("manifest_sha256"),
            structural_match,
            content_hashes_available,
            "Keyframe manifest matches.",
            "Keyframe IDs and structure match, but content hashing was not enabled.",
            "Keyframe IDs, structure, or content differs.",
        )
    return decisions


def compare_features(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    keyframe_decisions: dict[str, dict[str, str]],
) -> dict[str, dict[str, dict[str, str]]]:
    old_config = _config_features(baseline)
    new_config = _config_features(candidate)
    old_videos = baseline.get("features", {}).get("videos", {}) or {}
    new_videos = candidate.get("features", {}).get("videos", {}) or {}
    content_hashes_available = _content_hashes_available(baseline) and _content_hashes_available(candidate)
    decisions: dict[str, dict[str, dict[str, str]]] = {}

    for video_id in sorted(set(old_videos) | set(new_videos) | set(keyframe_decisions)):
        old = old_videos.get(video_id, {})
        new = new_videos.get(video_id, {})
        old_counts = old.get("feature_counts", {}) or {}
        new_counts = new.get("feature_counts", {}) or {}
        old_manifests = old.get("feature_manifests", {}) or {}
        new_manifests = new.get("feature_manifests", {}) or {}
        frame_action = keyframe_decisions.get(video_id, {}).get("decision")
        video_decisions: dict[str, dict[str, str]] = {}

        for feature_name in sorted(new_config):
            if feature_name not in old_config:
                video_decisions[feature_name] = {
                    "decision": "analyse",
                    "reason": "Feature is new in the candidate configuration.",
                }
                continue
            if old_config[feature_name] != new_config[feature_name]:
                video_decisions[feature_name] = {
                    "decision": "reanalyse",
                    "reason": "Feature model or index contract changed.",
                }
                continue
            if frame_action in {"reextract", "reprocess"}:
                video_decisions[feature_name] = {
                    "decision": "reanalyse",
                    "reason": "Feature inputs are changing with the keyframes.",
                }
                continue
            if feature_name not in new_counts:
                video_decisions[feature_name] = {
                    "decision": "analyse",
                    "reason": "Candidate report has no output for this feature.",
                }
                continue

            structural_match = (
                old_counts.get(feature_name) == new_counts.get(feature_name)
                and old.get("feature_frame_ids", {}).get(feature_name)
                == new.get("feature_frame_ids", {}).get(feature_name)
            )
            video_decisions[feature_name] = _manifest_decision(
                old_manifests.get(feature_name),
                new_manifests.get(feature_name),
                structural_match,
                content_hashes_available,
                "Feature manifest matches.",
                "Feature coverage matches, but content hashing was not enabled.",
                "Feature output coverage or content differs.",
            )
        decisions[video_id] = video_decisions
    return decisions


def compare_milvus(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, str]:
    old = baseline.get("milvus", {}) or {}
    new = candidate.get("milvus", {}) or {}
    if not old.get("enabled") or not new.get("enabled"):
        return {
            "decision": "inspect_required",
            "reason": "Both reports must include enabled Milvus metadata.",
        }
    if not old.get("exists") or not new.get("exists"):
        return {
            "decision": "inspect_required",
            "reason": "Both referenced collections must exist.",
        }
    old_contract = {
        "schema": old.get("schema"),
        "indexes": old.get("indexes"),
    }
    new_contract = {
        "schema": new.get("schema"),
        "indexes": new.get("indexes"),
    }
    if old_contract == new_contract:
        return {
            "decision": "reuse_possible",
            "reason": "Collection schema and indexes match.",
        }
    return {
        "decision": "new_collection_required",
        "reason": "Collection schema or indexes differ.",
    }


def compare_reports(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    old_features = _config_features(baseline)
    new_features = _config_features(candidate)
    changed_features = sorted(
        name
        for name in set(old_features) & set(new_features)
        if old_features[name] != new_features[name]
    )
    source_decisions = compare_sources(baseline, candidate)
    keyframe_decisions = compare_keyframes(baseline, candidate, source_decisions)
    feature_decisions = compare_features(baseline, candidate, keyframe_decisions)
    milvus_decision = compare_milvus(baseline, candidate)

    all_keyframes_reusable = all(
        item.get("decision") == "reuse" for item in keyframe_decisions.values()
    )
    all_features_reusable = all(
        item.get("decision") == "reuse"
        for video in feature_decisions.values()
        for item in video.values()
    )
    index_decision = "reuse_possible"
    if not all_keyframes_reusable or not all_features_reusable:
        index_decision = "rebuild_required"
    if milvus_decision["decision"] == "new_collection_required":
        index_decision = "new_collection_required"

    return {
        "report_version": 1,
        "baseline": baseline.get("workspace"),
        "candidate": candidate.get("workspace"),
        "configuration": {
            "add_changed": baseline.get("config", {}).get("add")
            != candidate.get("config", {}).get("add"),
            "features_added": sorted(set(new_features) - set(old_features)),
            "features_removed": sorted(set(old_features) - set(new_features)),
            "features_changed": changed_features,
        },
        "sources": source_decisions,
        "keyframes": keyframe_decisions,
        "features": feature_decisions,
        "milvus": milvus_decision,
        "index": {
            "decision": index_decision,
            "reason": "All reusable artifacts and a compatible collection are required for reuse.",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path, help="Existing batch contract report.")
    parser.add_argument("candidate", type=Path, help="Candidate/new-version contract report.")
    parser.add_argument("--output", type=Path, help="Write comparison JSON to this path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    rendered = json.dumps(compare_reports(baseline, candidate), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
