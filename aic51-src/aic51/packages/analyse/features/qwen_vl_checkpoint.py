"""Load and verify the Qwen3-VL embedding checkpoint through Sentence Transformers.

The released embedding checkpoint prefixes backbone weights with ``model.``;
Transformers 4.57's Qwen3VLModel expects the unprefixed backbone names. Verification
uses the same local checkpoint and compares every tensor in bounded row chunks.
It never loads a second model or changes the Sentence Transformers encode path.
"""
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import re


MODEL_ID = "Qwen/Qwen3-VL-Embedding-2B"
DEFAULT_KEY_MAPPING = {r"^model\.(language_model|visual)\.": r"\1."}


class CheckpointLoadError(RuntimeError):
    """The constructed embedding model does not match its checkpoint."""


def is_qwen3_embedding(pretrained_model: str) -> bool:
    """Limit the workaround to the released 2B model or its local ST snapshot."""
    if pretrained_model == MODEL_ID:
        return True
    directory = Path(pretrained_model)
    config_path = directory / "config.json"
    st_path = directory / "config_sentence_transformers.json"
    if not config_path.is_file() or not st_path.is_file():
        return False
    config = json.loads(config_path.read_text(encoding="utf-8"))
    st_config = json.loads(st_path.read_text(encoding="utf-8"))
    return (
        config.get("model_type") == "qwen3_vl"
        and config.get("text_config", {}).get("hidden_size") == 2048
        and st_config.get("model_type") == "SentenceTransformer"
    )


def prepare_model_kwargs(pretrained_model: str, model_kwargs: dict) -> tuple[dict, bool]:
    """Preserve caller values, including an explicit empty/None key mapping."""
    targeted = is_qwen3_embedding(pretrained_model)
    if not targeted:
        return model_kwargs, False
    result = dict(model_kwargs)
    if "key_mapping" not in result:
        result["key_mapping"] = dict(DEFAULT_KEY_MAPPING)
    return result, True


def checkpoint_routes(checkpoint_shapes: dict, expected_shapes: dict, key_mapping) -> dict:
    """Require a one-to-one, shape-exact route for every checkpoint/model key."""
    routes = {}
    destinations = set()
    for key, shape in checkpoint_shapes.items():
        target = key
        for pattern, replacement in (key_mapping or {}).items():
            target, count = re.subn(pattern, replacement, target)
            if count:
                break  # Matches Transformers' first-matching-pattern semantics.
        if target in destinations:
            raise CheckpointLoadError(f"Checkpoint mapping collision: {target}")
        if target not in expected_shapes:
            raise CheckpointLoadError(f"Checkpoint key has no model destination: {key} -> {target}")
        if tuple(shape) != tuple(expected_shapes[target]):
            raise CheckpointLoadError(f"Checkpoint shape mismatch: {key} -> {target}")
        routes[key] = target
        destinations.add(target)
    missing = set(expected_shapes) - destinations
    if missing:
        raise CheckpointLoadError(f"Checkpoint omits {len(missing)} model tensors: {sorted(missing)[:8]}")
    if not routes:
        raise CheckpointLoadError("Checkpoint contains no model tensors")
    return routes


def _checkpoint_directory(pretrained_model: str, auto_model, model_kwargs: dict) -> Path:
    directory = Path(pretrained_model)
    if not directory.is_dir():
        from huggingface_hub import snapshot_download

        revision = getattr(auto_model.config, "_commit_hash", None)
        if not revision:
            raise CheckpointLoadError("Loaded Qwen model has no exact checkpoint revision")
        directory = Path(snapshot_download(
            repo_id=pretrained_model, revision=revision,
            cache_dir=model_kwargs.get("cache_dir"), local_files_only=True,
        ))
    subfolder = model_kwargs.get("subfolder", "")
    directory = directory / subfolder
    return directory.resolve()


def _checkpoint_files(directory: Path) -> list[Path]:
    single = directory / "model.safetensors"
    index = directory / "model.safetensors.index.json"
    if single.is_file() and not index.is_file():
        return [single]
    if index.is_file() and not single.is_file():
        names = set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values())
        files = [(directory / name).resolve() for name in sorted(names)]
        if not files or any(not p.is_relative_to(directory) or not p.is_file() for p in files):
            raise CheckpointLoadError("Checkpoint shard is missing or outside its snapshot")
        return files
    raise CheckpointLoadError("Expected one unambiguous local safetensors checkpoint")


def verify_loaded_checkpoint(sentence_model, pretrained_model: str, model_kwargs: dict) -> dict:
    """Fail before encoding unless every loaded value equals its checkpoint cast.

    Compare chunks of at most about 4 MiB float32 values (or one tensor row),
    retaining the model's requested dtype/device. All tensor names and shapes
    must match; a finite embedding or constructor completion is not a proof.
    """
    import torch
    from safetensors import safe_open

    auto_model = sentence_model[0].auto_model
    if (
        auto_model.__class__.__name__ != "Qwen3VLModel"
        or getattr(auto_model.config, "model_type", None) != "qwen3_vl"
        or auto_model.base_model_prefix != ""
        or getattr(auto_model, "_checkpoint_conversion_mapping", {})
    ):
        raise CheckpointLoadError("Qwen AutoModel loading contract changed; review the mapping before encoding")
    directory = _checkpoint_directory(pretrained_model, auto_model, model_kwargs)
    files = _checkpoint_files(directory)
    state = auto_model.state_dict()
    expected_shapes = {key: tuple(value.shape) for key, value in state.items()}
    with ExitStack() as stack:
        readers = {str(path.relative_to(directory)): stack.enter_context(safe_open(str(path), framework="pt", device="cpu")) for path in files}
        checkpoint_shapes, locations = {}, {}
        for filename, reader in readers.items():
            for key in reader.keys():
                if key in locations:
                    raise CheckpointLoadError(f"Duplicate checkpoint tensor across shards: {key}")
                locations[key] = filename
                checkpoint_shapes[key] = tuple(reader.get_slice(key).get_shape())
        routes = checkpoint_routes(checkpoint_shapes, expected_shapes, model_kwargs.get("key_mapping"))
        elements = 0
        for key, destination in routes.items():
            actual = state[destination]
            if actual.is_meta or actual.is_quantized or not actual.is_floating_point():
                raise CheckpointLoadError(f"Cannot establish exact loaded-state proof for {destination}")
            reader = readers[locations[key]]
            shape = checkpoint_shapes[key]
            if not shape:
                chunks = [(actual, reader.get_tensor(key))]
            else:
                step = max(1, 1_048_576 // max(1, math.prod(shape[1:])))
                source = reader.get_slice(key)
                chunks = ((actual[start:start + step], source[start:start + step]) for start in range(0, shape[0], step))
            for loaded, saved in chunks:
                loaded = loaded.detach().to(device="cpu")
                saved = saved.to(dtype=loaded.dtype)
                if not torch.equal(loaded, saved):
                    raise CheckpointLoadError(f"Loaded tensor differs from checkpoint: {key} -> {destination}")
                elements += loaded.numel()
    return {
        "status": "VERIFIED_ALL_CHECKPOINT_TENSORS",
        "tensor_count": len(routes), "element_count": elements,
        "checkpoint_directory": str(directory),
        "checkpoint_files": [str(path.relative_to(directory)) for path in files],
        "checkpoint_revision": getattr(auto_model.config, "_commit_hash", None),
        "helper_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "mapping_sha256": hashlib.sha256(json.dumps(routes, sort_keys=True).encode()).hexdigest(),
        "comparison": "every tensor value equals checkpoint after casting to loaded dtype",
        "second_model_loaded": False,
    }
