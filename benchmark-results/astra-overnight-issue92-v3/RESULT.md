# Existing frame text: no overall improvement

Job 20260916T174638Z-cb4ad7fb45 completed at 18:15:08 UTC. Acceptance verified
all policy dependencies, 6350 source-file hashes, 115 query-cache hashes, final
rankings/summary hashes, exact control rows, deterministic ranking replay and
unchanged uncovered/tail slots. Independent rescoring reproduced every metric
and coverage aggregate on the 113 scoreable rows. See validation/accepted.json.

| Distinct-video metric | PR91 control | Frame text top30 |
|---|---:|---:|
| R@1 count | 49 | 46 |
| R@5 count | 77 | 77 |
| R@10 count | 82 | 84 |
| R@20 count | 87 | 87 |
| MRR@20 | 0.5299890165650186 | 0.5148030840118294 |

MRR delta is -0.0151859325531892. R@1 rescues: p0_q02, p1_q17, p1_q23,
p3_q14. R@1 regressions: p0_q04, p1_q07, p1_q10, p1_q12, p1_q20, p2_q08,
p2_q26. R@10 rescues: p3_q03 and p3_q25, with no regressions at that cutoff.
R@5 has three rescues and three regressions; all IDs, MRR changes and paired
bootstrap intervals are preserved in outputs/frame-text/summary.json.
Candidate video/complete/fractional coverage is exactly unchanged by design.

Do not promote: the deeper-rank gain does not offset the observed MRR/R@1
loss. The inherited evaluator's INCONCLUSIVE label reflects its R@20/coverage
decision gate, not absence of the negative first-rank point estimate.

Workload: 3275 new query-frame text pairs, 115 queries, zero truncated pairs,
1682.5346248 seconds of same-session pair inference. No new frame extraction
or corpus embedding. Preserve runtime/contention and repeated-benchmark caveats.

Policy SHA-256:
9385cca52326fc03a8c1fb0b5142fbf65003d5c838b0f9f573d427812c376fdd.
Exact source, code, model, queries, rankings, truth and scoring dependencies are
hash-bound in policy.json; text strings are included in inputs/. Research is
uncommitted; no remote publication or production change is claimed.
