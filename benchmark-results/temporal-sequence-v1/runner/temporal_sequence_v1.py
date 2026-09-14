#!/usr/bin/env python3
"""Issue #79: query-only temporal decomposition over the frozen Qwen surface.

This is an experiment harness, deliberately separate from production retrieval.
It builds the 113-row control, decomposes only query text, optionally queries
the existing Qwen/Milvus frame surface, and compares an unordered event union
with a strict increasing-frame chain.  Ground truth is read only by the score
stage; it never enters decomposition or live search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[4]
OFFICIAL_ROOT = Path(r"C:\Users\minhc\Code\Official-Dataset")
CONTROL_ROOT = Path(r"C:\Users\minhc\Code\official-dataset-control")
HISTORICAL_ROOT = ROOT / ".worktrees" / "shot-clustering"
MODEL_SNAPSHOT = Path(
    r"C:\Users\minhc\.cache\huggingface\hub\models--Qwen--Qwen3-VL-Embedding-2B"
    r"\snapshots\9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda"
)

CONTROL_REL = Path(
    "evaluation/headless-current-p0-p1-p2-p3-qwen-only-top100-v0"
)
QUERY_INSTRUCTION = "Retrieve images or text relevant to the user's query."


def jsonl_read(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"invalid JSONL {path}:{line_no}: {exc}") from exc
    return rows


def jsonl_write(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def phase_query_id(phase: str, number: int) -> str:
    return f"{phase.lower()}_q{number:02d}"


def query_number(*values: Any) -> int | None:
    for value in values:
        match = re.search(r"(?:^|[-_])q?(\d+)(?:$|[-_])", str(value or ""), re.I)
        if match:
            return int(match.group(1))
        match = re.search(r"(?:p\d+[-_])(?:q)?(\d+)", str(value or ""), re.I)
        if match:
            return int(match.group(1))
    return None


def normalize_capability_id(value: Any) -> str | None:
    match = re.match(r"p(\d+)[-_]q(\d+)$", str(value or "").strip(), re.I)
    if not match:
        return None
    return phase_query_id(f"p{match.group(1)}", int(match.group(2)))


def capability_key_for_source(current_row: dict[str, Any], fallback_query_id: str) -> str:
    source_key = str(current_row.get("canonical_source_key") or "")
    match = re.search(r"query-(p\d+)-(\d+)(?:-|$)", source_key, re.I)
    if match:
        return phase_query_id(match.group(1), int(match.group(2)))
    return fallback_query_id


def frame_number(result: dict[str, Any]) -> int | None:
    for key in ("frame_id", "source_frame_id"):
        value = result.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
        match = re.search(r"#(\d+)$", str(value or ""))
        if match:
            return int(match.group(1))
    return None


def video_id(result: dict[str, Any]) -> str | None:
    value = result.get("video_id")
    if value:
        return str(value)
    source = str(result.get("source_frame_id") or result.get("frame_id") or "")
    if "#" in source:
        return source.split("#", 1)[0]
    match = re.match(r"(L\d+_V\d+)", source)
    return match.group(1) if match else None


def source_frame_id(result: dict[str, Any]) -> str:
    source = result.get("source_frame_id")
    if source:
        return str(source)
    frame = result.get("frame_id")
    if isinstance(frame, (int, float)) and video_id(result):
        return f"{video_id(result)}#{int(frame):06d}"
    return str(frame or "")


def result_frame(result: dict[str, Any]) -> int | None:
    return frame_number(result)


def convert_result(result: dict[str, Any], rank: int | None = None, *, event_id: str | None = None) -> dict[str, Any]:
    distance = result.get("distance", result.get("score", result.get("final")))
    try:
        distance = float(distance)
    except (TypeError, ValueError):
        distance = None
    converted: dict[str, Any] = {
        "rank": int(rank if rank is not None else result.get("rank", 0)),
        "distance": distance,
        "score": distance,
        "video_id": video_id(result),
        "frame_id": result.get("frame_id"),
        "source_frame_id": source_frame_id(result),
        "time_line": result.get("time_line") if isinstance(result.get("time_line"), list) else [],
    }
    if event_id is not None:
        converted["event_id"] = event_id
    return converted


def split_query_events(query: str) -> list[str]:
    """Deterministic query-only splitter; never consults truth or candidate data."""
    query = str(query or "").replace("\r\n", "\n").replace("\r", "\n")
    pieces: list[str] = []
    for line in query.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Keep the operation lexical: these separators are present in source
        # query text, not inferred from answers or corpus inspection.
        line_parts = re.split(r"\s*(?:;|→|->|⇒)\s*", line)
        for part in line_parts:
            part = part.strip()
            if not part:
                continue
            sentences = re.split(r"(?<=[.!?])\s+", part)
            pieces.extend(sentence.strip() for sentence in sentences if sentence.strip())
    return pieces


def accepted_videos(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    if row.get("accepted_video_id"):
        values.add(str(row["accepted_video_id"]))
    for group in row.get("accepted_groups") or []:
        for interval in group or []:
            if interval.get("video_id"):
                values.add(str(interval["video_id"]))
    return values


def truth_intervals(row: dict[str, Any]) -> list[dict[str, Any]]:
    intervals: list[dict[str, Any]] = []
    for item in row.get("accepted_ranges") or []:
        if isinstance(item, dict):
            start = item.get("start_frame", item.get("start"))
            end = item.get("end_frame", item.get("end"))
            if start is not None and end is not None:
                intervals.append({"video_id": item.get("video_id") or row.get("accepted_video_id"), "start_frame": int(start), "end_frame": int(end)})
    for group in row.get("accepted_groups") or []:
        for item in group or []:
            start = item.get("start_frame", item.get("start"))
            end = item.get("end_frame", item.get("end"))
            if start is not None and end is not None:
                intervals.append({"video_id": item.get("video_id"), "start_frame": int(start), "end_frame": int(end)})
    return intervals


def video_hit(result: dict[str, Any], row: dict[str, Any]) -> bool:
    return video_id(result) in accepted_videos(row)


def range_hit(result: dict[str, Any], row: dict[str, Any]) -> bool:
    vid = video_id(result)
    frame = result_frame(result)
    if vid is None or frame is None:
        return False
    return any(
        interval.get("video_id") in (None, vid)
        and int(interval["start_frame"]) <= frame <= int(interval["end_frame"])
        and (interval.get("video_id") is None or interval.get("video_id") == vid)
        for interval in truth_intervals(row)
    )


def item_hit(result: dict[str, Any], row: dict[str, Any]) -> bool:
    chain = result.get("chain")
    if isinstance(chain, list) and chain:
        return any(range_hit(item, row) for item in chain)
    return range_hit(result, row)


def metrics(results: list[dict[str, Any]], row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for k in (1, 5, 20):
        top = results[:k]
        output[f"video_R@{k}"] = float(any(video_hit(item, row) for item in top))
        output[f"range_R@{k}"] = float(any(item_hit(item, row) for item in top))
    return output


def metric_summary(scored: list[dict[str, Any]], field: str, *, eligible_only: bool = False) -> dict[str, Any]:
    if eligible_only:
        scored = [row for row in scored if row.get("eligible")]
    values = [float(row["metrics"][field]) for row in scored if row.get("metrics") and field in row["metrics"]]
    return {"n": len(values), "hits": int(sum(values)), "recall": (sum(values) / len(values) if values else None)}


def normalize_rankings(items: list[dict[str, Any]], *, field: str = "distance") -> list[dict[str, Any]]:
    converted = [convert_result(item, rank=i + 1) for i, item in enumerate(items)]
    converted.sort(key=lambda item: (-(item.get(field) if item.get(field) is not None else -math.inf), item["rank"], item["source_frame_id"]))
    for index, item in enumerate(converted, 1):
        item["rank"] = index
    return converted


def load_capabilities(control_root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    directory = control_root / "evaluation/queries/benchmark/capability-decomposition-v0"
    for path in sorted(directory.glob("p*.jsonl")):
        for row in jsonl_read(path):
            qid = normalize_capability_id(row.get("query_id"))
            if qid:
                result[qid] = row
    return result


def read_inputs(args: argparse.Namespace) -> dict[str, Any]:
    current_path = args.official_root / CONTROL_REL / "qwen_only_top100.jsonl"
    gt_path = args.official_root / CONTROL_REL / "ground_truth_current_115.jsonl"
    p3_path = args.official_root / "evaluation/queries/p3-round3-benchmark-v1/baselines-20260913/qwen_only_v1.jsonl"
    manifest_path = args.historical_root / "benchmark-results/headless-vnext-p0-p1-p2-v1/manifest.json"
    scored_path = args.historical_root / "benchmark-results/headless-vnext-p0-p1-p2-v1/scored-combined/scored.jsonl"
    paths = [current_path, gt_path, p3_path, manifest_path, scored_path]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("missing frozen input(s):\n" + "\n".join(missing))
    return {
        "current": jsonl_read(current_path),
        "gt": jsonl_read(gt_path),
        "p3": jsonl_read(p3_path),
        "manifest": json.loads(manifest_path.read_text(encoding="utf-8")),
        "scored": jsonl_read(scored_path),
        "capabilities": load_capabilities(args.control_root),
        "paths": paths,
    }


def build_control(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inputs = read_inputs(args)
    current = {str(row["query_id"]): row for row in inputs["current"]}
    current_by_text = {norm_text(row.get("query")): row for row in inputs["current"]}
    current_by_source = {str(row.get("canonical_source_key")): row for row in inputs["current"]}
    gt = {str(row["query_id"]): row for row in inputs["gt"]}
    p3 = {str(row["query_id"]): row for row in inputs["p3"]}
    scored = {str(row["canonical_query_id"]): row for row in inputs["scored"]}
    historical = inputs["manifest"]["records"]
    controls: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []

    for record in historical:
        phase = str(record["operational_phase"])
        raw_id = str(record.get("raw_query_id") or record["canonical_query_id"])
        number = query_number(raw_id, record.get("canonical_query_id"))
        if number is None:
            raise RuntimeError(f"cannot map historical query number: {record['canonical_query_id']}")
        qid = phase_query_id(phase, number)
        source_prefix = f"query-{phase.lower()}-{number}-"
        source_candidates = [row for key, row in current_by_source.items() if key.startswith(source_prefix)]
        current_row = (source_candidates[0] if len(source_candidates) == 1 else None) or current_by_text.get(norm_text(record.get("query_text"))) or current.get(qid)
        if not current_row:
            raise RuntimeError(f"cannot map historical row to current source: {record['canonical_query_id']} -> {qid}")
        current_qid = str(current_row["query_id"])
        baseline_row = scored.get(str(record["canonical_query_id"]))
        if not baseline_row:
            raise RuntimeError(f"missing historical scored row: {record['canonical_query_id']}")
        cap_key = capability_key_for_source(current_row, current_qid)
        cap = inputs["capabilities"].get(cap_key, {})
        enriched = dict(record)
        enriched.update({
            "query_id": current_qid,
            "canonical_source_id": current_row.get("canonical_source_id"),
            "canonical_source_key": current_row.get("canonical_source_key"),
            "query_text": current_row.get("query", record.get("query_text")),
            "baseline_results": normalize_rankings(baseline_row.get("rankings") or []),
            "baseline_source": "frozen_headless_vnext_scored_combined",
            "truth_provenance": "frozen_headless_vnext_manifest",
            "truth_status": "development_frozen_manifest_truth",
            "capability_tags": cap.get("capability_tags", []),
            "capability_source_id": cap_key,
            "capability_summary": cap.get("summary"),
            "capability_primary_challenge": cap.get("primary_challenge"),
        })
        controls.append(enriched)
        ledger.append({"query_id": current_qid, "source": "historical", "historical_id": record["canonical_query_id"], "method": "exact_query_text" if current_by_text.get(norm_text(record.get("query_text"))) else "phase_number_fallback", "query_text_sha256": sha256_text(str(enriched["query_text"]))})

    for qid, p3_row in sorted(p3.items()):
        if qid == "p3_q09":
            continue
        truth = gt.get(qid)
        if not truth or not truth.get("scoreable"):
            continue
        cap = inputs["capabilities"].get(qid, {})
        enriched = {
            "query_id": qid,
            "canonical_source_id": truth.get("canonical_source_id", "p3"),
            "canonical_source_key": truth.get("canonical_source_key", qid),
            "query_text": p3_row.get("query_text") or truth.get("query"),
            "operational_phase": "P3",
            "raw_query_id": qid,
            "task_type": p3_row.get("task_type", truth.get("task_type")),
            "scoreability": {"video": True, "range": True, "qa_answer": False, "trake_event": False},
            "accepted_video_id": (truth.get("accepted_groups") or [[{}]])[0][0].get("video_id") if truth.get("accepted_groups") else None,
            "accepted_ranges": [],
            "accepted_groups": truth.get("accepted_groups", []),
            "trake_event_truth": [],
            "baseline_results": normalize_rankings(p3_row.get("top_results") or []),
            "baseline_source": "p3_qwen_only_v1",
            "truth_provenance": "current_p3_source_text_answer_key",
            "truth_status": truth.get("truth_status"),
            "capability_tags": cap.get("capability_tags", []),
            "capability_source_id": qid,
            "capability_summary": cap.get("summary"),
            "capability_primary_challenge": cap.get("primary_challenge"),
        }
        for group in truth.get("accepted_groups") or []:
            for interval in group or []:
                enriched["accepted_ranges"].append({"video_id": interval.get("video_id"), "start_frame": interval.get("start"), "end_frame": interval.get("end")})
        controls.append(enriched)
        ledger.append({"query_id": qid, "source": "current_p3", "method": "p3_baseline_query_id", "query_text_sha256": sha256_text(str(enriched["query_text"]))})

    controls.sort(key=lambda row: (str(row.get("operational_phase")), str(row["query_id"])))
    if len(controls) != 113:
        raise RuntimeError(f"expected exact 113-query control, got {len(controls)}")
    if len({row["query_id"] for row in controls}) != 113:
        duplicates = [qid for qid, count in Counter(row["query_id"] for row in controls).items() if count > 1]
        raise RuntimeError(f"control contains duplicate query IDs: {duplicates}")
    if {row["query_id"] for row in controls} & {"p0_q15", "p3_q09"}:
        raise RuntimeError("documented exclusions leaked into control")

    decompositions = []
    for row in controls:
        events = split_query_events(row["query_text"])
        tags = set(row.get("capability_tags") or [])
        eligible = len(events) >= 2 and bool(tags & {"SEQ", "BOUND", "TRACK", "MOTION"})
        decompositions.append({
            "query_id": row["query_id"],
            "query_text": row["query_text"],
            "query_text_sha256": sha256_text(row["query_text"]),
            "events": [{"event_id": f"E{i:02d}", "text": text} for i, text in enumerate(events, 1)],
            "ordering": "strict_increasing_frame",
            "eligible_for_ordered_search": eligible,
            "eligibility_reason": "query_only_split_and_temporal_capability_tag" if eligible else "fewer_than_two_events_or_no_temporal_capability_tag",
            "source": "query_only_sentence_and_source_delimiter_split",
            "ground_truth_used": False,
            "capability_tags": sorted(tags),
        })
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    jsonl_write(out / "control_113.jsonl", controls)
    jsonl_write(out / "mapping_ledger.jsonl", ledger)
    jsonl_write(out / "decompositions_113.jsonl", decompositions)
    input_hashes = {str(path): sha256_file(path) for path in inputs["paths"]}
    write_json(out / "control_manifest.json", {
        "experiment": "temporal-sequence-retrieval-v1",
        "issue": 79,
        "control_count": len(controls),
        "historical_count": sum(row["operational_phase"] != "P3" for row in controls),
        "p3_count": sum(row["operational_phase"] == "P3" for row in controls),
        "excluded": ["p0_q15", "p3_q09"],
        "decomposition_count": len(decompositions),
        "eligible_count": sum(item["eligible_for_ordered_search"] for item in decompositions),
        "event_count": sum(len(item["events"]) for item in decompositions),
        "input_sha256": input_hashes,
        "ground_truth_used_for_decomposition": False,
    })
    return controls, decompositions


def load_model(snapshot: Path):
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    if not snapshot.exists():
        raise FileNotFoundError(f"model snapshot missing: {snapshot}")
    # Match the production CPU surface. The current extractor uses the
    # checkpoint's bfloat16 weights; float32 changes the query vector enough
    # to make saved-baseline parity inconclusive.
    model = Qwen3VLForConditionalGeneration.from_pretrained(snapshot, dtype=torch.bfloat16, low_cpu_mem_usage=False)
    processor = AutoProcessor.from_pretrained(snapshot)
    model.eval()
    return torch, model, processor


def encode_texts(torch: Any, model: Any, processor: Any, texts: list[str]) -> list[list[float]]:
    conversations = [
        [
            {"role": "system", "content": [{"type": "text", "text": QUERY_INSTRUCTION}]},
            {"role": "user", "content": [{"type": "text", "text": text}]},
        ]
        for text in texts
    ]
    inputs = processor.apply_chat_template(
        conversations, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt", padding=True
    )
    with torch.inference_mode():
        output = model(**inputs, output_hidden_states=True)
    hidden = output.hidden_states[-1]
    last = inputs["attention_mask"].sum(dim=1) - 1
    vector = hidden[torch.arange(hidden.shape[0]), last]
    vector = torch.nn.functional.normalize(vector, p=2, dim=1)
    return vector.detach().cpu().float().numpy().tolist()


def encode_text(torch: Any, model: Any, processor: Any, text: str):
    return encode_texts(torch, model, processor, [text])[0]


def milvus_search(client: Any, collection: str, vector: list[float], limit: int, nprobe: int, event_id: str) -> list[dict[str, Any]]:
    hits = client.search(
        collection_name=collection,
        data=[vector],
        anns_field="qwen_vl",
        limit=limit,
        search_params={"metric_type": "COSINE", "params": {"nprobe": nprobe}},
        output_fields=["frame_id"],
    )
    rows: list[dict[str, Any]] = []
    for index, hit in enumerate((hits[0] if hits else []), 1):
        entity = hit.get("entity") if isinstance(hit, dict) else None
        frame = (entity or {}).get("frame_id") if isinstance(entity, dict) else None
        if frame is None and isinstance(hit, dict):
            frame = hit.get("id")
        result = {"frame_id": frame, "distance": hit.get("distance") if isinstance(hit, dict) else None}
        converted = convert_result(result, rank=index, event_id=event_id)
        rows.append(converted)
    return rows


def run_search(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = jsonl_read(out / "control_113.jsonl")
    decompositions = jsonl_read(out / "decompositions_113.jsonl")
    selected = {item.strip() for item in args.query_ids.split(",") if item.strip()} if args.query_ids else None
    events: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for decomposition in decompositions:
        if not decomposition.get("eligible_for_ordered_search"):
            continue
        if selected and decomposition["query_id"] not in selected:
            continue
        for event in decomposition["events"]:
            events.append((decomposition, event))
    expected_ids = {f"{qid}:{event['event_id']}" for qid, event in ((d["query_id"], e) for d, e in events)}
    ranking_path = out / "event_rankings.jsonl"
    existing: dict[str, dict[str, Any]] = {}
    if ranking_path.exists():
        for row in jsonl_read(ranking_path):
            key = f"{row['query_id']}:{row['event_id']}"
            # Do not resume rows produced under a different query contract or
            # from a previous bounded selection.
            if key in expected_ids and row.get("instruction") == QUERY_INSTRUCTION:
                existing[key] = row
    missing = sorted(expected_ids - set(existing))
    if not missing:
        print(f"search: all {len(expected_ids)} event rankings already present")
        return

    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    import pymilvus
    from pymilvus import MilvusClient
    torch, model, processor = load_model(args.model_snapshot)
    client = MilvusClient(uri=args.milvus_uri)
    parity_row = next((row for row in controls if row["query_id"] == args.parity_query), None)
    if parity_row:
        parity_vector = encode_text(torch, model, processor, parity_row["query_text"])
        parity_results = milvus_search(client, args.collection, parity_vector, min(args.limit, 20), args.nprobe, "FULL_QUERY")
        baseline_ids = [source_frame_id(item) for item in parity_row.get("baseline_results", [])[:20]]
        live_ids = [source_frame_id(item) for item in parity_results[:20]]
        baseline_set = set(baseline_ids)
        live_set = set(live_ids)
        write_json(out / "surface_parity.json", {
            "query_id": args.parity_query,
            "ground_truth_used": False,
            "baseline_source": parity_row.get("baseline_source"),
            "baseline_top1": baseline_ids[0] if baseline_ids else None,
            "live_top1": live_ids[0] if live_ids else None,
            "top20_overlap": len(baseline_set & live_set),
            "top20_overlap_fraction": (len(baseline_set & live_set) / len(baseline_set) if baseline_set else None),
            "top20_baseline": baseline_ids,
            "top20_live": live_ids,
            "parity_status": "top1_and_top20_overlap" if baseline_ids and live_ids and baseline_ids[0] == live_ids[0] and (len(baseline_set & live_set) / len(baseline_set)) >= 0.8 else "diagnostic_mismatch",
        })
        print(f"parity: {args.parity_query} top1={live_ids[0] if live_ids else None} overlap20={len(baseline_set & live_set)}", flush=True)
    print(f"search: {len(missing)} event queries; device={'cuda' if torch.cuda.is_available() else 'cpu'}", flush=True)
    started = time.time()
    pending = [(decomposition, event) for decomposition, event in events if f"{decomposition['query_id']}:{event['event_id']}" in missing]
    batch_size = max(1, int(args.encode_batch_size))
    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start:batch_start + batch_size]
        batch_started = time.time()
        vectors = encode_texts(torch, model, processor, [event["text"] for _, event in batch])
        batch_elapsed = round(time.time() - batch_started, 3)
        for (decomposition, event), vector in zip(batch, vectors):
            key = f"{decomposition['query_id']}:{event['event_id']}"
            results = milvus_search(client, args.collection, vector, args.limit, args.nprobe, event["event_id"])
            existing[key] = {
                "query_id": decomposition["query_id"],
                "event_id": event["event_id"],
                "event_text": event["text"],
                "event_text_sha256": sha256_text(event["text"]),
                "instruction": QUERY_INSTRUCTION,
                "results": results,
                "model_snapshot": str(args.model_snapshot),
                "collection": args.collection,
                "anns_field": "qwen_vl",
                "metric_type": "COSINE",
                "limit": args.limit,
                "nprobe": args.nprobe,
                "ground_truth_used": False,
                "elapsed_s": batch_elapsed,
            }
        jsonl_write(ranking_path, [existing[item] for item in sorted(existing)])
        end_index = min(batch_start + batch_size, len(pending))
        print(f"search [{batch_start + 1}-{end_index}/{len(events)}] batch={len(batch)} elapsed={batch_elapsed}s", flush=True)
    write_json(out / "surface_manifest.json", {
        "model_snapshot": str(args.model_snapshot),
        "model_config_sha256": sha256_file(args.model_snapshot / "config.json") if (args.model_snapshot / "config.json").exists() else None,
        "transformers": __import__("transformers").__version__,
        "pymilvus": pymilvus.__version__,
        "torch": torch.__version__,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "instruction": QUERY_INSTRUCTION,
        "collection": args.collection,
        "anns_field": "qwen_vl",
        "reembedding": False,
        "production_retrieval_rewrite": False,
        "event_queries": len(existing),
        "elapsed_s": round(time.time() - started, 3),
    })


def independent_max(event_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str | None, str], dict[str, Any]] = {}
    for event_row in event_rows:
        event_id = event_row["event_id"]
        for result in event_row.get("results") or []:
            key = (video_id(result), source_frame_id(result))
            score = result.get("distance")
            if score is None:
                continue
            candidate = dict(result)
            candidate["evidence_event_ids"] = [event_id]
            candidate["evidence_events"] = [event_id]
            old = best.get(key)
            if old is None or float(score) > float(old.get("distance", -math.inf)):
                best[key] = candidate
            elif float(score) == float(old.get("distance", -math.inf)):
                old["evidence_event_ids"] = sorted(set(old["evidence_event_ids"]) | {event_id})
                old["evidence_events"] = old["evidence_event_ids"]
    results = sorted(best.values(), key=lambda item: (-float(item.get("distance", -math.inf)), item.get("source_frame_id", "")))
    for rank, result in enumerate(results, 1):
        result["rank"] = rank
    return results


def ordered_chain(event_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    per_event: list[dict[str, list[dict[str, Any]]]] = []
    for event_row in event_rows:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for result in event_row.get("results") or []:
            vid = video_id(result)
            if vid and frame_number(result) is not None and result.get("distance") is not None:
                grouped[vid].append(result)
        for values in grouped.values():
            values.sort(key=lambda item: (frame_number(item), -float(item.get("distance", -math.inf))))
        per_event.append(grouped)
    videos = set().union(*(set(grouped) for grouped in per_event)) if per_event else set()
    chains: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for vid in sorted(videos):
        states: list[dict[str, Any]] = []
        completed_events = 0
        for event_index, grouped in enumerate(per_event):
            candidates = grouped.get(vid, [])
            if event_index == 0:
                states = [{"path": [candidate], "score": float(candidate["distance"])} for candidate in candidates]
                completed_events = 1 if states else 0
                continue
            next_states: list[dict[str, Any]] = []
            for candidate in candidates:
                current_frame = frame_number(candidate)
                compatible = [state for state in states if frame_number(state["path"][-1]) is not None and frame_number(state["path"][-1]) < current_frame]
                if compatible:
                    best = max(compatible, key=lambda state: (sum(float(item["distance"]) for item in state["path"]) / len(state["path"]), -frame_number(state["path"][-1])))
                    next_states.append({"path": best["path"] + [candidate], "score": (sum(float(item["distance"]) for item in best["path"]) + float(candidate["distance"])) / (len(best["path"]) + 1)})
            states = next_states
            if not states:
                break
            completed_events = event_index + 1
        if states:
            best = max(states, key=lambda state: (state["score"], -frame_number(state["path"][-1])))
            path = best["path"]
            chains.append({
                "video_id": vid,
                "frame_id": path[-1].get("frame_id"),
                "source_frame_id": source_frame_id(path[-1]),
                "distance": best["score"],
                "score": best["score"],
                "rank": 0,
                "chain_complete": True,
                "chain": path,
                "evidence_event_ids": [item.get("event_id") for item in path],
                "ordering": "strict_increasing_frame",
            })
        else:
            partial.append({"video_id": vid, "max_completed_events": completed_events})
    chains.sort(key=lambda item: (-float(item["distance"]), item["video_id"]))
    for rank, chain in enumerate(chains, 1):
        chain["rank"] = rank
    return chains, {"videos_considered": len(videos), "complete_chains": len(chains), "partial_or_failed_videos": partial}


def event_diagnostics(event_rows: list[dict[str, Any]], row: dict[str, Any], k: int) -> dict[str, Any]:
    expected_videos = accepted_videos(row)
    expected_ranges = truth_intervals(row)
    per_event = []
    for event_row in event_rows:
        top = event_row.get("results", [])[:k]
        per_event.append({
            "event_id": event_row["event_id"],
            "video_hit": any(video_id(item) in expected_videos for item in top),
            "range_hit": any(range_hit(item, row) for item in top),
            "top_video_ids": sorted({video_id(item) for item in top if video_id(item)}),
        })
    return {"event_count": len(event_rows), "truth_video_count": len(expected_videos), "truth_interval_count": len(expected_ranges), "per_event": per_event, "all_event_video_hit": bool(per_event) and all(item["video_hit"] for item in per_event), "all_event_range_hit": bool(per_event) and all(item["range_hit"] for item in per_event)}


def score_run(args: argparse.Namespace) -> None:
    out = args.out_dir
    controls = jsonl_read(out / "control_113.jsonl")
    decompositions = {row["query_id"]: row for row in jsonl_read(out / "decompositions_113.jsonl")}
    event_rows = {}
    if (out / "event_rankings.jsonl").exists():
        for row in jsonl_read(out / "event_rankings.jsonl"):
            event_rows.setdefault(row["query_id"], []).append(row)
    scored: list[dict[str, Any]] = []
    for row in controls:
        qid = row["query_id"]
        decomposition = decompositions[qid]
        eligible = bool(decomposition.get("eligible_for_ordered_search"))
        expected_event_ids = {event["event_id"] for event in decomposition.get("events") or []}
        events = [
            item for item in event_rows.get(qid, [])
            if item.get("event_id") in expected_event_ids and item.get("instruction") == QUERY_INSTRUCTION
        ]
        events.sort(key=lambda item: item["event_id"])
        baseline = normalize_rankings(row.get("baseline_results") or [])
        result: dict[str, Any] = {
            "query_id": qid,
            "operational_phase": row.get("operational_phase"),
            "task_type": row.get("task_type"),
            "scoreability": row.get("scoreability", {}),
            "capability_tags": row.get("capability_tags", []),
            "truth_status": row.get("truth_status"),
            "eligible": eligible,
            "event_count": len(decomposition.get("events") or []),
            "event_rankings_present": len(events),
            "baseline": {"metrics": metrics(baseline, row)},
            "variants": {},
            "diagnostics": {},
        }
        for k in (20, 50, 100):
            result["diagnostics"][f"events_at_{k}"] = event_diagnostics(events, row, k) if events else None
        if eligible and len(events) == len(decomposition.get("events") or []):
            independent = independent_max(events)
            chain, chain_diag = ordered_chain(events)
            result["variants"]["independent_max"] = {f"R@{k}": metrics(independent[:k], row) for k in (20, 50, 100)}
            result["variants"]["ordered_chain"] = {f"R@{k}": metrics(chain[:k], row) for k in (1, 5, 20)}
            result["variants"]["ordered_chain"]["chain_diagnostics"] = chain_diag
            result["candidate_counts"] = {"independent_max": len(independent), "ordered_chain": len(chain)}
            result["top_results"] = {"independent_max": independent[:100], "ordered_chain": chain[:100]}
        else:
            result["not_run_reason"] = "no_live_event_rankings" if eligible else "not_temporal_eligible"
        scored.append(result)

    jsonl_write(out / "scored_variants.jsonl", scored)
    summaries: dict[str, Any] = {"control_113": {"n": len(scored)}}
    for arm, getter in [("baseline", lambda item: item["baseline"]["metrics"]), ("independent_max@20", lambda item: (item.get("variants", {}).get("independent_max", {}).get("R@20") or {})), ("ordered_chain@20", lambda item: (item.get("variants", {}).get("ordered_chain", {}).get("R@20") or {}))]:
        arm_rows = [{"eligible": item["eligible"], "metrics": getter(item)} for item in scored if getter(item)]
        summaries[arm] = {field: metric_summary(arm_rows, field, eligible_only=(arm != "baseline")) for field in ("video_R@1", "video_R@5", "video_R@20", "range_R@1", "range_R@5", "range_R@20")}
    live_ids = {
        item["query_id"] for item in scored
        if item["eligible"] and item["event_rankings_present"] == item["event_count"]
    }
    live_baseline_rows = [
        {"eligible": item["eligible"], "metrics": item["baseline"]["metrics"]}
        for item in scored if item["query_id"] in live_ids
    ]
    summaries["baseline_live_subset"] = {
        field: metric_summary(live_baseline_rows, field, eligible_only=False)
        for field in ("video_R@1", "video_R@5", "video_R@20", "range_R@1", "range_R@5", "range_R@20")
    }
    write_json(out / "arm_summaries.json", summaries)
    write_report(args, controls, decompositions, scored, summaries)


def write_report(args: argparse.Namespace, controls: list[dict[str, Any]], decompositions: dict[str, Any], scored: list[dict[str, Any]], summaries: dict[str, Any]) -> None:
    out = args.out_dir
    eligible = [row for row in scored if row["eligible"]]
    live = [row for row in eligible if row["event_rankings_present"] == row["event_count"]]
    live_query_ids = [row["query_id"] for row in live]
    live_non_range_scoreable = sum(not bool(row.get("scoreability", {}).get("range")) for row in live)
    parity = {}
    parity_path = out / "surface_parity.json"
    if parity_path.exists():
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
    lines = [
        "# Temporal sequence retrieval v1 (Vecna issue #79)",
        "",
        "This is an experiment-side comparison over the existing Qwen frame embedding surface. It does not change production retrieval, create ground truth, or re-embed the corpus.",
        "",
        f"- Control: {len(controls)} rows = {sum(row.get('operational_phase') != 'P3' for row in controls)} frozen P0-P2 + {sum(row.get('operational_phase') == 'P3' for row in controls)} provisional P3.",
        f"- Exclusions: `p0_q15`, `p3_q09`.",
        f"- Query-only decompositions: {len(decompositions)}; temporal-eligible: {len(eligible)}; live complete: {len(live)}.",
        f"- Live comparison subset: {', '.join(live_query_ids)}; the other {len(eligible) - len(live)} eligible rows have no live event streams.",
        f"- Range-score caveat: {live_non_range_scoreable}/{len(live)} live rows are TRAKE/video-only and have no reviewed frame-range truth; range recall is not a temporal-truth measure for those rows.",
        f"- Search surface: `{args.collection}` / `qwen_vl`, top-{args.limit}, `nprobe={args.nprobe}`.",
        f"- Model surface: `{args.model_snapshot}`; device is recorded in `surface_manifest.json`.",
        f"- Surface parity: `{parity.get('parity_status', 'not-run')}`; top-20 overlap={parity.get('top20_overlap_fraction')}.",
        "",
        "## Reproduction commands",
        "",
        "```powershell",
        f"py -3.12 aic51-src/script/temporal_sequence_v1.py --stage build --out-dir {args.out_dir}",
        f"py -3.12 aic51-src/script/temporal_sequence_v1.py --stage search --out-dir {args.out_dir} --query-ids {','.join(live_query_ids)} --encode-batch-size 4",
        f"py -3.12 aic51-src/script/temporal_sequence_v1.py --stage score --out-dir {args.out_dir}",
        "```",
        "",
        "## Arm summary",
        "",
        "| arm | n | video R@1 | video R@5 | video R@20 | range R@20 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm in ("baseline", "baseline_live_subset", "independent_max@20", "ordered_chain@20"):
        summary = summaries.get(arm, {})
        def recall(field: str) -> str:
            value = summary.get(field, {}).get("recall")
            return "n/a" if value is None else f"{value:.3f}"
        lines.append(f"| {arm} | {summary.get('video_R@20', {}).get('n', 0)} | {recall('video_R@1')} | {recall('video_R@5')} | {recall('video_R@20')} | {recall('range_R@20')} |")
    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "Independent-max is an unordered union of per-event ranked frames. Ordered-chain emits one result per video only when one hit per event can be selected with strictly increasing frame numbers; its score is the mean event cosine distance. These choices are fixed in code and are not tuned against ground truth.",
        "",
        "P3 truth is provisional source-text evidence and historical TRAKE truth remains development evidence. Results are therefore a retrieval diagnostic, not an organizer score. Inspect `scored_variants.jsonl`, `event_rankings.jsonl`, and `mapping_ledger.jsonl` before making a claim.",
        "",
        "If surface parity is `diagnostic_mismatch`, the independent-max and ordered-chain numbers are diagnostic only and must not be interpreted as a valid comparison against the saved baseline.",
        "",
    ])
    (out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(out / "run_manifest.json", {
        "experiment": "temporal-sequence-retrieval-v1",
        "issue": 79,
        "created_by": "aic51-src/script/temporal_sequence_v1.py",
        "control": str(out / "control_113.jsonl"),
        "decompositions": str(out / "decompositions_113.jsonl"),
        "event_rankings": str(out / "event_rankings.jsonl"),
        "live_query_ids": live_query_ids,
        "live_event_count": sum(row["event_rankings_present"] for row in live),
        "surface_parity": parity,
        "ground_truth_used_for_search": False,
        "no_full_corpus_reembedding": True,
        "no_production_retrieval_rewrite": True,
        "args": {key: str(value) for key, value in vars(args).items()},
    })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("build", "search", "score", "all"), default="all")
    parser.add_argument("--official-root", type=Path, default=OFFICIAL_ROOT)
    parser.add_argument("--control-root", type=Path, default=CONTROL_ROOT)
    parser.add_argument("--historical-root", type=Path, default=HISTORICAL_ROOT)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "benchmark-results/temporal-sequence-v1")
    parser.add_argument("--model-snapshot", type=Path, default=MODEL_SNAPSHOT)
    parser.add_argument("--milvus-uri", default="http://127.0.0.1:19530")
    parser.add_argument("--collection", default="official_l21_l30_all_v2")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--nprobe", type=int, default=32)
    parser.add_argument("--query-ids", default="", help="comma-separated eligible query IDs for a bounded search")
    parser.add_argument("--encode-batch-size", type=int, default=4, help="independent event texts per model call")
    parser.add_argument("--parity-query", default="p3_q01", help="full-query parity diagnostic ID")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.stage in ("build", "all"):
        build_control(args)
        print(f"built 113-query control at {args.out_dir}")
    if args.stage in ("search", "all"):
        run_search(args)
    if args.stage in ("score", "all"):
        score_run(args)
        print(f"scored temporal variants at {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
