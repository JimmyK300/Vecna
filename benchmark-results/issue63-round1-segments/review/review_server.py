"""Local Issue #63 Stage A reviewer with atomic, separate autosave output."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import mimetypes
import os
import re
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REVIEW_DIR = Path(__file__).resolve().parent
PACKET_DIR = REVIEW_DIR.parent
TOOLS_DIR = PACKET_DIR / "stage_a_tools"
OUTPUT_PATH = REVIEW_DIR / "reviewed-ranges.json"
PRELIMINARY_ROUND1_PATH = REVIEW_DIR / "preliminary-round1-questions.txt"
DECISIONS = {"accept", "adjust", "reject", "ambiguous"}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def official_text() -> dict[str, str]:
    """Extract the generator's literal query map without requiring PyYAML."""
    tree = ast.parse((TOOLS_DIR / "generate_records.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "OFFICIAL_TEXT"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise RuntimeError("OFFICIAL_TEXT not found")


def preliminary_round1_text() -> dict[str, dict[str, str]]:
    """Parse and validate Minh's supplied 25-question Preliminary Round 1 list."""
    section_labels = {
        "Bộ câu hỏi vòng thi (25 câu)",
        "Textual Known Item Search (KIS)",
        "Question Answering (Q&A)",
        "Temporal Retrieval and Alignment of Key Events (TRAKE)",
    }
    header = re.compile(r"^Câu query-(p1-\d+)-(kis|qa|trake)\s*$")
    parsed: dict[str, dict[str, str]] = {}
    active_id = active_type = None
    body: list[str] = []

    def finish() -> None:
        if active_id is None:
            return
        if active_id in parsed:
            raise RuntimeError(f"Duplicate Preliminary Round 1 query: {active_id}")
        text = "\n".join(body).strip()
        if not text:
            raise RuntimeError(f"Empty Preliminary Round 1 query: {active_id}")
        parsed[active_id] = {"type": active_type, "text": text}

    for line in PRELIMINARY_ROUND1_PATH.read_text(encoding="utf-8").splitlines():
        match = header.match(line)
        if match:
            finish()
            active_id, active_type, body = match.group(1), match.group(2), []
        elif line not in section_labels and active_id is not None:
            body.append(line)
    finish()
    expected = {f"p1-{number}" for number in range(1, 26)}
    if set(parsed) != expected:
        missing, extra = sorted(expected - set(parsed)), sorted(set(parsed) - expected)
        raise RuntimeError(f"Preliminary Round 1 query set mismatch; missing={missing}, extra={extra}")
    return parsed


def build_records() -> list[dict]:
    anchors = json.loads((PACKET_DIR / "anchors.json").read_text(encoding="utf-8"))
    probes = json.loads((REVIEW_DIR / "provenance.json").read_text(encoding="utf-8"))["video_probes"]
    anchor_by_key = {(a["submission"], a["query_id"]): a for a in anchors}
    raw_records = [
        *load_module("issue63_records_t88", TOOLS_DIR / "records_t88.py").R,
        *load_module("issue63_records_final", TOOLS_DIR / "records_final.py").R,
    ]
    texts = official_text()
    preliminary_texts = preliminary_round1_text()
    records = []
    for raw in raw_records:
        anchor = anchor_by_key.get((raw["submission"], raw["qid"]), {})
        video_path = anchor.get("video_path")
        probe = probes.get(video_path, {}) if video_path else {}
        fps = probe.get("fps")
        ranges = []
        for start_s, end_s in raw["ranges"]:
            item = {"start_s": round(start_s, 3), "end_s": round(end_s, 3)}
            if fps:
                item.update(start_frame=round(start_s * fps), end_frame=round(end_s * fps))
            ranges.append(item)
        still_root = REVIEW_DIR / "stills" / raw["submission"] / raw["qid"]
        stills = (
            [p.relative_to(REVIEW_DIR).as_posix() for p in sorted(still_root.rglob("*.jpg"))]
            if still_root.is_dir() else []
        )
        is_preliminary = raw["submission"] == "final_round1_10_4of13"
        if is_preliminary and preliminary_texts[raw["qid"]]["type"] != raw["qtype"]:
            raise RuntimeError(f'Question type mismatch for {raw["qid"]}')
        records.append({
            "record_id": f'{raw["submission"]}::{raw["qid"]}',
            "query_id": raw["qid"],
            "query": preliminary_texts[raw["qid"]]["text"] if is_preliminary else texts.get(raw["qid"]),
            "query_text_status": "user_supplied_preliminary_round1_25_questions" if is_preliminary else raw["text_status"],
            "source_submission": raw["submission"],
            "source_label": "Preliminary Round 1 · 10.4/13" if is_preliminary else "Testing 8.8 submission",
            "source_csv": anchor.get("source_csv"), "submitted_type": raw["qtype"],
            "video_id": raw["video"], "video_path": video_path,
            "video_exists": bool(video_path and Path(video_path).is_file()),
            "video_duration_s": probe.get("duration_s"), "video_fps_projection": fps,
            "video_nb_frames": probe.get("nb_frames"),
            "submitted_anchor_frames": anchor.get("anchor_frames", raw["anchors"]),
            "submitted_timestamps_s": anchor.get("derived_anchor_times_s", []),
            "qa_answer_verbatim": anchor.get("qa_answer_verbatim"),
            "proposed_correct_ranges": ranges, "confidence": raw["confidence"],
            "boundary_reasoning": raw["reasoning"], "conflict_notes": raw["conflicts"],
            "reviewer_note": raw.get("note"), "review_status": "NEEDS_MINH_REVIEW",
            "stills": stills,
        })
    return records


RECORDS = build_records()
RECORD_BY_ID = {record["record_id"]: record for record in RECORDS}


def empty_output() -> dict:
    return {"schema_version": 1, "purpose": "Issue #63 Stage A human range review",
            "source_packet": str(PACKET_DIR), "benchmark_writeback": False,
            "saved_at_utc": None, "reviews": {}}


def load_output() -> dict:
    if not OUTPUT_PATH.exists():
        return empty_output()
    value = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("reviews"), dict):
        raise ValueError("reviewed-ranges.json must contain a reviews object")
    return value


def validate_output(value: object) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("reviews"), dict):
        raise ValueError("Body must contain a reviews object")
    clean = empty_output()
    for record_id, review in value["reviews"].items():
        if record_id not in RECORD_BY_ID or not isinstance(review, dict):
            raise ValueError(f"Unknown or invalid record: {record_id}")
        if review.get("decision") not in DECISIONS:
            raise ValueError(f"Invalid decision for {record_id}")
        source, normalized_ranges = RECORD_BY_ID[record_id], []
        if not isinstance(review.get("reviewed_ranges", []), list):
            raise ValueError(f"reviewed_ranges must be a list for {record_id}")
        for item in review.get("reviewed_ranges", []):
            start_s, end_s = float(item["start_s"]), float(item["end_s"])
            if start_s < 0 or end_s < start_s:
                raise ValueError(f"Invalid range for {record_id}")
            normalized = {"start_s": round(start_s, 6), "end_s": round(end_s, 6)}
            fps = source.get("video_fps_projection")
            if fps:
                normalized.update(start_frame=round(start_s * fps), end_frame=round(end_s * fps))
            normalized_ranges.append(normalized)
        clean["reviews"][record_id] = {
            "query_id": source["query_id"], "source_submission": source["source_submission"],
            "source_label": source["source_label"],
            "video_id": source["video_id"], "decision": review["decision"],
            "reviewed_ranges": normalized_ranges,
            "reviewer_note": str(review.get("reviewer_note", "")),
            "updated_at_utc": str(review.get("updated_at_utc", "")),
        }
        draft = review.get("draft_marker")
        if draft is not None:
            if not isinstance(draft, dict) or int(draft.get("range_index", -1)) < 0:
                raise ValueError(f"Invalid draft marker for {record_id}")
            clean["reviews"][record_id]["draft_marker"] = {
                "range_index": int(draft["range_index"]),
                "start_s": None if draft.get("start_s") is None else round(float(draft["start_s"]), 6),
                "end_s": None if draft.get("end_s") is None else round(float(draft["end_s"]), 6),
            }
    clean["saved_at_utc"] = datetime.now(timezone.utc).isoformat()
    return clean


def atomic_save(value: dict) -> None:
    temp = OUTPUT_PATH.with_name(f".{OUTPUT_PATH.name}.{os.getpid()}.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, OUTPUT_PATH)
    finally:
        try: temp.unlink()
        except FileNotFoundError: pass


class ReviewHandler(SimpleHTTPRequestHandler):
    server_version = "Issue63Review/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REVIEW_DIR), **kwargs)

    def send_json(self, value: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/records": self.send_json({"records": RECORDS}); return
        if parsed.path == "/api/reviews":
            try: self.send_json(load_output())
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/video": self.serve_video(parsed); return
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/reviews": self.send_error(HTTPStatus.NOT_FOUND); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 5 * 1024 * 1024: raise ValueError("Invalid request size")
            clean = validate_output(json.loads(self.rfile.read(length).decode("utf-8")))
            atomic_save(clean); self.send_json({"ok": True, "saved_at_utc": clean["saved_at_utc"]})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except OSError as exc: self.send_json({"error": f"Save failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_video(self, parsed) -> None:
        record = RECORD_BY_ID.get(parse_qs(parsed.query).get("record_id", [""])[0])
        path = Path(record["video_path"]) if record and record.get("video_path") else None
        if path is None or not path.is_file(): self.send_error(HTTPStatus.NOT_FOUND, "Source unavailable"); return
        size, start, end, partial = path.stat().st_size, 0, path.stat().st_size - 1, False
        if self.headers.get("Range"):
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers["Range"].strip())
            if not match: self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE); return
            first, last = match.groups()
            if first: start, end = int(first), int(last) if last else size - 1
            elif last: start = max(0, size - int(last))
            if start >= size or end < start:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
            end, partial = min(end, size - 1), True
        length = end - start + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "video/mp4")
        self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(length))
        if partial: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with path.open("rb") as handle:
                handle.seek(start); remaining = length
                while remaining:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError): pass

    def log_message(self, fmt: str, *args) -> None:
        if not (args and str(args[0]).startswith("GET /api/video")): super().log_message(fmt, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", type=int, default=8763)
    args = parser.parse_args(); server = ThreadingHTTPServer((args.host, args.port), ReviewHandler)
    print(f"Issue #63 reviewer: http://{args.host}:{args.port}/")
    print(f"Autosave output: {OUTPUT_PATH}")
    print(f"Loaded {len(RECORDS)} records; {sum(r['video_exists'] for r in RECORDS)} videos available.")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")
    finally: server.server_close()


if __name__ == "__main__": main()
