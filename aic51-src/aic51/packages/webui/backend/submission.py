"""Versioned, offline-first submission payload validation."""

from __future__ import annotations

from typing import Any


class SubmissionValidationError(ValueError):
    pass


def validate_submission_payload(payload: dict[str, Any], *, rule_version: str = "unknown") -> dict[str, Any]:
    """Validate a submission payload without sending it anywhere."""

    if not isinstance(payload, dict):
        raise SubmissionValidationError("submission payload must be an object")
    video_id = payload.get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        raise SubmissionValidationError("video_id must be a non-empty string")

    has_frame = payload.get("frame_id") is not None
    has_timestamp = payload.get("timestamp_ms") is not None
    if not has_frame and not has_timestamp:
        raise SubmissionValidationError("submission requires frame_id or timestamp_ms")

    if has_timestamp:
        timestamp = payload["timestamp_ms"]
        if not isinstance(timestamp, (int, float)) or timestamp < 0:
            raise SubmissionValidationError("timestamp_ms must be a non-negative number")

    if has_frame and (not isinstance(payload["frame_id"], (str, int)) or str(payload["frame_id"]).strip() == ""):
        raise SubmissionValidationError("frame_id must be a non-empty string or integer")

    return {"valid": True, "rule_version": rule_version, "payload": payload}
