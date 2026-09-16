#!/usr/bin/env python3
"""GT-blind Packet B transforms over immutable provider frame lists.

The exact main control is nested max scaling, not RRF or min-max.  Exported
``candidate_tie_order`` preserves main's stable sort over a Python set.  We
refuse to invent this order, project weights, score orientation, or a baseline.
This module has no model/database dependencies and never reads ground truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

SCHEMA = "vecna82-provider-export-v1"
PROVIDERS = ("qwen", "siglip", "ocr_sparse", "ocr_dense", "asr_sparse", "asr_dense")
STATES = {"ok", "empty", "disabled", "unavailable", "failed", "not_attempted"}
ARMS = ("fusion_current_control", "fusion_rrf", "fusion_minmax_sum",
        "fusion_robust_z_sum", "fusion_softmax_sum")
RRF_K = 60  # official-dataset-control/scripts/generate_unknown_query_candidates.py
MAD_FACTOR = 1.4826
ROBUST_CLIP = 6.0
SOFTMAX_TEMPERATURE = 1.0


class ContractError(ValueError):
    """Input does not establish a fair frozen comparison."""


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_json(data: Any) -> str:
    return digest_bytes(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"), allow_nan=False).encode("utf-8"))


def run_identity_digest(manifest: dict) -> str:
    return digest_json({key: manifest[key] for key in
                       ("run_id", "identity", "config_sha256", "canonical_queries_sha256", "collector_sha256")})


def finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ContractError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ContractError(f"{name} must be finite")
    return result


def validate_config(config: dict) -> dict:
    if config.get("schema") != "vecna82-fusion-config-v1":
        raise ContractError("missing or unsupported frozen fusion config")
    if not config.get("weight_authority") or not config.get("alpha_authority"):
        raise ContractError("weights and alphas require explicit project authority")
    if config.get("rrf_k") != RRF_K:
        raise ContractError("RRF k must remain the inherited project value 60")
    if config.get("robust_clip") != ROBUST_CLIP or config.get("mad_factor") != MAD_FACTOR:
        raise ContractError("robust transform differs from the predeclared policy")
    if config.get("softmax_temperature") != SOFTMAX_TEMPERATURE:
        raise ContractError("temperature differs from the predeclared policy")
    for key in ("ocr_weight", "asr_weight", "ocr_alpha", "asr_alpha"):
        if key not in config or not 0 <= finite(config[key], key) <= 1:
            raise ContractError(f"explicit {key} must be within [0,1]")
    if config["ocr_weight"] + config["asr_weight"] > 1:
        raise ContractError("weights require runtime clamping; freeze effective values instead")
    if config.get("visual_providers") != ["qwen", "siglip"]:
        raise ContractError("this frozen contract requires Qwen then SigLIP visual providers")
    if config.get("visual_weight_policy") != "equal_nominal_share":
        raise ContractError("declare equal nominal visual shares from the established donor path")
    for key in ("provider_depth", "output_frame_k", "output_video_k", "expected_query_count"):
        if isinstance(config.get(key), bool) or not isinstance(config.get(key), int) or config[key] <= 0:
            raise ContractError(f"{key} must be an explicit positive integer")
    if config["provider_depth"] not in (50, 100):
        raise ContractError("only primary depth100 or declared depth50 truncation is supported")
    if config.get("collapse") != "truncate_frames_then_first_unique_video":
        raise ContractError("unknown frame/video collapse contract")
    if config.get("tie_break") != "exported_main_set_order":
        raise ContractError("exact main tie behavior requires an exported candidate order")
    if config.get("score_orientation") != "higher_is_better":
        raise ContractError("current control only supports established COSINE/BM25 orientation")
    return config


def nominal_weights(config: dict) -> dict[str, float]:
    visual = 1.0 - config["ocr_weight"] - config["asr_weight"]
    return {
        "qwen": visual / 2.0, "siglip": visual / 2.0,
        "ocr_sparse": config["ocr_weight"] * (1.0 - config["ocr_alpha"]),
        "ocr_dense": config["ocr_weight"] * config["ocr_alpha"],
        "asr_sparse": config["asr_weight"] * (1.0 - config["asr_alpha"]),
        "asr_dense": config["asr_weight"] * config["asr_alpha"],
    }


def frame_video(frame_id: str) -> str:
    if not isinstance(frame_id, str) or frame_id.count("#") != 1:
        raise ContractError("frame_id must be the exact video#frame key")
    video, frame = frame_id.split("#")
    if not video or not frame.isdigit():
        raise ContractError("frame_id has an invalid video or frame component")
    return video


def validate_row(row: dict, config: dict) -> dict[str, dict[str, float]]:
    if row.get("schema") != SCHEMA or row.get("status") != "complete":
        raise ContractError("provider export is incomplete or has unknown schema")
    if row.get("config_sha256") != digest_json(config):
        raise ContractError("export was collected with a different frozen config")
    run_identity = row.get("run_identity_sha256")
    if (not isinstance(run_identity, str) or len(run_identity) != 64
            or any(c not in "0123456789abcdef" for c in run_identity)):
        raise ContractError("provider row lacks an immutable collection/model/run identity")
    if not row.get("query_id") or not isinstance(row.get("query_text"), str):
        raise ContractError("query ID/text missing")
    if row.get("query_text_sha256") != digest_bytes(row["query_text"].encode("utf-8")):
        raise ContractError("query text hash mismatch")
    if row.get("transformations") != {"query_expansion": False, "translation": False,
                                      "reranking": False, "yolo": False,
                                      "temporal_parser": False, "segment_clustering": False}:
        raise ContractError("non-target query/retrieval behavior was not proved off")
    providers = row.get("providers", {})
    if set(providers) != set(PROVIDERS):
        raise ContractError("all six provider states must be explicit")
    weights = nominal_weights(config)
    maps = {}
    candidate_ids = set()
    for name in PROVIDERS:
        provider = providers[name]
        state = provider.get("state")
        if state not in STATES:
            raise ContractError(f"{name}: unknown provider state")
        hits = provider.get("hits")
        if not isinstance(hits, list):
            raise ContractError(f"{name}: explicit hit list required")
        if state == "ok" and not hits:
            raise ContractError(f"{name}: an empty list must have state empty")
        if state != "ok" and hits:
            raise ContractError(f"{name}: non-ok provider contains hits")
        if state in {"failed", "not_attempted"} and weights[name] > 0:
            raise ContractError(f"{name}: a failed/unattempted active provider cannot mimic current output")
        if state == "disabled" and weights[name] > 0:
            raise ContractError(f"{name}: active provider marked disabled")
        if provider.get("metric") != ("BM25" if name.endswith("sparse") else "COSINE"):
            raise ContractError(f"{name}: unknown score metric/orientation")
        if provider.get("score_orientation") != "higher_is_better":
            raise ContractError(f"{name}: raw score orientation is ambiguous")
        if len(hits) > config["provider_depth"]:
            raise ContractError(f"{name}: input list exceeds the frozen depth")
        previous = math.inf
        score_map = {}
        for rank, hit in enumerate(hits, 1):
            fid = hit.get("frame_id")
            video = frame_video(fid)
            if hit.get("video_id") != video or hit.get("rank") != rank:
                raise ContractError(f"{name}: frame/video identity or rank sequence differs")
            if fid in score_map:
                raise ContractError(f"{name}: duplicate frame must not cast extra votes")
            score = finite(hit.get("score"), f"{name}.score")
            if score > previous:
                raise ContractError(f"{name}: scores contradict rank/orientation")
            previous = score
            score_map[fid] = score
        maps[name] = score_map if weights[name] > 0 else {}
        candidate_ids.update(maps[name])
    tie_order = row.get("candidate_tie_order")
    if (not isinstance(tie_order, list) or len(tie_order) != len(set(tie_order))
            or set(tie_order) != candidate_ids):
        raise ContractError("main's exported set order must cover every eligible frame exactly once")
    if not isinstance(row.get("current_control_reference"), list):
        raise ContractError("exact source control reference is missing")
    return maps


def maxscale(values: dict[str, float]) -> dict[str, float]:
    """Exact Searcher._normalize_scores behavior, including negative scores."""
    maximum = max(values.values(), default=0.0)
    return {key: value / maximum if maximum > 0 else 0.0 for key, value in values.items()}


def transform(scores: dict[str, float], arm: str) -> tuple[dict[str, float], dict]:
    if not scores:
        return {}, {"count": 0}
    keys = list(scores)
    values = list(scores.values())
    stats = {"count": len(values), "min": min(values), "max": max(values)}
    if arm == "fusion_rrf":
        out = [1.0 / (RRF_K + rank) for rank in range(1, len(values) + 1)]
    elif arm == "fusion_minmax_sum":
        minimum = stats["min"]
        spread = stats["max"] - minimum
        out = [(value - minimum) / spread for value in values] if spread else [1.0] * len(values)
        stats["equal_score_rule"] = "all_one" if not spread else None
    elif arm == "fusion_robust_z_sum":
        center = statistics.median(values)
        mad = statistics.median(abs(value - center) for value in values)
        scale = MAD_FACTOR * mad
        fallback = scale == 0.0
        if fallback:
            scale = max(abs(value - center) for value in values)
        zscores = [(value - center) / scale if scale else 0.0 for value in values]
        out = [1.0 / (1.0 + math.exp(-max(-ROBUST_CLIP, min(ROBUST_CLIP, z)))) for z in zscores]
        stats.update(median=center, mad=mad, scale=scale, zero_mad_fallback=fallback,
                     clipped_count=sum(abs(z) > ROBUST_CLIP for z in zscores))
    elif arm == "fusion_softmax_sum":
        maximum = max(values)
        masses = [math.exp((value - maximum) / SOFTMAX_TEMPERATURE) for value in values]
        total = sum(masses)
        out = [mass / total for mass in masses]
        stats.update(temperature=SOFTMAX_TEMPERATURE, largest_relative_mass=max(out))
    else:
        raise ContractError(f"unknown arm {arm}")
    if any(not math.isfinite(value) for value in out):
        raise ContractError("nonfinite normalized result")
    return dict(zip(keys, out)), stats


def current_scores(maps: dict, order: list[str], config: dict) -> tuple[dict, dict]:
    """Preserve sum-visual/maxscale and text maxscale/blend/maxscale exactly."""
    visual = {}
    for provider in config["visual_providers"]:
        for fid, score in maps[provider].items():
            visual[fid] = visual.get(fid, 0) + score
    visual_norm = maxscale(visual)
    modality_norm = {}
    contributions = {fid: {provider: 0.0 for provider in PROVIDERS} for fid in order}
    visual_weight = 1.0 - config["ocr_weight"] - config["asr_weight"]
    visual_maximum = max(visual.values(), default=0)
    for fid in order:
        for provider in config["visual_providers"]:
            contributions[fid][provider] = (
                visual_weight * maps[provider].get(fid, 0.0) / visual_maximum
                if visual_maximum > 0 else 0.0)
    for modality in ("ocr", "asr"):
        sparse = maxscale(maps[modality + "_sparse"])
        dense = maxscale(maps[modality + "_dense"])
        alpha = config[modality + "_alpha"]
        merged = {}
        for fid in order:
            if fid not in sparse and fid not in dense:
                continue
            if alpha <= 0:
                value = sparse.get(fid, 0.0)
            elif alpha >= 1:
                value = dense.get(fid, 0.0)
            else:
                value = alpha * dense.get(fid, 0.0) + (1.0 - alpha) * sparse.get(fid, 0.0)
            merged[fid] = value
        modality_norm[modality] = maxscale(merged)
        maximum = max(merged.values(), default=0)
        weight = config[modality + "_weight"]
        if maximum > 0:
            for fid in order:
                contributions[fid][modality + "_sparse"] = weight * (1.0 - alpha) * sparse.get(fid, 0.0) / maximum
                contributions[fid][modality + "_dense"] = weight * alpha * dense.get(fid, 0.0) / maximum
    final = {
        fid: visual_weight * visual_norm.get(fid, 0.0)
        + config["ocr_weight"] * modality_norm["ocr"].get(fid, 0.0)
        + config["asr_weight"] * modality_norm["asr"].get(fid, 0.0)
        for fid in order
    }
    return final, contributions


def _rank(scores: dict, contributions: dict, order: list, config: dict) -> tuple[list, list]:
    # Stable sort over the exact exported pre-sort set order, for EVERY arm.
    ranked = sorted(order, key=lambda fid: scores[fid], reverse=True)
    frames = [{"frame_id": fid, "video_id": frame_video(fid), "rank": rank,
               "score": scores[fid], "contributions": contributions[fid]}
              for rank, fid in enumerate(ranked[:config["output_frame_k"]], 1)]
    seen = set()
    videos = []
    for frame in frames:
        if frame["video_id"] in seen:
            continue
        seen.add(frame["video_id"])
        videos.append({**frame, "frame_rank": frame["rank"], "rank": len(videos) + 1})
        if len(videos) >= config["output_video_k"]:
            break
    return frames, videos


def study_query(row: dict, config: dict) -> dict:
    validate_config(config)
    maps = validate_row(row, config)
    order = row["candidate_tie_order"]
    weights = nominal_weights(config)
    output = {"query_id": row["query_id"], "query_text_sha256": row["query_text_sha256"],
              "config_sha256": digest_json(config), "provider_input_sha256": digest_json(row),
              "run_identity_sha256": row["run_identity_sha256"],
              "provider_states": {name: row["providers"][name]["state"] for name in PROVIDERS},
              "nominal_weights": weights, "candidate_count": len(order), "arms": {}}
    for arm in ARMS:
        started = time.perf_counter_ns()
        cpu_started = time.process_time_ns()
        diagnostics = {}
        if arm == "fusion_current_control":
            scores, contributions = current_scores(maps, order, config)
        else:
            contributions = {fid: {name: 0.0 for name in PROVIDERS} for fid in order}
            for name in PROVIDERS:
                normalized, diagnostics[name] = transform(maps[name], arm)
                for fid, value in normalized.items():
                    contributions[fid][name] = weights[name] * value
            scores = {fid: sum(contributions[fid].values()) for fid in order}
        frames, videos = _rank(scores, contributions, order, config)
        elapsed = time.perf_counter_ns() - started
        cpu_elapsed = time.process_time_ns() - cpu_started
        # Parity is essential but is not part of any fusion arm's timing.
        if arm == "fusion_current_control":
            ranked_all = sorted(order, key=lambda fid: scores[fid], reverse=True)
            reference = row["current_control_reference"]
            if [item.get("frame_id") for item in reference] != ranked_all:
                raise ContractError("current control order differs from exact source replay")
            for item in reference:
                if not math.isclose(finite(item.get("score"), "reference.score"), scores[item["frame_id"]],
                                    rel_tol=1e-12, abs_tol=1e-12):
                    raise ContractError("current control score differs from exact source replay")
        output["arms"][arm] = {"frames": frames, "videos": videos,
                                  "fusion_wall_ns": elapsed, "fusion_cpu_ns": cpu_elapsed,
                                  "normalization": diagnostics}
    output["current_control_replay_verified"] = True
    return output


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(rankings_path: Path, config_path: Path, queries_path: Path, output_path: Path,
        manifest_path: Path) -> dict:
    config = validate_config(json.loads(config_path.read_text(encoding="utf-8")))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("status") != "complete" or manifest.get("scope") != "full_query_projection"
            or manifest.get("rows_written") != config["expected_query_count"]):
        raise ContractError("collector manifest is incomplete, failed, or only a smoke subset")
    if manifest.get("config_sha256") != digest_json(config):
        raise ContractError("collector manifest config differs from study config")
    identity_hash = run_identity_digest(manifest)
    if manifest.get("run_identity_sha256") != identity_hash:
        raise ContractError("collector run identity hash mismatch")
    if manifest.get("rankings_sha256") != digest_bytes(rankings_path.read_bytes()):
        raise ContractError("raw rankings file differs from completed collector manifest")
    if manifest.get("canonical_queries_sha256") != digest_bytes(queries_path.read_bytes()):
        raise ContractError("canonical projection differs from completed collector manifest")
    queries = load_jsonl(queries_path)
    allowed = {"query_id", "query_text", "query_text_sha256", "phase", "task_type", "capabilities"}
    if any(set(row) - allowed for row in queries):
        raise ContractError("scorer accepts a GT-free canonical projection only")
    expected = {row["query_id"]: digest_bytes(row["query_text"].encode("utf-8")) for row in queries}
    if len(expected) != len(queries) or len(queries) != config["expected_query_count"]:
        raise ContractError("canonical query projection count/uniqueness mismatch")
    if config.get("canonical_query_projection_sha256") != digest_json(expected):
        raise ContractError("canonical query IDs/text differ from frozen authority")
    rows = load_jsonl(rankings_path)
    if any(row.get("run_identity_sha256") != identity_hash for row in rows):
        raise ContractError("provider export contains mixed or foreign collection/model/run identities")
    observed = {row.get("query_id"): row.get("query_text_sha256") for row in rows}
    if len(observed) != len(rows) or observed != expected:
        raise ContractError("provider export does not match the entire frozen canonical query projection")
    results = [study_query(row, config) for row in rows]
    # Validate every row before writing any proposed scientific output.
    if output_path.exists():
        raise ContractError("output exists; select a new immutable run path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
    return {"queries": len(results), "arms": list(ARMS), "ground_truth_read": False,
            "harness_sha256": digest_bytes(Path(__file__).read_bytes()),
            "collection_manifest_sha256": digest_bytes(manifest_path.read_bytes()),
            "run_identity_sha256": identity_hash,
            "rankings_sha256": digest_bytes(rankings_path.read_bytes()),
            "queries_sha256": digest_bytes(queries_path.read_bytes()),
            "config_sha256": digest_json(config), "output_sha256": digest_bytes(output_path.read_bytes())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True, help="GT-free canonical query JSONL")
    parser.add_argument("--collection-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.rankings, args.config, args.queries, args.output, args.collection_manifest), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
