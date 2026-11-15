# Qwen3-VL reranker audit on the 113-query development benchmark

Summary copied from the evidence packet at commit
[`37b3210`](https://github.com/JimmyK300/Vecna/blob/37b321048432ccba5182a66bd39b1ca73c547537/benchmark-results/astra-retrieval-rd-v1/outputs/reranker/REPORT.md)
(branch `btl/issue-82-failure-ledger-and-proposal`, draft PR #83 / #91).
This file contains query IDs only.

**Decision:** the reranker is **not shipped**. It stays experimental and operator-triggered: R@20 improves, R@1 and R@10 don't, and it costs about 28 s per query.

## Setup
- This is a historical saved-rank comparison: Qwen3-VL retrieval baseline vs. the same pool reranked (top-20 retained per query).
- **Metric:** the *frozen range/event contract*, which requires the accepted time range or event and is stricter than the distinct-video metric in [fusion_sweep_113.md](fusion_sweep_113.md).
  The capture also differs from the fusion sweep's, so don't compare the two tables head to head.
- **Statistics:** 10,000-resample paired bootstrap, seed 82.

| Metric | Baseline | Reranker | Gain / loss queries | Δ pp (95% CI) |
|---|---:|---:|---:|---:|
| R@1 | 41/113 | 40/113 | +15 / −16 | −0.88 [−10.62, +8.85] |
| R@5 | 56/113 | 61/113 | +15 / −10 | +4.42 [−4.42, +13.27] |
| R@10 | 65/113 | 64/113 | +8 / −9 | −0.88 [−7.96, +6.19] |
| **R@20** | **68/113** | **76/113** | +9 / −1 | **+7.08 [+1.77, +12.39]** |
| MRR@20 | 0.424340 | 0.432021 | +26 / −24 | +0.77 [−6.59, +8.51] (×100) |

## Latency
114 non-empty reranks averaged **28.219 s** (p50 28.049 s, p95 30.742 s).
That is the rerank cost only, not end-to-end search. Cold-load time can't be recovered from the logs.

## Why it was not shipped
The R@20 gain is real but comes with no R@1 or R@10 gain. MRR is flat, and the latency is far beyond the interactive budget of a live contest round.
The recommended next step is a preregistered latency budget plus a truth-independent trigger, evaluated on held-out queries.
