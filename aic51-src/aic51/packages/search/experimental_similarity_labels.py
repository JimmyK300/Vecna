"""Experimental OpenCubee-derived similarity annotations for Vecna Issue #66.

This module is intentionally not imported by production search code.  It adapts
OpenCubee's INTRO / REUSE / DUP operator labels to Vecna's existing Milvus
vectors using one read-only nearest-neighbour lookup for a selected frame.

Frozen donor concept:
- k19tvan/Opencubee2@0412b55a0f9a3c9642805a669efd871fddf3e970
- backend/services/search.py::classify_similarity_match
- backend/services/search.py::find_similar_frames

Unlike OpenCubee's full-corpus precompute, this experiment never performs an
all-pairs build and never writes to Milvus.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DONOR_REPOSITORY = "k19tvan/Opencubee2"
DONOR_COMMIT = "0412b55a0f9a3c9642805a669efd871fddf3e970"
DONOR_SOURCE = "backend/services/search.py::classify_similarity_match/find_similar_frames"

DEFAULT_FEATURE = "image_siglip_so400m-384"
DEFAULT_THRESHOLD = 0.985
DEFAULT_INTRO_MIN_FRAME_GAP = 100
DEFAULT_INTRO_START_WINDOW_FRAMES = 300
DEFAULT_LIMIT = 20
DEFAULT_NPROBE = 32


@dataclass(frozen=True)
class FrameIdentity:
    video_id: str
    frame: int
    canonical_id: str


def parse_frame_identity(value: Any) -> FrameIdentity | None:
    """Parse Vecna's canonical ``video_id#frame`` identity without guessing."""
    if isinstance(value, dict):
        value = value.get("frame_id") or value.get("id")
    if not isinstance(value, str) or "#" not in value:
        return None
    video_id, frame_text = value.rsplit("#", 1)
    video_id = video_id.strip()
    frame_text = frame_text.strip()
    if not video_id or not frame_text:
        return None
    try:
        frame = int(frame_text)
    except (TypeError, ValueError):
        return None
    if frame < 0:
        return None
    return FrameIdentity(video_id=video_id, frame=frame, canonical_id=value)


def classify_similarity_match(
    source: Any,
    candidate: Any,
    *,
    intro_min_frame_gap: int = DEFAULT_INTRO_MIN_FRAME_GAP,
    intro_start_window_frames: int = DEFAULT_INTRO_START_WINDOW_FRAMES,
) -> str | None:
    """Classify one already-similar pair as DUP, INTRO, REUSE, or hidden.

    Similarity itself is deliberately not inferred here.  Callers must first
    establish that the pair clears a visual cosine threshold.
    """
    source_id = parse_frame_identity(source)
    candidate_id = parse_frame_identity(candidate)
    if source_id is None or candidate_id is None:
        return None
    if source_id.canonical_id == candidate_id.canonical_id:
        return None
    if source_id.video_id != candidate_id.video_id:
        return "DUP"

    gap = abs(candidate_id.frame - source_id.frame)
    if gap < max(0, int(intro_min_frame_gap)):
        return None
    if min(source_id.frame, candidate_id.frame) <= max(0, int(intro_start_window_frames)):
        return "INTRO"
    return "REUSE"


def _hit_entity(hit: Any) -> dict[str, Any]:
    if isinstance(hit, dict):
        entity = hit.get("entity")
        if isinstance(entity, dict):
            return entity
        return hit
    entity = getattr(hit, "entity", None)
    return entity if isinstance(entity, dict) else {}


def _hit_score(hit: Any) -> float:
    if isinstance(hit, dict):
        value = hit.get("distance", hit.get("score", 0.0))
    else:
        value = getattr(hit, "distance", getattr(hit, "score", 0.0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def find_similar_frames(
    searcher: Any,
    source_frame_id: str,
    *,
    feature: str = DEFAULT_FEATURE,
    threshold: float = DEFAULT_THRESHOLD,
    limit: int = DEFAULT_LIMIT,
    nprobe: int = DEFAULT_NPROBE,
    intro_min_frame_gap: int = DEFAULT_INTRO_MIN_FRAME_GAP,
    intro_start_window_frames: int = DEFAULT_INTRO_START_WINDOW_FRAMES,
    oversample_factor: int = 5,
) -> dict[str, Any]:
    """Run one read-only Vecna cosine lookup and attach operator labels.

    The function depends only on ``Searcher.get`` and ``Searcher._database.search``.
    It never inserts, updates, deletes, indexes, embeds, or changes normal search.
    """
    source_identity = parse_frame_identity(source_frame_id)
    if source_identity is None:
        raise ValueError(f"invalid canonical frame id: {source_frame_id!r}")

    if not isinstance(feature, str) or not feature.strip():
        raise ValueError("feature must be a non-empty visual index field")
    feature = feature.strip()
    threshold = float(threshold)
    if not -1.0 <= threshold <= 1.0:
        raise ValueError("threshold must be a cosine value in [-1, 1]")
    limit = max(1, int(limit))
    nprobe = max(1, int(nprobe))
    oversample_factor = max(1, int(oversample_factor))

    record = searcher.get(source_frame_id)
    if not record:
        raise ValueError(f"source frame not found in active collection: {source_frame_id}")

    database = getattr(searcher, "_database", None)
    if database is None or not hasattr(database, "search"):
        raise ValueError("searcher does not expose the expected read-only database search seam")

    field_name = database.process_field_name(feature) if hasattr(database, "process_field_name") else feature
    source_entity = record[0]
    if field_name not in source_entity:
        raise ValueError(f"feature {feature!r} is unavailable for source frame {source_frame_id}")
    source_vector = source_entity[field_name]
    if source_vector is None:
        raise ValueError(f"feature {feature!r} has no vector for source frame {source_frame_id}")

    raw = database.search(
        data=[source_vector],
        filter="",
        offset=0,
        limit=max(limit * oversample_factor, limit + 1),
        anns_field=feature,
        search_params={"nprobe": nprobe, "metric_type": "COSINE"},
    )
    hits = raw[0] if raw else []

    candidates: list[dict[str, Any]] = []
    for hit in hits:
        score = _hit_score(hit)
        if score < threshold:
            continue
        entity = _hit_entity(hit)
        candidate_frame_id = entity.get("frame_id")
        relation = classify_similarity_match(
            source_frame_id,
            candidate_frame_id,
            intro_min_frame_gap=intro_min_frame_gap,
            intro_start_window_frames=intro_start_window_frames,
        )
        if relation is None:
            continue
        candidate_identity = parse_frame_identity(candidate_frame_id)
        if candidate_identity is None:
            continue
        candidates.append(
            {
                "frame_id": candidate_identity.canonical_id,
                "video_id": candidate_identity.video_id,
                "frame": candidate_identity.frame,
                "cosine_similarity": score,
                "relation": relation,
            }
        )

    candidates.sort(key=lambda item: (-item["cosine_similarity"], item["frame_id"]))
    candidates = candidates[:limit]

    collection_name = getattr(database, "_collection_name", None)
    return {
        "schema_version": "vecna.experimental_similarity_labels.v1",
        "source_frame_id": source_identity.canonical_id,
        "source_video_id": source_identity.video_id,
        "source_frame": source_identity.frame,
        "collection": collection_name,
        "feature": feature,
        "metric": "COSINE",
        "threshold": threshold,
        "nprobe": nprobe,
        "intro_min_frame_gap": int(intro_min_frame_gap),
        "intro_start_window_frames": int(intro_start_window_frames),
        "donor": {
            "repository": DONOR_REPOSITORY,
            "commit": DONOR_COMMIT,
            "source": DONOR_SOURCE,
        },
        "results": candidates,
    }
