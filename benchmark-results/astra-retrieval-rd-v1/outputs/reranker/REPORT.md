# Packet C: retained Qwen3-VL reranker utility

Recommendation: keep reranking experimental and operator opt-in. The retained result improves R@20 while regressing R@1/R@10; the MRR difference is small and latency is about 28 seconds per query. No automatic conditional gate has been validated.

Runtime qualification: these are historical saved-rank measurements. C's exact package versions, loaded tensor state and corpus extraction/index lineage remain unverified. The separate current Qwen defect and its verified repair do not establish historical contamination or retroactively certify C. See [the loader provenance followup](LOADER_PROVENANCE_LIMIT.md) for immutable historical evidence and the pinned current repair proof.

The exact 113-query join and every frozen per-query score reproduce. P0–P2 contain 72 accepted-range and 6 strict all-event TRAKE cases; P3 contains 35 provisional source-text cases, including 2 fractional TRAKE cases. Historical TRAKE windows are submission-anchor proxies; frozen benchmark truth is a development control, not organizer gold. Excluded: p0_q15 and p3_q09. QA measures retrieval location, not answer correctness.

| Metric | Frozen baseline | Frozen reranker | Paired gain/loss queries | Delta, percentage points (95% bootstrap CI) |
|---|---:|---:|---:|---:|
| R@1 | 41/113 | 40/113 | +15 / −16 | -0.88 [-10.62, +8.85] |
| R@5 | 56/113 | 61/113 | +15 / −10 | +4.42 [-4.42, +13.27] |
| R@10 | 65/113 | 64/113 | +8 / −9 | -0.88 [-7.96, +6.19] |
| R@20 | 68/113 | 76/113 | +9 / −1 | +7.08 [+1.77, +12.39] |
| MRR@20 | 0.424340 | 0.432021 | +26 / −24 | +0.77 [-6.59, +8.51] |

MRR deltas are shown ×100 in the last column; bootstrap uses 10,000 paired-query resamples, seed 82. These are descriptive uncertainty estimates for this cohort, with no held-out or multiplicity-adjusted claims. Shared videos and near-duplicate query templates may violate independent-query assumptions.

| Diagnostic layer | Baseline R@1 / R@5 / R@10 / R@20 | Reranker R@1 / R@5 / R@10 / R@20 | Baseline → reranker MRR@20 |
|---|---|---|---|
| Video presence, candidate positions | 59 / 69 / 76 / 82 | 59 / 76 / 81 / 94 | 0.570656 → 0.587494 |
| Frozen range/event contract | 41 / 56 / 65 / 68 | 40 / 61 / 64 / 76 | 0.424340 → 0.432021 |
| Diagnostic: original timelines restored | 41 / 56 / 65 / 68 | 40 / 61 / 64 / 76 | 0.424340 → 0.432021 |
| Diagnostic: first frame only in both arms | 40 / 55 / 64 / 68 | 40 / 61 / 64 / 76 | 0.416122 → 0.432021 |

Video scoring accepts any target video at its candidate rank and keeps duplicates; it does not prove localization or ordered-event success.

The older #79 video control used 78 historical Headless candidates plus 35 prior P3 Qwen candidates. With the identical video metric and truth, those inputs reproduce 57/70/76/83, whereas the current Qwen-only export gives 59/69/76/82. Candidate order or identity differs on 105/113 rows. This is an input-run difference, not a metric substitution; details are in legacy_video_control_audit.json. On the exact eight TRAKE cases, current video R@20 is 6/8 → 7/8 while frozen event success/recall remains zero in both arms.

Candidate audit: all 2280 retained rows match the baseline pool at their exact original rank and video/frame identity. Only the top20 is retained despite the filename containing top100. Missing reranker targets are censored at20; the unavailable 21–100 positions are never reconstructed.

The baseline top100 contains the accepted video for 102/113 queries and all required range/event targets for 86/113. An empty pool at p2_q17 is an upstream absence, not a reranking regression. Query-level pool diagnoses and every changed ranking are retained in per_query.jsonl and changed_queries.jsonl. Semantic causes remain unresolved without frame/clip review; capability tags are annotations rather than explanations.

Six queries carry baseline timelines that the reranker export drops: p0_q06, p1_q18, p2_q03, p3_q13, p3_q16, p3_q36. Timelines are restored solely for a matched-evidence diagnostic using exact original-rank links. This is not a production repair or a replacement for frozen controls.
Restoration changes retained reranker metrics for: none. Removing timelines from the baseline changes metrics for: p3_q36.

In p3_q36 the baseline timeline hits the accepted range at rank1, while its first-frame-only rank is14. The retained reranker hits at rank2 in either diagnostic. Removing baseline evidence would flip this query's MRR regression into an improvement, so frozen and matched-timeline comparisons retain the original regression.

| Phase | n | Frozen baseline → reranker R@20 | MRR change |
|---|---:|---:|---:|
| P0 | 23 | 15 → 16 | -0.014450 |
| P1 | 25 | 18 → 19 | -0.093056 |
| P2 | 30 | 17 → 19 | +0.095135 |
| P3 | 35 | 18 → 22 | +0.019219 |

Capability, truth-tier, task-type and score-family slices are in slices.json. Canonical source numbers join the capability records; current query ordinals cannot be used after task-type regrouping. Overlapping capability slices are exploratory, with no oracle-based routing recommendation.

Latency: 114 nonempty reranks average 28.219s; p50 28.049s; p95 30.742s. All 115 exported rows include one zero-latency empty pool; their mean is 27.973s. The stored 27,973.2ms average includes that empty pool. The first query takes 27.062s; subsequent nonempty queries average 28.229s. The log says the model loads once, but supplies no timed load interval, so cold-load overhead cannot be recovered. JSON timing agrees with the rounded stdout durations. These are rerank costs, not end-to-end or baseline-search costs.

Next experiment: preserve all100 scores and original timelines, then preregister a latency budget and a truth-independent trigger for held-out evaluation. Existing post-hoc gains do not justify always-on deployment.

Reproduce from the evidence packet root:

```bash
python code/analyze_reranker.py --root . --out-dir outputs/reranker --bootstrap-resamples 10000
python -m unittest discover -s tests -p test_reranker_analysis.py -v
```

Inputs are Git-blob verified against inputs/sources.json; provenance.json records pinned commits and SHA-256. The pinned scorer and control reproduction remain separate. No weights, model calls or production defaults changed.
