#!/usr/bin/env python3
"""Read-only Stage 2b evidence/processor probe; optional one-candidate CPU timing.

Default mode loads the already cached tokenizer/processor, never model weights.
Default mode prints one JSON object and writes no evidence cache. Optional timing
prints a processor checkpoint followed by a final JSON result (JSONL), so that a
supervisor cap cannot erase the cheap processor evidence. It never downloads.
Timing is explicitly opt-in, isolated from historical embedding caches, and is
not a retrieval-quality experiment. A parent supervisor must enforce its cap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

SNAPSHOT = "9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda"
CONFIG_SHA256 = "9172f55b0b9cce70b7f67b10c58a408ccf3ec15c587e6efd4d5f41631237fded"
INSTRUCTION = "Represent the user's input."
DEFAULT_CANDIDATE = "p3_q34:w3_d60:r001"


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def source_record(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha256_bytes(data)}


def local_path(value):
    path = Path(value)
    if path.exists() or os.name == "nt":
        return path
    # Allow read-only execution from the host WSL Python as well as Windows.
    if len(value) > 2 and value[1] == ":":
        return Path("/mnt") / value[0].lower() / value[3:].replace("\\", "/")
    return path


def tensor_hash(tensor):
    return sha256_bytes(tensor.detach().cpu().contiguous().numpy().tobytes())


def vector_summary(row):
    vector = row.get("vector", [])
    result = {key: value for key, value in row.items() if key != "vector"}
    result.update({
        "vector_dimensions": len(vector),
        "vector_finite": all(math.isfinite(float(value)) for value in vector),
        "vector_l2_norm": math.sqrt(sum(float(value) ** 2 for value in vector)),
        "vector_sha256_json": sha256_bytes(json.dumps(vector, separators=(",", ":"), allow_nan=False).encode()),
    })
    return result


def image_record(path, image):
    return {**source_record(path), "size": list(image.size), "mode": image.mode,
            "rgb_pixels_sha256": sha256_bytes(image.tobytes())}


def prepare_inputs(processor, images):
    conversation = [
        {"role": "system", "content": [{"type": "text", "text": INSTRUCTION}]},
        {"role": "user", "content": [{"type": "image", "image": image} for image in images]},
    ]
    text = processor.apply_chat_template([conversation], add_generation_prompt=True, tokenize=False)
    inputs = processor(text=text, images=images, truncation=True, max_length=8192,
                       padding=True, return_tensors="pt")
    return text, inputs


def processor_record(processor, images):
    import torch

    text, inputs = prepare_inputs(processor, images)
    grid = inputs["image_grid_thw"].tolist()
    patch_counts = [math.prod(value) for value in grid]
    merge_size = int(processor.image_processor.merge_size)
    image_token_id = processor.tokenizer.convert_tokens_to_ids("<|image_pad|>")
    ids = inputs["input_ids"][0].tolist()
    spans = []
    for position, token in enumerate(ids):
        if token == image_token_id:
            if spans and spans[-1][1] == position:
                spans[-1][1] += 1
            else:
                spans.append([position, position + 1])
    expected_tokens = [count // (merge_size ** 2) for count in patch_counts]
    patch_order_matches_individual = []
    patch_hashes = []
    position = 0
    for image, count in zip(images, patch_counts):
        individual = processor.image_processor(images=[image], return_tensors="pt")
        chunk = inputs["pixel_values"][position:position + count]
        patch_order_matches_individual.append(torch.equal(chunk, individual["pixel_values"]))
        patch_hashes.append(tensor_hash(chunk))
        position += count
    token_counts = [stop - start for start, stop in spans]
    return {
        "image_count": len(images), "image_sizes": [list(image.size) for image in images],
        "input_pixel_hashes": [sha256_bytes(image.tobytes()) for image in images],
        "image_grid_thw": grid, "merge_size": merge_size,
        "pixel_values_shape": list(inputs["pixel_values"].shape),
        "pixel_values_dtype": str(inputs["pixel_values"].dtype),
        "input_ids_shape": list(inputs["input_ids"].shape),
        "sequence_length": len(ids), "max_length": 8192,
        "image_token_id": image_token_id, "image_token_spans": spans,
        "image_token_counts": token_counts, "expected_image_tokens": expected_tokens,
        "all_image_tokens_present": token_counts == expected_tokens,
        "each_patch_chunk_equals_individual_image_processing": patch_order_matches_individual,
        "ordered_patch_chunk_hashes": patch_hashes,
        "native_order_and_distinctness_proven": (
            len(images) > 1 and len(grid) == len(images)
            and len(set(patch_hashes)) == len(images)
            and all(patch_order_matches_individual) and token_counts == expected_tokens
        ),
        "chat_template_sha256": sha256_bytes(json.dumps(text, ensure_ascii=False).encode()),
        "chat_template_image_placeholders": str(text).count("<|image_pad|>"),
        "model_weights_loaded": False,
    }


def probe(args):
    cache = args.cache_dir
    snapshot = args.model_snapshot
    if snapshot.name != SNAPSHOT:
        raise ValueError("Probe requires the frozen Qwen3-VL-Embedding-2B snapshot")
    config_record = source_record(snapshot / "config.json")
    if config_record["sha256"] != CONFIG_SHA256:
        raise ValueError("Frozen model config hash mismatch")
    candidates_path = cache / "stage2b_candidates.jsonl"
    embeddings_path = cache / "stage2b_embeddings.jsonl"
    candidates = read_rows(candidates_path)
    embeddings = read_rows(embeddings_path)
    selected = [row for row in candidates if row.get("candidate_id") == args.candidate_id]
    if len(selected) != 1 or selected[0]["status"] != "ready":
        raise ValueError("Expected one ready frozen candidate")
    candidate = selected[0]
    if candidate["requested_offsets"] != [-60, 0, 60]:
        raise ValueError("Probe requires original three ordered offsets")
    if [frame["frame_id"] for frame in candidate["frames"]] != [candidate["center_frame_id"] + offset for offset in [-60, 0, 60]]:
        raise ValueError("Frame IDs do not match the frozen offset definition")
    payload = {
        "schema_version": 1, "purpose": "packet-a-processor-proof-and-cache-audit",
        "candidate_id": args.candidate_id, "candidate": candidate,
        "sources": [source_record(candidates_path), source_record(embeddings_path), config_record],
        "candidate_rows": candidates,
        "embedding_rows": [vector_summary(row) for row in embeddings],
        "model_id": "Qwen/Qwen3-VL-Embedding-2B", "model_snapshot": str(snapshot),
        "model_revision": SNAPSHOT, "instruction": INSTRUCTION,
        "network_allowed": False, "ground_truth_used_for_selection": False,
        "selection": {"method": "explicit frozen candidate ID", "baseline_rank": candidate["baseline_center_rank"],
                      "has_cached_native3_embedding": any(row["candidate_id"] == args.candidate_id and row["input_mode"] == "native3" for row in embeddings)},
        "historical_cache_written": False,
    }
    for filename in ("stage2b_surface_manifest.json", "stage2b_prepare_manifest.json", "preprocessor_config.json", "config.json"):
        file = (snapshot if filename in ("preprocessor_config.json", "config.json") else cache) / filename
        payload[filename] = json.loads(file.read_text(encoding="utf-8"))
    if args.inventory_only:
        return payload
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    import torch
    import transformers
    from PIL import Image
    from transformers import Qwen3VLProcessor

    processor = Qwen3VLProcessor.from_pretrained(snapshot, local_files_only=True)
    originals = []
    for frame in candidate["frames"]:
        with Image.open(local_path(frame["path"])) as image:
            originals.append(image.convert("RGB"))
    resized = [image.resize((384, 216), Image.Resampling.LANCZOS) for image in originals]
    with Image.open(local_path(candidate["contact_sheet_path"])) as image:
        sheet = image.convert("RGB")
    reconstructed = Image.new("RGB", (384 * len(resized), 216))
    for index, image in enumerate(resized):
        reconstructed.paste(image, (index * 384, 0))
    payload["frame_images"] = [image_record(local_path(frame["path"]), image) for frame, image in zip(candidate["frames"], originals)]
    payload["contact_sheet_image"] = image_record(local_path(candidate["contact_sheet_path"]), sheet)
    payload["contact_sheet_equals_ordered_resized_frames"] = sheet.size == reconstructed.size and sheet.tobytes() == reconstructed.tobytes()
    payload["runtime"] = {
        "python": sys.version, "torch": torch.__version__, "transformers": transformers.__version__,
        "cuda_available": torch.cuda.is_available(), "num_threads": torch.get_num_threads(),
        "cpu_capability": torch.backends.cpu.get_cpu_capability(),
    }
    modes = {"native3_original": originals, "native3_matched_384x216": resized,
             "contact_sheet_original": [sheet], "single_center_matched_384x216": [resized[1]]}
    payload["processor_proof"] = {mode: processor_record(processor, images) for mode, images in modes.items()}
    if args.time_float32:
        # Import the exact recovered class structure, without calling its BF16 loader.
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

        print(json.dumps({"processor_probe_before_timing": payload}), flush=True)
        torch.set_num_threads(args.threads)
        start = time.perf_counter()
        model = Qwen3VLEmbedding.from_pretrained(snapshot, dtype=torch.float32,
            low_cpu_mem_usage=True, local_files_only=True).eval()
        load_seconds = time.perf_counter() - start
        _, inputs = prepare_inputs(processor, modes[args.timing_mode])
        actual_device = str(next(model.parameters()).device)
        actual_dtype = str(next(model.parameters()).dtype)
        start = time.perf_counter()
        with torch.inference_mode():
            outputs = model(**inputs)
            hidden = outputs.last_hidden_state
            mask = inputs["attention_mask"]
            last_positions = mask.shape[1] - 1 - mask.flip(dims=[1]).argmax(dim=1)
            vector = torch.nn.functional.normalize(hidden[torch.arange(hidden.shape[0]), last_positions], p=2, dim=1)
        payload["float32_timing_smoke"] = {
            "timing_mode": args.timing_mode, "model_load_s": load_seconds,
            "forward_and_pool_s": time.perf_counter() - start,
            "model_device": actual_device, "model_dtype": actual_dtype,
            "num_threads": torch.get_num_threads(), "vector_shape": list(vector.shape),
            "vector_finite": bool(torch.isfinite(vector).all()),
            "vector_l2_norm": float(vector.norm()), "vector_sha256": tensor_hash(vector),
            "quality_result": "not_measured", "cache_written": False,
            "comparability": "changes dtype and input resolution; timing-only, cannot resume old cache",
        }
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--candidate-id", default=DEFAULT_CANDIDATE)
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--time-float32", action="store_true")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--timing-mode", choices=("native3_original", "native3_matched_384x216", "contact_sheet_original", "single_center_matched_384x216"), default="native3_matched_384x216")
    args = parser.parse_args()
    print(json.dumps(probe(args), sort_keys=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
