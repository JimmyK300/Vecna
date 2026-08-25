# Issue #58 baseline sweep -- current-system summary

Generated: `2026-08-25T15:17:14.114651+00:00`

- Query source: canonical `aic51-src/benchmark/issue34_headless_queries.csv` (SHA-pinned issue34-v1 content, current-corpus scope).
- Cell: `clip_siglip_qwen_sparse` (baseline-v1 default; rerank OFF).
- Result hash (`results_sha256`): `bd4d33b37da50467fea610223744c7979c2d56cff0a08b57e29a65b62f4b3061`.
- Index generation: `idx_6baede5b9bc447e099c0004d8428ca7e` on collection `official_l21_l30_all_v2` (322924 entities).
- Serving stack git: `fd879fb0529165a441745374ab72244df8aadd5e` (dirty=True, live workspace).
- Ground-truth tier: **provisional** (`source_text_verified_needs_corpus_validation`) for all 21 scoreable queries; `p1_q22` unscoreable (missing official answer GT).

## Global Q0 metrics (21 provisional-scoreable)

| metric | value |
|---|---|
| Recall@1 | 0.52381 |
| Recall@5 | 0.630952 |
| Recall@20 | 0.797619 |
| MRR@20 | 0.58868 |
| median first-correct rank (hits) | 1.0 |
| no-hit@20 | 3 / 21 |
| mean latency | 8.172 s |

## Per-category Q0 metrics

| category | n | Recall@1 | Recall@5 | Recall@20 | MRR@20 | no-hit@20 | note |
|---|---|---|---|---|---|---|---|
| TKIS retrieval | 16 | 0.625 | 0.6875 | 0.875 | 0.668876 | 2 | interval source-frame membership |
| QA evidence | 2 | 0.5 | 1.0 | 1.0 | 0.625 | 0 | answer extraction NOT implemented; evidence-only |
| TRAKE video-level | 3 | 0.0 | 0.666667 | 1.0 | 0.325397 | see jsonl | localization NOT implemented |
| Temporal-path queries (serving mode) | 1 | 1.0 | — | — | 1.0 | 0 | first-correct rank 1; slowest slice (full channel stacks) |

_Categories with n < 5 (QA, TRAKE, temporal) are flagged small-sample; numbers are descriptive only._

## Failure taxonomy distribution (Q0)

| category | count |
|---|---|
| `poor_frame_sampling` | 2 |
| `temporal_understanding_required` | 1 |
| `correct_result_outside_top20` | 3 |
| `unresolved` | 1 |

See `failure-taxonomy.md` for per-query evidence.
