# BGE-M3 ONNX Runtime backend

`text_embedding` can run BGE-M3 through Transformers/PyTorch (unchanged) or
ONNX Runtime. The logical retrieval features stay `ocr_dense` and `asr_dense`.

## Config

```yaml
ocr_dense:
  model: "text_embedding"
  pretrained_model: "BAAI/bge-m3"
  text_source: "ocr"
  backend: onnx          # pytorch | onnx
  onnx_provider: auto    # auto | dml | cpu
  # onnx_model_path: models/BAAI-bge-m3_fp16.onnx
```

`searcher.language_models.text_bge_m3` should use the same `backend` /
`onnx_provider` so queries and documents share a generation.

ONNX analyse uses an overlapped pipeline by default (`onnx_pipeline: auto`):

1. A CPU thread reads/tokenizes a sliding window of pending documents and
   enqueues length-bucketed batches as soon as they exist.
2. The main thread consumes that queue on the single DML session immediately.
3. A writer thread saves `.npy` / provenance so disk I/O is off the GPU path.

The GPU does not wait for the whole corpus to be tokenized. Skip identity is
the ONNX artifact SHA + provider + model, not the Python source hash.

Progress logs include a representative document and the live batch width, for
example `ocr_dense infer: batch=2500/L25_V048_ocr n=64 pad=32`.

`onnx_batch_adapt: auto` (default) sizes each launch from token length:
attention work is ~batch * seq^2, so short docs get more rows (capped by
`onnx_max_batch`, default 128) and 256-token docs stay at `analyse.batch_size`.
This does not keep the GPU at 80% on 2-token OCR — that would need batches of
hundreds of thousands of rows. `onnx_batch_adapt: off` restores a fixed
`batch_size`. Packing is not part of provider generation identity.

Set `onnx_pipeline: serial` to restore the old per-video tokenize-then-infer
loop. The pipeline does not change provider generation identity.

Environment fallback for the artifact:

```
VECNA_BGE_M3_ONNX=C:\path\to\BAAI-bge-m3_fp16.onnx
```

`tokenizer.json` must sit next to the `.onnx` file. Do not export a new model
unless that artifact is missing. The known-good dense-only FP16 export is
`hotchpotch/vespa-onnx-BAAI-bge-m3-only-dense`.

## Providers

- `pytorch`: original Transformers path.
- `onnx` + `dml`: `DmlExecutionProvider`. Requires `onnxruntime-directml`.
- `onnx` + `cpu`: same `.onnx` file on `CPUExecutionProvider`.
- `onnx` + `auto`: DirectML if the ORT build has it and GPU use is allowed.
- `--no-gpu` and `backends.search.gpu: false` force CPU.

DirectML is an ONNX Runtime execution provider. Detection does **not** use
`torch.cuda`. Initialization logs the backend, artifact, and active provider
and never claims DirectML unless the session actually activated it.

Optional extras (do not install both ORT packages in one env):

```
pip install -e ".[onnx]"
pip install -e ".[onnx-directml]"
```

## Provenance

Provider generation includes execution framework, ORT version, provider,
artifact path, SHA-256, precision, tokenizer, and max length. CPU and DML
runs of the same ONNX file are different generations. Existing dense files
from another generation are renamed
`*.preserved.<generation>.<timestamp>.npy` instead of being overwritten.

## Analyse

```
aic51-cli analyse --use-text-embedding --keep-going
```

Text embedding can discover videos/frames from `features/<video>/<frame>/{ocr,asr}.npy`
when keyframe images are absent. OCR/ASR source files are never deleted.
