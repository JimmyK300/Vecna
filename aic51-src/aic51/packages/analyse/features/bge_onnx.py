"""BGE-M3 dense ONNX Runtime backend (DirectML / CPU).

Session, tokenizer, and pooling follow the known-good Windows DirectML PoC:
CLS token + L2 normalize, int64 inputs, same FP16 dense-only artifact.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from aic51.packages.logger import logger
from aic51.packages.utils.provenance import file_sha256

ONNX_ENV_VAR = "VECNA_BGE_M3_ONNX"
DEFAULT_ONNX_NAME = "BAAI-bge-m3_fp16.onnx"
DEFAULT_TOKENIZER_NAME = "tokenizer.json"
DEFAULT_MODEL_ID = "hotchpotch/vespa-onnx-BAAI-bge-m3-only-dense"
HIDDEN = 1024
MAX_LENGTH = 8192
DEFAULT_MAX_LENGTH = 512
CLS_ID = 0
PAD_ID = 1
EOS_ID = 2
CPU_DISABLED_OPTIMIZERS = ("SimplifiedLayerNormFusion",)
TOKENIZE_CHUNK = 4096
LENGTH_BUCKET_EDGES = (
    32,
    48,
    64,
    80,
    96,
    128,
    160,
    192,
    224,
    256,
    384,
    512,
    768,
    1024,
    2048,
    MAX_LENGTH,
)
DEFAULT_MAX_BATCH = 128
PRELOAD_RAM_BUDGET_BYTES = 4 * 1024 * 1024 * 1024

_SESSION_CACHE: dict[tuple[str, str], Any] = {}


class OnnxRuntimeUnavailable(RuntimeError):
    pass


class DirectMLUnavailable(RuntimeError):
    pass


def l2_normalize(x: np.ndarray, axis: int = -1, eps: float = 1e-12) -> np.ndarray:
    denom = np.linalg.norm(x, axis=axis, keepdims=True)
    return x / np.maximum(denom, eps)


def import_onnxruntime():
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise OnnxRuntimeUnavailable(
            "ONNX backend requested but ONNX Runtime is not installed. "
            "On Windows AMD GPUs install `onnxruntime-directml`. "
            "On other platforms install `onnxruntime`. "
            "Do not install both packages in the same environment."
        ) from exc
    return ort


def available_providers() -> list[str]:
    ort = import_onnxruntime()
    return list(ort.get_available_providers())


def has_directml() -> bool:
    try:
        return "DmlExecutionProvider" in available_providers()
    except OnnxRuntimeUnavailable:
        return False


def resolve_onnx_model_path(explicit: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env = os.environ.get(ONNX_ENV_VAR)
    if env:
        candidates.append(Path(env).expanduser())
    cwd_models = Path.cwd() / "models" / DEFAULT_ONNX_NAME
    candidates.append(cwd_models)
    for path in candidates:
        if path.is_file():
            return path.resolve()
    searched = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(
        "BGE-M3 ONNX artifact not found. Set features.*.onnx_model_path or "
        f"{ONNX_ENV_VAR}. Looked at: {searched}"
    )


def resolve_tokenizer_path(model_path: Path, explicit: str | Path | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path.resolve()
        raise FileNotFoundError(f"BGE-M3 tokenizer not found: {path}")
    sibling = model_path.parent / DEFAULT_TOKENIZER_NAME
    if sibling.is_file():
        return sibling.resolve()
    raise FileNotFoundError(
        f"tokenizer.json must sit next to the ONNX artifact ({model_path.parent})"
    )


def resolve_provider_choice(
    requested: str,
    *,
    allow_gpu: bool,
) -> tuple[str, str | None]:
    """Return (session_provider, warning).

    session_provider is `dml` or `cpu`. Detection uses ORT providers, never
    torch.cuda.
    """
    choice = (requested or "auto").strip().lower()
    if choice not in {"auto", "dml", "cpu"}:
        raise ValueError(f"unknown ONNX provider {requested!r}; use auto|dml|cpu")

    if choice == "cpu" or not allow_gpu:
        warning = None
        if choice == "dml" and not allow_gpu:
            warning = "DirectML disabled by --no-gpu / allow_gpu=false; using CPU."
        elif choice == "auto" and not allow_gpu:
            warning = "DirectML unavailable/disabled; using CPU."
        return "cpu", warning

    providers = available_providers()
    if "DmlExecutionProvider" not in providers:
        if choice == "dml":
            raise DirectMLUnavailable(
                "DmlExecutionProvider is not in this ONNX Runtime build. "
                f"Available: {providers}. Install onnxruntime-directml."
            )
        return "cpu", "DirectML unavailable/disabled; using CPU."
    return "dml", None


def _session_providers(choice: str) -> list:
    if choice == "dml":
        return [("DmlExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def create_session(model_path: Path, choice: str):
    ort = import_onnxruntime()
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.log_severity_level = 3
    if choice == "dml":
        # Required by ONNX Runtime's DirectML execution provider.
        so.enable_mem_pattern = False
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    disabled = list(CPU_DISABLED_OPTIMIZERS) if choice == "cpu" else None
    return ort.InferenceSession(
        str(model_path),
        sess_options=so,
        providers=_session_providers(choice),
        disabled_optimizers=disabled,
    )


def get_shared_session(model_path: Path, choice: str):
    key = (str(model_path), choice)
    sess = _SESSION_CACHE.get(key)
    if sess is None:
        sess = create_session(model_path, choice)
        _SESSION_CACHE[key] = sess
    return sess


def active_execution_provider(session) -> str:
    providers = list(session.get_providers())
    if not providers:
        raise RuntimeError("ONNX session reported no execution providers")
    return providers[0]


def assert_requested_provider(session, choice: str) -> str:
    active = active_execution_provider(session)
    if choice == "dml" and active != "DmlExecutionProvider":
        raise DirectMLUnavailable(
            f"requested DmlExecutionProvider but session activated {session.get_providers()}"
        )
    return active


def configure_tokenizer(tokenizer_path: Path, max_length: int):
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(tokenizer_path))
    tok.enable_truncation(max_length=max_length)
    tok.enable_padding(pad_id=PAD_ID, pad_token="<pad>", pad_type_id=0)
    return tok


def encode_texts(tokenizer, texts: list[str], max_length: int) -> dict[str, np.ndarray]:
    token_lists = tokenize_unpadded(tokenizer, texts, max_length=max_length)
    return pad_token_lists(token_lists)


def tokenize_unpadded(
    tokenizer,
    texts: Sequence[str],
    max_length: int,
    chunk_size: int = TOKENIZE_CHUNK,
) -> list[list[int]]:
    """CPU-only tokenization. No padding — that happens per ready batch."""
    tokenizer.no_padding()
    tokenizer.enable_truncation(max_length=max_length)
    encoded: list[list[int]] = []
    total = len(texts)
    for start in range(0, total, chunk_size):
        chunk = list(texts[start : start + chunk_size])
        encoded.extend(item.ids for item in tokenizer.encode_batch(chunk))
    return encoded


def length_bucket(length: int, edges: Sequence[int] = LENGTH_BUCKET_EDGES) -> int:
    for edge in edges:
        if length <= edge:
            return int(edge)
    return int(edges[-1])


def adaptive_batch_limit(
    seq_len: int,
    *,
    ref_batch: int,
    ref_seq: int,
    max_batch: int,
) -> int:
    """Docs per launch so attention work stays near ref_batch x ref_seq.

    Attention is ~batch * seq^2. Short sequences therefore take more rows.
    max_batch is a hard DML/host cap: 2-token docs cannot fill a 6900 XT.
    """
    seq = max(int(seq_len), 1)
    ref_seq = max(int(ref_seq), 1)
    ref_batch = max(int(ref_batch), 1)
    max_batch = max(int(max_batch), 1)
    target = ref_batch * ref_seq * ref_seq
    by_attn = max(1, target // (seq * seq))
    return max(1, min(max_batch, by_attn))


def pad_token_lists(token_lists: Sequence[Sequence[int]]) -> dict[str, np.ndarray]:
    if not token_lists:
        empty = np.empty((0, 0), dtype=np.int64)
        return {
            "input_ids": empty,
            "attention_mask": empty,
            "token_type_ids": empty,
        }
    width = max(max(len(ids) for ids in token_lists), 1)
    batch = len(token_lists)
    input_ids = np.full((batch, width), PAD_ID, dtype=np.int64)
    attention_mask = np.zeros((batch, width), dtype=np.int64)
    for row, ids in enumerate(token_lists):
        length = len(ids)
        if not length:
            continue
        input_ids[row, :length] = np.asarray(ids, dtype=np.int64)
        attention_mask[row, :length] = 1
    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": np.zeros_like(input_ids),
    }


@dataclass(frozen=True)
class ReadyBatch:
    """One inference-ready padded batch. Tokenization already finished."""

    encoded: dict[str, np.ndarray]
    indices: tuple[int, ...]
    pad_width: int
    bucket: int


def _pack_bucket(
    items: list[tuple[int, list[int]]],
    *,
    batch_size: int,
    max_length: int,
    max_batch: int | None,
    adapt: str,
) -> list[tuple[list[tuple[int, list[int]]], int]]:
    """Split one length-sorted bucket into chunks. Returns (chunk, pad_width)."""
    mode = (adapt or "off").strip().lower()
    use_adapt = mode in {"auto", "attn", "token", "on", "true", "1"}
    cap = int(max_batch) if max_batch is not None else batch_size
    if cap < 1:
        raise ValueError("max_batch must be >= 1")
    chunks: list[tuple[list[tuple[int, list[int]]], int]] = []
    chunk: list[tuple[int, list[int]]] = []
    for item in items:
        candidate = chunk + [item]
        pad = max(len(ids) for _, ids in candidate) or 1
        limit = (
            adaptive_batch_limit(
                pad,
                ref_batch=batch_size,
                ref_seq=max_length,
                max_batch=cap,
            )
            if use_adapt
            else min(batch_size, cap)
        )
        if chunk and len(candidate) > limit:
            chunks.append((chunk, max(len(ids) for _, ids in chunk) or 1))
            chunk = [item]
            continue
        chunk = candidate
    if chunk:
        chunks.append((chunk, max(len(ids) for _, ids in chunk) or 1))
    return chunks


def build_ready_batches(
    token_lists: Sequence[Sequence[int]],
    batch_size: int,
    max_length: int,
    edges: Sequence[int] = LENGTH_BUCKET_EDGES,
    max_batch: int | None = None,
    adapt: str = "auto",
) -> list[ReadyBatch]:
    """Sort by length bucket, then pack batches padded only to the batch max.

    With adapt=auto, short docs share a launch (up to max_batch) so attention
    work stays near batch_size * max_length^2. adapt=off keeps a fixed
    batch_size. Packing is not part of provider generation identity.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    buckets: dict[int, list[tuple[int, list[int]]]] = defaultdict(list)
    for index, raw in enumerate(token_lists):
        ids = list(raw[:max_length])
        buckets[length_bucket(len(ids), edges)].append((index, ids))

    ready: list[ReadyBatch] = []
    for bucket in sorted(buckets):
        items = buckets[bucket]
        items.sort(key=lambda item: len(item[1]))
        for chunk, _pad in _pack_bucket(
            items,
            batch_size=batch_size,
            max_length=max_length,
            max_batch=max_batch,
            adapt=adapt,
        ):
            encoded = pad_token_lists([ids for _, ids in chunk])
            ready.append(
                ReadyBatch(
                    encoded=encoded,
                    indices=tuple(index for index, _ in chunk),
                    pad_width=int(encoded["input_ids"].shape[1]),
                    bucket=bucket,
                )
            )
    return ready


def estimate_preload_bytes(n_docs: int, max_length: int, avg_text_bytes: int = 256) -> int:
    token_bytes = int(n_docs * max_length * 8 * 2 * 0.35)
    return token_bytes + n_docs * avg_text_bytes


def preload_shard_size(n_docs: int, max_length: int, budget: int = PRELOAD_RAM_BUDGET_BYTES) -> int:
    if n_docs <= 0:
        return 0
    if estimate_preload_bytes(n_docs, max_length) <= budget:
        return n_docs
    for size in (100_000, 50_000, 20_000, 8_000, 2_000):
        if estimate_preload_bytes(size, max_length) <= budget:
            return min(size, n_docs)
    return min(2_000, n_docs)


def feed_dict(session, encoded: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    names = {item.name for item in session.get_inputs()}
    feed = {key: value for key, value in encoded.items() if key in names}
    missing = names - set(feed)
    if missing:
        raise KeyError(f"model inputs not produced by tokenizer: {sorted(missing)}")
    return feed


def pooled_dense(session, outputs: list[np.ndarray]) -> np.ndarray:
    names = [item.name.lower() for item in session.get_outputs()]
    arrays = {name: arr for name, arr in zip(names, outputs)}
    for key in ("sentence_embedding", "dense_vecs", "dense", "pooler_output"):
        if key in arrays:
            vec = np.asarray(arrays[key], dtype=np.float32)
            if vec.ndim == 3:
                vec = vec[:, 0, :]
            return l2_normalize(vec)

    hidden = np.asarray(outputs[0], dtype=np.float32)
    if hidden.ndim == 2:
        return l2_normalize(hidden)
    if hidden.ndim != 3:
        raise ValueError(f"unexpected hidden rank {hidden.ndim}, shape={hidden.shape}")
    return l2_normalize(hidden[:, 0, :])


def _run_iobinding(session, feed: dict[str, np.ndarray]) -> list[np.ndarray]:
    io_binding = session.io_binding()
    for name, value in feed.items():
        io_binding.bind_cpu_input(name, np.ascontiguousarray(value))
    for output in session.get_outputs():
        io_binding.bind_output(output.name)
    session.run_with_iobinding(io_binding)
    return io_binding.copy_outputs_to_cpu()


def run_encoded(session, encoded: dict[str, np.ndarray]) -> list[np.ndarray]:
    feed = feed_dict(session, encoded)
    if active_execution_provider(session) == "DmlExecutionProvider":
        try:
            return _run_iobinding(session, feed)
        except Exception as exc:
            logger.debug(f"I/O binding unavailable, using session.run: {exc}")
    input_names = [item.name for item in session.get_inputs()]
    return session.run(None, {name: feed[name] for name in input_names})


def embed_encoded(session, encoded: dict[str, np.ndarray]) -> np.ndarray:
    if encoded["input_ids"].shape[0] == 0:
        return np.empty((0, HIDDEN), dtype=np.float32)
    vecs = pooled_dense(session, run_encoded(session, encoded))
    if vecs.ndim != 2 or vecs.shape[-1] != HIDDEN:
        raise ValueError(f"expected (*, {HIDDEN}) dense vectors, got {vecs.shape}")
    return np.asarray(vecs, dtype=np.float32)


def embed_texts(session, tokenizer, texts: list[str], max_length: int) -> np.ndarray:
    if not texts:
        return np.empty((0, HIDDEN), dtype=np.float32)
    return embed_encoded(session, encode_texts(tokenizer, texts, max_length=max_length))


def embed_token_lists(
    session,
    token_lists: Sequence[Sequence[int]],
    batch_size: int,
    max_length: int,
    max_batch: int | None = None,
    adapt: str = "auto",
) -> np.ndarray:
    if not token_lists:
        return np.empty((0, HIDDEN), dtype=np.float32)
    ready = build_ready_batches(
        token_lists,
        batch_size=batch_size,
        max_length=max_length,
        max_batch=max_batch,
        adapt=adapt,
    )
    out = np.empty((len(token_lists), HIDDEN), dtype=np.float32)
    for batch in ready:
        vecs = embed_encoded(session, batch.encoded)
        for row, index in enumerate(batch.indices):
            out[index] = vecs[row]
    return out


class BgeM3OnnxBackend:
    """Loaded ONNX session + tokenizer for BGE-M3 dense embeddings."""

    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        tokenizer_path: str | Path | None = None,
        provider: str = "auto",
        allow_gpu: bool = True,
        max_length: int = DEFAULT_MAX_LENGTH,
        pretrained_model: str = "BAAI/bge-m3",
    ) -> None:
        ort = import_onnxruntime()
        self.pretrained_model = pretrained_model
        self.model_path = resolve_onnx_model_path(model_path)
        self.tokenizer_path = resolve_tokenizer_path(self.model_path, tokenizer_path)
        self.max_length = min(max(8, int(max_length)), MAX_LENGTH)
        self.requested_provider = (provider or "auto").strip().lower()
        self.allow_gpu = bool(allow_gpu)

        choice, warning = resolve_provider_choice(
            self.requested_provider,
            allow_gpu=self.allow_gpu,
        )
        self.session = get_shared_session(self.model_path, choice)
        try:
            self.execution_provider = assert_requested_provider(self.session, choice)
        except DirectMLUnavailable:
            if self.requested_provider == "dml":
                raise
            choice = "cpu"
            warning = "DirectML unavailable/disabled; using CPU."
            self.session = get_shared_session(self.model_path, choice)
            self.execution_provider = assert_requested_provider(self.session, choice)

        self.provider_choice = choice
        self.tokenizer = configure_tokenizer(self.tokenizer_path, self.max_length)
        self.ort_version = ort.__version__
        self.model_sha256 = file_sha256(self.model_path)
        self.precision = "fp16"
        self.execution_framework = "onnxruntime"

        logger.info("BGE-M3 backend: ONNX Runtime")
        logger.info(f"BGE-M3 model: {self.model_path}")
        logger.info(f"BGE-M3 provider: {self.execution_provider}")
        if warning:
            logger.warning(warning)
        if (
            self.execution_provider != "DmlExecutionProvider"
            and self.requested_provider in {"auto", "dml"}
        ):
            logger.warning("WARNING: DirectML unavailable/disabled; using CPU.")

    def embed(self, texts: list[str]) -> np.ndarray:
        return embed_texts(self.session, self.tokenizer, texts, self.max_length)

    def tokenize_unpadded(self, texts: Sequence[str]) -> list[list[int]]:
        return tokenize_unpadded(self.tokenizer, texts, max_length=self.max_length)

    def embed_encoded(self, encoded: dict[str, np.ndarray]) -> np.ndarray:
        return embed_encoded(self.session, encoded)

    def embed_token_lists(
        self,
        token_lists: Sequence[Sequence[int]],
        batch_size: int,
        max_batch: int | None = None,
        adapt: str = "auto",
    ) -> np.ndarray:
        return embed_token_lists(
            self.session,
            token_lists,
            batch_size=batch_size,
            max_length=self.max_length,
            max_batch=max_batch,
            adapt=adapt,
        )

    def prepare_ready_batches(
        self,
        texts: Sequence[str],
        batch_size: int,
        max_batch: int | None = None,
        adapt: str = "auto",
    ) -> tuple[list[list[int]], list[ReadyBatch]]:
        token_lists = self.tokenize_unpadded(texts)
        return token_lists, build_ready_batches(
            token_lists,
            batch_size=batch_size,
            max_length=self.max_length,
            max_batch=max_batch,
            adapt=adapt,
        )

    def runtime_semantics(self) -> dict[str, Any]:
        return {
            "backend": "onnx",
            "execution_framework": self.execution_framework,
            "onnxruntime_version": self.ort_version,
            "execution_provider": self.execution_provider,
            "onnx_provider_request": self.requested_provider,
            "onnx_artifact": str(self.model_path),
            "onnx_artifact_name": self.model_path.name,
            "onnx_artifact_sha256": self.model_sha256,
            "onnx_model_id": DEFAULT_MODEL_ID,
            "tokenizer": str(self.tokenizer_path),
            "max_length": self.max_length,
            "precision": self.precision,
            "compute_type": self.precision,
            "hidden_size": HIDDEN,
            "pretrained_model": self.pretrained_model,
        }
