# YOLOE-26x DirectML corpus extraction

Vecna supports a baked-vocabulary YOLOE ONNX backend for Windows AMD GPUs.
DirectML is an ONNX Runtime execution provider; it is **not** exposed as a
`torch.device` and should not be added to `get_device()`.

## Proven artifact contract

The local proof used:

- source weights: `yoloe-26x-seg.pt`
- vocabulary: RAM++ 4,585 names, baked before export
- architecture: detection-only `YOLOE("yoloe-26x.yaml")` loaded from the
  segmentation weights (1206/1206 weights transferred)
- ONNX: opset 17, static batch 1, `1x3x640x640 -> 1x300x6`
- runtime: `onnxruntime-directml 1.24.4`
- first provider: `DmlExecutionProvider` (asserted)
- DirectML session: `enable_mem_pattern=False`, `ORT_SEQUENTIAL`
- measured RX 6900 XT: ~19.58 infer img/s, ~10.81 img/s end-to-end including
  letterbox preprocessing on 1,000 real frames

The ONNX artifact is intentionally not committed to Git. Put the proven
throughput artifact at the default path:

```text
models/yoloe-26x-det-ram-plus-640-b1.onnx
```

or set:

```powershell
$env:VECNA_YOLO_ONNX="C:\path\to\yoloe-26x-det-ram-plus-640-b1.onnx"
```

The backend first tries an optional class-name file (`VECNA_YOLO_NAMES` or
`onnx_class_names_path`) and otherwise reads the Ultralytics `names` metadata
from the ONNX model. The proven artifact should expose all 4,585 baked names.

### `max_det` is an export-time contract

YOLO26/YOLOE end-to-end detection applies top-k selection **inside the model
head**. The exported second dimension therefore reflects the export-time
`max_det`: the proven `1x300x6` artifact was built with `max_det=300`.

Vecna currently configures `max_det=100`. Post-hoc capping a `1x300x6` output to
100 rows is useful as a conservative corpus cap, but it is **not guaranteed to
be identical** to a PyTorch model or ONNX export whose head itself ran with
`max_det=100`. This explains why the standalone proof had very high recall but
extra lower-confidence boxes relative to the PyTorch comparison.

Before production, choose one parity contract and use it on every backend:

1. **Recommended:** export the baked detection-only ONNX artifact with
   `max_det=100` so its output is `1x100x6`, matching Vecna's current PyTorch
   configuration; or
2. deliberately standardize both PyTorch and ONNX on `max_det=300` and accept
   the denser detector output.

Do not add external NMS to solve this. End-to-end YOLO26/YOLOE outputs are
already final one-to-one predictions; after a matching export, runtime
post-processing is confidence filtering plus coordinate restoration.

## Runtime installation

For the AMD DirectML environment:

```powershell
pip uninstall -y onnxruntime onnxruntime-directml
pip install -e ".\aic51-src[yolo-directml]"
```

Do not install `onnxruntime` and `onnxruntime-directml` together. Vecna also
sets `YOLO_AUTOINSTALL=false` in its CLI so Ultralytics cannot silently replace
the DirectML wheel with CPU ONNX Runtime.

For NVIDIA hosts keep using the normal Ultralytics/CUDA extra:

```powershell
pip install -e ".\aic51-src[yolo]"
```

`backend=auto` prefers CUDA when the selected Torch device is CUDA. DirectML
is therefore an AMD/Windows path, not a universal YOLO backend.

## Smoke test in Vecna

Run the raw detector only on one known-small video first:

```powershell
$env:PYTHONPATH="aic51-src"
aic51-cli analyse-yolo `
  --raw-only `
  --yolo-backend onnx `
  --yolo-onnx-provider dml `
  --yolo-onnx-model $env:VECNA_YOLO_ONNX `
  --video L26_V194
```

Expected startup semantics include:

```text
backend=onnx
execution_framework=onnxruntime
execution_provider=DmlExecutionProvider
provider_choice=dml
input_shape=[1, 3, 640, 640]
vocabulary_size=4585
```

If `dml` is explicitly requested and the first provider is not
`DmlExecutionProvider`, Vecna raises instead of silently using CPU.

After the raw detector succeeds, omit `--raw-only` to also generate the
`yolo_semantic` BGE-M3 projection.

## Decode semantics

For an end-to-end export whose `max_det` matches the configured runtime
contract, Vecna should:

1. apply the same centered 640x640 letterbox geometry;
2. run the static ONNX session;
3. filter final rows by configured confidence;
4. restore coordinates from letterbox space to the original keyframe;
5. convert labels, counts, coarse position, and coarse size into the semantic
   text consumed by BM25/BGE-M3.

No external NMS is required. If an older `1x300x6` artifact is used while Vecna
is configured for 100, the current decoder may cap the rows to 100 as a safety
measure, but that should not be described as exact PyTorch parity.

## Production routing

The intended routing remains:

```text
RTX 5060    -> Ultralytics CUDA / TensorRT (benchmark separately)
RTX 4060    -> Ultralytics CUDA / TensorRT (benchmark separately)
RX 6900 XT  -> ONNX Runtime / DirectML
CPU         -> optional explicit CPU fallback
```

Do not launch the full 317k corpus until the Vecna-integrated smoke test confirms
provider identity, 4,585-class names, semantic output quality, matching
export/runtime `max_det`, and throughput on a representative sample.
