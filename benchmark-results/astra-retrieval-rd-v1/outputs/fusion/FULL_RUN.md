# Packet B full run

Run collection once in the disposable Windows checkout of the pinned research
branch. The commands below use repository-relative paths; the invoking Python
must be `C:/Users/minhc/Code/Vecna/.venv/Scripts/python.exe`, and its working
directory must be the disposable repository root. Use the same CPU device and
existing HTTP Milvus endpoint as the successful metadata preflight. Set six
intra-op CPU threads, matching the stable A run; actual intra-op and inter-op
thread counts are recorded in the run identity. The collection is
`official_l21_l30_all_v2`, with an asserted count of 322,924 rows.

```text
C:/Users/minhc/Code/Vecna/.venv/Scripts/python.exe -B -u benchmark-results/astra-retrieval-rd-v1/code/collect_fusion_providers.py --runtime-root . --runtime-config C:/Users/minhc/Code/Vecna/config.yaml --config benchmark-results/astra-retrieval-rd-v1/outputs/fusion/frozen_config.json --queries benchmark-results/astra-retrieval-rd-v1/outputs/fusion/queries.jsonl --output-dir benchmark-results/astra-retrieval-rd-v1/outputs/fusion/capture-full115-v1 --milvus-uri http://localhost:19530 --device cpu --cpu-threads 6
```

Do not pass `--smoke-count`. The selected output directory must not exist.
Capture child stdout and stderr as separate files under the research artifact
scope. Check the child's exit code, not only the outer broker status: a broker
can successfully report a failed child. The child prints one compact progress
record per query; the authoritative raw output is in its files.

There is no measured full-run duration yet. Startup includes exact model-weight
and tokenizer fingerprints, then 115 full-text queries against four active
providers. The first completed smoke will supply startup and query timings;
do not extrapolate model-loading time as a per-query cost. If permitted by the
broker deadline, use a conservative 1,800-second child guard and an outer guard
at least 60 seconds longer, then report measured duration. This is a timeout
budget, not a performance estimate. A timed-out or partial run is unscoreable.
Do not stitch smoke/partial rows together or restart only failed queries under
one purported run identity.

Recover both `provider_rankings.jsonl` and `collection_manifest.json` unchanged
from the broker artifact. Retain stdout/stderr and the broker return metadata.
The manifest must say `status=complete`, `scope=full_query_projection`,
`expected_query_count=115`, `planned_query_count=115`, `rows_written=115`, and
`ground_truth_read=false`. Every row must have the same recorded run identity.
Report each provider's availability states: the frozen configuration assigns
nonzero weight to Qwen, SigLIP, OCR sparse and ASR sparse; both dense providers
are explicitly disabled. Do not label this a six-active-provider experiment or
hide an unavailable provider behind an empty list. Native quote eligibility
can leave fewer than 100 text hits.

For offline evaluation, change the working directory to the evidence packet
root (`benchmark-results/astra-retrieval-rd-v1`, or its recovered scratch copy).
Ordinary Python with the standard library is sufficient for this stage.

```bash
python code/evaluate_fusion_study.py --root . --rankings outputs/fusion/capture-full115-v1/provider_rankings.jsonl --collection-manifest outputs/fusion/capture-full115-v1/collection_manifest.json --config outputs/fusion/frozen_config.json --queries outputs/fusion/queries.jsonl --outdir outputs/fusion/evaluation
```

This command invokes the fusion harness first, validates the complete collector
manifest and all source-control replays, writes all 115 transformed rows, and
only then opens truth for the unchanged 113-query mapping. The evaluation
directory must not exist. It writes `study_results.jsonl`, `per_query.jsonl`,
`summary.json`, `slices.json`, `policy.json`, and `REPORT.md`. Bootstrap uses the
predeclared 10,000 paired-query resamples and seed 82. No parameter tuning or
per-query arm selection is performed.

The standalone truth-blind harness CLI is available when only transform
validation is wanted. It is already called by the evaluator, so a second
standalone run is unnecessary for the full sequence:

```bash
python code/fusion_study.py --rankings outputs/fusion/capture-full115-v1/provider_rankings.jsonl --collection-manifest outputs/fusion/capture-full115-v1/collection_manifest.json --config outputs/fusion/frozen_config.json --queries outputs/fusion/queries.jsonl --output outputs/fusion/transform-validation/study_results.jsonl
```

After B evaluation completes and the source-audit producers have finished,
regenerate D from one stable set of inputs:

```bash
python code/build_failure_ledger.py --root . --out-dir outputs/failure-ledger
```

D reads `outputs/fusion/evaluation/study_results.jsonl` and the sibling
`summary.json`, verifies B's single global winner, and retains distinct-video
ranks separately from frame-position/localization ranks. B's fresh matched
Qwen capture and C's historical saved Qwen candidates are different surfaces;
cross-packet comparisons require that qualification.
