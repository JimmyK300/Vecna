#!/usr/bin/env python3
"""Post-freeze atom-level sufficiency judge and deterministic aggregation for Issue #95."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PACKETS_DEFAULT = ROOT / "eval_packets.jsonl"
CONFIG_DEFAULT = ROOT / "evaluation_config.json"
JUDGMENTS_DEFAULT = ROOT / "judgments"
METRICS_DEFAULT = ROOT / "evaluation_metrics.json"
LEDGER_DEFAULT = ROOT / "missing_evidence_ledger.jsonl"
REPORT_DEFAULT = ROOT / "REPORT.md"
VALID_STATUSES = {"SUPPORTED", "PARTIAL", "MISSING", "CONTRADICTED", "UNVERIFIABLE"}
VALID_EXACT = {"CORRECT", "INCORRECT", "MISSING", "NOT_APPLICABLE"}

JUDGE_PROMPT = """You are evaluating a query-independent video caption after the caption has been frozen.
Use only the supplied caption and authoritative query requirements. Do not use outside knowledge and do not repair the caption.

For every requirement, assign exactly one status:
- SUPPORTED: the caption explicitly preserves the complete requirement.
- PARTIAL: it preserves some material parts but omits or weakens at least one material part.
- MISSING: the needed evidence is absent.
- CONTRADICTED: the caption explicitly states evidence incompatible with the requirement.
- UNVERIFIABLE: the supplied text is too corrupt or ambiguous to compare. Do not use this merely for missing evidence.

For requirements involving literal OCR/text, a number, or a count, list the applicable exact_categories from OCR_TEXT, NUMBER, COUNT and set exact_result to CORRECT, INCORRECT, or MISSING. Otherwise use an empty list and NOT_APPLICABLE.
List unsupported_claims only when a caption assertion is directly contradicted by a supplied requirement. Claims outside the requirements are not reviewable here and must not be called unsupported.

Return JSON only with this shape:
{{"requirements":[{{"event_id":"E01","status":"SUPPORTED|PARTIAL|MISSING|CONTRADICTED|UNVERIFIABLE","caption_evidence":"short exact excerpt or empty string","reason":"brief reason","exact_categories":[],"exact_result":"CORRECT|INCORRECT|MISSING|NOT_APPLICABLE"}}],"unsupported_claims":[{{"caption_claim":"...","conflict_with":"E01","reason":"..."}}],"review_limits":["..."]}}

QUERY TEXT:
{query_text}

REQUIREMENTS:
{requirements}

FROZEN CAPTION ({prompt_family}):
{caption}
"""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return jsonable(dump())
        except Exception:
            pass
    return str(value)


def parse_json_output(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def validate_judgment(packet: dict[str, Any], value: Any) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("requirements"), list):
        raise ValueError("judge output lacks requirements list")
    expected = [r["event_id"] for r in packet["requirements"]]
    actual = [r.get("event_id") for r in value["requirements"]]
    if actual != expected:
        raise ValueError(f"requirement IDs/order mismatch: expected {expected}, got {actual}")
    for row in value["requirements"]:
        if row.get("status") not in VALID_STATUSES:
            raise ValueError(f"invalid status for {row.get('event_id')}: {row.get('status')}")
        if row.get("exact_result") not in VALID_EXACT:
            raise ValueError(f"invalid exact_result for {row.get('event_id')}: {row.get('exact_result')}")
        if not isinstance(row.get("exact_categories"), list):
            raise ValueError(f"exact_categories is not a list for {row.get('event_id')}")
    if not isinstance(value.get("unsupported_claims", []), list):
        raise ValueError("unsupported_claims is not a list")


def judge(args: argparse.Namespace) -> None:
    try:
        from google import genai
    except Exception as exc:
        raise RuntimeError("google-genai is required: pip install -r requirements.txt") from exc
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY must be present")
    packets = read_jsonl(args.packets)
    prompt_sha = sha256_text(JUDGE_PROMPT)
    client = genai.Client()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    completed = failed = 0
    for packet in packets:
        rendered = JUDGE_PROMPT.format(
            query_text=packet.get("query_text") or "",
            requirements=json.dumps(packet.get("requirements", []), ensure_ascii=False, indent=2),
            prompt_family=packet["prompt_family"],
            caption=json.dumps(packet.get("caption"), ensure_ascii=False, indent=2),
        )
        identity = {
            "model": args.model,
            "judge_prompt_sha256": prompt_sha,
            "packet_sha256": sha256_text(json.dumps(packet, ensure_ascii=False, sort_keys=True)),
        }
        cache_key = sha256_text(json.dumps(identity, sort_keys=True))
        stem = f"{packet['query_id']}__{packet['prompt_family']}__{cache_key[:16]}"
        prior = sorted(args.output_dir.glob(stem + "*.json"))
        cached = False
        for path in prior:
            try:
                if json.loads(path.read_text(encoding="utf-8")).get("status") == "ok":
                    cached = True
                    break
            except Exception:
                pass
        if cached and not args.force:
            completed += 1
            continue
        target = args.output_dir / f"{stem}__attempt-{len(prior) + 1:02d}.json"
        started = time.time()
        record: dict[str, Any] = {
            "schema": "shot-caption-oracle-judgment-v0",
            "query_id": packet["query_id"],
            "prompt_family": packet["prompt_family"],
            "caption_cache_key": packet.get("caption_cache_key"),
            "model": args.model,
            "judge_prompt_sha256": prompt_sha,
            "cache_key": cache_key,
            "started_at_unix": started,
            "caption_was_frozen_before_judging": True,
        }
        try:
            interaction = client.interactions.create(model=args.model, input=[{"type": "text", "text": rendered}])
            output_text = str(getattr(interaction, "output_text", "") or "")
            parsed = parse_json_output(output_text)
            validate_judgment(packet, parsed)
            record.update({
                "status": "ok",
                "output_text": output_text,
                "parsed_json": parsed,
                "interaction_id": getattr(interaction, "id", None),
                "usage": jsonable(getattr(interaction, "usage", None)),
            })
            completed += 1
        except Exception as exc:
            record.update({"status": "error", "error_type": type(exc).__name__, "error": str(exc)})
            failed += 1
        record["elapsed_s"] = time.time() - started
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"query_id": packet["query_id"], "prompt": packet["prompt_family"], "status": record["status"], "elapsed_s": record["elapsed_s"]}), flush=True)
        if failed and args.stop_on_error:
            raise RuntimeError(f"judge failure for {packet['query_id']} / {packet['prompt_family']}: {record.get('error')}")
    print(json.dumps({"completed_or_cached": completed, "failed": failed, "output_dir": str(args.output_dir)}))


def safe_rate(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def metric_block(items: list[dict[str, Any]]) -> dict[str, Any]:
    atoms = [atom for item in items for atom in item["atoms"]]
    status_counts = Counter(atom["status"] for atom in atoms)
    exact = [atom for atom in atoms if atom["exact_result"] != "NOT_APPLICABLE"]
    exact_counts = Counter(atom["exact_result"] for atom in exact)
    fully = sum(bool(item["atoms"]) and all(a["status"] == "SUPPORTED" for a in item["atoms"]) for item in items)
    unsupported_claims = sum(len(item["unsupported_claims"]) for item in items)
    unsupported_captions = sum(bool(item["unsupported_claims"]) for item in items)
    total = len(atoms)
    return {
        "caption_count": len(items),
        "atom_count": total,
        "status_counts": dict(sorted(status_counts.items())),
        "all_requirements_covered_count": fully,
        "all_requirements_covered_rate": safe_rate(fully, len(items)),
        "strict_atomic_recall": safe_rate(status_counts["SUPPORTED"], total),
        "partial_credit_atomic_recall": safe_rate(status_counts["SUPPORTED"] + 0.5 * status_counts["PARTIAL"], total),
        "contradicted_atom_rate": safe_rate(status_counts["CONTRADICTED"], total),
        "exact_requirement_count": len(exact),
        "exact_result_counts": dict(sorted(exact_counts.items())),
        "exact_requirement_correctness": safe_rate(exact_counts["CORRECT"], len(exact)),
        "reviewable_unsupported_claim_count": unsupported_claims,
        "reviewable_unsupported_claim_caption_rate": safe_rate(unsupported_captions, len(items)),
        "average_caption_length_chars": safe_rate(sum(item["caption_length_chars"] for item in items), len(items)),
    }


def aggregate(args: argparse.Namespace) -> None:
    packets = {(p["query_id"], p["prompt_family"]): p for p in read_jsonl(args.packets)}
    judgments: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(args.judgment_dir.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("status") != "ok":
            continue
        key = (row["query_id"], row["prompt_family"])
        if key in judgments:
            raise RuntimeError(f"multiple successful judgments for {key}")
        judgments[key] = row
    missing = sorted(set(packets) - set(judgments))
    extra = sorted(set(judgments) - set(packets))
    if missing or extra:
        raise RuntimeError(f"judgment/packet mismatch: missing={missing}, extra={extra}")
    items: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for key, packet in sorted(packets.items()):
        parsed = judgments[key]["parsed_json"]
        validate_judgment(packet, parsed)
        atoms = parsed["requirements"]
        item = {
            "query_id": packet["query_id"],
            "prompt_family": packet["prompt_family"],
            "capability_tags": packet.get("capability_tags", []),
            "task_type": packet.get("task_type"),
            "atoms": atoms,
            "unsupported_claims": parsed.get("unsupported_claims", []),
            "review_limits": parsed.get("review_limits", []),
            "caption_length_chars": len(json.dumps(packet.get("caption"), ensure_ascii=False)),
        }
        items.append(item)
        for atom in atoms:
            if atom["status"] != "SUPPORTED":
                ledger.append({
                    "query_id": packet["query_id"],
                    "prompt_family": packet["prompt_family"],
                    "event_id": atom["event_id"],
                    "status": atom["status"],
                    "caption_evidence": atom.get("caption_evidence", ""),
                    "reason": atom.get("reason", ""),
                })
    by_prompt = {name: metric_block([i for i in items if i["prompt_family"] == name]) for name in sorted({i["prompt_family"] for i in items})}
    by_capability = {name: metric_block([i for i in items if name in i["capability_tags"]]) for name in sorted({tag for i in items for tag in i["capability_tags"]})}
    by_task = {name: metric_block([i for i in items if i["task_type"] == name]) for name in sorted({i["task_type"] for i in items if i["task_type"]})}
    def selection_key(name: str) -> tuple[Any, ...]:
        m = by_prompt[name]
        return (
            -(m["all_requirements_covered_rate"] or 0),
            -(m["strict_atomic_recall"] or 0),
            -(m["exact_requirement_correctness"] or 0),
            m["contradicted_atom_rate"] or 0,
            m["reviewable_unsupported_claim_caption_rate"] or 0,
            m["average_caption_length_chars"] or 0,
            name,
        )
    selected = min(by_prompt, key=selection_key)
    audit = {"configured_packet_count": 0, "audited_atom_count": 0, "status_agreement_count": 0, "status_agreement_rate": None}
    if args.manual_audit and args.manual_audit.exists():
        rows = read_jsonl(args.manual_audit)
        audit = {
            "configured_packet_count": len({(r["query_id"], r["prompt_family"]) for r in rows}),
            "audited_atom_count": len(rows),
            "status_agreement_count": sum(r.get("automated_status") == r.get("audit_status") for r in rows),
        }
        audit["status_agreement_rate"] = safe_rate(audit["status_agreement_count"], audit["audited_atom_count"])
    metrics = {
        "schema": "shot-caption-oracle-evaluation-v0",
        "overall": metric_block(items),
        "by_prompt_family": by_prompt,
        "by_capability_tag": by_capability,
        "by_task_type": by_task,
        "prompt_selection": {"selected_prompt_family": selected, "policy": json.loads(args.config.read_text(encoding="utf-8"))["prompt_freeze_policy"]},
        "manual_audit": audit,
        "limitations": [
            "Unsupported claims are reviewable only when directly contradicted by supplied requirements; the metric is not full clip-level factuality.",
            "The automated judge is the declared Gemini model and may share model-family biases with the captioner.",
        ],
    }
    args.metrics.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_jsonl(args.ledger, ledger)
    lines = [
        "# Gemini shot-caption oracle sufficiency v0 — result",
        "",
        f"Frozen prompt selection: `{selected}`.",
        "",
        "## Prompt comparison",
        "",
        "| Prompt | All covered | Strict atomic recall | Partial-credit recall | Exact correctness | Contradiction rate | Reviewable unsupported-caption rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, m in by_prompt.items():
        pct = lambda value: "n/a" if value is None else f"{100 * value:.1f}%"
        lines.append(f"| {name} | {pct(m['all_requirements_covered_rate'])} | {pct(m['strict_atomic_recall'])} | {pct(m['partial_credit_atomic_recall'])} | {pct(m['exact_requirement_correctness'])} | {pct(m['contradicted_atom_rate'])} | {pct(m['reviewable_unsupported_claim_caption_rate'])} |")
    lines += [
        "",
        "## Audit and limits",
        "",
        f"The predeclared manual subset covers {audit['configured_packet_count']} packets and {audit['audited_atom_count']} atoms; status agreement is " + ("not yet recorded." if audit["status_agreement_rate"] is None else f"{100 * audit['status_agreement_rate']:.1f}%."),
        "",
        "Unsupported-claim review is bounded to direct conflicts with the supplied requirements. It is not a clip-level hallucination estimate.",
        "",
        "See `evaluation_metrics.json` for capability/task slices and `missing_evidence_ledger.jsonl` for every non-supported atom.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"packets": len(items), "atoms": metrics["overall"]["atom_count"], "selected_prompt_family": selected, "metrics": str(args.metrics), "ledger": str(args.ledger), "report": str(args.report)}))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="stage", required=True)
    j = sub.add_parser("judge")
    j.add_argument("--packets", type=Path, default=PACKETS_DEFAULT)
    j.add_argument("--output-dir", type=Path, default=JUDGMENTS_DEFAULT)
    j.add_argument("--model", default="gemini-3.8-flash")
    j.add_argument("--force", action="store_true")
    j.add_argument("--stop-on-error", action="store_true")
    j.set_defaults(func=judge)
    a = sub.add_parser("aggregate")
    a.add_argument("--packets", type=Path, default=PACKETS_DEFAULT)
    a.add_argument("--judgment-dir", type=Path, default=JUDGMENTS_DEFAULT)
    a.add_argument("--config", type=Path, default=CONFIG_DEFAULT)
    a.add_argument("--manual-audit", type=Path, default=ROOT / "manual_audit.jsonl")
    a.add_argument("--metrics", type=Path, default=METRICS_DEFAULT)
    a.add_argument("--ledger", type=Path, default=LEDGER_DEFAULT)
    a.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    a.set_defaults(func=aggregate)
    return p


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
