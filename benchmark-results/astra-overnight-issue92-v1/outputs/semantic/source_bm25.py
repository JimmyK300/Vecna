#!/usr/bin/env python3
"""Dependency-free semantic-index candidate retrieval benchmark.

This measures the semantic index as a *coarse candidate stage*. It does not
claim frame-exact TKIS/TRAKE localization accuracy.

Inputs are committed repository artifacts only:
- 19 validated-current official queries
- preserved official query text/annotations
- production semantic-index records

The benchmark runs two BM25 views:
1. raw_query: official bilingual query text only
2. query_plus_atomic: official text plus the query-derived atomic decomposition

Semantic records are ranked globally, then collapsed to videos by each video's
best record score. Recall@K and MRR are therefore target-video candidate metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
VALIDATED_PATH = ROOT / "evaluation/queries/benchmark/benchmark_validated.csv"
QUERY_PATH = ROOT / "Official-Queries/verified-queries/verified-queries-initial.csv"
DURATION_PATH = ROOT / "derived/metadata/corpus-video-hours-v1/video_durations.csv"

PRODUCTION_SURFACES = [
    "l21-l22-asr-final-v0",
    "l23-asr-ocr-race-phases-v0",
    "l24-performance-identity-v0",
    "l25-lesson-blocks-v0",
    "l26a-dishes-v0",
    "l26b-dishes-v0",
    "l26c-dishes-v0",
    "l26d-dishes-v0",
    "l26e-dishes-v0",
    "l27-travel-chapters-v0",
    "l28-vignettes-final-v0",
    "l29-whole-video-final-v0",
    "l30-whole-video-final-v0",
]

EXCLUDED_TEXT_KEYS = {
    "prefix", "video_id", "segment_id", "start_sec", "end_sec",
    "start_approx_s", "end_approx_s", "confidence", "evidence_provenance",
    "provenance", "uncertainties", "uncertainty", "source_artifact",
    "source_file", "source_files",
}

WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass
class Record:
    path: str
    video_id: str
    segment_id: str
    start_sec: float | None
    end_sec: float | None
    text: str
    tokens: list[str]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.n = len(docs)
        self.lengths = [len(d) for d in docs]
        self.avgdl = statistics.fmean(self.lengths) if self.lengths else 1.0
        self.tfs = [Counter(d) for d in docs]
        df: Counter[str] = Counter()
        for doc in docs:
            df.update(set(doc))
        self.idf = {
            term: math.log(1.0 + (self.n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def scores(self, query_tokens: list[str]) -> list[float]:
        qtf = Counter(query_tokens)
        scores = [0.0] * self.n
        for i, tf in enumerate(self.tfs):
            dl = self.lengths[i]
            norm = self.k1 * (1.0 - self.b + self.b * dl / self.avgdl)
            s = 0.0
            for term, q_count in qtf.items():
                f = tf.get(term)
                if not f:
                    continue
                q_weight = 1.0 + math.log(q_count)
                s += self.idf.get(term, 0.0) * ((f * (self.k1 + 1.0)) / (f + norm)) * q_weight
            scores[i] = s
        return scores


def normalize_text(text: str) -> str:
    text = text.lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def tokenize(text: str) -> list[str]:
    words = WORD_RE.findall(normalize_text(text))
    return [w for w in words if len(w) > 1 or w.isdigit()]


def flatten_text(value: Any, key: str | None = None) -> Iterable[str]:
    if key in EXCLUDED_TEXT_KEYS:
        return
    if isinstance(value, str):
        if value.strip():
            yield value.strip()
    elif isinstance(value, list):
        for item in value:
            yield from flatten_text(item, key)
    elif isinstance(value, dict):
        for subkey, subvalue in value.items():
            yield from flatten_text(subvalue, subkey)


def record_text(obj: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key, value in obj.items():
        if key in EXCLUDED_TEXT_KEYS:
            continue
        chunks.extend(flatten_text(value, key))
    return " \n ".join(dict.fromkeys(chunks))


def load_durations() -> dict[str, float]:
    with DURATION_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
        return {
            row["media_id"]: float(row["duration_seconds"])
            for row in csv.DictReader(fh)
            if row.get("probe_status") == "ok" and row.get("duration_seconds")
        }


def add_record(
    records: dict[tuple[Any, ...], Record],
    *,
    path: Path,
    obj: dict[str, Any],
    video_id: str,
    segment_id: str,
    start: float,
    end: float,
) -> None:
    text = record_text(obj)
    if not text.strip():
        return
    key = (
        video_id,
        segment_id,
        float(start),
        float(end),
        obj.get("semantic_unit_type"),
        obj.get("primary_topic") or obj.get("identity"),
    )
    if key in records:
        return
    records[key] = Record(
        path=str(path.relative_to(ROOT)),
        video_id=video_id,
        segment_id=segment_id,
        start_sec=float(start),
        end_sec=float(end),
        text=text,
        tokens=tokenize(text),
    )


def load_records() -> list[Record]:
    records: dict[tuple[Any, ...], Record] = {}
    semantic_root = ROOT / "semantic-index"

    # Most production surfaces use JSONL records with start_sec/end_sec.
    for surface in PRODUCTION_SURFACES:
        base = semantic_root / surface
        if not base.exists():
            raise FileNotFoundError(f"Missing production surface: {base}")
        for path in sorted(base.rglob("*.jsonl")):
            with path.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    video_id = obj.get("video_id")
                    start = obj.get("start_sec")
                    end = obj.get("end_sec")
                    if not video_id or start is None or end is None:
                        continue
                    segment_id = str(obj.get("segment_id") or f"{video_id}@{start}-{end}")
                    add_record(
                        records,
                        path=path,
                        obj=obj,
                        video_id=str(video_id),
                        segment_id=segment_id,
                        start=float(start),
                        end=float(end),
                    )

    # L23 is intentionally additive and uses one structured JSON file rather
    # than JSONL. Treat each race-phase unit as a searchable semantic record.
    # A few final units intentionally have no textual end boundary; use the
    # canonical ffprobe duration for those open-ended final phases.
    durations = load_durations()
    l23_path = semantic_root / "l23-asr-ocr-race-phases-v0/l23_race_phases.json"
    with l23_path.open("r", encoding="utf-8") as fh:
        l23 = json.load(fh)
    for video in l23.get("videos", []):
        video_id = str(video["video_id"])
        if video_id not in durations:
            raise RuntimeError(f"Missing canonical duration for {video_id}")
        for unit in video.get("units", []):
            number = int(unit["unit"])
            raw_start = unit.get("start_approx_s")
            raw_end = unit.get("end_approx_s")
            if raw_start is None:
                raise RuntimeError(f"Missing start_approx_s for {video_id} unit {number}")
            start = float(raw_start)
            end = float(raw_end) if raw_end is not None else durations[video_id]
            if end <= start:
                raise RuntimeError(f"Invalid L23 interval {video_id} unit {number}: {start}–{end}")
            obj = {
                "video_id": video_id,
                "segment_id": f"{video_id}__race_phase_{number:02d}",
                "start_sec": start,
                "end_sec": end,
                "semantic_unit_type": "race_phase_episode",
                "primary_topic": unit.get("identity", ""),
                "retrieval_text": unit.get("identity", ""),
                "evidence": unit.get("evidence", ""),
            }
            add_record(
                records,
                path=l23_path,
                obj=obj,
                video_id=video_id,
                segment_id=obj["segment_id"],
                start=start,
                end=end,
            )

    out = list(records.values())
    out.sort(key=lambda r: (r.video_id, r.start_sec or -1.0, r.segment_id))
    if not out:
        raise RuntimeError("No semantic records loaded")
    unique_videos = {r.video_id for r in out}
    if len(unique_videos) != 873:
        raise RuntimeError(f"loaded {len(unique_videos)} unique videos, expected 873")
    return out


def load_queries() -> list[dict[str, str]]:
    with VALIDATED_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
        validated = {
            row["query_id"]: row
            for row in csv.DictReader(fh)
            if row.get("benchmark_validation_state") == "validated_current"
        }
    with QUERY_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
        query_rows = {row["query_id"]: row for row in csv.DictReader(fh)}

    missing = sorted(set(validated) - set(query_rows))
    if missing:
        raise RuntimeError(f"Validated query IDs absent from official query table: {missing}")

    rows: list[dict[str, str]] = []
    for qid in sorted(validated, key=lambda x: int(x.rsplit("q", 1)[1])):
        row = dict(query_rows[qid])
        row["target_media_ids"] = validated[qid]["target_media_ids"]
        rows.append(row)
    return rows


def rank_for_query(
    records: list[Record], bm25: BM25, query_text: str, target_video: str, topn: int = 20
) -> dict[str, Any]:
    scores = bm25.scores(tokenize(query_text))
    record_order = sorted(range(len(records)), key=lambda i: (-scores[i], records[i].segment_id))

    best_by_video: dict[str, tuple[float, int]] = {}
    for i in record_order:
        video = records[i].video_id
        candidate = (scores[i], i)
        if video not in best_by_video or candidate[0] > best_by_video[video][0]:
            best_by_video[video] = candidate

    video_order = sorted(best_by_video.items(), key=lambda item: (-item[1][0], item[0]))
    ranked_videos = [video for video, _ in video_order]
    target_rank = ranked_videos.index(target_video) + 1 if target_video in ranked_videos else None

    target_candidates = [i for i in record_order if records[i].video_id == target_video]
    target_record_i = target_candidates[0] if target_candidates else None
    target_record_rank = record_order.index(target_record_i) + 1 if target_record_i is not None else None

    top_videos: list[dict[str, Any]] = []
    for rank, (video, (score, i)) in enumerate(video_order[:topn], 1):
        rec = records[i]
        top_videos.append({
            "rank": rank,
            "video_id": video,
            "score": round(score, 6),
            "segment_id": rec.segment_id,
            "start_sec": rec.start_sec,
            "end_sec": rec.end_sec,
            "path": rec.path,
            "text_preview": rec.text.replace("\n", " ")[:220],
        })

    target_record = records[target_record_i] if target_record_i is not None else None
    return {
        "target_rank": target_rank,
        "target_record_rank": target_record_rank,
        "target_record": {
            "segment_id": target_record.segment_id,
            "start_sec": target_record.start_sec,
            "end_sec": target_record.end_sec,
            "score": round(scores[target_record_i], 6),
            "path": target_record.path,
            "text_preview": target_record.text.replace("\n", " ")[:320],
        } if target_record is not None else None,
        "top_videos": top_videos,
    }


def metric_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranks = [row["target_rank"] for row in rows if row["target_rank"] is not None]
    out: dict[str, Any] = {
        "n": len(rows),
        "mrr": round(sum(1.0 / r for r in ranks) / len(rows), 6) if rows else 0.0,
        "median_target_rank": statistics.median(ranks) if ranks else None,
    }
    for k in (1, 5, 10, 20):
        out[f"recall@{k}"] = round(sum(1 for r in ranks if r <= k) / len(rows), 6) if rows else 0.0
    return out


def write_outputs(out_dir: Path, records: list[Record], queries: list[dict[str, str]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    bm25 = BM25([r.tokens for r in records])

    all_rows: list[dict[str, Any]] = []
    modes = {
        "raw_query": lambda q: q.get("query", ""),
        "query_plus_atomic": lambda q: "\n".join(
            part for part in (q.get("query", ""), q.get("atomic_decomposition", "")) if part.strip()
        ),
    }

    for mode, query_builder in modes.items():
        for q in queries:
            target = q["target_media_ids"].strip()
            result = rank_for_query(records, bm25, query_builder(q), target)
            all_rows.append({
                "mode": mode,
                "query_id": q["query_id"],
                "task_type": q.get("task_type", ""),
                "target_video": target,
                "target_rank": result["target_rank"],
                "target_record_rank": result["target_record_rank"],
                "target_record": result["target_record"],
                "top_videos": result["top_videos"],
            })

    summary: dict[str, Any] = {
        "benchmark": "semantic-index-bm25-v0",
        "scope": "candidate-stage target-video retrieval only; not exact TKIS/TRAKE boundary scoring",
        "validated_query_count": len(queries),
        "semantic_record_count": len(records),
        "unique_video_count": len({r.video_id for r in records}),
        "retrieval_payload": "all semantic record text except IDs/times/confidence/provenance/uncertainty fields",
        "token_normalization": "lowercase + Vietnamese accent stripping",
        "modes": {},
    }

    for mode in modes:
        mode_rows = [r for r in all_rows if r["mode"] == mode]
        summary["modes"][mode] = {
            "all": metric_block(mode_rows),
            "tkis": metric_block([r for r in mode_rows if r["task_type"].lower() == "tkis"]),
            "trake": metric_block([r for r in mode_rows if r["task_type"].lower() == "trake"]),
            "qa": metric_block([r for r in mode_rows if r["task_type"].lower() == "qa"]),
        }

    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(all_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with (out_dir / "results.csv").open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "mode", "query_id", "task_type", "target_video", "target_rank",
            "target_record_rank", "target_segment_id", "target_start_sec", "target_end_sec",
            "target_score", "top1_video", "top1_segment_id", "top1_score", "top5_videos",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            target_record = row["target_record"] or {}
            top = row["top_videos"]
            writer.writerow({
                "mode": row["mode"],
                "query_id": row["query_id"],
                "task_type": row["task_type"],
                "target_video": row["target_video"],
                "target_rank": row["target_rank"],
                "target_record_rank": row["target_record_rank"],
                "target_segment_id": target_record.get("segment_id", ""),
                "target_start_sec": target_record.get("start_sec", ""),
                "target_end_sec": target_record.get("end_sec", ""),
                "target_score": target_record.get("score", ""),
                "top1_video": top[0]["video_id"] if top else "",
                "top1_segment_id": top[0]["segment_id"] if top else "",
                "top1_score": top[0]["score"] if top else "",
                "top5_videos": " | ".join(x["video_id"] for x in top[:5]),
            })

    lines = [
        "# Semantic index BM25 benchmark v0",
        "",
        f"Validated current queries: **{len(queries)}**",
        f"Loaded semantic records: **{len(records)}** across **{len({r.video_id for r in records})}** videos.",
        "",
        "> Candidate-stage benchmark only. A hit means the semantic index surfaced the correct target video; exact TKIS/TRAKE moment localization is not scored here.",
        "",
        "| Mode | Scope | MRR | R@1 | R@5 | R@10 | R@20 | Median rank |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in modes:
        for scope in ("all", "tkis", "trake", "qa"):
            m = summary["modes"][mode][scope]
            lines.append(
                f"| `{mode}` | {scope} (n={m['n']}) | {m['mrr']:.3f} | "
                f"{m['recall@1']:.3f} | {m['recall@5']:.3f} | {m['recall@10']:.3f} | "
                f"{m['recall@20']:.3f} | {m['median_target_rank']} |"
            )

    preferred = [r for r in all_rows if r["mode"] == "query_plus_atomic"]
    lines += [
        "", "## Per-query target rank — query + atomic decomposition", "",
        "| Query | Type | Target | Video rank | Best target record rank | Top-1 video |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in preferred:
        top1 = row["top_videos"][0]["video_id"] if row["top_videos"] else ""
        lines.append(
            f"| {row['query_id']} | {row['task_type']} | {row['target_video']} | "
            f"{row['target_rank']} | {row['target_record_rank']} | {top1} |"
        )

    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "evaluation/queries/benchmark/semantic-index-bm25-v0",
    )
    args = parser.parse_args()

    records = load_records()
    queries = load_queries()
    if len(queries) != 19:
        raise RuntimeError(f"Expected 19 validated-current queries, found {len(queries)}")
    write_outputs(args.output_dir, records, queries)


if __name__ == "__main__":
    main()
