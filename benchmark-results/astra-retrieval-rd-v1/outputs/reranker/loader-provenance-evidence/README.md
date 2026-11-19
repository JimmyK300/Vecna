# Current 115-query Qwen baseline and Qwen3-VL reranker comparison

This is the consolidated current-round headless benchmark packet for the
115-query set: P0 (24), P1 (25), P2 (30), and P3 (36).

## Arms

- `qwen_only_top100.jsonl`: Qwen3-VL-Embedding-2B baseline; the top 100
  candidates per query.
- `qwen3_vl_reranker_2b_top100.json`: the same candidate pool reranked by
  Qwen3-VL-Reranker-2B. The reranker model was loaded once for the run.
- `comparison_qwen_vs_reranker.{json,md}`: paired comparison and metrics.
- `ground_truth_current_115.jsonl` plus its manifest and README: the current
  query ledger and explicit scoring gates.

## Provisional comparison

Only 35 P3 rows have provisional source-text-verified targets. The remaining
80 rows are retained for retrieval inspection but are not treated as scored
organizer truth. On the 35-row provisional gate:

| Arm | R@1 | R@5 | R@10 | R@20 | MRR@20 | No-hit@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen-only | 0.228571 | 0.428571 | 0.485714 | 0.514286 | 0.316463 | 17 |
| Qwen + reranker | 0.228571 | 0.457143 | 0.485714 | 0.628571 | 0.335681 | 13 |

The reranker delta is 0 at R@1, +2.9 percentage points at R@5, 0 at R@10,
and +11.4 percentage points at R@20. These are provisional retrieval
comparisons, not organizer scores.

## Top-20 candidate rerank

`qwen3_vl_reranker_2b_top20.json` reranks only the first 20 Qwen-only
candidates per query. The paired outputs are
`comparison_qwen_vs_reranker_top20.{json,md}`. On the same 35-row provisional
gate, Qwen + reranker reaches R@1 0.228571, R@5 0.457143, R@10 0.485714,
R@20 0.514286, MRR@20 0.310058, and No-hit@20 17. Relative to Qwen-only,
that is +2.9 percentage points at R@5, no change at R@1/R@10/R@20, and
MRR@20 -0.006405. Query `p2_q17` had zero baseline candidates and is recorded
explicitly. These are provisional retrieval comparisons, not organizer scores.

## Runtime evidence

The full-run logs are included beside the result files. They verify DirectML
on the AMD Radeon RX 6900 XT (`privateuseone:0`) for both arms. The reranker
log contains a known DirectML CPU fallback warning for
`aten::repeat_interleave.Tensor`; this affects throughput but does not mean
the model was CPU-only. No newly initialized model-weight warning was emitted.

The two smoke-test files are intentionally excluded from this publication.
The older 22-query Qwen-only archive was removed from `main` because its 22
rows were verified to be an exact result-bearing subset of this 115-query
baseline.
