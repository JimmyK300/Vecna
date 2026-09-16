#!/usr/bin/env python3
"""Matched Vecna82 temporal experiment: plan by default; encode/score opt-in.

Exactly eight frozen queries, current top-three candidate identities, and three
matched arms. Encode reads no truth and writes only its new output directory.
Score requires every query/candidate/arm before loading frozen truth. Model
weights never download; all actual shards are hashed before inference.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time

QUERY_IDS = ("p0_q22", "p0_q23", "p0_q24", "p1_q25", "p2_q29", "p2_q30", "p3_q21", "p3_q34")
ARMS = ("single_center", "contact_sheet", "native3")
OFFSETS = (-60, 0, 60)
QUERY_INSTRUCTION = "Retrieve images or text relevant to the user's query."
IMAGE_INSTRUCTION = "Represent the user's input."
REVISION = "9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda"
CONFIG_SHA = "9172f55b0b9cce70b7f67b10c58a408ccf3ec15c587e6efd4d5f41631237fded"
CURRENT_SHA = "85d5dd169bcd6934ebfa8435b6aee82ce9bc149bac3a704afbdbcb4b986568f0"
LEGACY_CANDIDATES_SHA = "50784b4d23fa68ec2c73cfc25d92f686aee4e436afd091912e9ef1b95fa88890"
TRUTH_SHA = "63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f"
SCORER_SHA = "82cbc5d7f5b6309f747165f8f278d4c3b66e9db83092c1808d2f72d1f8e76316"
PREPROCESSING = {"mode": "RGB", "tile_size": [384, 216], "resize": "PIL.Image.Resampling.LANCZOS",
                 "sheet_layout": "three tiles left-to-right", "max_length": 8192,
                 "dtype": "torch.float32", "device": "cpu", "threads": 6}


def now():
    return datetime.now(timezone.utc).isoformat()


def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def hash_file(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def file_record(path):
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": hash_file(path)}


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_row(path, value):
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def unique_index(rows, key):
    result = {}
    for row in rows:
        value = key(row)
        if value in result:
            raise ValueError("Duplicate record identity: " + str(value))
        result[value] = row
    return result


def local_path(value):
    path = Path(value)
    if path.exists() or os.name == "nt":
        return path
    if len(value) > 2 and value[1] == ":":
        return Path("/mnt") / value[0].lower() / value[3:].replace("\\", "/")
    return path


def source_id(row):
    value = str(row.get("source_frame_id") or row["frame_id"])
    if "#" in value:
        video, frame = value.rsplit("#", 1)
    else:
        video, frame = row["video_id"], value
    return f"{video}#{int(frame):06d}"


def build_plan(current_rows, cached_rows):
    current = unique_index(current_rows, lambda row: row["query_id"])
    cached = unique_index(
        [row for row in cached_rows if row["window_spec"] == "w3_d60" and row["status"] == "ready"],
        lambda row: (row["query_id"], row["video_id"], int(row["center_frame_id"])))
    queries, candidates = [], []
    for qid in QUERY_IDS:
        row = current[qid]
        text = row["query"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Missing frozen query text: " + qid)
        queries.append({"query_id": qid, "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
        pool = row["candidates_top100"][:3]
        if len(pool) != 3 or len({source_id(item) for item in pool}) != 3:
            raise ValueError("Expected three distinct frozen candidate identities: " + qid)
        for rank, item in enumerate(pool, 1):
            identity = source_id(item)
            video, frame = identity.rsplit("#", 1)
            center = int(frame)
            historical = cached.get((qid, video, center))
            if historical is None:
                raise ValueError("No exact cached frame window for current candidate: " + qid + " " + identity)
            frames = historical["frames"]
            if len(frames) != 3 or [entry["offset"] for entry in frames] != list(OFFSETS):
                raise ValueError("Cached temporal offsets/order mismatch")
            if [entry["frame_id"] for entry in frames] != [center + offset for offset in OFFSETS]:
                raise ValueError("Cached frame IDs mismatch")
            if [source_id(entry) for entry in frames] != [f"{video}#{center + offset:06d}" for offset in OFFSETS]:
                raise ValueError("Cached video/frame identity mismatch")
            candidates.append({"candidate_key": qid + "|" + identity, "query_id": qid,
                "source_frame_id": identity, "video_id": video, "center_frame_id": center,
                "current_baseline_rank": rank, "legacy_candidate_id": historical["candidate_id"],
                "frames": [{key: entry[key] for key in ("source_frame_id", "video_id", "frame_id", "offset", "path")} for entry in frames]})
    return {"schema_version": 1, "experiment": "vecna82-temporal-matched-v1", "query_ids": list(QUERY_IDS),
        "queries": queries, "candidates": candidates, "arms": list(ARMS), "preprocessing": PREPROCESSING,
        "model_revision": REVISION, "model_config_sha256": CONFIG_SHA,
        "query_instruction": QUERY_INSTRUCTION, "image_instruction": IMAGE_INSTRUCTION,
        "selection": "frozen current top-three candidate identities for eight prespecified queries",
        "ground_truth_used_for_selection": False, "historical_embeddings_reused": False,
        "expected_query_embeddings": 8, "expected_image_embeddings": 72}


def input_fingerprint(candidate, arm):
    return hash_json({"candidate_key": candidate["candidate_key"], "arm": arm,
        "ordered_frame_source_ids": [entry["source_frame_id"] for entry in candidate["frames"]],
        "frame_file_sha256": candidate.get("frame_file_sha256", []), "preprocessing": PREPROCESSING})


def validate_records(plan, query_records, embedding_records, run_fingerprint, *, complete):
    if plan["query_ids"] != list(QUERY_IDS) or plan["arms"] != list(ARMS):
        raise ValueError("Experiment query/arm contract changed")
    queries = unique_index(query_records, lambda row: row["query_id"])
    embeddings = unique_index(embedding_records, lambda row: (row["candidate_key"], row["arm"]))
    expected_queries = {row["query_id"]: row for row in plan["queries"]}
    expected_candidates = unique_index(plan["candidates"], lambda row: row["candidate_key"])
    counts = {qid: sum(row["query_id"] == qid for row in plan["candidates"]) for qid in QUERY_IDS}
    if set(expected_queries) != set(QUERY_IDS) or counts != dict.fromkeys(QUERY_IDS, 3):
        raise ValueError("Plan must contain all eight queries and three candidates per query")
    expected_keys = {(key, arm) for key in expected_candidates for arm in ARMS}
    if set(queries) - set(expected_queries) or set(embeddings) - expected_keys:
        raise ValueError("Unexpected query/candidate/arm record")
    if complete and (set(queries) != set(expected_queries) or set(embeddings) != expected_keys):
        raise ValueError("Incomplete paired experiment: requires 8 query vectors and all 72 candidate/arm vectors")
    for row in list(queries.values()) + list(embeddings.values()):
        if row["run_fingerprint"] != run_fingerprint:
            raise ValueError("Stale run fingerprint")
        vector = row["vector"]
        if len(vector) != 2048 or not all(math.isfinite(value) for value in vector):
            raise ValueError("Invalid embedding dimensions or nonfinite values")
        if abs(math.sqrt(sum(value * value for value in vector)) - 1) > 1e-4:
            raise ValueError("Expected normalized float32 embedding")
    for qid, row in queries.items():
        if row["query_text_sha256"] != expected_queries[qid]["text_sha256"]:
            raise ValueError("Stale query text")
    for (key, arm), row in embeddings.items():
        candidate = expected_candidates[key]
        if row["frame_source_ids"] != [entry["source_frame_id"] for entry in candidate["frames"]]:
            raise ValueError("Stale or reordered frame identity")
        if row["input_fingerprint"] != input_fingerprint(candidate, arm):
            raise ValueError("Stale image input fingerprint")


def validate_complete(plan, query_records, embedding_records, run_fingerprint):
    validate_records(plan, query_records, embedding_records, run_fingerprint, complete=True)


def rank_candidates(plan, query_records, embedding_records, arm, run_fingerprint):
    validate_complete(plan, query_records, embedding_records, run_fingerprint)
    if arm not in ARMS:
        raise ValueError("Unknown arm")
    qvectors = {row["query_id"]: row["vector"] for row in query_records}
    embeddings = {(row["candidate_key"], row["arm"]): row for row in embedding_records}
    output = {}
    for qid in QUERY_IDS:
        ranked = []
        for candidate in plan["candidates"]:
            if candidate["query_id"] != qid:
                continue
            vector = embeddings[(candidate["candidate_key"], arm)]["vector"]
            score = sum(a * b for a, b in zip(qvectors[qid], vector))
            ranked.append({"candidate_key": candidate["candidate_key"], "video_id": candidate["video_id"],
                "frame_id": candidate["center_frame_id"], "source_frame_id": candidate["source_frame_id"],
                "score": score, "distance": score, "current_baseline_rank": candidate["current_baseline_rank"],
                "window_frame_ids": [entry["frame_id"] for entry in candidate["frames"]]})
        ranked.sort(key=lambda row: (-row["score"], row["source_frame_id"]))
        for rank, row in enumerate(ranked, 1):
            row["rank"] = rank
        output[qid] = ranked
    return output


def read_plan_inputs(args):
    if hash_file(args.current_candidates) != CURRENT_SHA:
        raise ValueError("Current frozen candidate export checksum mismatch")
    if args.cached_candidates.suffix == ".jsonl":
        if hash_file(args.cached_candidates) != LEGACY_CANDIDATES_SHA:
            raise ValueError("Legacy cached candidate manifest checksum mismatch")
        cached = read_rows(args.cached_candidates)
    else:
        probe = json.loads(args.cached_candidates.read_text(encoding="utf-8"))
        declared = [row for row in probe["sources"] if row["path"].replace("\\", "/").endswith("/stage2b_candidates.jsonl")]
        if len(declared) != 1 or declared[0]["sha256"] != LEGACY_CANDIDATES_SHA:
            raise ValueError("Cached processor evidence has a different candidate source")
        cached = probe["candidate_rows"]
    plan = build_plan(read_rows(args.current_candidates), cached)
    plan["sources"] = [file_record(args.current_candidates), file_record(args.cached_candidates)]
    return plan


def ensure_new_output(out, protected, resume):
    resolved = out.resolve()
    for path in protected:
        target = path.resolve()
        if resolved == target or resolved in target.parents or target in resolved.parents:
            raise ValueError("Output must be isolated from source/model/cache directories")
    if out.exists() and any(out.iterdir()) and not resume:
        raise ValueError("Output directory is not empty; use a new directory or explicit --resume")
    if out.exists() and any(out.iterdir()) and resume and not (out / "run_manifest.json").exists():
        raise ValueError("Resume requires this experiment's existing run manifest")
    out.mkdir(parents=True, exist_ok=True)


def load_model(snapshot):
    import torch
    from transformers.models.qwen3_vl.modeling_qwen3_vl import Qwen3VLModel, Qwen3VLPreTrainedModel

    class Qwen3VLEmbedding(Qwen3VLPreTrainedModel):
        _checkpoint_conversion_mapping = {}
        accepts_loss_kwargs = False

        def __init__(self, config):
            super().__init__(config)
            self.model = Qwen3VLModel(config)
            self.post_init()

        def get_input_embeddings(self):
            return self.model.get_input_embeddings()

        def set_input_embeddings(self, value):
            return self.model.set_input_embeddings(value)

        def get_decoder(self):
            return self.model.get_decoder()

        def set_decoder(self, value):
            return self.model.set_decoder(value)

        def forward(self, **kwargs):
            return self.model(**kwargs)

    model, info = Qwen3VLEmbedding.from_pretrained(snapshot, dtype=torch.float32,
        low_cpu_mem_usage=True, local_files_only=True, output_loading_info=True)
    if any(info.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
        raise ValueError("Model checkpoint does not load exactly: " + json.dumps(info))
    return model.eval(), info


def processor_inputs(processor, *, text=None, images=None):
    instruction = QUERY_INSTRUCTION if text is not None else IMAGE_INSTRUCTION
    content = [{"type": "text", "text": text}] if text is not None else [{"type": "image", "image": image} for image in images]
    conversation = [{"role": "system", "content": [{"type": "text", "text": instruction}]}, {"role": "user", "content": content}]
    # Query template/tokenization matches the original query instruction and
    # add_generation_prompt=True path. Single-row calls avoid padding ambiguity.
    if text is not None:
        return processor.apply_chat_template([conversation], add_generation_prompt=True,
            tokenize=True, return_dict=True, return_tensors="pt", padding=True)
    rendered = processor.apply_chat_template([conversation], add_generation_prompt=True, tokenize=False)
    return processor(text=rendered, images=images, truncation=True, max_length=8192, padding=True, return_tensors="pt")


def encode_vector(torch, model, inputs):
    start = time.perf_counter()
    with torch.inference_mode():
        outputs = model(**inputs)
        hidden = outputs.last_hidden_state
        mask = inputs["attention_mask"]
        last = mask.shape[1] - 1 - mask.flip(dims=[1]).argmax(dim=1)
        vector = torch.nn.functional.normalize(hidden[torch.arange(hidden.shape[0]), last], p=2, dim=1)
        values = vector[0].detach().cpu().float().tolist()
    return values, time.perf_counter() - start


def encode(args, plan):
    if args.output_dir is None or args.model_snapshot is None:
        raise ValueError("encode requires --output-dir and --model-snapshot")
    snapshot = args.model_snapshot
    if snapshot.name != REVISION or hash_file(snapshot / "config.json") != CONFIG_SHA:
        raise ValueError("Frozen model snapshot/config mismatch")
    frame_paths = [local_path(frame["path"]) for candidate in plan["candidates"] for frame in candidate["frames"]]
    protected = [snapshot, args.current_candidates.parent, args.cached_candidates.parent] + [path.parent for path in frame_paths]
    ensure_new_output(args.output_dir, protected, args.resume)
    out = args.output_dir
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "USE_TF": "0", "TRANSFORMERS_NO_TF": "1"})
    import torch
    import transformers
    import PIL
    from PIL import Image
    from transformers import Qwen3VLProcessor

    torch.set_num_threads(6)
    shard_paths = sorted(snapshot.glob("*.safetensors"))
    if not shard_paths:
        raise ValueError("No cached safetensors weights present")
    manifest_paths = sorted({*shard_paths, *snapshot.glob("*.json"), *snapshot.glob("*.txt"), *snapshot.glob("*.jinja")})
    model_sources = [file_record(path) for path in manifest_paths]
    for candidate in plan["candidates"]:
        candidate["frame_file_sha256"] = [hash_file(local_path(frame["path"])) for frame in candidate["frames"]]
    environment = {"python": sys.version, "platform": platform.platform(), "torch": torch.__version__,
        "transformers": transformers.__version__, "pillow": PIL.__version__, "num_threads": torch.get_num_threads(),
        "cpu_capability": torch.backends.cpu.get_cpu_capability(), "cuda_available": torch.cuda.is_available()}
    code_source = file_record(Path(__file__))
    fingerprint = hash_json({"plan": plan, "model_sources": model_sources, "environment": environment, "code": code_source})
    manifest = {"status": "prepared", "run_fingerprint": fingerprint, "started_at": now(), "plan": plan,
        "model_sources": model_sources, "environment": environment, "code": code_source,
        "truth_loaded": False, "ground_truth_used_for_selection": False, "old_embeddings_reused": False,
        "supervisor_wall_budget_s": args.max_seconds, "query_embeddings_completed": 0, "image_embeddings_completed": 0}
    query_path, image_path = out / "query_embeddings.jsonl", out / "image_embeddings.jsonl"
    if args.resume and (out / "run_manifest.json").exists():
        old = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
        if old["run_fingerprint"] != fingerprint:
            raise ValueError("Resume fingerprint mismatch; create a new isolated output directory")
        manifest["previous_started_at"] = old["started_at"]
    queries = read_rows(query_path) if query_path.exists() else []
    embeddings = read_rows(image_path) if image_path.exists() else []
    validate_records(plan, queries, embeddings, fingerprint, complete=False)
    write_json(out / "plan.json", plan)
    write_json(out / "run_manifest.json", manifest)
    print(json.dumps({"status": "loading_model", "run_fingerprint": fingerprint, "output_dir": str(out)}), flush=True)
    started = time.perf_counter()
    last_candidate = None
    try:
        model_start = time.perf_counter()
        model, loading = load_model(snapshot)
        manifest["model_load_s"] = time.perf_counter() - model_start
        manifest["model_loading_info"] = loading
        manifest["actual_parameter_device"] = str(next(model.parameters()).device)
        manifest["actual_parameter_dtype"] = str(next(model.parameters()).dtype)
        if manifest["actual_parameter_device"] != "cpu" or manifest["actual_parameter_dtype"] != "torch.float32":
            raise ValueError("Actual model device/dtype differs from the declared matched CPU float32 policy")
        processor = Qwen3VLProcessor.from_pretrained(snapshot, local_files_only=True)
        manifest["status"] = "in_progress"
        write_json(out / "run_manifest.json", manifest)

        def budget_gate():
            if time.perf_counter() - started >= args.max_seconds:
                raise TimeoutError("Between-forward budget reached; resume this exact fingerprint only")

        existing_queries = {row["query_id"] for row in queries}
        for query in plan["queries"]:
            if query["query_id"] in existing_queries:
                continue
            budget_gate()
            row_start = time.perf_counter()
            inputs = processor_inputs(processor, text=query["text"])
            if inputs["input_ids"].shape[1] >= 8192:
                raise ValueError("Query exceeds the frozen token budget")
            vector, elapsed = encode_vector(torch, model, inputs)
            row = {"query_id": query["query_id"], "query_text_sha256": query["text_sha256"], "vector": vector,
                "run_fingerprint": fingerprint, "instruction": QUERY_INSTRUCTION, "forward_pool_s": elapsed,
                "row_wall_s": time.perf_counter() - row_start, "sequence_tokens": int(inputs["input_ids"].shape[1])}
            append_row(query_path, row)
            queries.append(row)
            manifest["query_embeddings_completed"] = len(queries)
            write_json(out / "run_manifest.json", manifest)
            print(json.dumps({"query_id": row["query_id"], "query_forward_pool_s": elapsed}), flush=True)
        existing_images = {(row["candidate_key"], row["arm"]) for row in embeddings}
        for candidate in plan["candidates"]:
            last_candidate = candidate["candidate_key"]
            if all((last_candidate, arm) in existing_images for arm in ARMS):
                continue
            tiles = []
            for frame, expected_hash in zip(candidate["frames"], candidate["frame_file_sha256"]):
                path = local_path(frame["path"])
                if hash_file(path) != expected_hash:
                    raise ValueError("Frame file changed after plan hashing")
                with Image.open(path) as image:
                    tiles.append(image.convert("RGB").resize((384, 216), Image.Resampling.LANCZOS))
            sheet = Image.new("RGB", (1152, 216))
            for index, tile in enumerate(tiles):
                sheet.paste(tile, (384 * index, 0))
            arm_images = {"single_center": [tiles[1]], "contact_sheet": [sheet], "native3": tiles}
            for arm in ARMS:
                if (last_candidate, arm) in existing_images:
                    continue
                budget_gate()
                row_start = time.perf_counter()
                inputs = processor_inputs(processor, images=arm_images[arm])
                grid = inputs["image_grid_thw"].tolist()
                image_tokens = [math.prod(value) // int(processor.image_processor.merge_size) ** 2 for value in grid]
                token_id = processor.tokenizer.convert_tokens_to_ids("<|image_pad|>")
                retained_image_tokens = int((inputs["input_ids"] == token_id).sum())
                expected_count = 3 if arm == "native3" else 1
                if len(grid) != expected_count or retained_image_tokens != sum(image_tokens):
                    raise ValueError("Native image/grid count or token-retention proof failed")
                if sum(image_tokens) != (84 if arm == "single_center" else 252):
                    raise ValueError("Processor visual budget differs from the matched proof")
                vector, elapsed = encode_vector(torch, model, inputs)
                row = {"candidate_key": last_candidate, "arm": arm, "run_fingerprint": fingerprint,
                    "input_fingerprint": input_fingerprint(candidate, arm), "frame_source_ids": [frame["source_frame_id"] for frame in candidate["frames"]],
                    "vector": vector, "instruction": IMAGE_INSTRUCTION, "forward_pool_s": elapsed,
                    "row_wall_s": time.perf_counter() - row_start, "image_grid_thw": grid,
                    "image_tokens": image_tokens, "sequence_tokens": int(inputs["input_ids"].shape[1]),
                    "input_pixel_sha256": [hashlib.sha256(image.tobytes()).hexdigest() for image in arm_images[arm]],
                    "actual_parameter_device": manifest["actual_parameter_device"], "actual_parameter_dtype": manifest["actual_parameter_dtype"]}
                append_row(image_path, row)
                embeddings.append(row)
                manifest["image_embeddings_completed"] = len(embeddings)
                manifest["last_candidate_key"] = last_candidate
                write_json(out / "run_manifest.json", manifest)
                print(json.dumps({"candidate_key": last_candidate, "arm": arm, "forward_pool_s": elapsed, "completed": len(embeddings)}), flush=True)
            for image in tiles + [sheet]:
                image.close()
        validate_complete(plan, queries, embeddings, fingerprint)
        manifest["status"] = "complete_unscored"
    except BaseException as exc:
        manifest["status"] = "incomplete"
        manifest["error_type"] = type(exc).__name__
        manifest["error"] = str(exc)
        raise
    finally:
        manifest["last_candidate_key"] = last_candidate
        manifest["query_embeddings_completed"] = len(queries)
        manifest["image_embeddings_completed"] = len(embeddings)
        manifest["run_wall_s"] = time.perf_counter() - started
        manifest["finished_or_checkpointed_at"] = now()
        manifest["query_forward_pool_s"] = sum(row["forward_pool_s"] for row in queries)
        manifest["image_forward_pool_s"] = sum(row["forward_pool_s"] for row in embeddings)
        manifest["artifact_sources"] = [file_record(path) for path in (query_path, image_path) if path.exists()]
        write_json(out / "run_manifest.json", manifest)
    return {"status": manifest["status"], "query_embeddings": len(queries), "image_embeddings": len(embeddings)}


def load_scorer(path):
    spec = importlib.util.spec_from_file_location("matched_frozen_scorer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score_location(items, truth, scorer):
    # Canonical truth uses truth_tier; the pinned scorer's router uses _source.
    # Set it explicitly so historical TRAKE retains its strict all-events rule.
    routed = {**truth, "_source": "historical" if truth["truth_tier"] == "frozen_headless_benchmark_truth" else "p3"}
    raw = scorer.score_query(items, routed)
    return {"recall_at_1": float(raw["recall"]["R@1"]), "mrr_at_20": raw["reciprocal_rank"], "raw": raw}


def score(args):
    if args.output_dir is None or args.truth is None or args.scorer is None:
        raise ValueError("score requires --output-dir, --truth, and --scorer")
    out = args.output_dir
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    plan = manifest["plan"]
    queries, embeddings = read_rows(out / "query_embeddings.jsonl"), read_rows(out / "image_embeddings.jsonl")
    # This gate intentionally precedes even reading the truth path.
    validate_complete(plan, queries, embeddings, manifest["run_fingerprint"])
    if manifest["status"] != "complete_unscored":
        raise ValueError("Only a complete unscored encoding run may be scored")
    for record in manifest["artifact_sources"]:
        artifact_name = record["path"].replace("\\", "/").rsplit("/", 1)[-1]
        if hash_file(out / artifact_name) != record["sha256"]:
            raise ValueError("Completed vector artifact checksum mismatch")
    if hash_file(args.truth) != TRUTH_SHA:
        raise ValueError("Frozen canonical truth checksum mismatch")
    if hash_file(args.scorer) != SCORER_SHA:
        raise ValueError("Frozen scorer implementation checksum mismatch")
    truth = unique_index(read_rows(args.truth), lambda row: row["query_id"])
    scorer = load_scorer(args.scorer)
    query_text = {row["query_id"]: row["text"] for row in plan["queries"]}
    for qid in QUERY_IDS:
        if truth[qid]["query"] != query_text[qid] or not truth[qid].get("scoreable"):
            raise ValueError("Frozen truth query text/scoreability mismatch")
    rankings = {arm: rank_candidates(plan, queries, embeddings, arm, manifest["run_fingerprint"]) for arm in ARMS}
    rows = []
    for qid in QUERY_IDS:
        row = {"query_id": qid, "truth_tier": truth[qid]["truth_tier"], "arms": {}}
        accepted = {str(truth[qid]["accepted_video_id"]).casefold()} if truth[qid].get("accepted_video_id") else {
            str(target["video_id"]).casefold() for group in truth[qid].get("accepted_groups", []) for target in group}
        for arm in ARMS:
            items = rankings[arm][qid]
            first = next((item["rank"] for item in items if item["video_id"].casefold() in accepted), None)
            center = [{**item, "time_line": []} for item in items]
            window = [{**item, "time_line": item["window_frame_ids"]} for item in items]
            row["arms"][arm] = {"pool_video_r1": float(first == 1), "pool_video_mrr": 1 / first if first else 0,
                "pool_video_first_rank": first, "center_only": score_location(center, truth[qid], scorer),
                "equal_three_frame_window": score_location(window, truth[qid], scorer), "ranking": items}
        rows.append(row)
    summary = {"status": "COMPLETE_BOUNDED_PROBE", "paired_queries": 8, "candidates_per_query": 3,
        "model_revision": REVISION, "run_fingerprint": manifest["run_fingerprint"], "arms": {},
        "limits": ["Eight selected development queries; no generalization claim.", "R@5/R@20 over the same three candidates cannot show reranking recall gains.", "Frozen event/localization truth includes submission-derived proxies and provisional P3 targets.", "Center-only and equal-window localization are separate; each arm receives the same scoring opportunity."]}
    for arm in ARMS:
        summary["arms"][arm] = {key: statistics.mean(row["arms"][arm][key] for row in rows) for key in ("pool_video_r1", "pool_video_mrr")}
        for view in ("center_only", "equal_three_frame_window"):
            summary["arms"][arm][view] = {key: statistics.mean(row["arms"][arm][view][key] for row in rows)
                for key in ("recall_at_1", "mrr_at_20")}
        durations = [row["forward_pool_s"] for row in embeddings if row["arm"] == arm]
        summary["arms"][arm]["latency"] = {"count": len(durations), "total_s": sum(durations), "mean_s": statistics.mean(durations), "min_s": min(durations), "max_s": max(durations)}
    deltas = [{"query_id": row["query_id"], "comparisons": {
        arm: {"pool_video_r1": row["arms"][arm]["pool_video_r1"] - row["arms"]["single_center"]["pool_video_r1"],
              "pool_video_mrr": row["arms"][arm]["pool_video_mrr"] - row["arms"]["single_center"]["pool_video_mrr"]}
        for arm in ("contact_sheet", "native3")}} for row in rows]
    pool_present = [row["query_id"] for row in rows if row["arms"]["single_center"]["pool_video_first_rank"] is not None]
    target_counts = {}
    for view in ("center_only", "equal_three_frame_window"):
        ranks = []
        for row in rows:
            raw = row["arms"]["single_center"][view]["raw"]
            ranks.extend(raw.get("event_first_ranks", raw.get("target_ranks", [raw.get("first_correct_rank")])) )
        target_counts[view] = {"observed_target_count": len(ranks), "targets_present_in_sampled_pool": sum(rank is not None for rank in ranks)}
    summary["candidate_pool_ceiling"] = {"accepted_video_present_query_count": len(pool_present),
        "accepted_video_present_query_ids": pool_present, "accepted_video_absent_query_ids": [qid for qid in QUERY_IDS if qid not in pool_present],
        "target_coverage": target_counts,
        "scoring_unit": "Exact sampled frame IDs, not all intervening frames in the temporal interval."}
    summary["paired_native3_vs_contact_sheet"] = {
        key: statistics.mean(row["arms"]["native3"][key] - row["arms"]["contact_sheet"][key] for row in rows)
        for key in ("pool_video_r1", "pool_video_mrr")}
    write_json(out / "scores.json", {"summary": summary, "per_query": rows, "per_query_deltas": deltas,
        "truth_source": file_record(args.truth), "scorer_source": file_record(args.scorer),
        "scoring_driver_source": file_record(Path(__file__)),
        "encoding_driver_source": manifest["code"],
        "similarity": "dot product accumulated as Python float64 over normalized float32 embedding values"})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("plan", "encode", "score"), default="plan")
    parser.add_argument("--current-candidates", type=Path)
    parser.add_argument("--cached-candidates", type=Path)
    parser.add_argument("--model-snapshot", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--truth", type=Path)
    parser.add_argument("--scorer", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-seconds", type=float, default=1800,
        help="Between-forward budget only; use an external supervisor for a hard wall-time cap.")
    args = parser.parse_args()
    if args.max_seconds <= 0:
        parser.error("--max-seconds must be positive")
    if args.action == "score":
        result = score(args)
    else:
        if args.current_candidates is None or args.cached_candidates is None:
            parser.error("plan/encode require --current-candidates and --cached-candidates")
        plan = read_plan_inputs(args)
        result = {"status": "PLAN_ONLY_NO_INFERENCE", "plan": plan} if args.action == "plan" else encode(args, plan)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
