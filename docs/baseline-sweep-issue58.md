# baseline-sweep-issue58 — reproducible current-system sweep (Issue #58)

**Status:** executed 2026-08-25. Measurement only. Rerank OFF. No retrieval-semantics change. Artifacts: [`../benchmark-results/issue58-baseline-sweep/`](../benchmark-results/issue58-baseline-sweep/).

This packet is the Issue #58 "Ox Alpha" baseline sweep required by
[issue #58](https://github.com/JimmyK300/Vecna/issues/58) (parent #34): one
reproducible run of the **current system** over the authoritative canonical
query set, plus a failure-taxonomy report. It extends [`baseline-v1.md`](./baseline-v1.md)
and re-measures its best-known-config cell through the same official runner.

## Query source (authoritative)

`aic51-src/benchmark/issue34_headless_queries.csv` — canonical issue34-v1 set,
current-corpus scope (`include_current_dataset`), immutable content digest
verified at run time:

| item | value |
|---|---|
| Queries in scope | 22 (`p1_q01`..`p1_q22`; all Q0, no hints) |
| Scoreable | 21 provisional (`source_text_verified_needs_corpus_validation`) |
| Unscoreable | `p1_q22` (missing official answer GT) |
| Canonical content SHA-256 | `1aba0cf592976a7ec3e2417ff7e9c46628ad2269dc786125fa07c26e0a34470e` (match) |

## Rerun

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' aic51-src\script\run_issue58_baseline_sweep.py --overwrite
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' aic51-src\script\classify_issue58_failures.py
```

The launcher delegates to the official headless path
(`aic51-src/script/run_p20_p21_measurement.py --mode quality --cell clip_siglip_qwen_sparse`)
inside the live primary workspace `C:\Users\minhc\Code\Vecna`, which is treated as
read-only (no bytecode, no writes; artifacts land in this worktree). Full identity,
hashes, and caveats: [`../benchmark-results/issue58-baseline-sweep/RERUN.md`](../benchmark-results/issue58-baseline-sweep/RERUN.md).

## Recorded identity (2026-08-25 run)

| item | value |
|---|---|
| Serving stack | primary workspace git `fd879fb0529165a441745374ab72244df8aadd5e` (+live dirty WIP), status hash `98e56cc5674327660c6d186daad75583d976cbee803baf753de3e2cfd0477afa` |
| Benchmark worktree | this repo @ `9b8a871e8531aae85de6eb87fea400bef8669d48`, branch `codex/issue-58-baseline-sweep` |
| Cell | `clip_siglip_qwen_sparse` (CLIP+SigLIP+Qwen visual; OCR/ASR BM25 sparse; rerank OFF) |
| Search params | nprobe=32, temporal_k=2000, ocr_weight=0.25, asr_weight=0.25 |
| Collection / index | `official_l21_l30_all_v2` (322,924 entities), generation `idx_6baede5b9bc447e099c0004d8428ca7e` |
| Encoders | CPU (torch 2.8.0+cpu fallback) |
| Result hash | `bd4d33b37da50467fea610223744c7979c2d56cff0a08b57e29a65b62f4b3061` (per-query JSONL) |

## Headline result (Q0, 21 provisional-scoreable)

R@1 0.523810 · R@5 0.630952 · R@20 0.797619 · MRR@20 0.588680 · no-hit@20 3/21
— quality metrics reproduce the baseline-v1 guardrail bit-for-bit; latency
(mean 8.17 s warm-ish) differs from the published 15.37 s because of machine load.

Failure taxonomy (3 misses): see
[`../benchmark-results/issue58-baseline-sweep/failure-taxonomy.md`](../benchmark-results/issue58-baseline-sweep/failure-taxonomy.md).
