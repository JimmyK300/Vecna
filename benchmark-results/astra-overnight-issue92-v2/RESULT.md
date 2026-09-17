# Semantic cross-encoder: negative ranking result

Job 20260916T172450Z-ea757ee98d completed 17:41:05 UTC. Scientific acceptance
verified all 825 policy input hashes, 115 per-query cache hashes, ranking and
summary hashes, exact control rows, deterministic ranking replay, 100-frame
membership, and independently recomputed all 113 scored rows and aggregates.
Evidence is in validation/accepted.json and validation/recomputed/.

| Distinct-video metric | Exact PR91 control | Semantic cross-encoder | Delta |
|---|---:|---:|---:|
| R@1 count | 49 | 45 | -4 |
| R@5 count | 77 | 72 | -5 |
| R@10 count | 82 | 82 | 0 |
| R@20 count | 87 | 87 | 0 |
| MRR@20 | 0.5299890165650186 | 0.5087963413184652 | -0.02119267524655344 |

MRR improved on 18 queries and regressed on 25. Paired bootstrap 95% interval
for its delta is [-0.06986718081574275, 0.02610984701139566], so this is a
negative point estimate with uncertainty, not established universal harm.
R@1 rescues: p1_q11, p1_q17, p2_q02, p2_q18, p2_q20, p3_q13.
R@1 regressions: p1_q05, p1_q10, p2_q04, p2_q08, p2_q09, p2_q13, p2_q21,
p2_q26, p2_q29, p3_q27. All other paired IDs and layers are in summary.json.
R@20 and candidate coverage were invariant by construction. No promotion;
the strongest supported architecture remains the exact parent control.
The reused evaluator labels this INCONCLUSIVE because its decision rule only
uses R@20 and candidate coverage for negativity; the accuracy interpretation
above explicitly includes the negative MRR/R@1 outcome.

Workload: 2026 query-record pairs, 115 queries, zero truncated pairs, zero
new corpus embeddings. Same-session pair inference totaled 944.6247307 seconds.
Model loading reported no missing, unexpected or mismatched keys. CPU float32,
torch 2.8.0+cpu, transformers 4.57.6; 567755777 parameters. These times are not
production latency estimates.

Policy SHA-256:
1fc8828282ff85a215e0b6ff72abd915ae09feaf5fb9222cb45cd526f88d533b.
Source, exact dependencies, cache identities and scoring contract are retained
in policy.json and README.md. Code remains uncommitted on the isolated branch.

Next hypothesis: semantic descriptions may discard frame-local lexical
evidence. Test the same cached text model on existing OCR/ASR for the control's
top30 frames, using one globally frozen rule in v3. Do not select individual
queries from the rescue/regression list. Saved multimodal scores still lack
matched fresh candidate coverage; they are not substituted as valid inference.
