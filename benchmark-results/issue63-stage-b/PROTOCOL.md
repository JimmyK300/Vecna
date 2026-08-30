# Issue #63 Stage B frozen execution protocol

Authority: GitHub Issue #63 and the comments `Stage A human gate cleared — Stage B may proceed` and `Stage B Browser Task Lead checkpoint / local operator packet — 2026-08-30`.

## Frozen inputs

- Stage A commit: `f0532c1be14b02b6da73d4b23e2d773591a48f97`
- Reviewed decisions: `benchmark-results/issue63-round1-segments/review/reviewed-ranges.json`
- Legacy benchmark donor/evidence: `cb5216b6f80826f626d61e01496589179520dfa4`
- Read-only live runtime root: `C:\Users\minhc\Code\Vecna`
- Baseline cell: `clip_siglip_qwen_sparse`, rerank OFF, OCR/ASR weights 0.25/0.25, nprobe 32, temporal_k 2000, query expansion/translation OFF.

## Invocation budget

- One full counted run after deterministic tests and a no-retrieval scoring smoke test pass.
- One Searcher initialization.
- Exactly 69 scoreable Q0 searches: 21 legacy scoreable records followed by 48 accepted reconstructed records.
- No search for either non-scoreable record: the one legacy excluded record or `testing88_submission633::p1-21`.
- A failed search is preserved as evidence and is not silently retried.

## Scoring

- Legacy records retain the current `headless_benchmark.py` scoring behavior.
- Reconstructed records use source-qualified IDs and score a hit only when the returned video matches and any returned point/timeline frame is inside any accepted reviewed interval, endpoints inclusive.
- Any accepted alternative interval may satisfy a reconstructed record.
- Exact-frame tolerance is diagnostic only for reconstructed records.

## Allowed writes

- `aic51-src/script/run_issue63_stage_b.py`
- `aic51-src/script/issue63_stage_b_scoring.py`
- `aic51-src/tests/test_issue63_stage_b.py`
- `benchmark-results/issue63-stage-b/**`

The live runtime root and production retrieval/config/index files are read-only. No corpus analysis, indexing, retrieval tuning, query expansion, model/fusion changes, or production semantic changes are allowed.

## Stop conditions

Stop before the counted run if reviewed truth cannot be frozen deterministically, scorer tests fail, the required Milvus collection/index generation is unavailable, fixed-cell configuration cannot be enforced in-memory without file changes, or an additional semantic decision is required. Stop during the run on infrastructure failure, unexplained old-set drift, or any need for retry/tuning; preserve partial evidence.
