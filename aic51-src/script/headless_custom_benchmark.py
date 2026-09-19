"""Headless Recall benchmark for the Vecna searcher.

Run this from ``aic51-src``.  It talks directly to ``Searcher`` and therefore
does not start FastAPI, the frontend, or any extra backend process.  Milvus
must already be running.

The benchmark is intentionally different from the old HTTP benchmark:

* visual models receive an English translation of the Vietnamese query;
* hybrid OCR/ASR clauses retain the original Vietnamese text;
* TRAKE uses only E1, E2, ... as ordered temporal clauses;
* TRAKE ground truth keeps every event frame instead of only the first one;
* Recall@1/5/10/20 is reported for both ordinary and temporal queries.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import requests
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

# Make ``python script/headless_custom_benchmark.py`` work even when the
# project has not been installed in editable mode.
SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aic51.packages.config import GlobalConfig
from aic51.packages.search import Searcher
from aic51.packages.utils import get_device


K_VALUES = (1, 5, 10, 20)
VISUAL_FEATURES = [
    "image_clip_pe-l-14-336",
    "image_siglip_so400m-384",
    "qwen_vl",
]
TRANSLATION_MODEL = "Helsinki-NLP/opus-mt-vi-en"
TASK_RE = re.compile(r"-(kis|qa|trake)$", re.IGNORECASE)
EVENT_RE = re.compile(r"^\s*E\s*(\d+)\s*:\s*(.*?)\s*$", re.IGNORECASE)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\ufeff", "")).strip()


def frame_number(value: Any) -> int | None:
    match = re.search(r"(\d+)", str(value))
    return int(match.group(1)) if match else None


def frame_key(video: Any, frame: Any) -> tuple[str, int] | None:
    number = frame_number(frame)
    if number is None:
        return None
    return str(video).strip().lower(), number


def task_name(query_id: str) -> str:
    match = TASK_RE.search(query_id)
    return match.group(1).lower() if match else "kis"


def query_clauses(raw_query: str, task: str) -> list[str]:
    lines = [clean_text(line) for line in raw_query.splitlines() if clean_text(line)]
    if task != "trake":
        return [" ".join(lines)] if lines else [""]

    events: list[tuple[int, str]] = []
    for line in lines:
        match = EVENT_RE.match(line)
        if match:
            events.append((int(match.group(1)), match.group(2)))
    if events:
        return [text for _, text in sorted(events)]
    # Keep the benchmark usable for an accidentally malformed TRAKE file.
    return lines


def parse_ground_truth(query_id: str, raw_csv: bytes) -> dict[str, Any]:
    task = task_name(query_id)
    point_set: set[tuple[str, int]] = set()
    sequences: list[list[tuple[str, int]]] = []
    reader = csv.reader(io.StringIO(raw_csv.decode("utf-8-sig", errors="replace")))

    for row in reader:
        row = [item.strip() for item in row]
        if len(row) < 2 or not row[0]:
            continue
        points = [frame_key(row[0], value) for value in row[1:]]
        points = [point for point in points if point is not None]
        if not points:
            # This skips CSV headers such as video_id,frame_id,...
            continue
        if task == "trake":
            sequences.append(points)
        else:
            point_set.update(points[:1])

    if task == "trake":
        return {"task": task, "sequences": sequences, "points": set()}
    return {"task": task, "sequences": [], "points": point_set}


def load_round(data_root: Path, round_number: int) -> dict[str, dict[str, Any]]:
    query_zip = data_root / f"SOTUYEN{round_number}-bo-de-thi.zip"
    truth_zip = data_root / f"vong{round_number}.zip"
    if not query_zip.exists():
        raise FileNotFoundError(f"Missing query archive: {query_zip}")
    if not truth_zip.exists():
        raise FileNotFoundError(f"Missing ground-truth archive: {truth_zip}")

    queries: dict[str, str] = {}
    with zipfile.ZipFile(query_zip) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".txt"):
                queries[Path(name).stem] = archive.read(name).decode("utf-8-sig").strip()

    truth: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(truth_zip) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".csv"):
                truth[Path(name).stem] = parse_ground_truth(
                    Path(name).stem,
                    archive.read(name),
                )

    missing_truth = sorted(set(queries) - set(truth))
    if missing_truth:
        raise ValueError(
            f"Round {round_number}: no ground truth for {len(missing_truth)} queries, "
            f"for example {missing_truth[:3]}"
        )

    return {
        query_id: {
            "raw_query": raw_query,
            "task": task_name(query_id),
            "clauses": query_clauses(raw_query, task_name(query_id)),
            "truth": truth[query_id],
        }
        for query_id, raw_query in queries.items()
    }


class LocalTranslator:
    """CPU translator so it does not compete with the visual models for VRAM."""

    def __init__(self, model_name: str, local_files_only: bool) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        ).to("cpu").eval()

    def translate(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        inputs = self.tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        with torch.inference_mode():
            outputs = self.model.generate(**inputs, max_new_tokens=192)
        return [clean_text(text) for text in self.tokenizer.batch_decode(outputs, skip_special_tokens=True)]


def translated_clauses(
    clauses: list[str],
    translator: LocalTranslator,
    cache: dict[str, str],
) -> list[str]:
    missing = [clause for clause in clauses if clause not in cache]
    if missing:
        for source, translated in zip(missing, translator.translate(missing)):
            cache[source] = translated
    return [cache[clause] for clause in clauses]


def build_search_query(
    clauses: list[str],
    mode: str,
    translator: LocalTranslator,
    cache: dict[str, str],
) -> str:
    english = translated_clauses(clauses, translator, cache)
    if mode == "clip":
        return " / ".join(english)
    # Query._parse_one_query routes the tagged text to BM25 while the plain
    # English part is embedded by CLIP/SigLIP/Qwen-VL.
    return " / ".join(
        f"{en} [ocr: {vi}] [asr: {vi}]"
        for en, vi in zip(english, clauses)
    )


def result_points(result: dict[str, Any]) -> tuple[list[tuple[str, int]], str]:
    entity = result.get("entity") or {}
    record_id = str(entity.get("frame_id", ""))
    if "#" not in record_id:
        return [], record_id
    video, first_frame = record_id.split("#", 1)
    timeline = result.get("time_line") or [first_frame]
    points = [frame_key(video, frame) for frame in timeline]
    return [point for point in points if point is not None], record_id


def api_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert the web backend's light response to Searcher-like records."""
    results = []
    for frame in payload.get("frames", []):
        video_id = frame.get("video_id")
        frame_id = frame.get("frame_id")
        if video_id is None or frame_id is None:
            continue
        result = {
            "entity": {"frame_id": f"{video_id}#{frame_id}"},
            "time_line": frame.get("time_line") or [frame_id],
        }
        if frame.get("scores") is not None:
            result["scores"] = frame["scores"]
        results.append(result)
    return results


def point_hit(result: dict[str, Any], targets: set[tuple[str, int]], tolerance: int) -> bool:
    return any(
        point[0] == target[0] and abs(point[1] - target[1]) <= tolerance
        for point in result_points(result)[0]
        for target in targets
    )


def sequence_match(
    candidate: list[tuple[str, int]],
    target: list[tuple[str, int]],
    tolerance: int,
) -> int:
    matched = 0
    for candidate_video, candidate_frame in candidate:
        if matched >= len(target):
            break
        target_video, target_frame = target[matched]
        if candidate_video == target_video and abs(candidate_frame - target_frame) <= tolerance:
            matched += 1
    return matched


def temporal_match(
    result: dict[str, Any],
    alternatives: list[list[tuple[str, int]]],
    tolerance: int,
) -> tuple[bool, float]:
    candidate, _ = result_points(result)
    if not alternatives:
        return False, 0.0
    matched_counts = [sequence_match(candidate, target, tolerance) for target in alternatives]
    best = max(matched_counts)
    target_size = max(len(target) for target in alternatives)
    return best == target_size, best / target_size if target_size else 0.0


def metric_for_query(
    results: list[dict[str, Any]],
    truth: dict[str, Any],
    tolerance: int,
) -> dict[str, Any]:
    hits: dict[int, bool] = {}
    event_recalls: dict[int, float] = {}
    best_rank: int | None = None
    best_event_rank: int | None = None
    task = truth["task"]

    per_result: list[dict[str, Any]] = []
    for rank, result in enumerate(results, 1):
        if task == "trake":
            hit, event_recall = temporal_match(result, truth["sequences"], tolerance)
        else:
            hit = point_hit(result, truth["points"], tolerance)
            event_recall = float(hit)
        if hit and best_rank is None:
            best_rank = rank
        if event_recall > 0 and best_event_rank is None:
            best_event_rank = rank
        per_result.append(
            {
                "rank": rank,
                "frame_id": result.get("entity", {}).get("frame_id"),
                "time_line": result.get("time_line"),
                "distance": result.get("distance"),
                "hit": hit,
                "event_recall": round(event_recall, 4),
            }
        )

    for k in K_VALUES:
        prefix = per_result[:k]
        hits[k] = any(item["hit"] for item in prefix)
        event_recalls[k] = max((item["event_recall"] for item in prefix), default=0.0)

    return {
        "hit_rank": best_rank,
        "event_hit_rank": best_event_rank,
        "recall": {f"R@{k}": int(hits[k]) for k in K_VALUES},
        "event_recall": {f"R@{k}": round(event_recalls[k], 4) for k in K_VALUES},
        "top_results": per_result,
    }


def json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return str(value)


def make_searcher() -> Searcher:
    collection = GlobalConfig.get("backends", "search", "collection") or "milvus"
    use_gpu = bool(GlobalConfig.get("backends", "search", "gpu"))
    device = get_device(use_gpu)
    print(f"Loading headless searcher: collection={collection}, device={device}", flush=True)
    return Searcher(collection, device)


def run(args: argparse.Namespace) -> dict[str, Any]:
    rounds = [int(item) for item in args.rounds.split(",") if item.strip()]
    modes = [item.strip().lower() for item in args.modes.split(",") if item.strip()]
    invalid = sorted(set(modes) - {"clip", "hybrid"})
    if invalid:
        raise ValueError(f"Unsupported mode(s): {', '.join(invalid)}")

    all_rounds = {round_number: load_round(Path(args.data_root), round_number) for round_number in rounds}
    translator = LocalTranslator(args.translation_model, args.local_files_only)
    searcher = None if args.api_url else make_searcher()
    api_session = requests.Session() if args.api_url else None
    output: dict[str, Any] = {"config": vars(args), "results": {}, "queries": []}
    # Reuse the same VI->EN translations between clip and hybrid runs.
    translation_caches = {round_number: {} for round_number in all_rounds}

    for mode in modes:
        mode_summary: dict[str, Any] = {}
        for round_number, queries in all_rounds.items():
            totals = {k: 0 for k in K_VALUES}
            event_totals = {k: 0.0 for k in K_VALUES}
            count = 0
            errors = 0
            translation_cache = translation_caches[round_number]
            query_items = []

            for index, (query_id, item) in enumerate(sorted(queries.items()), 1):
                started = time.perf_counter()
                search_query = build_search_query(
                    item["clauses"], mode, translator, translation_cache
                )
                translated_at = time.perf_counter()
                error = None
                results: list[dict[str, Any]] = []
                try:
                    if api_session is not None:
                        response = api_session.get(
                            args.api_url,
                            params={
                                "q": search_query,
                                "offset": 0,
                                "limit": args.top_k,
                                "target_features": ",".join(VISUAL_FEATURES),
                                "nprobe": args.nprobe,
                                "temporal_k": args.temporal_k,
                                "ocr_weight": 0.25 if mode == "hybrid" else 0.0,
                                "asr_weight": 0.25 if mode == "hybrid" else 0.0,
                                "max_interval": args.max_interval,
                                "auto_translate": False,
                                "en_to_vi_translate": False,
                            },
                            timeout=args.request_timeout,
                        )
                        response.raise_for_status()
                        results = api_results(response.json())
                    else:
                        response = searcher.search_multimodal(
                            search_query,
                            0,
                            args.top_k,
                            VISUAL_FEATURES,
                            nprobe=args.nprobe,
                            temporal_k=args.temporal_k,
                            ocr_weight=0.25 if mode == "hybrid" else 0.0,
                            asr_weight=0.25 if mode == "hybrid" else 0.0,
                            max_interval=args.max_interval,
                            auto_translate=False,
                            en_to_vi_translate=False,
                        )
                        results = response.get("results", [])
                    metrics = metric_for_query(results, item["truth"], args.point_tolerance)
                    count += 1
                    for k in K_VALUES:
                        totals[k] += metrics["recall"][f"R@{k}"]
                        event_totals[k] += metrics["event_recall"][f"R@{k}"]
                except Exception as exc:  # Keep the rest of the benchmark running.
                    errors += 1
                    metrics = {
                        "hit_rank": None,
                        "event_hit_rank": None,
                        "recall": {f"R@{k}": 0 for k in K_VALUES},
                        "event_recall": {f"R@{k}": 0.0 for k in K_VALUES},
                        "top_results": [],
                    }
                    error = f"{type(exc).__name__}: {exc}"

                elapsed_ms = (time.perf_counter() - started) * 1000
                query_record = {
                    "round": round_number,
                    "mode": mode,
                    "query_id": query_id,
                    "task": item["task"],
                    "temporal": item["task"] == "trake",
                    "raw_query": item["raw_query"],
                    "clauses": item["clauses"],
                    "search_query": search_query,
                    "translation_ms": round((translated_at - started) * 1000, 2),
                    "search_ms": round((time.perf_counter() - translated_at) * 1000, 2),
                    "elapsed_ms": round(elapsed_ms, 2),
                    "n_results": len(results),
                    "error": error,
                    **metrics,
                }
                query_items.append(json_safe(query_record))
                print(
                    f"{mode} r{round_number} {index}/{len(queries)} {query_id} "
                    f"{'T' if item['task'] == 'trake' else '-'} "
                    f"R@20={metrics['recall']['R@20']} {elapsed_ms / 1000:.2f}s",
                    flush=True,
                )

            denominator = count or 1
            summary = {
                "n": count,
                "errors": errors,
                "recall": {f"R@{k}": round(totals[k] / denominator, 4) for k in K_VALUES},
                "event_recall": {
                    f"R@{k}": round(event_totals[k] / denominator, 4) for k in K_VALUES
                },
            }
            mode_summary[f"round_{round_number}"] = summary
            output["queries"].extend(query_items)
            print(json.dumps({"mode": mode, "round": round_number, **summary}), flush=True)
        output["results"][mode] = mode_summary

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(json_safe(output), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote benchmark output: {output_path}", flush=True)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=r"C:\Users\minh ngo\Downloads")
    parser.add_argument("--rounds", default="1,3", help="Comma-separated rounds, e.g. 1,3")
    parser.add_argument("--modes", default="clip,hybrid", help="Comma-separated: clip,hybrid")
    parser.add_argument("--output", default="workspace/benchmark-results/headless_custom.json")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--temporal-k", type=int, default=1000)
    parser.add_argument("--max-interval", type=int, default=1000)
    parser.add_argument("--nprobe", type=int, default=32)
    parser.add_argument("--point-tolerance", type=int, default=0)
    parser.add_argument("--translation-model", default=TRANSLATION_MODEL)
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument(
        "--api-url",
        default="",
        help="Reuse an already-running search backend, e.g. http://127.0.0.1:1337/api/search_multimodal",
    )
    parser.add_argument("--request-timeout", type=float, default=600.0)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
