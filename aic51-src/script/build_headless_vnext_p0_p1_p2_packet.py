#!/usr/bin/env python3
"""Build additive Headless-vNext P0+P1+P2 packet. Does not rewrite frozen 48-row files."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FROZEN_MANIFEST = ROOT / "benchmark-results" / "headless-vnext" / "manifest.json"
FROZEN_TEXTS = ROOT / "benchmark-results" / "headless-vnext" / "canonical-query-texts.json"
PACKET_DIR = ROOT / "benchmark-results" / "headless-vnext-p0-p1-p2-v1"
IDENTITY_MAP = Path(
    r"C:\Users\minhc\Documents\Codex\2026-09-13\i-just-downloaded-from-hai-and\work\p2-canonical\identity-map.json"
)
RANGE_CONV = Path(
    r"C:\Users\minhc\Documents\Codex\2026-09-13\i-just-downloaded-from-hai-and\work\p2-canonical\range-conversion.json"
)
P2_MD = Path(
    r"C:\Users\minhc\Documents\Codex\2026-09-13\i-just-downloaded-from-hai-and\work\p2-canonical\actual-p2-official.md"
)
OURS_P2 = Path(
    r"C:\Users\minhc\Documents\Codex\2026-09-13\i-just-downloaded-from-hai-and\work\ours\p2"
)
P3_CSV = Path(
    r"D:\Official-Dataset\evaluation\queries\p3-round3-benchmark-v1\p3_headless_queries.csv"
)

P2_SOURCE_COMMIT = "ecf97977ff09c1e8a6c7a282020699f102e79f42"
P2_SOURCE_PATH = "Official-Queries/current-rounds/actual-p2-official.md"
P2_SOURCE_SHA = "be8340af693115d98d4ba7e67ff1618302e077e6c09c0ca38a6f39ee76fffe99"
PROJECTION_REL = "benchmark-results/headless-vnext-p0-p1-p2-v1/canonical-query-texts.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def frames(video: str, start_s: float, end_s: float, fps: float) -> dict[str, Any]:
    return {
        "end_frame": int(round(end_s * fps)),
        "end_s": end_s,
        "start_frame": int(round(start_s * fps)),
        "start_s": start_s,
    }


def p2_decisions(conv: dict[str, Any]) -> dict[int, dict[str, Any]]:
    converted = conv["converted_ranges"]
    trake = conv["trake"]
    vong2 = conv["vong2"]
    fps = conv["fps_needed"]

    def rng(n: int, **overrides: Any) -> dict[str, Any]:
        rec = dict(converted[str(n)])
        rec.update(overrides)
        if "start_s" in overrides or "end_s" in overrides:
            rec.update(frames(rec["video_id"], rec["start_s"], rec["end_s"], rec["rounded_fps"]))
        return rec

    # q4 banner is 28-30s; 31s is already the clothes pile. Keep the hanging window only.
    q4 = rng(4, start_s=28.0, end_s=31.0)
    q15 = frames("L26_V074", 18.0, 38.0, fps["L26_V074"])
    q15["video_id"] = "L26_V074"
    q15["rounded_fps"] = fps["L26_V074"]
    q30 = frames("L26_V254", 12.0, 36.0, fps["L26_V254"])
    q30["video_id"] = "L26_V254"
    q30["rounded_fps"] = fps["L26_V254"]

    accepted: dict[int, dict[str, Any]] = {}
    for n in (1, 2, 3, 7, 9, 10, 11, 12, 13, 14, 16, 17, 19, 20, 22, 23, 24, 25, 26, 27, 28):
        accepted[n] = {"status": "ACCEPTED_TRUTH", "range": rng(n)}
    accepted[4] = {
        "status": "ACCEPTED_TRUTH",
        "range": q4,
        "note": "Independent inspect: banner hang at 28-30s; 25s/31s+ are clothes piles.",
    }
    accepted[15] = {
        "status": "ACCEPTED_TRUTH",
        "range": q15,
        "note": (
            "Independent P2 inspect of L26_V074: 18s colorful flowers, 20s shrimp, "
            "24s fish paste, 28s lotus, 32-36s static wide ingredients. Not copied from P3."
        ),
    }
    accepted[30] = {
        "status": "ACCEPTED_TRUTH",
        "range": q30,
        "note": (
            "QA evidence: white apron MÓN NGON, galangal, 2 clams in hand at 12s, "
            "clams on white plate at 20s, dialogue 24-36s. OCR nghêu at 63s. Place-4 not isolated; evidence clip accepted."
        ),
    }
    for n, key in ((8, "8"), (21, "21")):
        accepted[n] = {"status": "ACCEPTED_TRUTH", "trake": trake[key]}

    unscoreable = {
        5: {
            "status": "UNRESOLVED",
            "reason": "L21_V022 inspect 10-850s is news studio / mannequins / cycling desk, not red-shirt white-hat water-on-face with two cyclists. Do not guess.",
        },
        6: {
            "status": "UNRESOLVED",
            "reason": "L22_V024@830s shows the news clip with one red circle, not two. Leave unscoreable.",
        },
        18: {
            "status": "UNRESOLVED",
            "reason": "No OCR hit for Hồ Tùng Mậu; L23_V019@512s is finish-line ĐÍCH, not the 13s-countdown intersection. Leave unscoreable.",
        },
        29: {
            "status": "NEEDS_DECISION",
            "reason": (
                "Material video conflict: L26_V034 overlay thịt bê 200g + cà ri without the specified 9-item still-life; "
                "L26_V439 overlay thịt ốc 300g (competitor answer) without curry still-life. Do not guess."
            ),
        },
    }
    for n, rec in unscoreable.items():
        accepted[n] = rec
    accepted["_vong2"] = vong2
    return accepted


def submitted_anchors(vong2: dict[str, Any], csv_name: str, video: str | None) -> list[int]:
    rows = vong2.get(csv_name, {}).get("rows") or []
    frames_out: list[int] = []
    for row in rows:
        if len(row) < 2:
            continue
        if video and row[0] != video:
            continue
        try:
            frames_out.append(int(row[1]))
        except ValueError:
            continue
        if len(frames_out) >= 8:
            break
    return frames_out


def make_p2_record(q: dict[str, Any], decision: dict[str, Any], vong2: dict[str, Any], texts_sha: str) -> dict[str, Any]:
    n = int(q["n"])
    csv_name = f"{q['organizer_query_id']}.csv"
    csv_sha = vong2.get(csv_name, {}).get("sha256", "")
    task = q["task_type"]
    text = q["query_text"]
    cid = q["canonical_query_id"]
    video = None
    ranges: list[dict[str, Any]] = []
    trake_truth: list[dict[str, Any]] = []
    scoreable = decision["status"] == "ACCEPTED_TRUTH"
    if scoreable and "range" in decision:
        rec = decision["range"]
        video = rec["video_id"]
        ranges = [
            {
                "end_frame": rec["end_frame"],
                "end_s": rec["end_s"],
                "start_frame": rec["start_frame"],
                "start_s": rec["start_s"],
            }
        ]
    if scoreable and "trake" in decision:
        rec = decision["trake"]
        video = rec["video_id"]
        for ev in rec["events"]:
            trake_truth.append(
                {
                    "event_index": ev["event_index"],
                    "proxy_window": {
                        "end_frame": ev["proxy_window"]["end_frame"],
                        "start_frame": ev["proxy_window"]["start_frame"],
                    },
                    "submitted_frame": ev["submitted_frame"],
                    "truth_note": "Submission-derived development proxy; not organizer GT and replaceable by reviewed event truth.",
                    "truth_tier": "provisional_submission_anchor",
                }
            )
    is_trake = task == "trake"
    record = {
        "accepted_ranges": ranges,
        "accepted_video_id": video or "",
        "canonical_query_id": cid,
        "canonical_source_id": "actual_p2_official",
        "operational_phase": "P2",
        "provenance": {
            "canonical_query_text_projection_path": PROJECTION_REL,
            "canonical_query_text_projection_sha256": texts_sha,
            "classification": decision["status"],
            "classification_note": decision.get("note") or decision.get("reason") or "",
            "competitor_submission_is_not_organizer_gold": True,
            "official_dataset_control_commit": P2_SOURCE_COMMIT,
            "official_dataset_control_path": P2_SOURCE_PATH,
            "official_dataset_control_query_text_sha256": P2_SOURCE_SHA,
            "p3_range_not_copied": True,
            "source_csv": csv_name,
            "source_csv_sha256": csv_sha,
            "submitted_anchor_frames": submitted_anchors(vong2, csv_name, video),
        },
        "qa_answer": {"status": "not_evaluated"},
        "query_text": text,
        "query_text_sha256": sha256_text(text),
        "raw_query_id": q["organizer_query_id"],
        "reviewed_semantic_ranges_preserved": None,
        "scoreability": {
            "qa_answer": False,
            "range": bool(scoreable and not is_trake),
            "trake_event": bool(scoreable and is_trake),
            "video": bool(scoreable),
        },
        "task_type": task,
        "trake_event_truth": trake_truth,
        "vecna_provenance_id": f"p2-canonical-v1::{q['short_id']}",
    }
    return record


def p3_normalized_texts() -> set[str]:
    texts: set[str] = set()
    if not P3_CSV.exists():
        return texts
    with P3_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            q = (row.get("query") or "").strip()
            if q:
                texts.add(" ".join(q.split()).casefold())
    return texts


def validate_no_p3(records: list[dict[str, Any]]) -> None:
    p3 = p3_normalized_texts()
    overlap = []
    for rec in records:
        norm = " ".join(rec["query_text"].split()).casefold()
        if norm in p3:
            overlap.append(rec["canonical_query_id"])
    if overlap:
        raise SystemExit(f"P3 text contamination in P2 packet: {overlap}")


def count_packet(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "execution_rows": len(records),
        "p0_rows": sum(r["operational_phase"] == "P0" for r in records),
        "p1_rows": sum(r["operational_phase"] == "P1" for r in records),
        "p2_rows": sum(r["operational_phase"] == "P2" for r in records),
        "p2_video_scoreable": sum(r["operational_phase"] == "P2" and r["scoreability"]["video"] for r in records),
        "p2_unscoreable": sum(r["operational_phase"] == "P2" and not r["scoreability"]["video"] for r in records),
        "range_scoreable_non_trake": sum(r["scoreability"]["range"] for r in records),
        "trake_rows": sum(r["scoreability"]["trake_event"] for r in records),
        "trake_events": sum(len(r.get("trake_event_truth") or []) for r in records),
        "video_scoreable": sum(r["scoreability"]["video"] for r in records),
    }


def main() -> None:
    frozen_manifest = load_json(FROZEN_MANIFEST)
    frozen_texts = load_json(FROZEN_TEXTS)
    identity = load_json(IDENTITY_MAP)
    conv = load_json(RANGE_CONV)
    decisions = p2_decisions(conv)
    vong2 = conv["vong2"]
    queries = identity["queries"]
    if len(queries) != 30:
        raise SystemExit(f"identity map has {len(queries)} queries, need 30")

    p2_text_block = {
        q["organizer_query_id"]: {"query_text": q["query_text"], "task_type": q["task_type"]}
        for q in queries
    }
    combined_texts = {
        "official_dataset_control_commit": frozen_texts["official_dataset_control_commit"],
        "p2_official_dataset_control_commit": P2_SOURCE_COMMIT,
        "purpose": "Additive P0/P1/P2 query-text projection. Frozen 48-row P0/P1 texts are copied, not rewritten.",
        "queries": dict(frozen_texts["queries"]),
    }
    combined_texts["queries"]["actual_p2_official"] = p2_text_block
    texts_bytes = json.dumps(combined_texts, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    texts_sha = sha256_bytes(texts_bytes)

    p2_records = [make_p2_record(q, decisions[int(q["n"])], vong2, texts_sha) for q in queries]
    validate_no_p3(p2_records)
    if len(p2_records) != 30:
        raise SystemExit("P2 record count != 30")
    if any(r["operational_phase"] != "P2" for r in p2_records):
        raise SystemExit("non-P2 row in P2-only packet")
    ids = [r["canonical_query_id"] for r in p2_records]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate canonical ids in P2 packet")

    for rec in p2_records:
        rec["provenance"]["canonical_query_text_projection_sha256"] = texts_sha

    combined_records = list(frozen_manifest["records"]) + p2_records
    combined_ids = [r["canonical_query_id"] for r in combined_records]
    if len(combined_ids) != len(set(combined_ids)):
        raise SystemExit("duplicate canonical ids in combined packet")

    p2_only_manifest = {
        "benchmark_id": "headless-main-vnext-p2-only-v1",
        "contract_commit": frozen_manifest["contract_commit"],
        "counts": count_packet(p2_records),
        "frozen_p0_p1_manifest_untouched": True,
        "purpose": "Canonical 30-query P2 retrieval packet. Additive; does not rewrite frozen 48-row P0/P1 files.",
        "p2_source": {
            "canonical_source_id": "actual_p2_official",
            "commit": P2_SOURCE_COMMIT,
            "path": P2_SOURCE_PATH,
            "sha256": P2_SOURCE_SHA,
        },
        "records": p2_records,
    }
    combined_manifest = {
        "benchmark_id": "headless-main-vnext-p0-p1-p2-v1",
        "contract_commit": frozen_manifest["contract_commit"],
        "counts": count_packet(combined_records),
        "frozen_p0_p1_manifest_path": "benchmark-results/headless-vnext/manifest.json",
        "frozen_p0_p1_manifest_sha256": sha256_bytes(FROZEN_MANIFEST.read_bytes()),
        "purpose": "Additive combined P0/P1/P2 scoring packet. Frozen 48-row P0/P1 scoring manifest is copied, not rewritten.",
        "p2_source": p2_only_manifest["p2_source"],
        "records": combined_records,
    }

    classification = {
        "canonical_round": "P2",
        "query_count": 30,
        "scoreable": sorted(n for n, d in decisions.items() if isinstance(n, int) and d["status"] == "ACCEPTED_TRUTH"),
        "unscoreable": sorted(n for n, d in decisions.items() if isinstance(n, int) and d["status"] != "ACCEPTED_TRUTH"),
        "needs_decision": [29],
        "decisions": {str(n): {k: v for k, v in d.items() if k != "range" and k != "trake"} | (
            {"video_id": d["range"]["video_id"], "start_s": d["range"]["start_s"], "end_s": d["range"]["end_s"],
             "start_frame": d["range"]["start_frame"], "end_frame": d["range"]["end_frame"]} if "range" in d
            else {"video_id": d["trake"]["video_id"], "submitted_frames": d["trake"]["submitted_frames"]} if "trake" in d
            else {}
        ) for n, d in decisions.items() if isinstance(n, int)},
        "p3_text_overlap": [],
        "rule": "canonical round is dataset identity + 30-query membership, never organizer p2-* prefix",
    }

    PACKET_DIR.mkdir(parents=True, exist_ok=True)
    (PACKET_DIR / "canonical-query-texts.json").write_bytes(texts_bytes)
    dump_json(PACKET_DIR / "p2-only-manifest.json", p2_only_manifest)
    dump_json(PACKET_DIR / "manifest.json", combined_manifest)
    dump_json(PACKET_DIR / "p2-classification.json", classification)
    dump_json(IDENTITY_MAP.parent / "p2-classification.json", classification)
    print("wrote", PACKET_DIR)
    print("counts", combined_manifest["counts"])
    print("p2_only", p2_only_manifest["counts"])
    print("texts_sha", texts_sha)


if __name__ == "__main__":
    main()
