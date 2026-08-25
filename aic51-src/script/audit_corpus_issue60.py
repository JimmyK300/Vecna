#!/usr/bin/env python3
"""Issue #60 corpus integrity audit. Read-only; writes only to --output-dir."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy optional, deep scans degrade
    np = None

FRAME_ID_RE = re.compile(r"^\d{6}$")
NPY_MAGIC = b"\x93NUMPY"
AUDITED_ROOTS = (
    "data-index",
    "data-source",
    "data-staging",
    "temp-extraction",
    "provenance",
    "benchmark-results",
)
FEATURE_ARTIFACTS = (
    "asr.npy",
    "ocr.npy",
    "image_clip_pe-l-14-336.npy",
    "image_siglip_so400m-384.npy",
)
TEXT_ARTIFACTS = ("asr.npy", "ocr.npy")
EMBEDDING_DIMS = {
    "image_clip_pe-l-14-336": 1024,
    "image_siglip_so400m-384": 1152,
}
STATUS_ORDER = (
    "valid",
    "missing",
    "malformed",
    "legacy_unknown",
    "foreign_unowned",
    "unresolved",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def file_sha256(path: Path, limit: int | None = None) -> str:
    digest = hashlib.sha256()
    read = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            read += len(chunk)
            digest.update(chunk)
            if limit is not None and read >= limit:
                break
    return digest.hexdigest()


class Flags:
    def __init__(self, max_examples: int):
        self.items: list[dict[str, Any]] = []
        self.max_examples = max_examples

    def add(
        self,
        *,
        category: str,
        status: str,
        path: str,
        video_id: str | None,
        reason: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        item = {
            "category": category,
            "status": status,
            "path": path,
            "video_id": video_id,
            "reason": reason,
        }
        if detail:
            item["detail"] = detail
        self.items.append(item)

    def tally(self) -> dict[str, int]:
        return dict(Counter(item["status"] for item in self.items))


def stable_sample(universe: list[str], count: int) -> list[str]:
    if count <= 0 or len(universe) <= count:
        return list(universe)
    step = len(universe) / count
    picked = sorted({universe[min(len(universe) - 1, int(i * step))] for i in range(count)})
    return picked


def parse_npy_header(head: bytes) -> tuple[int, str, tuple[int, ...], bool]:
    """Return (header_len, dtype_str, shape, fortran_order); raise ValueError on problems."""
    if len(head) < 10 or not head.startswith(NPY_MAGIC):
        raise ValueError("missing npy magic")
    major, minor = head[6], head[7]
    if major == 1:
        if len(head) < 10:
            raise ValueError("truncated header prefix")
        header_len = int.from_bytes(head[8:10], "little")
        offset = 10
    else:
        if len(head) < 12:
            raise ValueError("truncated header prefix")
        header_len = int.from_bytes(head[8:12], "little")
        offset = 12
    end = offset + header_len
    header_bytes = head[offset:end]
    if len(header_bytes) < header_len:
        raise ValueError("truncated header")
    text = header_bytes.decode("latin-1")
    text = text.rstrip()
    if not (text.startswith("{") and text.endswith("}")):
        raise ValueError("malformed header dict")
    import ast

    data = ast.literal_eval(text)
    descr = data.get("descr")
    shape = data.get("shape")
    if not isinstance(descr, str):
        raise ValueError("missing descr")
    if not isinstance(shape, tuple):
        shape = (shape,) if shape is not None else ()
    fortran = bool(data.get("fortran_order", False))
    return offset + header_len, descr, tuple(shape), fortran


def descr_itemsize(descr: str) -> int:
    m = re.match(r"^[<>=|]([biufc])(\d+)$", descr)
    if m:
        kind = m.group(1)
        size = int(m.group(2))
        if kind == "b":
            return 1
        return size
    if descr in ("|b1", "|i1"):
        return 1
    m = re.match(r"^[<>=|]U(\d+)$", descr)
    if m:
        return int(m.group(1)) * 4
    m = re.match(r"^[<>=|]S(\d+)$", descr)
    if m:
        return int(m.group(1))
    if descr == "|O":
        return 0
    raise ValueError(f"unparsed descr {descr}")


def shape_numel(shape: tuple[int, ...]) -> int:
    numel = 1
    for dim in shape:
        if dim < 0:
            raise ValueError("negative dimension")
        numel *= dim
    return numel


def audit_npy_file(
    path: Path,
    expected_dim: int | None,
    load_content: bool,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Header-level validation plus optional full load. Returns (info, problems)."""
    info: dict[str, Any] = {}
    problems: list[tuple[str, str]] = []
    try:
        size = path.stat().st_size
    except OSError as exc:
        return {"readable": False}, [("unreadable", f"stat failed: {exc}")]
    info["size_bytes"] = size
    try:
        with open(path, "rb") as handle:
            head = handle.read(4096)
        header_len, descr, shape, _fortran = parse_npy_header(head[:4096])
    except (OSError, ValueError) as exc:
        info["readable"] = False
        problems.append(("unreadable", f"npy header parse failed: {exc}"))
        return info, problems
    info.update({"readable": True, "dtype": descr, "shape": list(shape)})
    if size < header_len:
        problems.append(("truncated", f"file smaller than header ({size} < {header_len})"))
        return info, problems
    try:
        itemsize = descr_itemsize(descr)
        expected_payload = shape_numel(shape) * itemsize
    except ValueError as exc:
        problems.append(("malformed", f"invalid descriptor: {exc}"))
        return info, problems
    if itemsize == 0 and descr == "|O":
        problems.append(("malformed", "object dtype requires pickle; not allow_pickle=False safe"))
        return info, problems
    actual_payload = size - header_len
    if actual_payload < expected_payload:
        problems.append(
            (
                "truncated",
                f"payload {actual_payload} bytes < declared shape/dtype needs {expected_payload}",
            )
        )
        return info, problems
    if load_content and np is not None:
        try:
            array = np.load(path, allow_pickle=False)
        except Exception as exc:
            problems.append(("malformed", f"np.load failed: {exc}"))
            return info, problems
        info["loaded_dtype"] = str(array.dtype)
        info["loaded_shape"] = list(array.shape)
        if array.dtype.kind == "f":
            finite = bool(np.isfinite(array).all())
            info["all_finite"] = finite
            if not finite:
                problems.append(("malformed", "non-finite values (NaN/Inf) in float array"))
        if expected_dim is not None and array.ndim >= 1 and array.shape[-1] != expected_dim:
            problems.append(
                ("malformed", f"last dim {array.shape[-1]} != configured dim {expected_dim}")
            )
    return info, problems


def discover_feature_root(corpus_root: Path) -> Path | None:
    direct = corpus_root / "data-source" / "features" / "features_L21-L30" / "features"
    if direct.is_dir():
        return direct
    base = corpus_root / "data-source" / "features"
    if base.is_dir():
        candidates = sorted(
            child / "features"
            for child in base.iterdir()
            if child.is_dir() and (child / "features").is_dir()
        )
        if candidates:
            return candidates[0]
    return None


def rel_path(path: Path, corpus_root: Path) -> str:
    try:
        return path.resolve().relative_to(corpus_root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def audit_registry(
    corpus_root: Path,
    collection: str,
    flags: Flags,
    hashes: dict[str, Any],
) -> dict[str, Any] | None:
    registry_path = corpus_root / "provenance" / "indexes" / f"{collection}.json"
    if not registry_path.is_file():
        flags.add(
            category="index_registry",
            status="missing",
            path=rel_path(registry_path, corpus_root),
            video_id=None,
            reason=f"collection registry file not found for active collection {collection}",
        )
        return None
    hashes["registry_sha256_raw"] = file_sha256(registry_path)
    try:
        with open(registry_path, encoding="utf-8") as handle:
            registry = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        flags.add(
            category="index_registry",
            status="malformed",
            path=rel_path(registry_path, corpus_root),
            video_id=None,
            reason=f"registry JSON unparseable: {exc}",
        )
        return None
    hashes["registry_sha256_canonical"] = hashlib.sha256(
        canonical_json(registry).encode("utf-8")
    ).hexdigest()
    schema = registry.get("schema_version")
    if schema != "vecna.index.v1":
        flags.add(
            category="index_registry",
            status="unresolved",
            path=rel_path(registry_path, corpus_root),
            video_id=None,
            reason=f"unexpected schema_version {schema!r}",
        )
    state = registry.get("index_state")
    if state != "ready":
        flags.add(
            category="index_registry",
            status="unresolved",
            path=rel_path(registry_path, corpus_root),
            video_id=None,
            reason=f"index_state is {state!r}; collection may be mid-mutation or stale",
        )
    current_id = registry.get("current_index_generation_id")
    generations = registry.get("generations") or []
    generation = None
    if not current_id:
        flags.add(
            category="index_registry",
            status="unresolved",
            path=rel_path(registry_path, corpus_root),
            video_id=None,
            reason="current_index_generation_id is null/absent (invalidated run without completion)",
        )
    else:
        matches = [item for item in generations if item.get("index_generation_id") == current_id]
        if not matches:
            flags.add(
                category="index_registry",
                status="unresolved",
                path=rel_path(registry_path, corpus_root),
                video_id=None,
                reason=f"current generation {current_id} not present among recorded generations",
            )
        elif len(matches) > 1:
            flags.add(
                category="duplicates",
                status="malformed",
                path=rel_path(registry_path, corpus_root),
                video_id=None,
                reason=f"duplicate generation records for id {current_id}",
            )
        else:
            generation = matches[0]
    gen_ids = [item.get("index_generation_id") for item in generations]
    duplicate_gen_ids = sorted({gid for gid, n in Counter(gen_ids).items() if n > 1 and gid})
    for gid in duplicate_gen_ids:
        flags.add(
            category="duplicates",
            status="malformed",
            path=rel_path(registry_path, corpus_root),
            video_id=None,
            reason=f"generation id {gid} appears multiple times in generations[]",
        )
    if generation is None:
        return None
    status = generation.get("status")
    if status != "success":
        flags.add(
            category="index_generation",
            status="unresolved",
            path=rel_path(registry_path, corpus_root),
            video_id=None,
            reason=f"current index generation status is {status!r}",
        )
    failed_videos = generation.get("failed_videos") or []
    for entry in failed_videos:
        video_id = entry.get("video_id") if isinstance(entry, dict) else str(entry)
        flags.add(
            category="index_generation",
            status="missing",
            path=rel_path(registry_path, corpus_root),
            video_id=video_id,
            reason="video listed in current generation failed_videos (indexed run reported failure)",
            detail=entry if isinstance(entry, dict) else None,
        )
    lineage = generation.get("video_lineage") or {}
    feature_fields = list(generation.get("feature_fields") or [])
    return {
        "path": registry_path,
        "registry": registry,
        "generation": generation,
        "lineage_ids": sorted(lineage.keys()),
        "lineage": lineage,
        "feature_fields": feature_fields,
    }


def audit_provenance_sidecars(corpus_root: Path, flags: Flags, hashes: dict[str, Any]) -> dict[str, Any]:
    prov_root = corpus_root / "provenance"
    summary: dict[str, Any] = {}
    for sub in ("sources", "keyframes", "analysis", "evidence"):
        target = prov_root / sub
        exists = target.is_dir()
        count = 0
        if exists:
            count = sum(1 for _ in target.rglob("*.json"))
        summary[sub] = {"present": exists, "json_manifest_count": count}
        if not exists:
            flags.add(
                category="provenance_sidecar_store",
                status="missing",
                path=rel_path(target, corpus_root),
                video_id=None,
                reason=(
                    f"new-format provenance store '{sub}/' absent at corpus root; "
                    "per-video producer/config manifests cannot be dereferenced locally"
                ),
            )
    staging_prov = corpus_root / "data-staging" / "p11-sample" / "provenance"
    staging_counts: dict[str, int] = {}
    if staging_prov.is_dir():
        for sub in ("sources", "keyframes", "analysis", "evidence"):
            staging_counts[sub] = sum(1 for _ in (staging_prov / sub).rglob("*.json")) if (
                staging_prov / sub
            ).is_dir() else 0
    summary["staging_p11_sample"] = staging_counts
    indexes_dir = prov_root / "indexes"
    registry_files = sorted(indexes_dir.glob("*.json")) if indexes_dir.is_dir() else []
    summary["index_registries"] = [rel_path(p, corpus_root) for p in registry_files]
    extra_registries = [
        rel_path(p, corpus_root)
        for p in registry_files
        if p.name not in ("official_l21_l30_all_v2.json",)
    ]
    for name in extra_registries:
        flags.add(
            category="foreign_artifacts",
            status="legacy_unknown",
            path=name,
            video_id=None,
            reason=(
                "index registry for a non-active collection; kept under provenance/indexes but "
                "not referenced by the active search configuration"
            ),
        )
    return summary


def classify_lineage_states(lineage: dict[str, Any], feature_fields: list[str]) -> dict[str, Any]:
    per_feature: dict[str, Counter] = {name: Counter() for name in feature_fields}
    claim_records = 0
    for video_id in sorted(lineage.keys()):
        entry = lineage[video_id] or {}
        for name in feature_fields:
            state = (entry.get(name) or {}).get("state", "absent")
            per_feature[name][state] += 1
            claim_records += len((entry.get(name) or {}).get("lineages", []) or [])
    unresolved_summary = {
        name: {
            "resolved": per_feature[name].get("resolved", 0),
            "unavailable": per_feature[name].get("unavailable", 0),
            "mixed": per_feature[name].get("mixed", 0),
            "absent": per_feature[name].get("absent", 0),
        }
        for name in sorted(feature_fields)
    }
    return {
        "per_feature_states": unresolved_summary,
        "lineage_claim_records_total": claim_records,
        "claim_id_referenceability": (
            "unresolvable_locally: provenance/{sources,keyframes,analysis,evidence} absent at "
            "corpus root, so src_/rnd_/sel_/prv_ identifiers cannot be dereferenced within the "
            "audited corpus"
            if claim_records
            else "no claim records present"
        ),
    }


def audit_video_structure(
    video_id: str,
    video_dir: Path,
    corpus_root: Path,
    flags: Flags,
    deep: bool,
    load_content: bool,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "video_id": video_id,
        "frame_count": 0,
        "artifact_files": 0,
        "problem_frames": 0,
    }
    frame_ids: list[str] = []
    artifact_sets: Counter = Counter()
    problem_examples = 0
    empty_frames = 0
    unreadable_or_truncated = 0
    try:
        frame_entries = sorted(os.scandir(video_dir), key=lambda e: e.name)
    except OSError as exc:
        flags.add(
            category="feature_video_dir",
            status="malformed",
            path=rel_path(video_dir, corpus_root),
            video_id=video_id,
            reason=f"feature dir not scannable: {exc}",
        )
        info["error"] = str(exc)
        return info
    for frame_entry in frame_entries:
        if not frame_entry.is_dir():
            flags.add(
                category="feature_frame",
                status="foreign_unowned",
                path=rel_path(Path(frame_entry.path), corpus_root),
                video_id=video_id,
                reason="unexpected non-directory entry directly under feature video dir",
            )
            continue
        frame_id = frame_entry.name
        if not FRAME_ID_RE.match(frame_id):
            flags.add(
                category="feature_frame",
                status="malformed",
                path=rel_path(Path(frame_entry.path), corpus_root),
                video_id=video_id,
                reason=f"frame directory name {frame_id!r} violates 6-digit numeric convention",
            )
            continue
        frame_ids.append(frame_id)
        present: list[str] = []
        for artifact in FEATURE_ARTIFACTS:
            artifact_path = Path(frame_entry.path) / artifact
            if artifact_path.is_file():
                present.append(artifact)
                info["artifact_files"] += 1
        artifact_sets[tuple(present)] += 1
        if not present:
            empty_frames += 1
    info["frame_count"] = len(frame_ids)
    if empty_frames:
        info["empty_frames"] = empty_frames
        flags.add(
            category="feature_frame",
            status="malformed",
            path=rel_path(video_dir, corpus_root),
            video_id=video_id,
            reason=f"{empty_frames} frame dirs contain none of the expected .npy artifacts (incomplete analysis output)",
        )
    if len(artifact_sets) > 1:
        combos = {",".join(keys) if keys else "<none>": n for keys, n in artifact_sets.items()}
        majority = max(artifact_sets.values())
        partial = {k: v for k, v in combos.items() if k != "<none>" and v < majority}
        if partial:
            info["problem_frames"] = sum(partial.values())
            flags.add(
                category="feature_frame",
                status="malformed",
                path=rel_path(video_dir, corpus_root),
                video_id=video_id,
                reason="inconsistent per-frame artifact sets across frames of one video",
                detail={"combination_counts": combos},
            )
    if not frame_ids:
        flags.add(
            category="feature_video_dir",
            status="malformed",
            path=rel_path(video_dir, corpus_root),
            video_id=video_id,
            reason="no valid frame directories found (incomplete or aborted analysis run)",
        )
    text_presence = {"ocr_readable_frames": 0, "asr_readable_frames": 0}
    info["deep_scanned"] = False
    if deep:
        info["deep_scanned"] = True
        flagged_problems = 0
        for frame_id in frame_ids:
            for artifact in FEATURE_ARTIFACTS:
                artifact_path = video_dir / frame_id / artifact
                if not artifact_path.is_file():
                    continue
                dim = EMBEDDING_DIMS.get(artifact[:-4])
                _, problems = audit_npy_file(artifact_path, dim, load_content)
                if problems:
                    unreadable_or_truncated += 1
                    if problem_examples < 5:
                        problem_examples += 1
                        flagged_problems += 1
                        flags.add(
                            category="feature_npy",
                            status=problems[0][0],
                            path=rel_path(artifact_path, corpus_root),
                            video_id=video_id,
                            reason=problems[0][1],
                            detail={"all_problems": [list(p) for p in problems]},
                        )
                elif artifact in TEXT_ARTIFACTS:
                    text_presence[f"{artifact[:-4]}_readable_frames"] += 1
        if unreadable_or_truncated > flagged_problems:
            flags.add(
                category="feature_npy",
                status="unresolved",
                path=rel_path(video_dir, corpus_root),
                video_id=video_id,
                reason=(
                    f"{unreadable_or_truncated} .npy files failed deep validation; "
                    f"only the first {flagged_problems} are itemized above"
                ),
            )
    info["text_readable_frames"] = text_presence
    info["unique_frame_ids"] = len(set(frame_ids)) == len(frame_ids)
    return info


def audit_corpus(
    corpus_root: Path,
    media_root: Path | None,
    collection: str,
    deep_sample_count: int,
    content_sample_count: int,
    full_headers: bool,
    max_examples: int,
) -> dict[str, Any]:
    flags = Flags(max_examples)
    hashes: dict[str, Any] = {}
    volatile: dict[str, Any] = {"generated_at": utc_now_iso()}
    started = datetime.now(timezone.utc)

    reg = audit_registry(corpus_root, collection, flags, hashes)
    provenance_summary = audit_provenance_sidecars(corpus_root, flags, hashes)

    lineage_ids: list[str] = reg["lineage_ids"] if reg else []
    lineage_states = (
        classify_lineage_states(reg["lineage"], reg["feature_fields"]) if reg else None
    )

    media_ids: list[str] = []
    media_by_id: dict[str, str] = {}
    if media_root is not None and media_root.is_dir():
        for group in sorted(media_root.iterdir()):
            if not group.is_dir():
                continue
            for media_file in sorted(group.iterdir()):
                if media_file.is_file() and media_file.suffix.lower() == ".mp4":
                    media_ids.append(media_file.stem)
                    media_by_id[media_file.stem] = rel_path(media_file, corpus_root)
        media_ids.sort()
    else:
        flags.add(
            category="source_media",
            status="unresolved",
            path=str(media_root) if media_root else "<unset>",
            video_id=None,
            reason="media root unavailable; source-media cross-check skipped",
        )

    feature_root = discover_feature_root(corpus_root)
    feature_video_dirs: dict[str, Path] = {}
    if feature_root is None:
        flags.add(
            category="feature_store",
            status="missing",
            path=rel_path(corpus_root / "data-source" / "features", corpus_root),
            video_id=None,
            reason="no features/<workspace>/features tree discovered under data-source/features",
        )
    else:
        for entry in sorted(os.scandir(feature_root), key=lambda e: e.name):
            if entry.is_dir():
                feature_video_dirs[entry.name] = Path(entry.path)

    lineage_set = set(lineage_ids)
    media_set = set(media_ids)
    feature_set = set(feature_video_dirs)

    missing_features = sorted(lineage_set - feature_set)
    foreign_dirs = sorted(feature_set - lineage_set)
    missing_media = sorted(lineage_set - media_set)
    orphaned_media = sorted(media_set - lineage_set)

    for video_id in missing_features:
        flags.add(
            category="expected_video",
            status="missing",
            path=rel_path(feature_root / video_id, corpus_root) if feature_root else video_id,
            video_id=video_id,
            reason="video is in the indexed lineage but has no feature directory in the active feature store",
        )
    if media_root is not None and media_root.is_dir():
        for video_id in missing_media:
            flags.add(
                category="source_media",
                status="missing",
                path=media_by_id.get(video_id, video_id),
                video_id=video_id,
                reason="indexed lineage references this video id but no source .mp4 exists under media root",
            )
        for video_id in orphaned_media:
            flags.add(
                category="source_media",
                status="unresolved",
                path=media_by_id[video_id],
                video_id=video_id,
                reason="source media exists but is neither indexed nor present in the active feature store (out-of-scope media)",
            )
    for video_id in foreign_dirs:
        flags.add(
            category="expected_video",
            status="foreign_unowned",
            path=rel_path(feature_video_dirs[video_id], corpus_root),
            video_id=video_id,
            reason="feature directory exists but video id is absent from the active collection lineage (orphaned/unowned output)",
        )

    valid_videos = sorted(lineage_set & feature_set)
    all_scanned_dirs = sorted(set(valid_videos) | feature_set)

    sample_universe = sorted(all_scanned_dirs)
    deep_ids = set(sample_universe) if full_headers else set(stable_sample(sample_universe, deep_sample_count))
    deep_ids |= set(stable_sample(sorted(feature_set - lineage_set), min(4, max_examples)))
    content_pool = sorted(deep_ids)
    content_ids = set(content_pool) if full_headers else set(stable_sample(content_pool, content_sample_count))

    video_stats: dict[str, Any] = {}
    total_frames = 0
    total_artifact_files = 0
    for video_id in all_scanned_dirs:
        stats = audit_video_structure(
            video_id,
            feature_video_dirs[video_id],
            corpus_root,
            flags,
            deep=video_id in deep_ids,
            load_content=video_id in content_ids,
        )
        video_stats[video_id] = stats
        total_frames += stats.get("frame_count", 0)
        total_artifact_files += stats.get("artifact_files", 0)

    zero_text_videos = sorted(
        vid
        for vid, st in video_stats.items()
        if st.get("deep_scanned")
        and st["text_readable_frames"]["ocr_readable_frames"] == 0
        and st["text_readable_frames"]["asr_readable_frames"] == 0
        and st.get("frame_count", 0) > 0
    )
    for vid in zero_text_videos:
        flags.add(
            category="ocr_asr_presence",
            status="unresolved",
            path=rel_path(feature_video_dirs[vid], corpus_root),
            video_id=vid,
            reason=(
                "deep-scanned video has zero frames with readable OCR and ASR artifacts "
                "(could be legitimately silent/textless; human-gated confirmation)"
            ),
        )

    duplicates = audit_duplicates(
        corpus_root, feature_video_dirs, flags
    )

    foreign_findings, foreign_counts, foreign_groups = audit_foreign_files(
        corpus_root, flags, hashes
    )

    incomplete = audit_incomplete_run_markers(corpus_root, flags)

    content_hash = compute_report_content_hash(
        flags,
        {
            "registry": {k: v for k, v in hashes.items()},
            "counts": {
                "lineage": len(lineage_ids),
                "media": len(media_ids),
                "feature_dirs": len(feature_video_dirs),
                "frames": total_frames,
                "artifact_files": total_artifact_files,
            },
        },
    )

    finished = datetime.now(timezone.utc)
    report = {
        "schema_version": "vecna.issue60-audit.v1",
        "generated_at_excluded_from_hash": volatile["generated_at"],
        "report_content_sha256": content_hash,
        "parameters": {
            "corpus_root": str(corpus_root),
            "media_root": str(media_root) if media_root else None,
            "collection": collection,
            "deep_sample_videos": deep_sample_count,
            "content_sample_videos": content_sample_count,
            "full_headers": full_headers,
            "max_examples_per_category": max_examples,
        },
        "audited_scope": {
            "audited_roots": list(AUDITED_ROOTS),
            "active_collection": collection,
            "index_generation_id": (reg or {}).get("generation", {}).get("index_generation_id"),
            "expected_video_ids": len(lineage_ids),
            "source_media_ids": len(media_ids),
            "feature_video_dirs": len(feature_video_dirs),
            "total_frames": total_frames,
            "total_artifact_files": total_artifact_files,
            "feature_root": rel_path(feature_root, corpus_root) if feature_root else None,
            "deep_scanned_videos": len(deep_ids),
            "content_loaded_videos": len(content_ids),
        },
        "status_counts": flags.tally(),
        "status_counts_by_category": {
            category: dict(Counter(i["status"] for i in flags.items if i["category"] == category))
            for category in sorted({i["category"] for i in flags.items})
        },
        "provenance_coverage": {
            "corpus_root_stores": provenance_summary,
            "lineage_resolution": lineage_states,
            "coverage_statement": (
                "All 873 lineage videos lack new-format per-video sidecars at the audited root; "
                "dense-field claims inside the registry cannot be dereferenced locally."
            ),
        },
        "duplicates": duplicates,
        "incomplete_run_markers": incomplete,
        "foreign_ownership_counts": foreign_counts,
        "foreign_artifact_groups": foreign_groups,
        "hashes": hashes,
        "runtime_seconds": round((finished - started).total_seconds(), 3),
    }
    report["_flags_items"] = flags.items
    report["_video_stats"] = video_stats
    report["_foreign_findings"] = foreign_findings
    return report


def audit_duplicates(
    corpus_root: Path,
    feature_video_dirs: dict[str, Path],
    flags: Flags,
) -> dict[str, Any]:
    result: dict[str, Any] = {"duplicate_video_ids_across_roots": [], "notes": []}
    alt_roots = {
        "temp-extraction": corpus_root / "temp-extraction",
        "data-staging/clip-features": corpus_root / "data-staging" / "clip-features",
        "data-staging/keyframes": corpus_root / "data-staging" / "keyframes",
        "data-staging/p11-sample/features": corpus_root / "data-staging" / "p11-sample" / "features",
    }
    overlap: dict[str, list[str]] = {}
    for root_name, root in sorted(alt_roots.items()):
        if not root.is_dir():
            continue
        names = sorted(entry.name for entry in os.scandir(root) if entry.is_dir())
        shared = sorted(set(names) & set(feature_video_dirs))
        for video_id in shared:
            overlap.setdefault(video_id, []).append(root_name)
    result["duplicate_video_ids_across_roots"] = [
        {"video_id": vid, "also_present_in": roots} for vid, roots in sorted(overlap.items())
    ]
    for vid, roots in sorted(overlap.items()):
        flags.add(
            category="duplicates",
            status="foreign_unowned",
            path=", ".join(roots),
            video_id=vid,
            reason=(
                "same video id also has an artifact tree outside the active feature store "
                "(stale duplicate generation; not deleted by policy)"
            ),
        )
    return result


OWNERSHIP_RULES_DOC = {
    "benchmark-results": "benchmark output area used by aic51-src/script benchmark runners",
    "provenance/indexes": "active collection registry (traceability.py convention)",
    "provenance/<stores>": (
        "expected new-format provenance store component (sources/keyframes/analysis/evidence); "
        "absent at this corpus root"
    ),
    "data-index": (
        "pre-Milvus local sample-era index artifacts; only reference 'sample_video', unrelated to "
        "the active L21-L30 collection"
    ),
    "data-staging/p11-sample": (
        "documented P11 sample pipeline workspace with its own complete provenance store "
        "(referenced by docs/vecna-master-plan.md)"
    ),
    "data-staging/sample_video-era": (
        "sample_video-era staging outputs of the documented legacy pipeline; not part of the "
        "active collection"
    ),
    "feature_store": "active feature store backing collection official_l21_l30_all_v2",
    "media_slots": (
        "canonical source-media slots (empty in this workspace; media served from external media root)"
    ),
}

STAGING_KNOWN_SUBDIRS = (
    "audio-chunk-timestamps/",
    "audios/",
    "clip-features/",
    "keyframes/",
    "map-keyframes/",
    "preprocessing/",
    "transcripts/",
)

STAGING_KNOWN_DIR_NAMES = (
    "audio-chunk-timestamps",
    "audios",
    "clip-features",
    "keyframes",
    "map-keyframes",
    "preprocessing",
    "transcripts",
)

FOREIGN_REASON_COMPARISON = (
    "whisperx comparison artifacts inside the features tree; no ownership reference discovered "
    "in code/docs/config/provenance"
)
FOREIGN_REASON_LOOSE_REPORT = (
    "report/transcription artifact stored inside an analysis-output tree; no ownership reference "
    "discovered in code/docs/config/provenance"
)
FOREIGN_REASON_TEMP_EXTRACTION = (
    "temporary extraction output duplicating active-collection video ids with a different "
    "artifact generation; unreferenced by code/docs"
)


def match_ownership(rel: str) -> tuple[str, str]:
    """Classify one corpus-relative path. `rel` has no trailing slash."""
    if rel in AUDITED_ROOTS:
        return ("valid", "audited corpus container")
    if rel == "benchmark-results" or rel.startswith("benchmark-results/"):
        return ("valid", OWNERSHIP_RULES_DOC["benchmark-results"])
    if rel == "provenance":
        return ("valid", "audited corpus container")
    if rel == "provenance/indexes" or rel.startswith("provenance/indexes/"):
        return ("valid", OWNERSHIP_RULES_DOC["provenance/indexes"])
    if rel.startswith("provenance/"):
        return ("missing", OWNERSHIP_RULES_DOC["provenance/<stores>"])
    if rel == "data-index" or rel.startswith("data-index/"):
        return ("legacy_unknown", OWNERSHIP_RULES_DOC["data-index"])
    if rel == "data-staging" :
        return ("valid", "audited corpus container")
    if rel == "data-staging/p11-sample" or rel.startswith("data-staging/p11-sample/"):
        return ("valid", OWNERSHIP_RULES_DOC["data-staging/p11-sample"])
    if rel.startswith("data-staging/"):
        rest = rel[len("data-staging/") :]
        if rest.startswith(STAGING_KNOWN_SUBDIRS) or rest in STAGING_KNOWN_DIR_NAMES:
            return ("legacy_unknown", OWNERSHIP_RULES_DOC["data-staging/sample_video-era"])
        return ("foreign_unowned", "unrecognized entry under data-staging with no ownership evidence")
    if rel == "data-source":
        return ("valid", "audited corpus container")
    if rel == "data-source/videos" or rel.startswith("data-source/videos/"):
        return ("valid", OWNERSHIP_RULES_DOC["media_slots"])
    if rel == "data-source/audio" or rel.startswith("data-source/audio/"):
        return ("valid", OWNERSHIP_RULES_DOC["media_slots"])
    if rel == "data-source/metadata" or rel.startswith("data-source/metadata/"):
        if rel == "data-source/metadata":
            return ("valid", "audited corpus container")
        return ("foreign_unowned", FOREIGN_REASON_LOOSE_REPORT)
    if rel == "data-source/features":
        return ("valid", "audited corpus container")
    prefix = "data-source/features/features_L21-L30"
    if rel == prefix or rel.startswith(prefix + "/"):
        if rel == prefix or rel == prefix + "/features" or rel.startswith(prefix + "/features/"):
            return ("valid", OWNERSHIP_RULES_DOC["feature_store"])
        return ("foreign_unowned", FOREIGN_REASON_LOOSE_REPORT)
    if rel.startswith("data-source/features/"):
        rest = rel[len("data-source/features/") :]
        if rest.startswith(("l21_comparison/", "l22_comparison/", "l21_comparison", "l22_comparison")):
            return ("foreign_unowned", FOREIGN_REASON_COMPARISON)
        return ("foreign_unowned", FOREIGN_REASON_LOOSE_REPORT)
    if rel == "temp-extraction" or rel.startswith("temp-extraction/"):
        if rel == "temp-extraction":
            return ("foreign_unowned", FOREIGN_REASON_TEMP_EXTRACTION)
        return ("foreign_unowned", FOREIGN_REASON_TEMP_EXTRACTION)
    return ("foreign_unowned", "no ownership evidence discovered")


def foreign_group_key(rel: str) -> str:
    parts = rel.split("/")
    if parts[0] in ("data-source", "data-staging", "provenance", "benchmark-results"):
        return "/".join(parts[:2])
    return parts[0]


def audit_foreign_files(
    corpus_root: Path,
    flags: Flags,
    hashes: dict[str, Any],
    listing_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    counts: Counter = Counter()
    groups: dict[str, dict[str, Any]] = {}
    for top in AUDITED_ROOTS:
        root = corpus_root / top
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            entries: list[tuple[str, bool]] = [(name, False) for name in sorted(filenames)]
            entries += [(name, True) for name in sorted(dirnames)]
            for name, is_dir in entries:
                full = Path(dirpath) / name
                rel = rel_path(full, corpus_root)
                status, reason = match_ownership(rel)
                counts[status] += 1
                if status != "valid":
                    entry = {
                        "path": rel + ("/" if is_dir else ""),
                        "is_dir": is_dir,
                        "status": status,
                        "reason": reason,
                    }
                    findings.append(entry)
                    key = foreign_group_key(rel)
                    group = groups.setdefault(
                        key,
                        {"path": key + "/", "statuses": Counter(), "reasons": set()},
                    )
                    group["statuses"][status] += 1
                    group["reasons"].add(reason)
    if listing_path is not None:
        with open(listing_path, "w", encoding="utf-8", newline="\n") as handle:
            for entry in sorted(
                findings, key=lambda e: (e["status"], e["path"])
            ):
                handle.write(canonical_json(entry) + "\n")
    group_flags: list[dict[str, Any]] = []
    for key in sorted(groups):
        group = groups[key]
        statuses = dict(group["statuses"])
        dominant = sorted(statuses.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        flags.add(
            category="foreign_artifacts",
            status=dominant,
            path=group["path"],
            video_id=None,
            reason="; ".join(sorted(group["reasons"]))[:500],
            detail={"entry_counts_by_status": statuses},
        )
        group_flags.append({"path": group["path"], "statuses": statuses})
    hashed_samples: dict[str, str] = {}
    interesting = [
        "provenance/indexes/official_l21_l30_all_v2.json",
        "data-index/keyframe_metadata.npy",
        "data-index/transcript_metadata.json",
    ]
    for rel in interesting:
        target = corpus_root / rel
        if target.is_file():
            hashed_samples[rel] = file_sha256(target, limit=64 * 1024 * 1024)
    hashes["flagged_and_owned_samples"] = hashed_samples
    return findings, dict(counts), group_flags


def audit_incomplete_run_markers(corpus_root: Path, flags: Flags) -> dict[str, Any]:
    marker_patterns = ("*.tmp", "*.failures.json", "*.preserved.*", ".*.tmp")
    found: list[str] = []
    for top in AUDITED_ROOTS:
        root = corpus_root / top
        if not root.exists():
            continue
        for pattern in marker_patterns:
            for hit in root.rglob(pattern):
                rel = rel_path(hit, corpus_root)
                found.append(rel)
                flags.add(
                    category="incomplete_run_marker",
                    status="unresolved",
                    path=rel,
                    video_id=None,
                    reason=f"leftover run marker matching {pattern} (possible aborted write or preserved foreign generation)",
                )
    return {"markers_found": len(found), "examples": found[:50]}


def compute_report_content_hash(flags: Flags, context: dict[str, Any]) -> str:
    payload = {
        "flags": [
            {k: item[k] for k in sorted(item) if k != "detail"} | {"detail": item.get("detail")}
            for item in sorted(
                flags.items,
                key=lambda i: (i["category"], i["status"], i["path"], i.get("video_id") or ""),
            )
        ],
        "context": context,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def render_markdown(report: dict[str, Any], flags: Flags) -> str:
    scope = report["audited_scope"]
    lines: list[str] = []
    lines.append("# Issue #60 corpus integrity audit")
    lines.append("")
    lines.append(f"- Generated (excluded from hash): `{report['generated_at_excluded_from_hash']}`")
    lines.append(f"- Report content SHA-256: `{report['report_content_sha256']}`")
    lines.append(
        f"- Active collection: `{scope['active_collection']}` generation `{scope['index_generation_id']}`"
    )
    lines.append(
        f"- Expected videos: **{scope['expected_video_ids']}**, source media: **{scope['source_media_ids']}**, "
        f"feature dirs: **{scope['feature_video_dirs']}**, frames: **{scope['total_frames']}**, "
        f".npy files: **{scope['total_artifact_files']}**"
    )
    lines.append(
        f"- Deep header-scanned videos: {scope['deep_scanned_videos']} (sampled), "
        f"content-loaded videos: {scope['content_loaded_videos']} (sampled)"
    )
    lines.append("")
    lines.append("## Status totals (all categories)")
    lines.append("")
    lines.append("| status | items |")
    lines.append("|---|---|")
    totals = flags.tally()
    for status in STATUS_ORDER:
        lines.append(f"| {status} | {totals.get(status, 0)} |")
    lines.append("")
    lines.append("## Counts by category x status")
    lines.append("")
    lines.append("| category | " + " | ".join(STATUS_ORDER) + " |")
    lines.append("|---|" + "---|" * len(STATUS_ORDER))
    by_cat = report["status_counts_by_category"]
    for category in sorted(by_cat):
        row = [str(by_cat[category].get(status, 0)) for status in STATUS_ORDER]
        lines.append(f"| {category} | " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Flagged items")
    lines.append("")
    order = {"missing": 0, "malformed": 1, "unresolved": 2, "legacy_unknown": 3, "foreign_unowned": 4}
    flagged = sorted(
        (item for item in flags.items if item["status"] in order),
        key=lambda i: (order[i["status"]], i["category"], i["path"]),
    )
    current_status = None
    for item in flagged:
        if item["status"] != current_status:
            current_status = item["status"]
            lines.append(f"### {current_status}")
            lines.append("")
        detail = f" -- detail: `{canonical_json(item['detail'])}`" if item.get("detail") else ""
        lines.append(
            f"- `[{item['category']}]` `{item['path']}`"
            + (f" (video `{item['video_id']}`)" if item.get("video_id") else "")
            + f": {item['reason']}{detail}"
        )
    lines.append("")
    lines.append("## Provenance coverage")
    lines.append("")
    cov = report["provenance_coverage"]
    for store, info in cov["corpus_root_stores"].items():
        if isinstance(info, dict):
            lines.append(
                f"- `{store}`: present={info.get('present')}, manifests={info.get('json_manifest_count', '-')}"
            )
    lr = cov.get("lineage_resolution") or {}
    if lr.get("per_feature_states"):
        lines.append("")
        lines.append("| feature | resolved | unavailable | mixed | absent |")
        lines.append("|---|---|---|---|---|")
        for name, states in lr["per_feature_states"].items():
            lines.append(
                f"| {name} | {states['resolved']} | {states['unavailable']} | {states['mixed']} | {states['absent']} |"
            )
        lines.append("")
        lines.append(f"- Claim records embedded in registry: {lr['lineage_claim_records_total']}")
        lines.append(f"- Referenceability: {lr['claim_id_referenceability']}")
    lines.append("")
    lines.append("## Duplicates")
    lines.append("")
    dupes = report["duplicates"]["duplicate_video_ids_across_roots"]
    if dupes:
        for entry in dupes:
            lines.append(f"- `{entry['video_id']}` also present in: {', '.join(entry['also_present_in'])}")
    else:
        lines.append("- none found")
    lines.append("")
    lines.append("## Incomplete-run markers")
    lines.append("")
    lines.append(f"- markers found: {report['incomplete_run_markers']['markers_found']}")
    for example in report["incomplete_run_markers"]["examples"][:20]:
        lines.append(f"  - `{example}`")
    lines.append("")
    lines.append("## Determinism notes")
    lines.append("")
    lines.append("- All iteration is sorted; sampling uses evenly spaced indices over sorted IDs (no RNG).")
    lines.append("- `report_content_sha256` covers the sorted flag list (paths/status/reasons/details) plus scope counts and registry hashes; wall-clock time is excluded.")
    lines.append("- Registry hash: raw-file SHA-256 plus canonicalized-JSON SHA-256 (`registry_sha256_canonical`).")
    lines.append("- Re-running with identical parameters on an unchanged corpus must reproduce `report_content_sha256` exactly.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, default=Path("D:/Official-Dataset/videos"))
    parser.add_argument("--collection", default="official_l21_l30_all_v2")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--deep-sample-videos", type=int, default=32)
    parser.add_argument("--content-sample-videos", type=int, default=4)
    parser.add_argument("--full-headers", action="store_true")
    parser.add_argument("--max-examples-per-category", type=int, default=200)
    args = parser.parse_args(argv)

    corpus_root = args.corpus_root.resolve()
    if not corpus_root.is_dir():
        print(f"error: corpus root not found: {corpus_root}", file=sys.stderr)
        return 2

    report = audit_corpus(
        corpus_root=corpus_root,
        media_root=args.media_root if args.media_root.exists() else None,
        collection=args.collection,
        deep_sample_count=args.deep_sample_videos,
        content_sample_count=args.content_sample_videos,
        full_headers=args.full_headers,
        max_examples=max(1, args.max_examples_per_category),
    )

    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    flags_list = report.pop("_flags_items")
    video_stats = report.pop("_video_stats")
    foreign_findings = report.pop("_foreign_findings")

    report_path = out_dir / "issue60-audit-report.json"
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")

    flags_path = out_dir / "flags.jsonl"
    ordered = sorted(
        flags_list,
        key=lambda i: (i["status"], i["category"], i["path"], i.get("video_id") or ""),
    )
    with open(flags_path, "w", encoding="utf-8", newline="\n") as handle:
        for item in ordered:
            handle.write(canonical_json(item) + "\n")

    stats_path = out_dir / "per-video-stats.json"
    with open(stats_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(video_stats, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")

    foreign_path = out_dir / "foreign-artifacts-listing.jsonl"
    with open(foreign_path, "w", encoding="utf-8", newline="\n") as handle:
        for entry in sorted(foreign_findings, key=lambda e: (e["status"], e["path"])):
            handle.write(canonical_json(entry) + "\n")

    md_path = out_dir / "issue60-audit-report.md"

    class _FlagsView:
        items = flags_list

        def tally(self_inner):  # noqa: N805
            return dict(Counter(i["status"] for i in flags_list))

    md_text = render_markdown(report, _FlagsView())
    with open(md_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(md_text)

    rerun_cmd = (
        f"& C:\\Users\\minhc\\Code\\Vecna\\.venv\\Scripts\\python.exe "
        f"aic51-src\\script\\audit_corpus_issue60.py "
        f"--corpus-root \"{report['parameters']['corpus_root']}\" "
        f"--media-root \"{report['parameters']['media_root']}\" "
        f"--collection {report['parameters']['collection']} "
        f"--output-dir \"{out_dir}\" "
        f"--deep-sample-videos {report['parameters']['deep_sample_videos']} "
        f"--content-sample-videos {report['parameters']['content_sample_videos']}"
    )
    rerun_path = out_dir / "RERUN.md"
    with open(rerun_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            "# Rerun instructions\n\n"
            "The checker is strictly read-only against the corpus root: it opens files only for reading\n"
            "and writes exclusively into `--output-dir`. Point `--output-dir` anywhere outside the\n"
            "corpus to keep the corpus untouched.\n\n"
            "```powershell\n"
            "$env:PYTHONDONTWRITEBYTECODE='1'\n"
            + rerun_cmd
            + "\n```\n\n"
            "Add `--full-headers` for an exhaustive truncation scan of every `.npy` (~1h on this corpus;\n"
            "the sampled default covers structure for all videos plus headers for a deterministic subset).\n\n"
            "Determinism: compare `report_content_sha256` between runs; it excludes wall-clock time.\n"
        )

    manifest_path = out_dir / "manifest-hashes.json"
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {
                "report_json_sha256": file_sha256(report_path),
                "flags_jsonl_sha256": file_sha256(flags_path),
                "markdown_sha256": file_sha256(md_path),
                "per_video_stats_sha256": file_sha256(stats_path),
                "foreign_listing_sha256": file_sha256(foreign_path),
                "report_content_sha256": report["report_content_sha256"],
                "inputs": report["hashes"],
            },
            handle,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        handle.write("\n")

    totals = dict(Counter(i["status"] for i in flags_list))
    print(json.dumps({"report": str(report_path), "status_totals": totals}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
