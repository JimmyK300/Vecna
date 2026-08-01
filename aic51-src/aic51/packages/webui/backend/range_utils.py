"""Strict HTTP byte-range parsing."""

from __future__ import annotations


def parse_byte_range(value: str | None, size: int) -> tuple[int, int] | None:
    if not value:
        return None
    if size <= 0 or not value.startswith("bytes="):
        raise ValueError("invalid range")
    spec = value[6:].strip()
    if "," in spec or "-" not in spec:
        raise ValueError("multiple or invalid ranges are unsupported")
    start_text, end_text = spec.split("-", 1)
    if not start_text:
        length = int(end_text)
        if length <= 0:
            raise ValueError("invalid suffix range")
        return max(0, size - length), size - 1
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start < 0 or start >= size or end < start:
        raise ValueError("range outside file")
    return start, min(end, size - 1)
