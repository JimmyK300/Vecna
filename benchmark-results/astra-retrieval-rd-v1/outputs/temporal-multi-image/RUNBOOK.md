# Reproduce the matched temporal probe

Run commands from the experiment packet directory. Planning uses only the frozen current candidate export and decoded-frame metadata; it imports no model runtime and opens no truth file. The current export contains baseline status/metric fields, which candidate construction ignores.

```bash
python code/temporal_matched.py --action plan \
  --current-candidates inputs/qwen_only_top100.jsonl \
  --cached-candidates inputs/temporal_processor_probe.json
```

Encoding requires the host's existing model snapshot and cached PNG frames. On Windows, use `py -3.12` for the installed CPU runtime. Replace `MODEL_SNAPSHOT` below with the existing `Qwen3-VL-Embedding-2B/snapshots/9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda` directory. A cached raw `stage2b_candidates.jsonl` may replace the processor-probe JSON; both must identify the pinned candidate manifest.

```bash
python code/temporal_matched.py --action encode \
  --current-candidates inputs/qwen_only_top100.jsonl \
  --cached-candidates inputs/temporal_processor_probe.json \
  --model-snapshot MODEL_SNAPSHOT \
  --output-dir outputs/temporal-multi-image/matched-v1 \
  --max-seconds 1800
```

Use a supervisor with a hard wall-time cap. `--max-seconds` stops between forward passes and cannot interrupt a stalled forward pass. The dispatched run uses a 1,860-second child cap and the 1,800-second internal budget.

The encoder requires a new empty output directory. An explicit `--resume` accepts only the same run fingerprint: current candidate/query source, cached frame hashes, model weights and processor files, code, environment, and preprocessing policy. Any mismatch requires a separate output directory. It never reads or resumes the historical embedding cache.

Every query is newly encoded with `Retrieve images or text relevant to the user's query.` Every image arm uses `Represent the user's input.` All forward passes use CPU float32 and six threads. For each candidate, exact decoded frames at offsets `[-60, 0, 60]` are resized with PIL LANCZOS to 384×216. The center arm receives the middle image; the sheet concatenates the same three images left-to-right; native3 receives those three images separately in order. Current processor checks require 84 visual tokens for center and 252 for both sheet and native3.

The output contains `run_manifest.json`, `plan.json`, eight query records in `query_embeddings.jsonl`, and 72 candidate/arm records in `image_embeddings.jsonl`. All records retain identity fingerprints and measured inference timing. The manifest records actual model device/dtype, complete weight-loading checks, and SHA-256 of all safetensors shards and processor files.

After the manifest says `complete_unscored`, run the separate scoring stage:

```bash
python code/temporal_matched.py --action score \
  --output-dir outputs/temporal-multi-image/matched-v1 \
  --truth inputs/canonical_truth.jsonl \
  --scorer reference/evaluate_reranker_fusion.py
python code/temporal_audit.py --root .
```

Scoring rejects incomplete, duplicate, reordered, stale, or unnormalized vectors before opening truth. It preserves historical strict all-event TRAKE and provisional P3 fractional target scoring. It reports center-only localization separately from a common three-frame-window scoring opportunity for every arm. Video R@1 and MRR measure pool ordering; video R@5/R@20 over three fixed candidates cannot establish retrieval recall gains.

```bash
python -m unittest discover -s tests -p 'test_temporal*.py' -v
```

The eight-query sample is a development probe. Its quality result and its runtime result require separate interpretation; changing BF16/full-resolution inputs to float32/matched-resolution inputs does not isolate the contribution of either runtime change alone.
