#!/usr/bin/env python3
"""Frozen offline A/B evaluator for Vecna Issue #64.

This evaluator intentionally does not run retrieval.  A local operator first
runs the same repaired Vecna headless benchmark once per visual model (CLIP,
SigLIP, Qwen) plus the current legacy/default arm.  This script then validates
that those JSONL files share identical query/ground-truth identity and applies
the default-off OpenCubee-derived model-weighted late fusion to the per-model
top results.

The confirmatory donor policy is frozen before scoring:
- one result list per visual model;
- equal model weights unless explicit weights were preregistered before run;
- union by frame identity;
- missing candidate from a model contributes zero;
- active model weights renormalize to sum to one;
- no post-result tuning.

It writes donor-fused JSONL, a run manifest, a machine-readable summary, and a
small Markdown comparison report.  The legacy input is never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

AIC51_ROOT = Path(__file__).resolve().parents[1]
if str(AIC51_ROOT) not in sys.path:
    sys.path.insert(0, str(AIC51_ROOT))

from aic51.packages.search.experimental_fusion import (  # noqa: E402
    DONOR_COMMIT,
    DONOR_REPOSITORY,
    DONOR_SOURCE,
    OPENCUBEE_MODEL_WEIGHTED_STRATEGY,
    fuse_model_results,
)

DEFAULT_MODELS = ("clip", "siglip", "qwen")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_mapping(values: list[str], *, value_type: type = str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"expected NAME=VALUE, got {raw!r}")
        name, value = raw.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"empty name in {raw!r}")
        result[name] = value_type(value)
    return result


def by_query(rows: list[dict[str, Any]], source: str) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        query_id = str(row.get("query_id") or "").strip()
        if not query_id:
            raise ValueError(f"{source}: row missing query_id")
        if query_id in mapped:
            raise ValueError(f"{source}: duplicate query_id {query_id}")
        mapped[query_id] = row
    return mapped


def truth_fingerprint(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record.get("query_text"),
        tuple(record.get("answers") or []),
        record.get("task_type"),
        record.get("ground_truth_tier"),
        record.get("match_contract"),
    )


def validate_arms(
    legacy: dict[str, dict[str, Any]],
    models: dict[str, dict[str, dict[str, Any]]],
) -> list[str]:
    legacy_ids = set(legacy)
    for model, rows in models.items():
        if set(rows) != legacy_ids:
            missing = sorted(legacy_ids - set(rows))
            extra = sorted(set(rows) - legacy_ids)
            raise ValueError(f"{model}: query-id mismatch missing={missing} extra={extra}")
        for query_id in sorted(legacy_ids):
            if truth_fingerprint(rows[query_id]) != truth_fingerprint(legacy[query_id]):
                raise ValueError(f"{model}: truth mismatch for {query_id}")
    return sorted(legacy_ids)


def frame_key(result: dict[str, Any]) -> tuple[str, Any]:
    return (str(result.get("video_id") or ""), result.get("frame_id"))


def validate_candidate_truth_consistency(
    per_model_results: dict[str, list[dict[str, Any]]],
    query_id: str,
) -> None:
    seen: dict[tuple[str, Any], bool] = {}
    for model, results in per_model_results.items():
        for item in results:
            key = frame_key(item)
            if not key[0] or key[1] is None:
                raise ValueError(f"{query_id}/{model}: result missing video_id/frame_id")
            value = bool(item.get("matches_ground_truth", False))
            if key in seen and seen[key] != value:
                raise ValueError(
                    f"{query_id}: ground-truth flag disagreement for {key}: "
                    f"existing={seen[key]} {model}={value}"
                )
            seen[key] = value


def rank_metrics(top_results: list[dict[str, Any]]) -> dict[str, Any]:
    first = next(
        (rank for rank, item in enumerate(top_results, start=1) if item.get("matches_ground_truth")),
        None,
    )
    return {
        "first_correct_rank": first,
        "reciprocal_rank": (1.0 / first) if first else 0.0,
        "recall_at_1": 1.0 if first and first <= 1 else 0.0,
        "recall_at_5": 1.0 if first and first <= 5 else 0.0,
        "recall_at_20": 1.0 if first and first <= 20 else 0.0,
        "no_hit_within_20": first is None or first > 20,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scoreable = [row for row in rows if row.get("answers")]
    if not scoreable:
        return {"n": 0}
    ranks = [row["first_correct_rank"] for row in scoreable if row.get("first_correct_rank")]
    return {
        "n": len(scoreable),
        "recall_at_1": sum(float(row["recall_at_1"]) for row in scoreable) / len(scoreable),
        "recall_at_5": sum(float(row["recall_at_5"]) for row in scoreable) / len(scoreable),
        "recall_at_20": sum(float(row["recall_at_20"]) for row in scoreable) / len(scoreable),
        "mrr_at_20": sum(float(row["reciprocal_rank"]) for row in scoreable) / len(scoreable),
        "median_first_correct_rank_within_20": statistics.median(ranks) if ranks else None,
        "no_hit_within_20_count": sum(1 for row in scoreable if row.get("no_hit_within_20")),
    }


def git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[2]),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue #64 OpenCubee late-fusion offline A/B")
    parser.add_argument("--legacy", type=Path, required=True, help="Current/default headless JSONL")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Per-model headless JSONL; repeat for clip/siglip/qwen",
    )
    parser.add_argument(
        "--weight",
        action="append",
        default=[],
        metavar="NAME=FLOAT",
        help="Preregistered model weight; defaults to 1.0 for every supplied model",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()

    model_paths = {name: Path(path) for name, path in parse_mapping(args.model).items()}
    if len(model_paths) < 2:
        raise ValueError("donor A/B requires at least two visual-model arms")
    requested_weights = parse_mapping(args.weight, value_type=float)
    unknown_weight_models = set(requested_weights) - set(model_paths)
    if unknown_weight_models:
        raise ValueError(f"weights supplied for missing model arms: {sorted(unknown_weight_models)}")
    weights = {model: float(requested_weights.get(model, 1.0)) for model in model_paths}
    if any(weight <= 0 for weight in weights.values()):
        raise ValueError("all preregistered model weights must be positive")

    legacy_path = args.legacy.resolve()
    model_paths = {model: path.resolve() for model, path in model_paths.items()}
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    legacy_rows = load_jsonl(legacy_path)
    legacy_map = by_query(legacy_rows, "legacy")
    model_maps = {
        model: by_query(load_jsonl(path), model)
        for model, path in sorted(model_paths.items())
    }
    query_ids = validate_arms(legacy_map, model_maps)

    donor_rows: list[dict[str, Any]] = []
    per_query: list[dict[str, Any]] = []
    for query_id in query_ids:
        legacy = legacy_map[query_id]
        per_model_results = {
            model: list(model_maps[model][query_id].get("top_results") or [])
            for model in model_maps
        }
        validate_candidate_truth_consistency(per_model_results, query_id)
        fused = fuse_model_results(per_model_results, weights)[: args.top_k]
        for rank, item in enumerate(fused, start=1):
            item["rank"] = rank

        metrics = rank_metrics(fused)
        donor = {
            key: legacy.get(key)
            for key in (
                "query_id",
                "source",
                "task_type",
                "capability_evaluated",
                "evaluation_scope",
                "validation_state",
                "query_mode",
                "ground_truth_tier",
                "query_text",
                "answers",
                "match_contract",
            )
            if key in legacy
        }
        donor.update(
            {
                "condition": "ISSUE64_OPENCUBEE_MODEL_WEIGHTED",
                "is_primary_baseline": False,
                "issue64_donor": {
                    "strategy": OPENCUBEE_MODEL_WEIGHTED_STRATEGY,
                    "repository": DONOR_REPOSITORY,
                    "commit": DONOR_COMMIT,
                    "source": DONOR_SOURCE,
                    "model_weights": dict(sorted(weights.items())),
                    "offline_replay": True,
                },
                **metrics,
                "top_results": fused,
            }
        )
        donor_rows.append(donor)

        legacy_rank = legacy.get("first_correct_rank")
        donor_rank = donor.get("first_correct_rank")
        per_query.append(
            {
                "query_id": query_id,
                "task_type": legacy.get("task_type"),
                "legacy_rank": legacy_rank,
                "donor_rank": donor_rank,
                "rank_delta_donor_minus_legacy": (
                    donor_rank - legacy_rank
                    if donor_rank is not None and legacy_rank is not None
                    else None
                ),
                "legacy_hit20": bool(legacy_rank and legacy_rank <= 20),
                "donor_hit20": bool(donor_rank and donor_rank <= 20),
            }
        )

    donor_path = output_dir / "donor-fused.jsonl"
    write_jsonl(donor_path, donor_rows)
    legacy_summary = aggregate(legacy_rows)
    donor_summary = aggregate(donor_rows)
    improved = sum(
        1 for row in per_query
        if row["legacy_rank"] is not None and row["donor_rank"] is not None and row["donor_rank"] < row["legacy_rank"]
    )
    worsened = sum(
        1 for row in per_query
        if row["legacy_rank"] is not None and row["donor_rank"] is not None and row["donor_rank"] > row["legacy_rank"]
    )
    gained20 = sum(1 for row in per_query if not row["legacy_hit20"] and row["donor_hit20"])
    lost20 = sum(1 for row in per_query if row["legacy_hit20"] and not row["donor_hit20"])

    summary = {
        "issue": 64,
        "strategy": OPENCUBEE_MODEL_WEIGHTED_STRATEGY,
        "donor": {
            "repository": DONOR_REPOSITORY,
            "commit": DONOR_COMMIT,
            "source": DONOR_SOURCE,
        },
        "weights": dict(sorted(weights.items())),
        "legacy": legacy_summary,
        "donor_fused": donor_summary,
        "delta": {
            key: donor_summary.get(key, 0) - legacy_summary.get(key, 0)
            for key in ("recall_at_1", "recall_at_5", "recall_at_20", "mrr_at_20")
        },
        "per_query_improved_rank": improved,
        "per_query_worsened_rank": worsened,
        "gained_top20": gained20,
        "lost_top20": lost20,
        "per_query": per_query,
        "latency_interpretation": (
            "offline replay only: input arm latencies are separate retrieval runs; "
            "do not infer donor production latency from this artifact"
        ),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run = {
        "issue": 64,
        "git_sha": git_sha(),
        "legacy": {"path": str(legacy_path), "sha256": sha256_file(legacy_path)},
        "model_inputs": {
            model: {"path": str(path), "sha256": sha256_file(path)}
            for model, path in sorted(model_paths.items())
        },
        "weights": dict(sorted(weights.items())),
        "top_k": args.top_k,
        "donor_output": {"path": str(donor_path), "sha256": sha256_file(donor_path)},
        "summary": {"path": str(summary_path), "sha256": sha256_file(summary_path)},
        "policy_frozen_before_scoring": True,
        "post_result_tuning_allowed": False,
    }
    (output_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Issue #64 OpenCubee donor A/B",
        "",
        f"- Strategy: `{OPENCUBEE_MODEL_WEIGHTED_STRATEGY}`",
        f"- Donor: `{DONOR_REPOSITORY}@{DONOR_COMMIT}` `{DONOR_SOURCE}`",
        f"- Model weights: `{dict(sorted(weights.items()))}`",
        "- Evaluation: offline fusion over frozen per-model headless rankings; no post-result tuning.",
        "- Latency: not inferred from offline replay; a runtime microbenchmark is required before promotion.",
        "",
        "| metric | legacy | donor | delta |",
        "|---|---:|---:|---:|",
    ]
    for key in ("recall_at_1", "recall_at_5", "recall_at_20", "mrr_at_20"):
        lines.append(
            f"| {key} | {legacy_summary.get(key, 0):.6f} | {donor_summary.get(key, 0):.6f} | {summary['delta'][key]:+.6f} |"
        )
    lines.extend(
        [
            "",
            f"- Improved correct rank: **{improved}** queries",
            f"- Worsened correct rank: **{worsened}** queries",
            f"- Gained top-20 hits: **{gained20}**",
            f"- Lost top-20 hits: **{lost20}**",
            "",
        ]
    )
    (output_dir / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
