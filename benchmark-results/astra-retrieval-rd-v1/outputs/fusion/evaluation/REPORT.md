# Packet B fusion study

Descriptive global winner: `fusion_current_control`. Production integration remains off.

115 queries were collected with exact main-transform replay; the pinned mapping scores113 and excludes p0_q15/p3_q09. The primary experiment assigns nonzero weights to four providers; actual availability remains explicit. Its top100 raw-provider surface is distinct from the historical UI pool and preserves native quote eligibility.

B uses the separately verified Qwen loader repair and the current constructor's exhaustive625-tensor checkpoint proof. Its matched Qwen-only control comes from this same capture. Historical C candidates and corpus feature/index loader lineage are separate, unresolved provenance questions; this query-loader repair does not establish or invalidate their correctness. Cross-packet differences are descriptive, while B's paired fusion comparisons hold its corrected provider lists fixed.

| Arm | Video R@1 | R@5 | R@10 | R@20 | MRR@20 | Median observed retained rank |
|---|---:|---:|---:|---:|---:|---:|
| fusion_current_control | 49/113 | 77/113 | 82/113 | 87/113 | 0.529989 | 1.0 |
| fusion_rrf | 36/113 | 68/113 | 76/113 | 85/113 | 0.433591 | 2 |
| fusion_minmax_sum | 36/113 | 67/113 | 79/113 | 84/113 | 0.429601 | 2 |
| fusion_robust_z_sum | 36/113 | 61/113 | 69/113 | 81/113 | 0.411475 | 3.0 |
| fusion_softmax_sum | 16/113 | 62/113 | 80/113 | 86/113 | 0.304353 | 3 |
| qwen_only_matched | 47/113 | 71/113 | 79/113 | 84/113 | 0.507495 | 1 |

Primary video ranks collapse duplicate videos after retaining100 fused frames. Separate frame-position video and frozen range/event scores are retained in summary.json so comparisons with Packet C do not mix ranking units.

| Alternative vs current | R@20 rescues / regressions | R@20 delta (95% paired interval) | MRR@20 delta (95% paired interval) |
|---|---:|---|---|
| fusion_rrf | 4 / 6 | -0.0177 [-0.0708, +0.0354] | -0.0964 [-0.1400, -0.0546] |
| fusion_minmax_sum | 5 / 8 | -0.0265 [-0.0885, +0.0354] | -0.1004 [-0.1501, -0.0510] |
| fusion_robust_z_sum | 3 / 9 | -0.0531 [-0.1150, +0.0088] | -0.1185 [-0.1718, -0.0692] |
| fusion_softmax_sum | 2 / 3 | -0.0088 [-0.0442, +0.0265] | -0.2256 [-0.2893, -0.1618] |

Evidence classification: `no_alternative_wins_the_predeclared_global_order`. Winner selection and capability slices use the same cohort; intervals are descriptive and unadjusted for selection/multiplicity.

Benefit scope: no globally winning alternative under the declared selection order.

Winner R@20 regressions: none.
Winner top1 regressions: none.

Provider contribution/removal evidence, full paired IDs, normalization diagnostics and category slices are retained. Removal keeps the normalizers and candidate union fixed; it suggests hypotheses without fitting weights. Candidate absence is a mechanical diagnosis; semantic, OCR/ASR extraction and outlier explanations remain unverified unless separately inspected.

Six historical TRAKE rows use provisional submission anchors; P3 truth remains source-text provisional. No ordinary organizer-certified temporal metric is implied. No production retrieval, model training or corpus embeddings were changed.
