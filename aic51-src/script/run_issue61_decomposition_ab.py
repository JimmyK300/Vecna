#!/usr/bin/env python3
"""Issue #61 query-decomposition A/B experiment harness (measurement only).

Frozen A/B experiment required by GitHub issue JimmyK300/Vecna#61 (parent #34):

  Arm A (control):  official Q0 full-query baseline through the EXISTING
                    retrieval path (identical to docs/baseline-v1.md protocol:
                    clip_siglip_qwen_sparse, rerank OFF, nprobe 32,
                    temporal_k 2000, OCR/ASR weights 0.25/0.25).
  Arm B (treatment): deterministic rule-based decomposition into tool-
                    appropriate subquery fragments (policy frozen in
                    benchmark-results/issue61-decomposition-ab/
                    decomposition-policy-v1.json BEFORE scoring), one search
                    call per fragment with per-kind surface routing, fused by
                    frozen RRF k=60, scored against the ORIGINAL ground truth.

No LLM calls. No production query-path changes. No retrieval/model/index/config
changes anywhere. The live runtime (code, config.yaml, canonical query CSV,
Milvus collection official_l21_l30_all_v2) is read from the PRIMARY checkout,
treated as read-only reference (nothing written there; bytecode disabled).

Phases:
  --phase freeze  Verify policy hash, derive all fragments deterministically,
                  and write policy-freeze.json BEFORE any scoring call.
  --phase run     Re-verify freeze manifest, then run Arms A/B interleaved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # never drop .pyc into the primary checkout

DEFAULT_PRIMARY_ROOT = Path(r"C:\Users\minhc\Code\Vecna")
DEFAULT_CELL = "clip_siglip_qwen_sparse"
POLICY_VERSION = "issue61-decomposition-v1"
RRF_K = 60

HERE = Path(__file__).resolve().parent
WORKTREE_AIC51 = HERE.parent
WORKTREE_ROOT = WORKTREE_AIC51.parent
DEFAULT_OUTPUT_DIR = WORKTREE_ROOT / "benchmark-results" / "issue61-decomposition-ab"
POLICY_JSON = DEFAULT_OUTPUT_DIR / "decomposition-policy-v1.json"
POLICY_MD = DEFAULT_OUTPUT_DIR / "decomposition-policy-v1.md"
FREEZE_JSON = DEFAULT_OUTPUT_DIR / "policy-freeze.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def worktree_git_identity(worktree_root: Path) -> dict[str, object]:
    def git(*argv: str) -> str:
        return subprocess.run(
            ["git", *argv], cwd=str(worktree_root), check=True, capture_output=True, text=True
        ).stdout.strip()

    return {
        "worktree_root": str(worktree_root),
        "sha": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty": bool(git("status", "--porcelain=v1").strip()),
    }


DECLARED_METADATA_COLUMNS = (
    "evidence_visual",
    "evidence_ocr",
    "evidence_asr",
    "semantic_constraint_types",
    "temporal_requirement",
)


def attach_declared_metadata(cases: list[dict[str, Any]], csv_path: Path) -> None:
    """Merge the declared category/modality CSV columns into parsed cases.

    headless_benchmark.load_cases does not surface these columns; the frozen
    policy classifies complexity from them, so they are joined by query_id from
    the SAME canonical CSV (read-only).
    """
    import csv

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = {row["query_id"].strip(): row for row in csv.DictReader(handle)}
    for case in cases:
        row = rows.get(case["query_id"])
        if row is None:
            raise ValueError(f"{case['query_id']}: missing from canonical CSV for metadata join")
        for column in DECLARED_METADATA_COLUMNS:
            case[column] = (row.get(column) or "").strip()


# ---------------------------------------------------------------------------
# Frozen policy engine (implements decomposition-policy-v1.json exactly)
# ---------------------------------------------------------------------------

TEMPORAL_COMPLEX = {
    "exact_boundary_multi_event",
    "ordered_sequence",
    "multi_scene_sequence",
    "long_temporal_relation",
}
SIMPLE_TEMPORAL = {"segment", "segment_start", "video"}
META_DROP_RE = re.compile(r"^(?:find|h\u00e3y t\u00ecm|t\u00ecm)\s+(?:the\s+)?(?:clip|video)\b", re.IGNORECASE)
EVENT_LINE_RE = re.compile(r"^E\s*\d+\s*[:.]", re.IGNORECASE)
TOKEN_RE = re.compile(r"[A-Za-z\u00c0-\u1ef9][\w\-']*")


def sanitize(text: str) -> str:
    text = text.replace("/", " ").replace("\\", " ")
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    sentences: list[str] = []
    for block in normalized.split("\n"):
        block = block.strip()
        if not block:
            continue
        for piece in re.split(r"(?<=[.!?])\s+", block):
            piece = piece.strip()
            if piece:
                sentences.append(piece)
    return sentences


def is_meta(sentence: str) -> bool:
    if sentence.endswith("?"):
        return True
    return bool(META_DROP_RE.match(sentence)) and len(sentence.split()) <= 12


def is_texty(sentence: str) -> bool:
    if any(ch.isdigit() for ch in sentence):
        return True
    if '"' in sentence:
        return True
    tokens = TOKEN_RE.findall(sentence)
    caps = sum(1 for i, tok in enumerate(tokens) if i > 0 and tok[0].isupper())
    return caps >= 2


def classify_complexity(case: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if case["task_type"] in {"trake", "qa"}:
        reasons.append("C1")
    temporal = (case.get("temporal_requirement") or "").strip().lower()
    if temporal in TEMPORAL_COMPLEX:
        reasons.append("C2")
    constraints = [c.strip() for c in (case.get("semantic_constraint_types") or "").split(";") if c.strip()]
    if len(constraints) >= 5:
        reasons.append("C3")
    ocr = (case.get("evidence_ocr") or "").strip().lower()
    asr = (case.get("evidence_asr") or "").strip().lower()
    if ocr == "strong" or asr == "strong":
        reasons.append("C4")
    return ("complex" if reasons else "simple"), reasons


def derive_fragments(case: dict[str, Any], forced_diagnostic: bool = False) -> dict[str, Any]:
    """Return {'mode','fragments':[{'kind','text'}],'derived':str} per frozen policy."""
    complexity, _reasons = classify_complexity(case)
    task_type = case["task_type"]
    evidence_ocr = (case.get("evidence_ocr") or "").strip().lower()
    evidence_asr = (case.get("evidence_asr") or "").strip().lower()

    full_sanitized = sanitize(case["query"])

    if complexity == "simple" and not forced_diagnostic:
        return {
            "mode": "identity_control",
            "derived": "simple_rule.identity",
            "fragments": [{"kind": "identity", "text": full_sanitized}],
        }

    if task_type == "trake":
        lines = [line.strip() for line in case["query"].replace("\r\n", "\n").split("\n")]
        event_lines = [line for line in lines if EVENT_LINE_RE.match(line)]
        if len(event_lines) >= 2:
            return {
                "mode": "trake_events",
                "derived": "trake_rule",
                "fragments": [{"kind": "event", "text": sanitize(line)} for line in event_lines],
            }

    sentences = [s for s in split_sentences(case["query"]) if not is_meta(s)]
    visual_sentences = [s for s in sentences if not is_texty(s)]
    texty_sentences = [s for s in sentences if is_texty(s)]
    v_text = sanitize(" ".join(visual_sentences))
    t_text = sanitize(" ".join(texty_sentences))

    strong_text = evidence_ocr == "strong" or evidence_asr == "strong" or task_type == "qa"
    fragments: list[dict[str, str]] = []
    derived = "generic_rule"
    if strong_text:
        if v_text:
            fragments.append({"kind": "visual", "text": v_text})
        if t_text:
            fragments.append({"kind": "text", "text": t_text})
        derived = "generic_rule.visual_plus_text"
    else:
        if v_text:
            fragments.append({"kind": "visual", "text": v_text})
        derived = "generic_rule.visual_only"

    min_words = min((len(f["text"].split()) for f in fragments), default=0)
    if not fragments or min_words < 3:
        return {
            "mode": "identity_fallback",
            "derived": derived + ".guard_identity_fallback",
            "fragments": [{"kind": "identity", "text": full_sanitized}],
        }
    if len(fragments) == 1 and fragments[0]["text"] == full_sanitized:
        fragments[0]["kind"] = "identity"
        return {"mode": "identity_derived", "derived": derived + ".identity", "fragments": fragments}

    mode = "forced_decomposition_generic" if forced_diagnostic else "generic"
    return {"mode": mode, "derived": derived, "fragments": fragments}


ROUTING = {
    "event": {"ocr_weight": 0.0, "asr_weight": 0.0},
    "visual": {"ocr_weight": 0.0, "asr_weight": 0.0},
    "text": {"ocr_weight": 0.25, "asr_weight": 0.25},
    "identity": {"ocr_weight": 0.25, "asr_weight": 0.25},
}


def rrf_fuse(fragment_lists: list[list[Any]], top_k: int) -> list[dict[str, Any]]:
    def key_of(item: dict[str, Any]) -> tuple[str, int]:
        raw_id = str((item.get("entity") or {}).get("frame_id") or "")
        video, _, frame = raw_id.rpartition("#")
        try:
            frame_key = int(frame)
        except ValueError:
            frame_key = -1
        return video, frame_key

    scores: dict[tuple[str, int], float] = {}
    best: dict[tuple[str, int], dict[str, Any]] = {}
    order: list[tuple[str, int]] = []

    for fragment_index, results in enumerate(fragment_lists):
        for rank_position, item in enumerate(results, start=1):
            key = key_of(item)
            contribution = 1.0 / (RRF_K + rank_position)
            if key not in scores:
                scores[key] = 0.0
                best[key] = item
                order.append(key)
            scores[key] += contribution
            # tie-break bookkeeping: remember earliest (fragment_index, rank)
            meta = best.setdefault(key, item)
            meta.setdefault("_first_seen", (fragment_index, rank_position))
            if (fragment_index, rank_position) < meta["_first_seen"]:
                meta["_first_seen"] = (fragment_index, rank_position)

    ranked_keys = sorted(
        order,
        key=lambda key: (-scores[key], best[key]["_first_seen"]),
    )
    fused: list[dict[str, Any]] = []
    for key in ranked_keys[:top_k]:
        item = dict(best[key])
        item["rrf_score"] = round(scores[key], 6)
        item.pop("_first_seen", None)
        fused.append(item)
    return fused


def gold_video_ids(case: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for group in case.get("accepted_groups") or []:
        for target in group:
            vid = target.get("video_id")
            if vid and vid not in ids:
                ids.append(vid)
    return ids


def classify_failure(case: dict[str, Any], record_metrics: dict[str, Any]) -> dict[str, Any]:
    """Frozen taxonomy (policy section 6); mirrors issue58 conventions."""
    facts: dict[str, Any] = {
        "scoreable": case["scoreable"],
        "first_correct_rank": record_metrics.get("first_correct_rank"),
        "gold_videos": gold_video_ids(case),
    }
    if not case["scoreable"]:
        return {"query_id": case["query_id"], "classification": "unscoreable", "categories": [], "facts": facts}
    hit = record_metrics.get("first_correct_rank") is not None
    if hit:
        return {"query_id": case["query_id"], "classification": "hit", "categories": [], "facts": facts}

    categories: list[str] = []
    constraints = (case.get("semantic_constraint_types") or "").lower()
    if "world_knowledge_bridge" in constraints:
        categories.append("knowledge_bridge_requires_llm")
    categories.append("correct_result_outside_top20")

    temporal = (case.get("temporal_requirement") or "").strip().lower()
    if temporal in TEMPORAL_COMPLEX:
        categories.append("temporal_understanding_required")

    nearest_seconds = record_metrics.get("nearest_gold_delta_seconds")
    if nearest_seconds is not None and float(nearest_seconds) > 10.0:
        categories.append("poor_frame_sampling")

    top_results = record_metrics.get("top_results") or []
    gold_set = set(facts["gold_videos"])
    present = any(item.get("video_id") in gold_set for item in top_results)
    facts["gold_video_entries_in_top20"] = [
        {"rank": item.get("rank"), "video_id": item.get("video_id"), "frame_id": item.get("frame_id")}
        for item in top_results
        if item.get("video_id") in gold_set
    ]
    facts["gold_video_absent_from_top20"] = not present
    if not present and nearest_seconds is None:
        categories.append("unresolved_no_gold_evidence_in_top20")
    return {"query_id": case["query_id"], "classification": "fail", "categories": categories, "facts": facts}


# ---------------------------------------------------------------------------
# Experiment phases
# ---------------------------------------------------------------------------


def load_policy() -> dict[str, Any]:
    if not POLICY_JSON.is_file():
        raise ValueError(f"frozen policy file missing: {POLICY_JSON}")
    policy = json.loads(POLICY_JSON.read_text(encoding="utf-8"))
    if policy.get("policy_id") != POLICY_VERSION:
        raise ValueError(f"unexpected policy id: {policy.get('policy_id')!r}")
    if policy.get("status") != "FROZEN":
        raise ValueError("policy is not marked FROZEN")
    return policy


def build_freeze_manifest(cases: list[dict[str, Any]]) -> dict[str, Any]:
    plan = []
    for case in cases:
        complexity, reasons = classify_complexity(case)
        confirmatory = derive_fragments(case, forced_diagnostic=False)
        diagnostic = derive_fragments(case, forced_diagnostic=True) if complexity == "simple" else None
        plan.append(
            {
                "query_id": case["query_id"],
                "task_type": case["task_type"],
                "scoreable": case["scoreable"],
                "complexity_class": complexity,
                "complexity_reasons": reasons,
                "confirmatory_mode": confirmatory["mode"],
                "confirmatory_derivation": confirmatory["derived"],
                "fragments": [
                    {"index": i, "kind": f["kind"], "routing": ROUTING[f["kind"]], "text": f["text"]}
                    for i, f in enumerate(confirmatory["fragments"])
                ],
                "diagnostic_plan": (
                    {
                        "mode": diagnostic["mode"],
                        "fragments": [
                            {"index": i, "kind": f["kind"], "routing": ROUTING[f["kind"]], "text": f["text"]}
                            for i, f in enumerate(diagnostic["fragments"])
                        ],
                    }
                    if diagnostic
                    else None
                ),
            }
        )
    preview_json = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    manifest = {
        "manifest_version": "issue61-freeze-v1",
        "created_at_utc": utc_now(),
        "policy_id": POLICY_VERSION,
        "policy_json_sha256": sha256_file(POLICY_JSON),
        "policy_md_sha256": sha256_file(POLICY_MD),
        "derivation_preview_sha256": sha256_text(preview_json),
        "query_count": len(cases),
        "plan": plan,
    }
    FREEZE_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_freeze(manifest: dict[str, Any], cases: list[dict[str, Any]]) -> None:
    problems: list[str] = []
    if manifest.get("policy_json_sha256") != sha256_file(POLICY_JSON):
        problems.append("policy JSON changed after freeze")
    if manifest.get("policy_md_sha256") != sha256_file(POLICY_MD):
        problems.append("policy MD changed after freeze")
    rebuilt = build_freeze_plan_silent(cases)
    if manifest.get("derivation_preview_sha256") != sha256_text(json.dumps(rebuilt, ensure_ascii=False, sort_keys=True)):
        problems.append("derivation preview changed relative to freeze manifest")
    if problems:
        raise ValueError("freeze verification FAILED: " + "; ".join(problems))


def build_freeze_plan_silent(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = []
    for case in cases:
        complexity, reasons = classify_complexity(case)
        confirmatory = derive_fragments(case, forced_diagnostic=False)
        diagnostic = derive_fragments(case, forced_diagnostic=True) if complexity == "simple" else None
        entry = {
            "query_id": case["query_id"],
            "task_type": case["task_type"],
            "scoreable": case["scoreable"],
            "complexity_class": complexity,
            "complexity_reasons": reasons,
            "confirmatory_mode": confirmatory["mode"],
            "confirmatory_derivation": confirmatory["derived"],
            "fragments": [
                {"index": i, "kind": f["kind"], "routing": ROUTING[f["kind"]], "text": f["text"]}
                for i, f in enumerate(confirmatory["fragments"])
            ],
            "diagnostic_plan": (
                {
                    "mode": diagnostic["mode"],
                    "fragments": [
                        {"index": i, "kind": f["kind"], "routing": ROUTING[f["kind"]], "text": f["text"]}
                        for i, f in enumerate(diagnostic["fragments"])
                    ],
                }
                if diagnostic
                else None
            ),
        }
        plan.append(entry)
    return plan


def fingerprint(results: list[Any]) -> list[list[Any]]:
    out = []
    for item in results[:20]:
        raw_id = str((item.get("entity") or {}).get("frame_id") or "")
        video, _, frame = raw_id.rpartition("#")
        out.append([video, frame])
    return out


def run_fragment_search(searcher: Any, fragment: dict[str, Any], args: argparse.Namespace, features: list[str]) -> tuple[dict[str, Any], list[Any]]:
    routing = ROUTING[fragment["kind"]]
    started = time.perf_counter()
    raw = searcher.search_multimodal(
        fragment["text"],
        0,
        args.top_k,
        features,
        nprobe=args.nprobe,
        temporal_k=args.temporal_k,
        ocr_weight=routing["ocr_weight"],
        asr_weight=routing["asr_weight"],
        max_interval=args.max_interval,
        selected=None,
        auto_translate=args.auto_translate,
        en_to_vi_translate=args.en_to_vi_translate,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    results = hb.normalize_results(list(raw.get("results", [])), args.top_k)
    detail = {
        "index": fragment["index"],
        "kind": fragment["kind"],
        "routing": routing,
        "text": fragment["text"],
        "latency_ms": round(latency_ms, 3),
        "n_results": len(results),
        "top20": fingerprint(results),
    }
    return detail, results


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue #61 decomposition A/B experiment (frozen policy)")
    parser.add_argument("--phase", choices=["freeze", "run"], required=True)
    parser.add_argument("--primary-root", type=Path, default=Path(os.environ.get("VECNA_PRIMARY_ROOT", str(DEFAULT_PRIMARY_ROOT))))
    parser.add_argument("--cell", default=DEFAULT_CELL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit-queries", type=int, default=None, help="Debug only")
    parser.add_argument("--overwrite", action="store_true")
    cli_args = parser.parse_args()

    output_dir = cli_args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    policy = load_policy()
    primary_root = cli_args.primary_root.resolve()
    primary_scripts = primary_root / "aic51-src" / "script"
    primary_aic51 = primary_root / "aic51-src"
    csv_path = primary_aic51 / "benchmark" / "issue34_headless_queries.csv"
    fps_csv = primary_aic51 / "benchmark" / "video_rounded_fps.csv"
    missing = [
        str(p)
        for p in (
            primary_root / "config.yaml",
            primary_scripts / "headless_benchmark.py",
            primary_scripts / "run_p20_p21_measurement.py",
            csv_path,
            fps_csv,
        )
        if not p.is_file()
    ]
    if missing:
        print(f"ERROR: primary checkout runtime inputs missing: {missing}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(primary_aic51))
    sys.path.insert(0, str(primary_scripts))
    global hb
    import headless_benchmark as hb  # noqa: E402

    import run_p20_p21_measurement as runner  # noqa: E402  (chdirs into primary root)

    if cli_args.cell not in runner.CELLS_BY_NAME:
        print(f"ERROR: unknown cell {cli_args.cell!r}", file=sys.stderr)
        return 2
    cell = runner.CELLS_BY_NAME[cli_args.cell]

    cases_all, inventory_validation, content_sha256 = runner.load_inventory()
    attach_declared_metadata(cases_all, csv_path)
    if cli_args.limit_queries is not None:
        cases_all = cases_all[: cli_args.limit_queries]

    launcher_metadata: dict[str, Any] = {
        "packet": "issue61-decomposition-ab",
        "purpose": "Frozen A/B experiment: rule-based query decomposition vs full query (issue #61)",
        "started_at": utc_now(),
        "launcher_path": str(Path(__file__).resolve()),
        "launcher_sha256": sha256_file(Path(__file__).resolve()),
        "python": sys.executable,
        "pythondontwritebytecode": True,
        "primary_root": str(primary_root),
        "primary_runtime_inputs": {
            "config_yaml_sha256": sha256_file(primary_root / "config.yaml"),
            "headless_benchmark_sha256": sha256_file(primary_scripts / "headless_benchmark.py"),
            "runner_sha256": sha256_file(primary_scripts / "run_p20_p21_measurement.py"),
            "queries_csv_sha256": sha256_file(csv_path),
            "fps_csv_sha256": sha256_file(fps_csv),
        },
        "canonical_content_sha256": content_sha256,
        "expected_canonical_content_sha256": hb.EXPECTED_CANONICAL_CONTENT_SHA256,
        "inventory_complete": inventory_validation["complete"],
        "cell": cli_args.cell,
        "policy_json_sha256": sha256_file(POLICY_JSON),
        "output_dir": str(output_dir),
        "worktree_git": worktree_git_identity(WORKTREE_ROOT),
    }

    if cli_args.phase == "freeze":
        manifest = build_freeze_manifest(cases_all)
        launcher_metadata.update(
            {
                "status": "frozen",
                "ended_at": utc_now(),
                "freezed_query_count": manifest["query_count"],
                "policy_md_sha256": manifest["policy_md_sha256"],
                "derivation_preview_sha256": manifest["derivation_preview_sha256"],
            }
        )
        (output_dir / "ab.launcher.json").write_text(
            json.dumps(launcher_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"FREEZE complete: {FREEZE_JSON}")
        print(f"  policy_json_sha256={manifest['policy_json_sha256']}")
        print(f"  derivation_preview_sha256={manifest['derivation_preview_sha256']}")
        return 0

    # ---- run phase ----
    freeze_manifest_path = FREEZE_JSON
    if not freeze_manifest_path.is_file():
        print("ERROR: no freeze manifest; run --phase freeze first", file=sys.stderr)
        return 2
    freeze_manifest = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    verify_freeze(freeze_manifest, cases_all)

    arm_a_path = output_dir / "armA-full-query.jsonl"
    arm_b_path = output_dir / "armB-decomposed.jsonl"
    arm_diag_path = output_dir / "armB-diagnostic-simple.jsonl"
    for path in (arm_a_path, arm_b_path, arm_diag_path):
        if path.exists() and not cli_args.overwrite:
            raise ValueError(f"refusing to overwrite {path}; pass --overwrite")

    started_at = utc_now()
    searcher, features, collection, generation, init_s = runner.setup_cell_searcher(cell)
    bench_args = runner.benchmark_args()
    match_config = bench_args.match_config

    exact_run_context = {
        "packet": "issue61-decomposition-ab",
        "policy_id": POLICY_VERSION,
        "policy_json_sha256": sha256_file(POLICY_JSON),
        "freeze_created_at_utc": freeze_manifest.get("created_at_utc"),
        "arm_protocol": {
            "A": "full Q0 query verbatim through existing search path (official baseline)",
            "B": "frozen-policy fragments, per-kind routing, RRF k=60 fusion at depth 20",
        },
        "cell": cell,
        "rerank": False,
        "ocr_weight": runner.OCR_WEIGHT,
        "asr_weight": runner.ASR_WEIGHT,
        "nprobe": runner.NPROBE,
        "temporal_k": runner.TEMPORAL_K,
        "features": features,
        "index_generation": {
            "state": generation.get("state"),
            "index_generation_id": generation.get("index_generation_id"),
            "collection_name": generation.get("collection_name"),
        },
        "collection_identity": {k: collection[k] for k in ("collection", "row_count", "indexes") if k in collection},
        "dataset_path": str(csv_path),
        "dataset_sha256": hb.sha256_file(csv_path),
        "canonical_content_sha256": content_sha256,
        "git": hb.git_provenance(),
        "critical_code": hb.critical_code_hashes(),
        "runtime": hb.runtime_versions(),
        "query_encoder_devices": hb.actual_query_encoder_devices(searcher, features),
        "searcher_init_s": round(init_s, 3),
        "inventory_complete": inventory_validation["complete"],
    }
    (output_dir / "ab.run.json").write_text(
        json.dumps({"status": "running", "started_at": started_at, **exact_run_context}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    scoreable_cases = [case for case in cases_all if case["query_mode"] == "text"]

    # discarded warmup (first scoreable case, Arm A params)
    if scoreable_cases:
        warm_case = next((c for c in scoreable_cases if c["scoreable"]), scoreable_cases[0])
        try:
            searcher.search_multimodal(
                warm_case["query"], 0, bench_args.top_k, features,
                nprobe=bench_args.nprobe, temporal_k=bench_args.temporal_k,
                ocr_weight=bench_args.ocr_weight, asr_weight=bench_args.asr_weight,
                max_interval=bench_args.max_interval, selected=None,
                auto_translate=False, en_to_vi_translate=False,
            )
        except MemoryError:
            raise
        except Exception:
            pass

    records_a: list[dict[str, Any]] = []
    records_b: list[dict[str, Any]] = []
    records_diag: list[dict[str, Any]] = []

    total = len(scoreable_cases)
    with arm_a_path.open("w", encoding="utf-8", newline="\n") as fa, arm_b_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as fb, arm_diag_path.open("w", encoding="utf-8", newline="\n") as fd:

        def emit(handle: Any, record: dict[str, Any]) -> None:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()

        for index, case in enumerate(scoreable_cases, 1):
            qid = case["query_id"]
            complexity, reasons = classify_complexity(case)
            plan_entry = next(e for e in freeze_manifest["plan"] if e["query_id"] == qid)

            # ---- Arm A ----
            try:
                record_a = hb.run_text_variant(searcher, case, 0, bench_args, features)
            except MemoryError:
                raise
            except Exception as exc:
                record_a = {
                    "query_id": qid, "source": case["source"], "task_type": case["task_type"],
                    "evaluation_scope": case["evaluation_scope"], "validation_state": case["validation_state"],
                    "query_mode": "text", "status": "failed_search", "condition": "Q0",
                    "is_primary_baseline": True, "is_all_hints": True, "hint_count": 0,
                    "query_text": case["query"], **hb._empty_metrics(), "latency_ms": None,
                    "top_results": [], "failure": {"type": type(exc).__name__, "message": str(exc)},
                }
            record_a.update(
                {
                    "arm": "A",
                    "policy_id": POLICY_VERSION,
                    "complexity_class": complexity,
                    "complexity_reasons": reasons,
                    "fragment_count": 1,
                    "extra_calls": 0,
                }
            )
            records_a.append(record_a)
            emit(fa, record_a)

            print(
                f"[{index:02d}/{total:02d}] {qid} A({complexity}) "
                f"rank={record_a.get('first_correct_rank') or '-'} "
                f"R@20={record_a.get('recall_at_20')} lat={record_a.get('latency_ms')}"
            )

            # ---- Arm B (confirmatory) ----
            frag_plan = plan_entry["fragments"]
            details: list[dict[str, Any]] = []
            fragment_lists: list[list[Any]] = []
            failure_b = None
            for fragment in frag_plan:
                try:
                    detail, results = run_fragment_search(searcher, fragment, bench_args, features)
                    details.append(detail)
                    fragment_lists.append(results)
                except MemoryError:
                    raise
                except Exception as exc:
                    failure_b = {"type": type(exc).__name__, "message": str(exc), "fragment_index": fragment["index"]}
                    break

            if failure_b is not None:
                record_b = {
                    "query_id": qid, "arm": "B", "status": "failed_search", "condition": "Q0-B",
                    "is_primary_baseline": True, "complexity_class": complexity,
                    "complexity_reasons": reasons, "mode": plan_entry["confirmatory_mode"],
                    "fragments": details, "failure": failure_b,
                    **hb._empty_metrics(), "latency_ms": None,
                }
            else:
                fused = rrf_fuse(fragment_lists, bench_args.top_k)
                metrics_b = hb.metrics_for_results(fused, case, match_config)
                tier = hb.ground_truth_tier(case)
                status_b = (
                    "scored_validated" if tier == "validated"
                    else "scored_provisional" if tier == "provisional"
                    else "unscored_missing_or_unvalidated_ground_truth"
                )
                lats = [d["latency_ms"] for d in details]
                record_b = {
                    "query_id": qid, "source": case["source"], "task_type": case["task_type"],
                    "evaluation_scope": case["evaluation_scope"], "validation_state": case["validation_state"],
                    "query_mode": "text", "arm": "B", "status": status_b, "condition": "Q0-B",
                    "is_primary_baseline": True, "is_all_hints": True, "hint_count": 0,
                    "ground_truth_tier": tier,
                    "query_text_arm_a": case["query"],
                    "complexity_class": complexity, "complexity_reasons": reasons,
                    "mode": plan_entry["confirmatory_mode"],
                    "derivation": plan_entry["confirmatory_derivation"],
                    "fragment_count": len(details),
                    "extra_calls": max(0, len(details) - 1),
                    "fragments": details,
                    "fusion": {"algorithm": "rrf", "k": RRF_K, "input_depth": bench_args.top_k, "output_depth": bench_args.top_k},
                    "answers": case["answer_strings"],
                    "target_mode": case["target_mode"],
                    **metrics_b,
                    "latency_ms": round(max(lats), 3) if lats else None,
                    "sum_fragment_latency_ms": round(sum(lats), 3) if lats else None,
                    "top_results": [
                        hb.serialize_result(item, rank, case, match_config)
                        for rank, item in enumerate(fused[: hb.JUDGING_DEPTH], 1)
                    ],
                }
                fused_fp = [[item.get("video_id"), item.get("frame_id")] for item in fused]
                record_b["fused_top20_fingerprint"] = fused_fp
            records_b.append(record_b)
            emit(fb, record_b)
            print(
                f"           {qid} B(mode={plan_entry['confirmatory_mode']}, frags={len(details)}) "
                f"rank={record_b.get('first_correct_rank') or '-'} "
                f"R@20={record_b.get('recall_at_20')} lat={record_b.get('latency_ms')}"
            )

            # ---- pre-declared simple-control diagnostic ----
            if complexity == "simple" and plan_entry.get("diagnostic_plan"):
                diag_plan = plan_entry["diagnostic_plan"]["fragments"]
                d_details: list[dict[str, Any]] = []
                d_lists: list[list[Any]] = []
                d_failure = None
                for fragment in diag_plan:
                    f = dict(fragment)
                    f.setdefault("index", fragment.get("index", len(d_details)))
                    try:
                        detail, results = run_fragment_search(searcher, f, bench_args, features)
                        d_details.append(detail)
                        d_lists.append(results)
                    except MemoryError:
                        raise
                    except Exception as exc:
                        d_failure = {"type": type(exc).__name__, "message": str(exc)}
                        break
                if d_failure is not None:
                    record_d = {
                        "query_id": qid, "arm": "B-diagnostic", "status": "failed_search",
                        "complexity_class": complexity, "fragments": d_details, "failure": d_failure,
                        **hb._empty_metrics(), "latency_ms": None,
                    }
                else:
                    fused_d = rrf_fuse(d_lists, bench_args.top_k)
                    metrics_d = hb.metrics_for_results(fused_d, case, match_config)
                    lats_d = [d["latency_ms"] for d in d_details]
                    record_d = {
                        "query_id": qid, "arm": "B-diagnostic", "status": "diagnostic_forced_decomposition",
                        "condition": "Q0-Bdiag", "is_primary_baseline": True,
                        "complexity_class": complexity, "mode": plan_entry["diagnostic_plan"]["mode"],
                        "fragment_count": len(d_details), "extra_calls": max(0, len(d_details) - 1),
                        "fragments": d_details,
                        "fusion": {"algorithm": "rrf", "k": RRF_K},
                        **metrics_d,
                        "latency_ms": round(max(lats_d), 3) if lats_d else None,
                        "sum_fragment_latency_ms": round(sum(lats_d), 3) if lats_d else None,
                        "top_results": [
                            hb.serialize_result(item, rank, case, match_config)
                            for rank, item in enumerate(fused_d[: hb.JUDGING_DEPTH], 1)
                        ],
                    }
                records_diag.append(record_d)
                emit(fd, record_d)
                print(f"           {qid} Bdiag(forced) rank={record_d.get('first_correct_rank') or '-'} R@20={record_d.get('recall_at_20')}")

        # ---- determinism probe: re-run Arm A on first two scoreable queries ----
        probe: dict[str, Any] = {"query_ids": [], "all_match": None, "per_query": {}}
        probe_cases = [c for c in scoreable_cases if c["scoreable"]][:2]
        for case in probe_cases:
            qid = case["query_id"]
            probe["query_ids"].append(qid)
            try:
                rerun = hb.run_text_variant(searcher, case, 0, bench_args, features)
                fp_new = [
                    item.get("video_id") + "#" + str(item.get("frame_id"))
                    for item in rerun.get("top_results") or []
                ]
                old_record = next(r for r in records_a if r["query_id"] == qid)
                fp_old = [
                    item.get("video_id") + "#" + str(item.get("frame_id"))
                    for item in old_record.get("top_results") or []
                ]
                match = fp_new == fp_old
                probe["per_query"][qid] = {"match": match, "depth_compared": len(fp_old)}
            except Exception as exc:
                probe["per_query"][qid] = {"error": str(exc)}
        matches = [v.get("match") for v in probe["per_query"].values()]
        probe["all_match"] = bool(matches) and all(m is True for m in matches)

    completed_at = utc_now()

    # ---- summaries ----
    def summarize_arm(records: list[dict[str, Any]], label: str) -> dict[str, Any]:
        scored = [r for r in records if r.get("status", "").startswith("scored_")]
        complex_group = [r for r in scored if r.get("complexity_class") == "complex"]
        simple_group = [r for r in scored if r.get("complexity_class") == "simple"]
        extra: dict[str, Any] = {}
        if label == "B":
            extra = {
                "mean_extra_calls": round(sum(r.get("extra_calls", 0) for r in scored) / len(scored), 3) if scored else None,
                "total_extra_calls": sum(r.get("extra_calls", 0) for r in scored),
                "mean_sum_fragment_latency_ms": (
                    round(sum(r.get("sum_fragment_latency_ms") or 0 for r in scored) / len(scored), 3) if scored else None
                ),
            }
        return {
            "arm": label,
            "global_q0": hb.aggregate(scored) if scored else None,
            "by_complexity": {
                "complex": hb.aggregate(complex_group) if complex_group else None,
                "simple": hb.aggregate(simple_group) if simple_group else None,
            },
            "by_task": {
                "tkis": hb._task_aggregate(scored, "tkis"),
                "qa": hb._task_aggregate(scored, "qa"),
                "trake": hb._task_aggregate(scored, "trake"),
            },
            **extra,
        }

    summary_a = summarize_arm(records_a, "A")
    summary_b = summarize_arm(records_b, "B")

    paired: list[dict[str, Any]] = []
    taxonomy_rows: list[dict[str, Any]] = []
    for ra, rb in zip(records_a, records_b):
        entry = {
            "query_id": ra["query_id"],
            "task_type": ra["task_type"],
            "complexity_class": ra["complexity_class"],
            "scoreable": ra["status"].startswith("scored_"),
            "A": {
                "first_correct_rank": ra.get("first_correct_rank"),
                "recall_at_1": ra.get("recall_at_1"),
                "recall_at_5": ra.get("recall_at_5"),
                "recall_at_10": ra.get("recall_at_10"),
                "recall_at_20": ra.get("recall_at_20"),
                "reciprocal_rank": ra.get("reciprocal_rank"),
                "video_first_correct_rank": (ra.get("video_retrieval") or {}).get("first_correct_video_rank"),
                "event_ranks": ra.get("target_ranks"),
                "latency_ms": ra.get("latency_ms"),
                "status": ra.get("status"),
            },
            "B": {
                "first_correct_rank": rb.get("first_correct_rank"),
                "recall_at_1": rb.get("recall_at_1"),
                "recall_at_5": rb.get("recall_at_5"),
                "recall_at_10": rb.get("recall_at_10"),
                "recall_at_20": rb.get("recall_at_20"),
                "reciprocal_rank": rb.get("reciprocal_rank"),
                "video_first_correct_rank": (rb.get("video_retrieval") or {}).get("first_correct_video_rank"),
                "event_ranks": rb.get("target_ranks"),
                "latency_ms": rb.get("latency_ms"),
                "sum_fragment_latency_ms": rb.get("sum_fragment_latency_ms"),
                "extra_calls": rb.get("extra_calls"),
                "status": rb.get("status"),
                "mode": rb.get("mode"),
            },
        }
        if entry["scoreable"]:
            entry["delta"] = {
                "recall_at_20": round(rb["recall_at_20"] - ra["recall_at_20"], 6),
                "reciprocal_rank": round((rb["reciprocal_rank"] or 0) - (ra["reciprocal_rank"] or 0), 6),
                "rank_delta_positions": (
                    None
                    if rb.get("first_correct_rank") is None or ra.get("first_correct_rank") is None
                    else ra["first_correct_rank"] - rb["first_correct_rank"]
                ),
            }
        paired.append(entry)
        taxonomy_rows.append({"query_id": ra["query_id"], "arm": "A", **classify_failure(next(c for c in scoreable_cases if c["query_id"] == ra["query_id"]), ra)})
        taxonomy_rows.append({"query_id": rb["query_id"], "arm": "B", **classify_failure(next(c for c in scoreable_cases if c["query_id"] == rb["query_id"]), rb)})

    def delta_of(group: str) -> dict[str, Any]:
        rows = [p for p in paired if p["scoreable"] and p["complexity_class"] == group]
        out: dict[str, Any] = {"n": len(rows)}
        for key in ("recall_at_1", "recall_at_5", "recall_at_10", "recall_at_20", "reciprocal_rank"):
            vals = [p["B"][key] - p["A"][key] for p in rows if p["B"][key] is not None and p["A"][key] is not None]
            out[f"delta_{key}"] = round(sum(vals) / len(vals), 6) if vals else None
        return out

    complex_delta = delta_of("complex")
    simple_delta = delta_of("simple")

    # frozen recommendation mapping
    dr20 = complex_delta.get("delta_recall_at_20")
    dmrr = complex_delta.get("delta_reciprocal_rank")
    if dr20 is None or dmrr is None:
        recommendation = "indeterminate_insufficient_scoreable_data"
    elif dr20 <= 0.05 and dmrr <= 0.03 or dr20 < 0 or dmrr < 0:
        recommendation = "no_benefit"
    elif dr20 >= 0.15 and dmrr >= 0.08:
        recommendation = "strong_benefit"
    else:
        recommendation = "conditional_benefit"

    diagnostics_simple = [
        {
            "query_id": r["query_id"],
            "first_correct_rank": r.get("first_correct_rank"),
            "recall_at_20": r.get("recall_at_20"),
            "latency_ms": r.get("latency_ms"),
            "extra_calls": r.get("extra_calls"),
        }
        for r in records_diag
    ]

    deltas_doc = {
        "created_at": completed_at,
        "policy_id": POLICY_VERSION,
        "recommendation_frozen_mapping": recommendation,
        "complex_group_delta": complex_delta,
        "simple_control_delta": simple_delta,
        "simple_control_diagnostic_forced_decomposition": diagnostics_simple,
        "determinism_probe": probe,
        "paired_per_query": paired,
        "failure_taxonomy": taxonomy_rows,
    }
    runner.write_json(output_dir / "deltas-issue61.json", deltas_doc)
    runner.write_json(
        output_dir / "summary-armA.json",
        {"created_at": completed_at, "started_at": started_at, **exact_run_context, **summary_a},
    )
    runner.write_json(
        output_dir / "summary-armB.json",
        {"created_at": completed_at, "started_at": started_at, **exact_run_context, **summary_b},
    )
    runner.write_json(
        output_dir / "failure-taxonomy.json",
        {
            "schema_version": "issue61-failure-taxonomy-v1",
            "generated_at": completed_at,
            "rules_source": "decomposition-policy-v1.json section failure_taxonomy_rules_frozen",
            "thresholds": {"high_latency_or_timeout_ms": 60000, "timestamp_alignment_near_s": 10.0},
            "rows": taxonomy_rows,
        },
    )

    final_meta = dict(launcher_metadata)
    final_meta.update(
        {
            "status": "complete",
            "ended_at": completed_at,
            "records_arm_a": len(records_a),
            "records_arm_b": len(records_b),
            "records_arm_b_diagnostic": len(records_diag),
            "results_sha256": {
                "armA-full-query.jsonl": sha256_file(arm_a_path),
                "armB-decomposed.jsonl": sha256_file(arm_b_path),
                "armB-diagnostic-simple.jsonl": sha256_file(arm_diag_path),
            },
            "determinism_probe_all_match": probe["all_match"],
            "recommendation_frozen_mapping": recommendation,
        }
    )
    (output_dir / "ab.launcher.json").write_text(
        json.dumps(final_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "ab.run.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "started_at": started_at,
                "ended_at": completed_at,
                "records_written": {"A": len(records_a), "B": len(records_b), "B_diag": len(records_diag)},
                **exact_run_context,
                "determinism_probe": probe,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"issue61 A/B complete: {output_dir}")
    print(f"recommendation(frozen mapping): {recommendation}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
