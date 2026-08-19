#!/usr/bin/env python3
"""Deterministic Issue #34 headless retrieval benchmark.

The script calls the same ``Searcher`` as the current search backend without
starting FastAPI or the frontend. It never runs corpus analysis or indexing.

Q0 is the official text exactly as stored in ``query``. Q1 appends Hint 1,
Q2 appends Hints 1-2, and QN appends every available hint. Metrics are always
judged at depth 20; Q0 is the primary baseline.

This evaluates supporting-frame retrieval. QA answer text is preserved for
provenance but is not graded as an extracted answer.

Primary retrieval matcher (not contest answer extraction):
  * TKIS intervals: inclusive source-frame membership, no extra slack.
  * TRAKE / QA points: |retrieved_time - gold_time| <= 2.0 seconds using
    each video's rounded FPS (``benchmark/video_rounded_fps.csv``).
A diagnostic official-like point window (±12 source frames) is also recorded.
Legacy ``--point-tolerance-frames`` still forces exact/±N frame matching.
Canonical answers are never rewritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HINT_RE = re.compile(r"^hint_(\d+)$", re.I)
ANSWER_ALT_RE = re.compile(r"^answer_alt_(\d+)$", re.I)
VIDEO_ID_RE = re.compile(r"(?i)(?:L\d+_)?V\d+")
VIDEO_SUFFIXES = (".mp4", ".mkv", ".avi", ".mov", ".webm")
JUDGING_DEPTH = 20
DEFAULT_FPS = 25.0
DEFAULT_RETRIEVAL_POINT_TOLERANCE_SECONDS = 2.0
DEFAULT_OFFICIAL_POINT_TOLERANCE_FRAMES = 12
DEFAULT_FPS_TABLE = Path(__file__).resolve().parent.parent / "benchmark" / "video_rounded_fps.csv"
ALLOWED_TASK_TYPES = {"tkis", "qa", "trake", "vkis"}
ALLOWED_QUERY_MODES = {"text", "media"}
ALLOWED_SCOPES = {"include_current_dataset", "exclude_different_dataset"}
CANONICAL_SCHEMA_VERSION = "issue34-v1"
CANONICAL_HINT_COLUMNS = tuple(f"hint_{number}" for number in range(1, 5))
CANONICAL_ALT_COLUMNS = ("answer_alt_1",)
CANONICAL_IDS = tuple(
    [*(f"set1_q{number:02d}" for number in range(1, 21))]
    + [*(f"p1_q{number:02d}" for number in range(1, 23))]
)
CANONICAL_ID_SET = frozenset(CANONICAL_IDS)
HINT_TO_Q0_IDS = frozenset(
    {
        "set1_q01",
        "set1_q05",
        "set1_q06",
        "set1_q07",
        "set1_q08",
        "set1_q09",
        "set1_q10",
        "set1_q13",
        "set1_q14",
        "set1_q15",
        "set1_q16",
        "set1_q17",
        "set1_q18",
        "set1_q20",
    }
)
MEDIA_QUERY_IDS = frozenset({"set1_q04", "set1_q12"})
MEDIA_SOURCE_URLS = {
    "set1_q04": "https://github.com/user-attachments/assets/03fe118d-8bd4-4075-a25b-5e325a98c714",
    "set1_q12": "https://github.com/user-attachments/assets/bf619563-1fd0-4b98-a36f-270ecea04260",
}
CANONICAL_SOURCES = {
    "Questions.txt": {
        "ids": frozenset(f"set1_q{number:02d}" for number in range(1, 21)),
        "scope": "exclude_different_dataset",
        "url": "https://github.com/user-attachments/files/30332673/Questions.txt",
        "sha256": "a3dc57f20c29a3c32cc53cf9c40dcc6932299cdb0ada3be96d7f63994e2497b0",
    },
    "p1.txt": {
        "ids": frozenset(f"p1_q{number:02d}" for number in range(1, 23)),
        "scope": "include_current_dataset",
        "url": "https://github.com/user-attachments/files/30968345/p1.txt",
        "sha256": "7592b911f4c4d7fb40a3455f81ac0436f53e0ba1cd91425ec170aedd4c6f6096",
    },
}
CANONICAL_CONTENT_FIELDS = (
    "query_id",
    "source",
    "source_question_number",
    "task_type",
    "query_mode",
    "query",
    *CANONICAL_HINT_COLUMNS,
    "media_file",
    "answer",
    *CANONICAL_ALT_COLUMNS,
    "scoreable",
    "evaluation_scope",
    "source_attachment_url",
    "source_attachment_sha256",
    "official_text_mapping",
    "media_source_url",
    "media_source_sha256",
    "media_source_size_bytes",
)
EXPECTED_CANONICAL_CONTENT_SHA256 = "1aba0cf592976a7ec3e2417ff7e9c46628ad2269dc786125fa07c26e0a34470e"
VALIDATED_GROUND_TRUTH_STATES = frozenset({"source_and_ground_truth_validated_current_corpus"})
PROVISIONAL_GROUND_TRUTH_STATES = frozenset(
    {
        "source_text_verified_needs_corpus_validation",
        "source_text_verified_video_only_ground_truth_needs_interval_review",
        "source_text_verified_media_asset_not_bundled",
    }
)
UNSCOREABLE_VALIDATION_STATES = frozenset(
    {
        "source_text_verified_missing_ground_truth",
        "source_text_verified_reversed_interval_needs_review",
    }
)
ALLOWED_VALIDATION_STATES = (
    VALIDATED_GROUND_TRUTH_STATES
    | PROVISIONAL_GROUND_TRUTH_STATES
    | UNSCOREABLE_VALIDATION_STATES
)
REQUIRED_COLUMNS = {
    "query_id",
    "source",
    "source_question_number",
    "task_type",
    "query_mode",
    "query",
    "media_file",
    "answer",
    "scoreable",
    "evaluation_scope",
    "provenance",
    "validation_state",
    "source_attachment_url",
    "source_attachment_sha256",
    "official_text_mapping",
    "media_source_url",
    "media_source_sha256",
    "media_source_size_bytes",
    *CANONICAL_HINT_COLUMNS,
    *CANONICAL_ALT_COLUMNS,
}

CRITICAL_CODE_PATHS = {
    "headless_benchmark": Path(__file__).resolve(),
    "searcher": ROOT / "aic51" / "packages" / "search" / "searcher.py",
}
RUNTIME_PACKAGES = ("aic51", "torch", "open-clip-torch", "transformers", "pymilvus", "numpy")


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def raw_text(value: Any) -> str:
    """Return an official text field without trimming or newline rewriting."""
    return "" if value is None else str(value)


def as_bool(value: Any, default: bool = True) -> bool:
    text = clean(value).lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_provenance() -> dict[str, Any]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT.parent,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status_output = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=ROOT.parent,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        status_entries = status_output.splitlines()
        return {
            "sha": sha,
            "dirty": bool(status_entries),
            "status_entries": status_entries,
            "status_sha256": hashlib.sha256(status_output.encode("utf-8")).hexdigest(),
        }
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {
            "sha": None,
            "dirty": None,
            "status_entries": None,
            "status_sha256": None,
        }


def critical_code_hashes() -> dict[str, dict[str, str]]:
    hashes: dict[str, dict[str, str]] = {}
    for name, path in CRITICAL_CODE_PATHS.items():
        if not path.is_file():
            raise ValueError(f"critical benchmark code is missing: {path}")
        hashes[name] = {
            "path": str(path),
            "sha256": sha256_file(path),
        }
    return hashes


def runtime_versions() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for package in RUNTIME_PACKAGES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": packages,
    }


def actual_query_encoder_devices(searcher: Any, features: list[str]) -> dict[str, str]:
    devices: dict[str, str] = {}
    feature_models = getattr(searcher, "_features", {})
    extractors = getattr(searcher, "_extractors", {})
    for feature in features:
        model_name = feature_models.get(feature)
        extractor_entry = extractors.get(model_name, {}) if model_name is not None else {}
        extractor = extractor_entry.get("feature_extractor")
        device = getattr(extractor, "_device", None)
        if model_name is None or extractor is None or device is None:
            raise ValueError(f"cannot determine actual query-encoder device for feature {feature!r}")
        devices[feature] = str(device)
    return devices


def expected_text_mapping(query_id: str) -> str:
    if query_id in HINT_TO_Q0_IDS:
        return "official_hint_1_to_q0_then_remaining_hints_in_order"
    if query_id in MEDIA_QUERY_IDS:
        return "official_media_query_attachment"
    return "official_question_body_to_q0"


def expected_source_record(query_id: str) -> dict[str, str]:
    if query_id.startswith("set1_q"):
        source = "Questions.txt"
    elif query_id.startswith("p1_q"):
        source = "p1.txt"
    else:
        raise ValueError(f"unknown canonical query_id: {query_id}")
    number = str(int(query_id.rsplit("q", 1)[1]))
    source_spec = CANONICAL_SOURCES[source]
    return {
        "source": source,
        "source_question_number": number,
        "evaluation_scope": source_spec["scope"],
        "source_attachment_url": source_spec["url"],
        "source_attachment_sha256": source_spec["sha256"],
        "official_text_mapping": expected_text_mapping(query_id),
        "media_source_url": MEDIA_SOURCE_URLS.get(query_id, ""),
        "media_source_sha256": "",
        "media_source_size_bytes": "",
    }


def _normalized_content_value(value: Any) -> str:
    return raw_text(value).replace("\r\n", "\n").replace("\r", "\n")


def canonical_content_sha256(path: Path) -> str:
    """Hash only immutable Issue #34 content, independent of CSV row order."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if not reader.fieldnames:
            raise ValueError("CSV has no header")
        reader.fieldnames = [name.lstrip("\ufeff").strip() for name in reader.fieldnames]
        missing = sorted(set(CANONICAL_CONTENT_FIELDS) - set(reader.fieldnames))
        if missing:
            raise ValueError(f"CSV is missing canonical content columns: {missing}")
        rows: dict[str, dict[str, Any]] = {}
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"CSV row {row_number} has extra unheaded fields: {row[None]!r}")
            query_id = clean(row["query_id"])
            if query_id in rows:
                raise ValueError(f"duplicate query_id: {query_id}")
            rows[query_id] = row

    ordered_ids = [query_id for query_id in CANONICAL_IDS if query_id in rows]
    unknown = sorted(set(rows) - CANONICAL_ID_SET)
    if unknown:
        raise ValueError(f"unknown Issue #34 query IDs: {unknown}")
    payload = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "fields": list(CANONICAL_CONTENT_FIELDS),
        "rows": [
            [_normalized_content_value(rows[query_id][field]) for field in CANONICAL_CONTENT_FIELDS]
            for query_id in ordered_ids
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_video_id(value: Any) -> str:
    text = Path(clean(value)).name.lower()
    for suffix in VIDEO_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    matches = VIDEO_ID_RE.findall(text)
    return matches[-1].lower() if matches else text


def parse_answer_string(raw: str, task_type: str, query_id: str) -> list[dict[str, Any]]:
    """Parse one official key without silently weakening malformed syntax."""
    raw = clean(raw)
    if not raw:
        return []

    matches = list(VIDEO_ID_RE.finditer(raw))
    if not matches:
        raise ValueError(f"{query_id}: cannot find video id in answer {raw!r}")
    vm = matches[-1]
    video_id = vm.group(0)
    suffix = raw[vm.end() :].strip()
    prefix = raw[: vm.start()].strip("- ")

    interval = re.fullmatch(r"-\s*(\d+)\s*(?:->|→|to|–|—)\s*(\d+)", suffix, re.I)
    if interval:
        start, end = map(int, interval.groups())
        if start > end:
            raise ValueError(
                f"{query_id}: reversed interval {start} -> {end}; validate official endpoint semantics before scoring"
            )
        return [{"video_id": video_id, "kind": "interval", "start": start, "end": end}]

    points = re.fullmatch(r"-\s*(\d+(?:\s*,\s*\d+)+)", suffix)
    if points:
        return [
            {"video_id": video_id, "kind": "point", "frame": int(point.strip())}
            for point in points.group(1).split(",")
        ]

    point_text = re.fullmatch(r"-\s*(\d+)\s*-\s*(\S(?:.*\S)?)", suffix, re.S)
    if point_text:
        return [{
            "video_id": video_id,
            "kind": "point",
            "frame": int(point_text.group(1)),
            "answer_text": point_text.group(2),
        }]

    point = re.fullmatch(r"-\s*(\d+)", suffix)
    if point:
        return [{"video_id": video_id, "kind": "point", "frame": int(point.group(1))}]

    if not suffix:
        target = {"video_id": video_id, "kind": "video"}
        if task_type == "qa":
            answer_text = re.sub(r"(?i)^QA[-\s]*", "", prefix).strip("- ")
            if answer_text:
                target["answer_text"] = answer_text
        return [target]

    raise ValueError(f"{query_id}: unrecognized answer suffix in {raw!r}")


def _numbered_columns(fieldnames: list[str], regex: re.Pattern[str], label: str) -> list[tuple[int, str]]:
    numbered = sorted(
        ((int(match.group(1)), name) for name in fieldnames if (match := regex.fullmatch(name.strip()))),
        key=lambda item: item[0],
    )
    numbers = [number for number, _ in numbered]
    if numbers and numbers != list(range(1, max(numbers) + 1)):
        raise ValueError(f"{label} columns must be contiguous from 1; got {numbers}")
    return numbered


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if not reader.fieldnames:
            raise ValueError("CSV has no header")
        reader.fieldnames = [name.lstrip("\ufeff").strip() for name in reader.fieldnames]
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames))
        if missing:
            raise ValueError(f"CSV is missing required columns: {missing}")

        hint_cols = _numbered_columns(reader.fieldnames, HINT_RE, "hint")
        alt_cols = _numbered_columns(reader.fieldnames, ANSWER_ALT_RE, "answer_alt")
        if tuple(number for number, _ in hint_cols) != tuple(range(1, len(CANONICAL_HINT_COLUMNS) + 1)):
            raise ValueError(f"Issue #34 requires exactly {list(CANONICAL_HINT_COLUMNS)}")
        if tuple(number for number, _ in alt_cols) != tuple(range(1, len(CANONICAL_ALT_COLUMNS) + 1)):
            raise ValueError(f"Issue #34 requires exactly {list(CANONICAL_ALT_COLUMNS)}")
        cases: list[dict[str, Any]] = []
        seen: set[str] = set()

        for row_num, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"CSV row {row_num} has extra unheaded fields: {row[None]!r}")
            qid = clean(row["query_id"])
            if not qid:
                raise ValueError(f"CSV row {row_num}: missing stable query_id")
            if qid in seen:
                raise ValueError(f"duplicate query_id: {qid}")
            seen.add(qid)

            source = clean(row["source"])
            source_number = clean(row["source_question_number"])
            task_type = clean(row["task_type"]).lower()
            query_mode = clean(row["query_mode"]).lower()
            evaluation_scope = clean(row["evaluation_scope"])
            provenance = clean(row["provenance"])
            validation_state = clean(row["validation_state"])
            source_attachment_url = clean(row["source_attachment_url"])
            source_attachment_sha256 = clean(row["source_attachment_sha256"])
            official_text_mapping = clean(row["official_text_mapping"])
            media_source_url = clean(row["media_source_url"])
            media_source_sha256 = clean(row["media_source_sha256"])
            media_source_size_bytes = clean(row["media_source_size_bytes"])
            if not source or not source_number or not provenance or not validation_state:
                raise ValueError(f"{qid}: source number, provenance, and validation_state are required")
            if task_type not in ALLOWED_TASK_TYPES:
                raise ValueError(f"{qid}: invalid task_type {task_type!r}")
            if query_mode not in ALLOWED_QUERY_MODES:
                raise ValueError(f"{qid}: invalid query_mode {query_mode!r}")
            if evaluation_scope not in ALLOWED_SCOPES:
                raise ValueError(f"{qid}: invalid evaluation_scope {evaluation_scope!r}")
            if validation_state not in ALLOWED_VALIDATION_STATES:
                raise ValueError(f"{qid}: invalid validation_state {validation_state!r}")

            query = raw_text(row["query"])
            media_file = clean(row["media_file"])
            if query_mode == "text" and not clean(query):
                raise ValueError(f"{qid}: missing official Q0 text")
            if query_mode == "media" and not media_file:
                raise ValueError(f"{qid}: media query requires media_file")

            hints: list[str] = []
            hint_values: list[str] = []
            saw_blank = False
            for _, name in hint_cols:
                value = raw_text(row[name])
                hint_values.append(value)
                if not clean(value):
                    saw_blank = True
                elif saw_blank:
                    raise ValueError(f"{qid}: non-contiguous hint values")
                else:
                    hints.append(value)

            main_answer = raw_text(row["answer"])
            alt_values = [raw_text(row[name]) for _, name in alt_cols]
            answer_strings = [main_answer] if clean(main_answer) else []
            answer_strings.extend(value for value in alt_values if clean(value))
            scoreable = as_bool(row["scoreable"], default=bool(answer_strings))
            if scoreable and not answer_strings:
                raise ValueError(f"{qid}: scoreable=true but no answer is present")
            if scoreable and validation_state in UNSCOREABLE_VALIDATION_STATES:
                raise ValueError(f"{qid}: validation_state {validation_state!r} requires scoreable=false")
            if not scoreable and validation_state not in UNSCOREABLE_VALIDATION_STATES:
                raise ValueError(f"{qid}: scoreable=false is inconsistent with validation_state {validation_state!r}")

            accepted_groups = (
                [parse_answer_string(answer, task_type, qid) for answer in answer_strings]
                if scoreable
                else []
            )
            target_mode = "events" if task_type == "trake" else "any"
            if target_mode == "events" and len(accepted_groups) > 1:
                raise ValueError(f"{qid}: alternative TRAKE event groups require explicit target-set semantics")

            cases.append({
                "query_id": qid,
                "source": source,
                "source_question_number": source_number,
                "task_type": task_type,
                "query_mode": query_mode,
                "query": query,
                "hints": hints,
                "hint_values": hint_values,
                "media_file": media_file,
                "scoreable": scoreable,
                "answer_strings": answer_strings,
                "main_answer": main_answer,
                "answer_alt_values": alt_values,
                "accepted_groups": accepted_groups,
                "target_mode": target_mode,
                "notes": clean(row.get("notes")),
                "evaluation_scope": evaluation_scope,
                "provenance": provenance,
                "validation_state": validation_state,
                "source_attachment_url": source_attachment_url,
                "source_attachment_sha256": source_attachment_sha256,
                "official_text_mapping": official_text_mapping,
                "media_source_url": media_source_url,
                "media_source_sha256": media_source_sha256,
                "media_source_size_bytes": media_source_size_bytes,
            })
    return cases


def validate_canonical_issue34_inventory(
    cases: list[dict[str, Any]], allow_incomplete: bool
) -> dict[str, Any]:
    actual_ids = {case["query_id"] for case in cases}
    unknown = sorted(actual_ids - CANONICAL_ID_SET)
    missing = sorted(CANONICAL_ID_SET - actual_ids)
    if unknown:
        raise ValueError(f"unknown Issue #34 query IDs: {unknown}")
    if missing and not allow_incomplete:
        raise ValueError(
            f"Issue #34 inventory is missing {len(missing)} canonical IDs: {missing}. "
            "Use --allow-incomplete only for an intentional dry-run audit."
        )

    for case in cases:
        expected = expected_source_record(case["query_id"])
        for field, expected_value in expected.items():
            if case[field] != expected_value:
                raise ValueError(
                    f"{case['query_id']}: canonical {field} must be {expected_value!r}, got {case[field]!r}"
                )

    source_counts = {
        source: sum(case["source"] == source for case in cases)
        for source in sorted(CANONICAL_SOURCES)
    }
    return {
        "complete": not missing and not unknown,
        "missing_query_ids": missing,
        "source_counts": source_counts,
    }


def ground_truth_tier(case: dict[str, Any]) -> str:
    if not case["scoreable"]:
        return "unscoreable"
    if case["validation_state"] in VALIDATED_GROUND_TRUTH_STATES:
        return "validated"
    return "provisional"


def provisional_scoreable_text_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        case
        for case in cases
        if case["query_mode"] == "text" and ground_truth_tier(case) == "provisional"
    ]


def validate_run_readiness(cases: list[dict[str, Any]], allow_provisional: bool) -> list[dict[str, Any]]:
    provisional = provisional_scoreable_text_cases(cases)
    if provisional and not allow_provisional:
        details = ", ".join(
            f"{case['query_id']}={case['validation_state']}" for case in provisional
        )
        raise ValueError(
            "selected scoreable ground truth is not validated against the current corpus; "
            f"refusing an authoritative run: {details}. Use --allow-provisional-ground-truth "
            "only for explicitly provisional results."
        )
    return provisional


def get_field(obj: Any, key: str, default: Any = None) -> Any:
    getter = getattr(obj, "get", None)
    if getter is not None:
        return getter(key, default)
    try:
        return obj[key]
    except (KeyError, TypeError):
        return default


def frame_number(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    text = clean(value)
    return int(text) if re.fullmatch(r"\d+", text) else None


def unpack_result(record: Any) -> tuple[str, int, list[int], Any]:
    entity = get_field(record, "entity")
    if entity is None:
        raise ValueError("retrieval result is missing entity")
    raw_id = clean(get_field(entity, "frame_id"))
    if "#" not in raw_id:
        raise ValueError(f"retrieval result has invalid entity.frame_id {raw_id!r}; expected '<video>#<frame>'")
    video, raw_frame = raw_id.rsplit("#", 1)
    frame = frame_number(raw_frame)
    if not video or frame is None:
        raise ValueError(f"retrieval result has invalid entity.frame_id {raw_id!r}")
    raw_timeline = get_field(record, "time_line", None)
    if raw_timeline is None:
        timeline = [frame]
    elif not isinstance(raw_timeline, (list, tuple)):
        raise ValueError("retrieval result time_line must be a list of frame integers")
    else:
        timeline = [frame_number(value) for value in raw_timeline]
        if any(value is None for value in timeline):
            raise ValueError(f"retrieval result has invalid time_line {raw_timeline!r}")
    return video, frame, [int(value) for value in timeline], entity


def stable_result_key(record: Any) -> tuple[float, str, int, tuple[int, ...]]:
    video, frame, timeline, _ = unpack_result(record)
    score = get_field(record, "distance")
    try:
        numeric_score = float(score)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"retrieval result has invalid distance {score!r}") from exc
    if not math.isfinite(numeric_score):
        raise ValueError(f"retrieval result has non-finite distance {score!r}")
    return (-numeric_score, normalize_video_id(video), frame, tuple(timeline))


def normalize_results(results: list[Any], requested_top_k: int) -> list[Any]:
    """Validate and tie-break candidates, then retain the requested retrieval depth."""
    return sorted(list(results), key=stable_result_key)[:requested_top_k]


@dataclass
class MatchConfig:
    """Task-aware retrieval matcher.

    TKIS intervals stay inclusive source-frame membership.
    TRAKE / QA points are timestamp-based: |Δt| <= retrieval_point_tolerance_seconds
    using each video's FPS. A separate official-like diagnostic uses ±N source frames.

    Passing an int into ``metrics_for_results`` still means legacy exact/±N *frame*
    matching, so existing unit tests stay bit-identical.
    """

    fps_by_video: dict[str, float] = field(default_factory=dict)
    default_fps: float = DEFAULT_FPS
    retrieval_point_tolerance_seconds: float = DEFAULT_RETRIEVAL_POINT_TOLERANCE_SECONDS
    official_point_tolerance_frames: int = DEFAULT_OFFICIAL_POINT_TOLERANCE_FRAMES
    legacy_point_tolerance_frames: int | None = None

    def fps_for(self, video_id: str) -> float:
        raw = video_id
        norm = normalize_video_id(video_id)
        if raw in self.fps_by_video:
            return float(self.fps_by_video[raw])
        if norm in self.fps_by_video:
            return float(self.fps_by_video[norm])
        return float(self.default_fps)


def default_match_config() -> MatchConfig:
    table = DEFAULT_FPS_TABLE if DEFAULT_FPS_TABLE.exists() else None
    fps = load_fps_table(table) if table is not None else {}
    return MatchConfig(fps_by_video=fps)


def load_fps_table(path: Path | None) -> dict[str, float]:
    if path is None or not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = csv.DictReader(fh)
        out: dict[str, float] = {}
        for row in rows:
            video = (row.get("video_id") or row.get("media_id") or "").strip()
            raw = row.get("rounded_fps") or row.get("fps") or ""
            if not video or not raw:
                continue
            try:
                fps = float(raw)
            except ValueError:
                continue
            if fps > 0:
                out[video] = fps
                out[normalize_video_id(video)] = fps
        return out


def coerce_match_config(value: MatchConfig | int | None) -> MatchConfig:
    if value is None:
        return default_match_config()
    if isinstance(value, MatchConfig):
        return value
    if isinstance(value, int):
        if value < 0:
            raise ValueError("point tolerance frames must be >= 0")
        return MatchConfig(legacy_point_tolerance_frames=value)
    raise TypeError(f"match config must be MatchConfig, int, or None; got {type(value)!r}")


def match_config_from_args(args: argparse.Namespace) -> MatchConfig:
    fps_path = getattr(args, "fps_csv", None)
    fps = load_fps_table(Path(fps_path) if fps_path else DEFAULT_FPS_TABLE)
    legacy = getattr(args, "point_tolerance_frames", None)
    seconds = getattr(args, "point_tolerance_seconds", DEFAULT_RETRIEVAL_POINT_TOLERANCE_SECONDS)
    official = getattr(args, "official_point_tolerance_frames", DEFAULT_OFFICIAL_POINT_TOLERANCE_FRAMES)
    if legacy is not None:
        return MatchConfig(
            fps_by_video=fps,
            legacy_point_tolerance_frames=int(legacy),
            retrieval_point_tolerance_seconds=float(seconds),
            official_point_tolerance_frames=int(official),
        )
    return MatchConfig(
        fps_by_video=fps,
        retrieval_point_tolerance_seconds=float(seconds),
        official_point_tolerance_frames=int(official),
    )


def _point_delta(frame: int, gold_frame: int) -> int:
    return abs(int(frame) - int(gold_frame))


def point_matches(
    frame: int,
    target: dict[str, Any],
    video_id: str,
    config: MatchConfig,
    *,
    mode: str,
) -> bool:
    gold = int(target["frame"])
    delta = _point_delta(frame, gold)
    if mode == "official":
        return delta <= config.official_point_tolerance_frames
    if config.legacy_point_tolerance_frames is not None:
        return delta <= config.legacy_point_tolerance_frames
    fps = config.fps_for(video_id)
    return (delta / fps) <= config.retrieval_point_tolerance_seconds


def target_matches(
    record: Any,
    target: dict[str, Any],
    point_tolerance: MatchConfig | int,
    *,
    mode: str = "retrieval",
) -> bool:
    config = coerce_match_config(point_tolerance)
    video, frame, timeline, _ = unpack_result(record)
    if normalize_video_id(video) != normalize_video_id(target["video_id"]):
        return False
    if target["kind"] == "video":
        return True
    frames = timeline or [frame]
    if target["kind"] == "interval":
        return any(target["start"] <= value <= target["end"] for value in frames)
    if target["kind"] == "point":
        return any(point_matches(value, target, video, config, mode=mode) for value in frames)
    raise ValueError(f"unknown target kind: {target['kind']}")


def group_match_ranks(
    results: list[Any],
    group: list[dict[str, Any]],
    point_tolerance: MatchConfig | int,
    *,
    mode: str = "retrieval",
) -> list[int | None]:
    return [
        next(
            (
                rank
                for rank, record in enumerate(results, 1)
                if target_matches(record, target, point_tolerance, mode=mode)
            ),
            None,
        )
        for target in group
    ]


def _nearest_gold(results: list[Any], case: dict[str, Any], config: MatchConfig) -> dict[str, Any] | None:
    nearest = None
    targets = [target for group in case.get("accepted_groups") or [] for target in group]
    for rank, record in enumerate(results, 1):
        try:
            video, frame, timeline, _ = unpack_result(record)
        except ValueError:
            continue
        frames = timeline or [frame]
        fps = config.fps_for(video)
        for value in frames:
            for target in targets:
                if normalize_video_id(video) != normalize_video_id(target["video_id"]):
                    continue
                if target["kind"] == "video":
                    delta_frames, delta_seconds = 0, 0.0
                elif target["kind"] == "interval":
                    if target["start"] <= value <= target["end"]:
                        delta_frames, delta_seconds = 0, 0.0
                    else:
                        delta_frames = min(abs(value - target["start"]), abs(value - target["end"]))
                        delta_seconds = delta_frames / fps
                elif target["kind"] == "point":
                    delta_frames = _point_delta(value, target["frame"])
                    delta_seconds = delta_frames / fps
                else:
                    continue
                cand = {
                    "rank": rank,
                    "video_id": video,
                    "frame": int(value),
                    "target_kind": target["kind"],
                    "gold": target.get("frame") if target["kind"] == "point" else [target.get("start"), target.get("end")],
                    "fps": fps,
                    "nearest_gold_delta_frames": int(delta_frames),
                    "nearest_gold_delta_seconds": float(delta_seconds),
                }
                if nearest is None or cand["nearest_gold_delta_seconds"] < nearest["nearest_gold_delta_seconds"]:
                    nearest = cand
    return nearest


def _empty_metrics() -> dict[str, Any]:
    return {
        "first_correct_rank": None,
        "reciprocal_rank": None,
        "recall_at_1": None,
        "recall_at_5": None,
        "recall_at_10": None,
        "recall_at_20": None,
        "no_hit_within_20": None,
        "all_targets_hit_at_20": None,
        "target_ranks": [],
    }


def _tolerance_diagnostics(judged: list[Any], case: dict[str, Any], config: MatchConfig) -> dict[str, Any]:
    official_groups = [
        group_match_ranks(judged, group, config, mode="official") for group in case["accepted_groups"]
    ]
    official_flat = [rank for ranks in official_groups for rank in ranks]
    official_first = min((rank for rank in official_flat if rank is not None), default=None)
    nearest = _nearest_gold(judged, case, config)
    return {
        "official_tolerance_hit": official_first is not None and official_first <= JUDGING_DEPTH,
        "official_first_correct_rank": official_first,
        "official_target_ranks": official_groups[0] if case.get("target_mode") == "events" else official_groups,
        "nearest_gold_delta_frames": None if nearest is None else nearest["nearest_gold_delta_frames"],
        "nearest_gold_delta_seconds": None if nearest is None else nearest["nearest_gold_delta_seconds"],
        "nearest_gold": nearest,
        "match_contract": {
            "primary": (
                "legacy_point_frames"
                if config.legacy_point_tolerance_frames is not None
                else "timestamp_seconds"
            ),
            "retrieval_point_tolerance_seconds": config.retrieval_point_tolerance_seconds,
            "official_point_tolerance_frames": config.official_point_tolerance_frames,
            "legacy_point_tolerance_frames": config.legacy_point_tolerance_frames,
            "tkis_intervals": "inclusive source-frame membership",
        },
    }


def metrics_for_results(
    results: list[Any],
    case: dict[str, Any],
    point_tolerance: MatchConfig | int | None,
) -> dict[str, Any]:
    config = coerce_match_config(point_tolerance)
    if not case["scoreable"]:
        return _empty_metrics()
    judged = list(results)[:JUDGING_DEPTH]
    group_ranks = [group_match_ranks(judged, group, config, mode="retrieval") for group in case["accepted_groups"]]
    if not group_ranks:
        raise ValueError(f"{case['query_id']}: no parsed ground-truth targets")

    flat = [rank for ranks in group_ranks for rank in ranks]
    first = min((rank for rank in flat if rank is not None), default=None)
    reciprocal_rank = 0.0 if first is None else 1.0 / first
    diagnostics = _tolerance_diagnostics(judged, case, config)
    diagnostics["retrieval_hit_2s"] = first is not None and first <= JUDGING_DEPTH

    if case["target_mode"] == "events":
        ranks = group_ranks[0]

        video_targets = [
            {"kind": "video", "video_id": target["video_id"]}
            for group in case["accepted_groups"]
            for target in group
        ]
        video_ranks = group_match_ranks(judged, video_targets, config, mode="retrieval")
        first_video = min((rank for rank in video_ranks if rank is not None), default=None)

        def recall(k: int) -> float:
            return sum(rank is not None and rank <= k for rank in ranks) / len(ranks)

        return {
            "first_correct_rank": first,
            "reciprocal_rank": reciprocal_rank,
            "recall_at_1": recall(1),
            "recall_at_5": recall(5),
            "recall_at_10": recall(10),
            "recall_at_20": recall(20),
            "no_hit_within_20": first is None,
            "all_targets_hit_at_20": all(rank is not None and rank <= 20 for rank in ranks),
            "target_ranks": ranks,
            "video_retrieval": {
                "first_correct_video_rank": first_video,
                "video_recall_at_1": float(first_video is not None and first_video <= 1),
                "video_recall_at_5": float(first_video is not None and first_video <= 5),
                "video_recall_at_10": float(first_video is not None and first_video <= 10),
                "video_recall_at_20": float(first_video is not None and first_video <= 20),
                "video_mrr_at_20": 0.0 if first_video is None else 1.0 / first_video,
            },
            "event_candidate_coverage": {
                "event_candidate_recall_at_1": recall(1),
                "event_candidate_recall_at_5": recall(5),
                "event_candidate_recall_at_10": recall(10),
                "event_candidate_recall_at_20": recall(20),
                "all_events_candidate_hit_at_20": all(rank is not None and rank <= 20 for rank in ranks),
            },
            "localization_status": "not_implemented",
            "end_to_end_trake_success": None,
            "frame_localization_error": None,
            **diagnostics,
        }

    def hit(k: int) -> float:
        return 1.0 if any(rank is not None and rank <= k for rank in flat) else 0.0

    metrics = {
        "first_correct_rank": first,
        "reciprocal_rank": reciprocal_rank,
        "recall_at_1": hit(1),
        "recall_at_5": hit(5),
        "recall_at_10": hit(10),
        "recall_at_20": hit(20),
        "no_hit_within_20": first is None,
        "all_targets_hit_at_20": hit(20) == 1.0,
        "target_ranks": group_ranks,
        **diagnostics,
    }
    if case.get("task_type") == "qa":
        metrics["evidence_retrieval"] = {
            "evidence_recall_at_1": metrics["recall_at_1"],
            "evidence_recall_at_5": metrics["recall_at_5"],
            "evidence_recall_at_10": metrics["recall_at_10"],
            "evidence_recall_at_20": metrics["recall_at_20"],
            "first_evidence_rank": first,
            "evidence_no_hit_within_20": metrics["no_hit_within_20"],
        }
    return metrics


def serialized_to_searcher_record(item: dict[str, Any]) -> dict[str, Any]:
    video = item.get("video_id") or ""
    frame = item.get("frame_id")
    timeline = item.get("time_line") or ([frame] if frame is not None else [])
    return {
        "entity": {
            "frame_id": f"{video}#{frame}",
            "ocr": item.get("ocr", ""),
            "asr": item.get("asr", ""),
        },
        "distance": float(item["distance"]) if item.get("distance") is not None else 0.0,
        "time_line": timeline,
        "scores": item.get("scores"),
    }


def case_from_stored_record(record: dict[str, Any]) -> dict[str, Any]:
    groups = []
    for raw in record.get("answers") or []:
        parsed = parse_answer_string(raw, record["task_type"], record["query_id"])
        if parsed:
            groups.append(parsed)
    return {
        "query_id": record["query_id"],
        "task_type": record["task_type"],
        "target_mode": record.get("target_mode") or "any",
        "scoreable": bool(groups),
        "accepted_groups": groups,
    }


def rescore_stored_record(record: dict[str, Any], config: MatchConfig | None = None) -> dict[str, Any]:
    """Re-judge stored top_results without re-running retrieval."""
    config = config or default_match_config()
    updated = dict(record)
    if record.get("status", "").startswith("unsupported") or record.get("query_mode") == "media":
        return updated
    case = case_from_stored_record(record)
    if not case["scoreable"]:
        return updated
    results = [serialized_to_searcher_record(item) for item in record.get("top_results") or []]
    metrics = metrics_for_results(results, case, config)
    updated.update(metrics)
    updated["top_results"] = [
        serialize_result(item, rank, case, config)
        for rank, item in enumerate(results[:JUDGING_DEPTH], 1)
    ]
    updated["rescored_with"] = metrics["match_contract"]
    return updated


def serialize_result(record: Any, rank: int, case: dict[str, Any], point_tolerance: MatchConfig | int) -> dict[str, Any]:
    video, frame, timeline, entity = unpack_result(record)
    matches_any = (
        any(
            target_matches(record, target, point_tolerance, mode="retrieval")
            for group in case["accepted_groups"]
            for target in group
        )
        if case["scoreable"]
        else None
    )
    return {
        "rank": rank,
        "video_id": video,
        "frame_id": frame,
        "time_line": timeline,
        "distance": get_field(record, "distance"),
        "scores": get_field(record, "scores"),
        "ocr": get_field(entity, "ocr", ""),
        "asr": get_field(entity, "asr", ""),
        "matches_ground_truth": matches_any,
    }


def choose_features(searcher: Any, requested: str) -> list[str]:
    selected = [name.strip() for name in requested.split(",") if name.strip()]
    if not selected:
        raise ValueError("--target-features is required; benchmark configuration must be explicit")
    available = list(searcher.target_features)
    unknown = [name for name in selected if name not in available]
    if unknown:
        raise ValueError(f"unknown target features {unknown}; available={available}")
    return selected


def preflight_collection(config_path: Path) -> dict[str, Any]:
    """Abort before Searcher can silently create a missing empty collection."""
    if not config_path.exists():
        raise ValueError(f"workspace config not found: {config_path}")
    from yaml import safe_load
    from pymilvus import MilvusClient

    config = safe_load(config_path.read_text(encoding="utf-8")) or {}
    collection = config.get("backends", {}).get("search", {}).get("collection") or "milvus"
    client = MilvusClient()
    try:
        if not client.has_collection(collection):
            raise ValueError(f"configured Milvus collection {collection!r} does not exist; refusing to create it")
        count_result = client.query(collection, output_fields=["count(*)"])
        row_count = int(count_result[0]["count(*)"]) if count_result else 0
        if row_count <= 0:
            raise ValueError(f"configured Milvus collection {collection!r} is empty; refusing benchmark run")
        return {
            "collection": collection,
            "row_count": row_count,
            "schema": client.describe_collection(collection),
            "indexes": client.list_indexes(collection),
        }
    finally:
        client.close()


def run_text_variant(
    searcher: Any,
    case: dict[str, Any],
    hint_count: int,
    args: argparse.Namespace,
    features: list[str],
) -> dict[str, Any]:
    query = "\n".join([case["query"], *case["hints"][:hint_count]])
    started = time.perf_counter()
    raw = searcher.search_multimodal(
        query,
        0,
        args.top_k,
        features,
        nprobe=args.nprobe,
        temporal_k=args.temporal_k,
        ocr_weight=args.ocr_weight,
        asr_weight=args.asr_weight,
        max_interval=args.max_interval,
        selected=None,
        auto_translate=args.auto_translate,
        en_to_vi_translate=args.en_to_vi_translate,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    results = normalize_results(list(raw.get("results", [])), args.top_k)
    match_config = getattr(args, "match_config", None) or match_config_from_args(args)
    metrics = metrics_for_results(results, case, match_config)
    all_hints = hint_count == len(case["hints"])
    tier = ground_truth_tier(case)
    if tier == "validated":
        status = "scored_validated"
    elif tier == "provisional":
        status = "scored_provisional"
    else:
        status = "unscored_missing_or_unvalidated_ground_truth"
    return {
        "query_id": case["query_id"],
        "source": case["source"],
        "task_type": case["task_type"],
        "capability_evaluated": {
            "qa": "evidence_retrieval",
            "trake": "video_retrieval_and_event_candidate_coverage",
            "tkis": "retrieval",
        }.get(case["task_type"], "retrieval"),
        "evaluation_scope": case["evaluation_scope"],
        "validation_state": case["validation_state"],
        "query_mode": "text",
        "status": status,
        "ground_truth_tier": tier,
        "condition": f"Q{hint_count}",
        "is_primary_baseline": hint_count == 0,
        "is_all_hints": all_hints,
        "hint_count": hint_count,
        "query_text": query,
        "hints_used": case["hints"][:hint_count],
        "answers": case["answer_strings"],
        "target_mode": case["target_mode"],
        **metrics,
        "latency_ms": round(latency_ms, 3),
        "top_results": [
            serialize_result(record, rank, case, match_config)
            for rank, record in enumerate(results[:JUDGING_DEPTH], 1)
        ],
    }


def unsupported_record(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_id": case["query_id"],
        "source": case["source"],
        "task_type": case["task_type"],
        "capability_evaluated": "unsupported",
        "evaluation_scope": case["evaluation_scope"],
        "validation_state": case["validation_state"],
        "query_mode": case["query_mode"],
        "status": "unsupported_external_media_query",
        "condition": "Q0",
        "is_primary_baseline": True,
        "is_all_hints": True,
        "hint_count": 0,
        "query_text": "",
        "media_file": case["media_file"],
        "answers": case["answer_strings"],
        **_empty_metrics(),
        "latency_ms": None,
        "top_results": [],
    }


def aggregate(group: list[dict[str, Any]]) -> dict[str, Any]:
    ranks = [record["first_correct_rank"] for record in group if record["first_correct_rank"] is not None]
    return {
        "scored_variants": len(group),
        "mean_recall_at_1": round(sum(record["recall_at_1"] for record in group) / len(group), 6),
        "mean_recall_at_5": round(sum(record["recall_at_5"] for record in group) / len(group), 6),
        "mean_recall_at_10": round(sum(record["recall_at_10"] for record in group) / len(group), 6),
        "mean_recall_at_20": round(sum(record["recall_at_20"] for record in group) / len(group), 6),
        "mrr_at_20": round(sum(record["reciprocal_rank"] for record in group) / len(group), 6),
        "median_first_correct_rank_within_20": median(ranks) if ranks else None,
        "no_hit_within_20_count": sum(record["no_hit_within_20"] for record in group),
        "mean_latency_ms": round(sum(record["latency_ms"] for record in group) / len(group), 3),
    }


def _task_aggregate(records: list[dict[str, Any]], task_type: str) -> dict[str, Any] | None:
    scoreable = [
        record for record in records
        if record.get("task_type") == task_type and record.get("status", "").startswith("scored_")
    ]
    if not scoreable:
        return None
    if task_type == "trake":
        video = [record["video_retrieval"] for record in scoreable]
        events = [record["event_candidate_coverage"] for record in scoreable]
        return {
            "cases": len(scoreable),
            "video_retrieval": {
                key: round(sum(item[key] for item in video) / len(video), 6)
                for key in ("video_recall_at_1", "video_recall_at_5", "video_recall_at_10", "video_recall_at_20", "video_mrr_at_20")
            },
            "event_candidate_coverage": {
                key: round(sum(item[key] for item in events) / len(events), 6)
                for key in ("event_candidate_recall_at_1", "event_candidate_recall_at_5", "event_candidate_recall_at_10", "event_candidate_recall_at_20")
            } | {"all_events_candidate_hit_at_20": sum(item["all_events_candidate_hit_at_20"] for item in events)},
            "localization_status": "not_implemented",
            "end_to_end_trake_success": None,
            "frame_localization_error": None,
        }
    metrics = aggregate(scoreable)
    if task_type == "qa":
        return {
            "scoreable_cases": len(scoreable),
            "evidence_retrieval": {
                "evidence_recall_at_1": metrics["mean_recall_at_1"],
                "evidence_recall_at_5": metrics["mean_recall_at_5"],
                "evidence_recall_at_10": metrics["mean_recall_at_10"],
                "evidence_recall_at_20": metrics["mean_recall_at_20"],
                "evidence_mrr_at_20": metrics["mrr_at_20"],
                "first_evidence_rank": median(ranks) if (ranks := [r["first_correct_rank"] for r in scoreable if r["first_correct_rank"] is not None]) else None,
                "evidence_no_hit_within_20": metrics["no_hit_within_20_count"],
            },
            "answer_extraction_status": "not_implemented",
            "end_to_end_answer_accuracy": None,
        }
    return metrics


def _metric_partition(records: list[dict[str, Any]], suppress_combined: bool) -> dict[str, Any] | None:
    if not records:
        return None
    by_condition: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_condition.setdefault(record["condition"], []).append(record)
    q0 = [record for record in records if record["is_primary_baseline"]]
    qn = [record for record in records if record["is_all_hints"]]
    by_source: dict[str, Any] = {}
    for source in sorted({record["source"] for record in records}):
        source_records = [record for record in records if record["source"] == source]
        source_q0 = [record for record in source_records if record["is_primary_baseline"]]
        source_qn = [record for record in source_records if record["is_all_hints"]]
        source_conditions: dict[str, list[dict[str, Any]]] = {}
        for record in source_records:
            source_conditions.setdefault(record["condition"], []).append(record)
        by_source[source] = {
            "primary_q0": aggregate(source_q0) if source_q0 else None,
            "all_hints_qn": aggregate(source_qn) if source_qn else None,
            "by_condition": {
                condition: aggregate(group) for condition, group in sorted(source_conditions.items())
            },
        }
    return {
        "primary_q0": None if suppress_combined or not q0 else aggregate(q0),
        "all_hints_qn": None if suppress_combined or not qn else aggregate(qn),
        "by_condition": None if suppress_combined else {
            condition: aggregate(group) for condition, group in sorted(by_condition.items())
        },
        "by_source": by_source,
        "mixed_source_aggregate_suppressed": suppress_combined,
    }


def summarize(records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    validated = [record for record in records if record["status"] == "scored_validated"]
    provisional = [record for record in records if record["status"] == "scored_provisional"]
    selected_sources = {case["source"] for case in cases}
    suppress_combined = len(selected_sources) > 1
    primary_records = [record for record in records if record.get("is_primary_baseline", False)]
    qa_aggregate = _task_aggregate(primary_records, "qa")
    return {
        "reporting": {
            "primary_report": "task_metrics",
            "legacy_reports": ["legacy_mixed_retrieval_diagnostic"],
            "legacy_reports_are_compatibility_only": True,
        },
        "dataset": {
            "questions_loaded": len(cases),
            "included_questions": len(cases),
            "scoreable_questions": sum(case["scoreable"] for case in cases),
            "text_questions": sum(case["query_mode"] == "text" for case in cases),
            "scoreable_text_questions": sum(
                case["query_mode"] == "text" and case["scoreable"] for case in cases
            ),
            "media_questions": sum(case["query_mode"] == "media" for case in cases),
            "unscoreable_questions": [case["query_id"] for case in cases if not case["scoreable"]],
            "unscoreable_reasons": {
                case["query_id"]: "missing official answer ground truth"
                for case in cases
                if case["task_type"] == "qa" and not case["scoreable"]
            },
            "unsupported_media_questions": [
                case["query_id"] for case in cases if case["query_mode"] == "media"
            ],
            "validation_states": sorted({case["validation_state"] for case in cases}),
            "validated_scoreable_text_questions": sum(
                case["query_mode"] == "text" and ground_truth_tier(case) == "validated"
                for case in cases
            ),
            "provisional_scoreable_text_questions": sum(
                case["query_mode"] == "text" and ground_truth_tier(case) == "provisional"
                for case in cases
            ),
        },
        "validated_metrics": _metric_partition(validated, suppress_combined),
        "provisional_metrics": _metric_partition(provisional, suppress_combined),
        "legacy_mixed_retrieval_diagnostic": {
            "validated": _metric_partition(validated, suppress_combined),
            "provisional": _metric_partition(provisional, suppress_combined),
        },
        "task_metrics": {
            "tkis": _task_aggregate(primary_records, "tkis"),
            "qa": {
                "scoreable_cases": sum(case["task_type"] == "qa" and case["scoreable"] for case in cases),
                "unscoreable_cases": [case["query_id"] for case in cases if case["task_type"] == "qa" and not case["scoreable"]],
                "evidence_retrieval": qa_aggregate["evidence_retrieval"] if qa_aggregate else None,
                "answer_extraction_status": "not_implemented",
                "end_to_end_answer_accuracy": None,
            },
            "trake": _task_aggregate(primary_records, "trake"),
        },
        "cohort_note": "Q0 is primary. Q1..QN cohorts contain only questions with that many official hints.",
    }


def validate_numeric_args(args: argparse.Namespace) -> None:
    if args.top_k < JUDGING_DEPTH:
        raise ValueError(f"--top-k must be >= {JUDGING_DEPTH}; all metrics are judged from top-20")
    if getattr(args, "point_tolerance_frames", None) is not None and args.point_tolerance_frames < 0:
        raise ValueError("--point-tolerance-frames must be >= 0")
    if getattr(args, "point_tolerance_seconds", 0) < 0:
        raise ValueError("--point-tolerance-seconds must be >= 0")
    if getattr(args, "official_point_tolerance_frames", 0) < 0:
        raise ValueError("--official-point-tolerance-frames must be >= 0")
    if not (0 <= args.ocr_weight <= 1 and 0 <= args.asr_weight <= 1):
        raise ValueError("OCR/ASR weights must each be within [0, 1]")
    if args.ocr_weight + args.asr_weight > 1:
        raise ValueError("--ocr-weight + --asr-weight must be <= 1; the backend otherwise clamps ASR")


def validate_output_paths(output_path: Path, overwrite: bool) -> Path:
    summary_path = output_path.with_suffix(".summary.json")
    run_path = output_path.with_suffix(".run.json")
    existing = [path for path in (output_path, summary_path, run_path) if path.exists()]
    if existing and not overwrite:
        raise ValueError(
            "refusing to overwrite existing benchmark output: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite-output only after preserving prior evidence."
        )
    return summary_path


def run_metadata_path(output_path: Path) -> Path:
    return output_path.with_suffix(".run.json")


def write_run_metadata(path: Path, metadata: dict[str, Any]) -> None:
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue #34 deterministic headless retrieval benchmark")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmark-results/headless_results.jsonl"))
    parser.add_argument("--top-k", type=int, default=JUDGING_DEPTH)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument(
        "--allow-provisional-ground-truth",
        action="store_true",
        help="Run explicitly provisional scoring when current-corpus ground truth validation is incomplete.",
    )
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help="Replace an existing JSONL/summary pair only after preserving prior evidence.",
    )
    parser.add_argument(
        "--evaluation-scope",
        choices=["current", "all"],
        default="current",
        help="Default runs only rows explicitly marked include_current_dataset.",
    )
    parser.add_argument("--target-features", required=True)
    parser.add_argument("--nprobe", type=int, default=32)
    parser.add_argument("--temporal-k", type=int, default=10000)
    parser.add_argument("--ocr-weight", type=float, default=0.5)
    parser.add_argument("--asr-weight", type=float, default=0.0)
    parser.add_argument("--max-interval", type=int, default=1000)
    parser.add_argument(
        "--point-tolerance-seconds",
        type=float,
        default=DEFAULT_RETRIEVAL_POINT_TOLERANCE_SECONDS,
        help="Primary TRAKE/QA retrieval tolerance in seconds (timestamp via per-video FPS). Default 2.0.",
    )
    parser.add_argument(
        "--official-point-tolerance-frames",
        type=int,
        default=DEFAULT_OFFICIAL_POINT_TOLERANCE_FRAMES,
        help="Diagnostic contest-like point window in source frames. Default 12. Does not replace the 2s retrieval score.",
    )
    parser.add_argument(
        "--point-tolerance-frames",
        type=int,
        default=None,
        help="Legacy primary matcher: exact/±N source frames. If set, overrides --point-tolerance-seconds.",
    )
    parser.add_argument(
        "--fps-csv",
        type=Path,
        default=DEFAULT_FPS_TABLE,
        help="CSV with video_id,rounded_fps used to convert frames to seconds.",
    )
    parser.add_argument("--auto-translate", action="store_true")
    parser.add_argument("--en-to-vi-translate", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate/filter the dataset without loading models or Milvus")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_numeric_args(args)

    inventory = load_cases(args.csv)
    inventory_validation = validate_canonical_issue34_inventory(inventory, args.allow_incomplete)
    content_sha256 = canonical_content_sha256(args.csv)
    if inventory_validation["complete"] and content_sha256 != EXPECTED_CANONICAL_CONTENT_SHA256:
        raise ValueError(
            "canonical Issue #34 immutable content digest mismatch: "
            f"expected {EXPECTED_CANONICAL_CONTENT_SHA256}, got {content_sha256}"
        )
    cases = (
        inventory
        if args.evaluation_scope == "all"
        else [case for case in inventory if case["evaluation_scope"] == "include_current_dataset"]
    )
    excluded = [case["query_id"] for case in inventory if case not in cases]
    print(
        f"Inventory: {len(inventory)} official items; selected {len(cases)} for scope={args.evaluation_scope}; "
        f"excluded={len(excluded)}"
    )
    provisional_cases = provisional_scoreable_text_cases(cases)
    validated_count = sum(
        case["query_mode"] == "text" and ground_truth_tier(case) == "validated"
        for case in cases
    )
    if args.dry_run:
        print(json.dumps({
            "complete_inventory": inventory_validation["complete"],
            "missing_query_ids": inventory_validation["missing_query_ids"],
            "source_counts": inventory_validation["source_counts"],
            "selected_question_count": len(cases),
            "selected_scoreable_text_count": sum(
                case["query_mode"] == "text" and case["scoreable"] for case in cases
            ),
            "validated_scoreable_text_count": validated_count,
            "provisional_scoreable_text_count": len(provisional_cases),
            "provisional_blockers": [
                {"query_id": case["query_id"], "validation_state": case["validation_state"]}
                for case in provisional_cases
            ],
            "real_run_ready": inventory_validation["complete"] and not provisional_cases,
            "excluded_query_ids": excluded,
            "dataset_sha256": sha256_file(args.csv),
            "canonical_content_sha256": content_sha256,
            "canonical_content_matches": content_sha256 == EXPECTED_CANONICAL_CONTENT_SHA256,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.allow_incomplete:
        raise ValueError("--allow-incomplete is dry-run only; incomplete inventories cannot produce benchmark metrics")
    validate_run_readiness(cases, args.allow_provisional_ground_truth)
    summary_path = validate_output_paths(args.output, args.overwrite_output)

    config_path = Path.cwd() / "config.yaml"
    collection_identity = preflight_collection(config_path)
    from aic51.packages.webui.backend.search import setup_searcher

    searcher = setup_searcher()
    features = choose_features(searcher, args.target_features)
    query_encoder_devices = actual_query_encoder_devices(searcher, features)
    print(f"Collection: {collection_identity['collection']} rows={collection_identity['row_count']}")
    print(f"Features: {features}")
    print(f"Query encoder devices: {query_encoder_devices}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    run_path = run_metadata_path(args.output)
    started_at = datetime.now(timezone.utc).isoformat()
    match_config = match_config_from_args(args)
    args.match_config = match_config
    benchmark_contract = {
        "primary_condition": "Q0",
        "judging_depth": JUDGING_DEPTH,
        "interval_endpoints": "inclusive source-frame counters; no extra slack",
        "primary_point_matcher": (
            "legacy_source_frames" if match_config.legacy_point_tolerance_frames is not None else "timestamp_seconds"
        ),
        "point_tolerance_seconds": match_config.retrieval_point_tolerance_seconds,
        "official_point_tolerance_frames": match_config.official_point_tolerance_frames,
        "legacy_point_tolerance_frames": match_config.legacy_point_tolerance_frames,
        "fps_table": str(args.fps_csv) if getattr(args, "fps_csv", None) else None,
        "fps_table_rows": len(match_config.fps_by_video),
        "qa_semantics": "supporting-frame / evidence-location retrieval only; answer text is not graded",
    }
    params = {
        "nprobe": args.nprobe,
        "temporal_k": args.temporal_k,
        "ocr_weight": args.ocr_weight,
        "asr_weight": args.asr_weight,
        "max_interval": args.max_interval,
        "point_tolerance_seconds": match_config.retrieval_point_tolerance_seconds,
        "official_point_tolerance_frames": match_config.official_point_tolerance_frames,
        "point_tolerance_frames": match_config.legacy_point_tolerance_frames,
        "auto_translate": args.auto_translate,
        "en_to_vi_translate": args.en_to_vi_translate,
    }
    exact_run_context = {
        "benchmark_contract": benchmark_contract,
        "run_complete_inventory": inventory_validation["complete"],
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "evaluation_scope": args.evaluation_scope,
        "allow_provisional_ground_truth": args.allow_provisional_ground_truth,
        "excluded_query_ids": excluded,
        "dataset_path": str(args.csv.resolve()),
        "dataset_sha256": sha256_file(args.csv),
        "canonical_content_sha256": content_sha256,
        "expected_canonical_content_sha256": EXPECTED_CANONICAL_CONTENT_SHA256,
        "workspace_config_path": str(config_path.resolve()),
        "workspace_config_sha256": sha256_file(config_path),
        "git": git_provenance(),
        "critical_code": critical_code_hashes(),
        "runtime": {
            **runtime_versions(),
            "actual_query_encoder_devices": query_encoder_devices,
        },
        "top_k_retrieved": args.top_k,
        "target_features": features,
        "collection_identity": collection_identity,
        "params": params,
    }
    run_metadata = {
        "status": "running",
        "started_at": started_at,
        "output_path": str(args.output.resolve()),
        "summary_path": str(summary_path.resolve()),
        **exact_run_context,
    }
    write_run_metadata(run_path, run_metadata)

    records: list[dict[str, Any]] = []
    try:
        with args.output.open("w", encoding="utf-8", newline="\n") as output:
            for index, case in enumerate(cases, 1):
                if case["query_mode"] != "text":
                    record = unsupported_record(case)
                    records.append(record)
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
                    print(f"[{index:02d}/{len(cases):02d}] {case['query_id']} UNSUPPORTED media query")
                    continue
                for hint_count in range(len(case["hints"]) + 1):
                    record = run_text_variant(searcher, case, hint_count, args, features)
                    records.append(record)
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
                    output.flush()
                    print(
                        f"[{index:02d}/{len(cases):02d}] {case['query_id']} {record['condition']} "
                        f"rank={record['first_correct_rank'] or '-'} "
                        f"R@10={record['recall_at_10']} R@20={record['recall_at_20']} "
                        f"latency={record['latency_ms']:.1f}ms"
                    )

        completed_at = datetime.now(timezone.utc).isoformat()
        summary = {
            "created_at": completed_at,
            "started_at": started_at,
            **exact_run_context,
            **summarize(records, cases),
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except BaseException as exc:
        run_metadata.update({
            "status": "failed",
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "records_written": len(records),
            "failure": {"type": type(exc).__name__, "message": str(exc)},
        })
        write_run_metadata(run_path, run_metadata)
        raise

    run_metadata.update({
        "status": "complete",
        "ended_at": completed_at,
        "records_written": len(records),
        "results_sha256": sha256_file(args.output),
        "summary_sha256": sha256_file(summary_path),
    })
    write_run_metadata(run_path, run_metadata)
    print(f"Results: {args.output}")
    print(f"Summary: {summary_path}")
    print(f"Run metadata: {run_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
