#!/usr/bin/env python3
"""Build the canonical Issue #34 projection for the current 115-query benchmark.

This script does not create new truth. It joins:
  * frozen 78-row P0/P1/P2 Headless vNext truth in Vecna; and
  * the current 115-row identity ledger in official-dataset-control, whose P3
    rows contain the newer provisional source-text truth.

Historical rows are joined by provenance-backed source identity, never query
text. Query text is used only as a fail-closed consistency check. The join
fails closed unless the validated 113/115 inventory is reproduced.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

VECNA_REPO = "JimmyK300/Vecna"
VECNA_COMMIT = "e0981b9022723f0a8bb20d4ccb108f725f4f2e50"
VECNA_PATH = "benchmark-results/headless-vnext-p0-p1-p2-v1/manifest.json"
VECNA_BLOB = "396fcc70df9a0af14e705720104f38bb2dd47828"

ODC_REPO = "JimmyK300/official-dataset-control"
ODC_COMMIT = "a8c15b94e576ea1c8a0acfe20d816112692b2639"
ODC_PATH = (
    "evaluation/headless-current-p0-p1-p2-p3-qwen-only-top100-v0/"
    "ground_truth_current_115.jsonl"
)
ODC_BLOB = "797fe9ef462fffa32e86af4419f0fb69e916293b"

OUTPUT_REL = Path("benchmark-results/issue34-current-115/ground_truth_current_115.jsonl")
META_REL = OUTPUT_REL.with_suffix(".meta.json")
AUTHORITY_REL = Path("benchmark-results/issue34-current-115/AUTHORITY.json")

EXPECTED_CURRENT = {"P0": 24, "P1": 25, "P2": 30, "P3": 36}
EXPECTED_HISTORICAL = {"P0": 23, "P1": 25, "P2": 30}
EXPECTED_UNSCOREABLE = {"p0_q15", "p3_q09"}


class BuildError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def run_gh_json(endpoint: str) -> dict:
    proc = subprocess.run(
        ["gh", "api", endpoint],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise BuildError(f"`gh api {endpoint}` failed: {detail}")
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BuildError(f"GitHub returned invalid JSON for {endpoint}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"Expected object from GitHub for {endpoint}")
    return value


def fetch_pinned_file(repo: str, commit: str, path: str, expected_blob: str) -> bytes:
    encoded = quote(path, safe="/")
    payload = run_gh_json(f"repos/{repo}/contents/{encoded}?ref={commit}")
    blob = payload.get("sha")
    if blob != expected_blob:
        raise BuildError(
            f"Pinned blob mismatch for {repo}@{commit}:{path}: "
            f"expected {expected_blob}, got {blob}"
        )
    if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        raise BuildError(f"Expected inline base64 file content for {repo}:{path}")
    try:
        return base64.b64decode(payload["content"], validate=False)
    except Exception as exc:
        raise BuildError(f"Could not decode {repo}:{path}") from exc


def normalize_query(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split())


def parse_current_ledger(raw: bytes) -> list[dict]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError("Current ODC ledger is not UTF-8") from exc

    rows: list[dict] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BuildError(f"Invalid ODC JSONL row {line_no}") from exc
        if not isinstance(row, dict):
            raise BuildError(f"ODC row {line_no} is not an object")
        rows.append(row)

    if len(rows) != 115:
        raise BuildError(f"Expected 115 current rows, found {len(rows)}")

    ids = [row.get("query_id") for row in rows]
    if any(not isinstance(qid, str) or not qid for qid in ids):
        raise BuildError("Every current row must have query_id")
    if len(set(ids)) != len(ids):
        raise BuildError("Duplicate current query_id detected")

    counts: dict[str, int] = {}
    for row in rows:
        phase = row.get("canonical_round")
        counts[phase] = counts.get(phase, 0) + 1
    if counts != EXPECTED_CURRENT:
        raise BuildError(f"Current phase counts changed: {counts}")
    return rows


def parse_vecna_manifest(raw: bytes) -> tuple[dict, list[dict]]:
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError("Invalid frozen Vecna manifest") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("records"), list):
        raise BuildError("Frozen Vecna manifest has unexpected schema")
    records = manifest["records"]
    if len(records) != 78:
        raise BuildError(f"Expected 78 frozen records, found {len(records)}")
    counts = manifest.get("counts", {})
    if counts.get("execution_rows") != 78:
        raise BuildError("Frozen manifest execution_rows is not 78")
    return manifest, records


def historical_identity(row: dict, row_number: int) -> tuple[str, str]:
    phase = row.get("operational_phase")
    raw_query_id = row.get("raw_query_id")
    task_type = row.get("task_type")
    provenance = row.get("provenance")
    if phase not in EXPECTED_HISTORICAL:
        raise BuildError(f"Frozen record {row_number} has unexpected phase {phase!r}")
    if not isinstance(raw_query_id, str) or not raw_query_id:
        raise BuildError(f"Frozen record {row_number} is missing raw_query_id")
    if not isinstance(task_type, str) or not task_type:
        raise BuildError(f"Frozen record {row_number} is missing task_type")
    if not isinstance(provenance, dict):
        raise BuildError(f"Frozen record {row_number} is missing provenance")
    source_csv = provenance.get("source_csv")
    if not isinstance(source_csv, str) or not source_csv:
        raise BuildError(f"Frozen record {row_number} is missing provenance.source_csv")

    source_key = Path(source_csv).stem
    expected_source_key = (
        f"query-{raw_query_id}-{task_type}" if phase in {"P0", "P1"} else raw_query_id
    )
    if source_key != expected_source_key:
        raise BuildError(
            f"Frozen record {row_number} source identity mismatch: "
            f"expected {expected_source_key}, got {source_key}"
        )
    if not source_key.endswith(f"-{task_type}"):
        raise BuildError(f"Frozen record {row_number} source key/task mismatch")

    # Historical P0 was stored under p1-* source filenames. Normalize only this
    # known namespace difference to the current ledger's canonical P0 identity.
    if phase == "P0":
        if not source_key.startswith("query-p1-"):
            raise BuildError(f"Frozen P0 record {row_number} has unexpected source key")
        source_key = "query-p0-" + source_key[len("query-p1-") :]
    elif not source_key.startswith(f"query-{phase.lower()}-"):
        raise BuildError(f"Frozen {phase} record {row_number} has unexpected source key")

    return phase, source_key


def historical_index(
    records: list[dict],
) -> tuple[dict[tuple[str, str], dict], dict[str, set[tuple[str, str]]]]:
    by_identity: dict[tuple[str, str], dict] = {}
    by_text: dict[str, set[tuple[str, str]]] = defaultdict(set)
    phase_counts: dict[str, int] = {}

    for i, row in enumerate(records, start=1):
        query = row.get("query_text")
        if not isinstance(query, str) or not query.strip():
            raise BuildError(f"Frozen record {i} is missing query_text")
        identity = historical_identity(row, i)
        if identity in by_identity:
            raise BuildError(f"Frozen manifest contains duplicate source identity {identity}")
        by_identity[identity] = row
        by_text[normalize_query(query)].add(identity)
        phase = row.get("operational_phase")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    if phase_counts != EXPECTED_HISTORICAL:
        raise BuildError(f"Frozen manifest phase counts changed: {phase_counts}")
    if len(by_identity) != 78:
        raise BuildError(f"Expected 78 unique frozen source identities, got {len(by_identity)}")
    return by_identity, by_text


def current_identity(current: dict) -> tuple[str, str]:
    phase = current.get("canonical_round")
    qid = current.get("query_id")
    source_key = current.get("canonical_source_key")
    sources = current.get("sources")
    if phase not in {"P0", "P1", "P2"}:
        raise BuildError(f"{qid} is not a historical P0/P1/P2 row")
    if not isinstance(source_key, str) or not source_key:
        raise BuildError(f"{qid} is missing canonical_source_key")
    if not isinstance(sources, list):
        raise BuildError(f"{qid} is missing sources")

    support = [
        source
        for source in sources
        if isinstance(source, dict)
        and (
            source.get("canonical_source_key") == source_key
            or source.get("row_id") == source_key
        )
    ]
    if len(support) != 1:
        raise BuildError(
            f"{qid} canonical_source_key is not supported by exactly one source row"
        )
    return phase, source_key


def make_historical_projection(current: dict, frozen: dict) -> dict:
    return {
        "query_id": current["query_id"],
        "canonical_round": current["canonical_round"],
        "canonical_source_key": current.get("canonical_source_key"),
        "query": current.get("query"),
        "task_type": frozen.get("task_type"),
        "scoreable": True,
        "truth_tier": "frozen_headless_benchmark_truth",
        "truth_authority": "JimmyK300/Vecna#34 historical Headless vNext lineage",
        "accepted_video_id": frozen.get("accepted_video_id"),
        "accepted_ranges": frozen.get("accepted_ranges", []),
        "trake_event_truth": frozen.get("trake_event_truth", []),
        "scoreability": frozen.get("scoreability"),
        "historical_identity": {
            "canonical_query_id": frozen.get("canonical_query_id"),
            "canonical_source_id": frozen.get("canonical_source_id"),
            "raw_query_id": frozen.get("raw_query_id"),
            "vecna_provenance_id": frozen.get("vecna_provenance_id"),
        },
        "source_provenance": frozen.get("provenance"),
        "current_identity_source": {
            "repository": ODC_REPO,
            "commit": ODC_COMMIT,
            "path": ODC_PATH,
            "source_row": current.get("sources", []),
        },
    }


def make_unscoreable_projection(current: dict) -> dict:
    return {
        "query_id": current["query_id"],
        "canonical_round": current["canonical_round"],
        "canonical_source_key": current.get("canonical_source_key"),
        "query": current.get("query"),
        "task_type": current.get("task_type"),
        "scoreable": False,
        "truth_tier": "unresolved",
        "truth_authority": current.get("truth_authority"),
        "truth_status": current.get("truth_status"),
        "notes": current.get("notes"),
        "source_provenance": current.get("sources", []),
    }


def make_p3_projection(current: dict) -> dict:
    scoreable = bool(current.get("scoreable"))
    return {
        "query_id": current["query_id"],
        "canonical_round": "P3",
        "canonical_source_key": current.get("canonical_source_key"),
        "query": current.get("query"),
        "task_type": current.get("task_type"),
        "scoreable": scoreable,
        "truth_tier": (
            "provisional_source_text_verified_needs_corpus_validation"
            if scoreable
            else "unresolved"
        ),
        "truth_authority": current.get("truth_authority"),
        "truth_status": current.get("truth_status"),
        "evaluation_gate": current.get("evaluation_gate"),
        "accepted_groups": current.get("accepted_groups", []),
        "answer_strings": current.get("answer_strings", []),
        "validation_state": current.get("validation_state"),
        "notes": current.get("notes"),
        "source_provenance": current.get("sources", []),
    }


def build_projection(current_rows: list[dict], frozen_records: list[dict]) -> list[dict]:
    frozen_by_identity, frozen_by_text = historical_index(frozen_records)
    used_identities: set[tuple[str, str]] = set()
    output: list[dict] = []
    historical_matches: dict[str, int] = {"P0": 0, "P1": 0, "P2": 0}

    for current in current_rows:
        phase = current["canonical_round"]
        qid = current["query_id"]

        if phase == "P3":
            output.append(make_p3_projection(current))
            continue

        identity = current_identity(current)
        frozen = frozen_by_identity.get(identity)
        if frozen is None:
            output.append(make_unscoreable_projection(current))
            continue

        if identity in used_identities:
            raise BuildError(f"Frozen truth matched more than once: {qid}")

        query = current.get("query")
        if not isinstance(query, str):
            raise BuildError(f"{qid} has no query text")
        text_candidates = frozen_by_text.get(normalize_query(query), set())
        if text_candidates and identity not in text_candidates:
            raise BuildError(
                f"Query-text consistency conflict for {qid}: identity={identity}, "
                f"text_candidates={sorted(text_candidates)}"
            )

        used_identities.add(identity)
        historical_matches[phase] += 1
        output.append(make_historical_projection(current, frozen))

    if historical_matches != EXPECTED_HISTORICAL:
        raise BuildError(f"Historical match counts changed: {historical_matches}")
    if len(used_identities) != 78 or len(frozen_by_identity) != 78:
        raise BuildError(
            "Frozen join is not bijective: "
            f"used={len(used_identities)}, frozen={len(frozen_by_identity)}"
        )

    unscoreable = {row["query_id"] for row in output if not row["scoreable"]}
    if unscoreable != EXPECTED_UNSCOREABLE:
        raise BuildError(f"Unexpected unscoreable set: {sorted(unscoreable)}")

    scoreable = sum(bool(row["scoreable"]) for row in output)
    if len(output) != 115 or scoreable != 113:
        raise BuildError(f"Expected 113/115 scoreable, got {scoreable}/{len(output)}")

    p3_scoreable = sum(
        bool(row["scoreable"]) for row in output if row["canonical_round"] == "P3"
    )
    if p3_scoreable != 35:
        raise BuildError(f"Expected 35 scoreable P3 rows, got {p3_scoreable}")
    return output


def encode_jsonl(rows: list[dict]) -> bytes:
    return (
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    ).encode("utf-8")


def metadata(*, vecna_raw: bytes, odc_raw: bytes, output_raw: bytes) -> dict:
    return {
        "schema": "issue34-headless-current-projection-meta-v1",
        "parent_issue": "JimmyK300/Vecna#34",
        "authority_contract": AUTHORITY_REL.as_posix(),
        "join": {
            "historical_identity": "(canonical_round, canonical_source_key)",
            "frozen_identity_source": "provenance.source_csv",
            "query_text_role": "consistency_check_only",
        },
        "counts": {
            "current_queries": 115,
            "scoreable": 113,
            "unscoreable": 2,
            "p0_p1_p2_frozen": 78,
            "p3_provisional_scoreable": 35,
        },
        "unscoreable_query_ids": sorted(EXPECTED_UNSCOREABLE),
        "sources": [
            {
                "repository": VECNA_REPO,
                "commit": VECNA_COMMIT,
                "path": VECNA_PATH,
                "blob_sha": VECNA_BLOB,
                "sha256": sha256_bytes(vecna_raw),
            },
            {
                "repository": ODC_REPO,
                "commit": ODC_COMMIT,
                "path": ODC_PATH,
                "blob_sha": ODC_BLOB,
                "sha256": sha256_bytes(odc_raw),
            },
        ],
        "projection": {
            "path": OUTPUT_REL.as_posix(),
            "sha256": sha256_bytes(output_raw),
        },
        "policy": (
            "Generated join only. P0-P2 frozen truth and P3 provisional truth retain "
            "their distinct authority tiers; no missing truth is inferred."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed projection + metadata without rewriting them",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    out_path = repo_root / OUTPUT_REL
    meta_path = repo_root / META_REL

    vecna_raw = fetch_pinned_file(VECNA_REPO, VECNA_COMMIT, VECNA_PATH, VECNA_BLOB)
    odc_raw = fetch_pinned_file(ODC_REPO, ODC_COMMIT, ODC_PATH, ODC_BLOB)
    _, frozen_records = parse_vecna_manifest(vecna_raw)
    current_rows = parse_current_ledger(odc_raw)
    rows = build_projection(current_rows, frozen_records)
    out_raw = encode_jsonl(rows)
    meta_raw = (
        json.dumps(
            metadata(vecna_raw=vecna_raw, odc_raw=odc_raw, output_raw=out_raw),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    if args.check:
        problems: list[str] = []
        if not out_path.is_file() or out_path.read_bytes() != out_raw:
            problems.append(f"stale or missing {OUTPUT_REL.as_posix()}")
        if not meta_path.is_file() or meta_path.read_bytes() != meta_raw:
            problems.append(f"stale or missing {META_REL.as_posix()}")
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1
        print("OK: Issue #34 projection reproduces 113/115 scoreable rows")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_raw)
    meta_path.write_bytes(meta_raw)
    print(
        f"Wrote {OUTPUT_REL.as_posix()} and metadata: "
        "113/115 scoreable, with p0_q15 and p3_q09 unresolved"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
