# OCR-only result: negative

Verified 115 query caches, 19756 source hashes, all 257 reused scores, independent
ranking replay and 113 score rows. Validation is in validation/accepted.json.

Distinct-video R@1/5/10/20 counts are 49/72/81/86 of 113; MRR@20 is
0.5231422170697905. Relative to accepted v5, R@20 loses four queries:
p1_q22, p2_q07, p2_q16, p3_q15, with no rescues. MRR delta is
-0.017501242611862082, paired bootstrap 95% interval
[-0.03482442704787837, -0.0016083719623542704]. Candidate coverage remains
94 accepted-video and 80 complete-target queries because membership is fixed.

Against exact PR91, R@20 is -1/113 and MRR delta -0.00684679949522822.
Complete per-query rescues/regressions and exact layer metrics are retained
under validation/vs-pr91 and outputs/frame-text; do not substitute the v5
comparison for the PR91 comparison.

Workload: 4356 scored pairs, 4099 new and 257 reused, no new truncation,
2209.4964079 seconds of same-session inference. This timing is not a controlled
cross-arm speed comparison. No new model downloads or index mutations.

Do not promote. Accepted v5 remains the parent for the complementary ASR-only
ablation. These are repeated-benchmark exploratory results, with inherited
provisional/proxy truth caveats and no independent holdout.
