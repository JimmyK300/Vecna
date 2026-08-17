# Integrated headless retrieval benchmark: Qwen + BGE

## Base and scope

This benchmark integration is based on `agent/bge-m3-onnx-directml@517a4ffb8b52edb872cde57938e5ca6e02939d02` (PR #55), which already contains the consolidated provenance/Qwen/BGE retrieval line plus the optional BGE-M3 ONNX Runtime/DirectML backend.

The port intentionally includes only the Issue #34 benchmark dataset, deterministic benchmark runner/tests, this integrated wrapper, and benchmark documentation. It does **not** import the historical runtime-bundle/backup tooling and does **not** import the divergent `query-expansion` branch.

## Why the wrapper exists

`script/headless_benchmark.py` remains the canonical Issue #34 evaluation contract. `script/headless_integrated_benchmark.py` adds only benchmark-local behavior:

- deterministic tie ordering after the current production `Searcher` returns results;
- runtime metadata for all configured retrieval extractors, including Qwen-VL and BGE-M3;
- package versions for Sentence Transformers and ONNX Runtime variants;
- the wrapper itself as a critical-code hash in the run manifest.

Production retrieval code, weights, reranking policy, indexing, and UI behavior are not changed.

## Dry validation

From `aic51-src`:

```bash
python script/headless_integrated_benchmark.py \
  --csv benchmark/issue34_headless_queries.csv \
  --target-features qwen_vl \
  --dry-run
```

Dry-run does not load models or connect to Milvus.

## Retrieval conditions

The visual target is explicit through `--target-features`. Useful isolated conditions include:

```text
image_clip_pe-l-14-336
image_siglip_so400m-384
qwen_vl
image_clip_pe-l-14-336,qwen_vl
image_siglip_so400m-384,qwen_vl
```

BGE-M3 OCR/ASR channels are not visual target features. They are exercised through the existing `--ocr-weight` and `--asr-weight` parameters and the current workspace configuration. The run manifest records the active BGE extractor backend/runtime semantics.

Example Qwen-only visual baseline:

```bash
python script/headless_integrated_benchmark.py \
  --csv benchmark/issue34_headless_queries.csv \
  --target-features qwen_vl \
  --ocr-weight 0 \
  --asr-weight 0 \
  --allow-provisional-ground-truth
```

Example Qwen + OCR/ASR BGE condition:

```bash
python script/headless_integrated_benchmark.py \
  --csv benchmark/issue34_headless_queries.csv \
  --target-features qwen_vl \
  --ocr-weight 0.25 \
  --asr-weight 0.25 \
  --allow-provisional-ground-truth
```

## Query expansion boundary

Query expansion is deliberately excluded from this baseline. Q0 remains the official unmodified query. A later experiment can compare corrected/HyDE/paraphrase variants against this baseline without making the evaluation contract itself depend on an external LLM.

## Acceptance gate

Before using results for a model decision:

1. run the canonical dataset dry validation;
2. run `python -m unittest tests.test_headless_benchmark tests.test_headless_integrated_benchmark` in the target environment;
3. verify `qwen_vl` is accepted as a target feature;
4. verify the run manifest includes Qwen and BGE extractor runtime semantics and the exact Git/code hashes;
5. repeat one identical condition and confirm the top-20 ordering is identical;
6. preserve the generated `.run.json`, JSONL, and summary files together.

No runtime pass is claimed merely from this source integration.
