# Packet B findings

The exact current score-fusion configuration remains the best supported global choice on this frozen 113-query comparison. No alternative wins the declared distinct-video R@20 → MRR@20 → R@1 → fixed-arm order. This result does not establish a universally best fusion formula or authorize production integration.

All 115 canonical queries were captured once; 113 are scored with the unchanged p0_q15/p3_q09 exclusions. Qwen, SigLIP, OCR sparse and ASR sparse each returned 100 hits for every query. Both dense providers were explicitly disabled. Every arm uses the same captured lists, output budget, native quote eligibility and exported stable tie order. The control replays main's weighted frame-hit calculation on all 115 queries before the research video projection.

| Arm | Video R@1 | R@5 | R@10 | R@20 | MRR@20 |
|---|---:|---:|---:|---:|---:|
| fusion_current_control | 49/113 | 77/113 | 82/113 | 87/113 | 0.529989 |
| fusion_rrf | 36/113 | 68/113 | 76/113 | 85/113 | 0.433591 |
| fusion_minmax_sum | 36/113 | 67/113 | 79/113 | 84/113 | 0.429601 |
| fusion_robust_z_sum | 36/113 | 61/113 | 69/113 | 81/113 | 0.411475 |
| fusion_softmax_sum | 16/113 | 62/113 | 80/113 | 86/113 | 0.304353 |
| qwen_only_matched | 47/113 | 71/113 | 79/113 | 84/113 | 0.507495 |

Current fusion's three video-R@20 rescues versus matched fresh Qwen are p0_q02, p1_q04 and p2_q21, with no R@20 regressions. Its R@1 result has 13 rescues and 11 regressions, and MRR improves for 14 queries while worsening for 20. The paired R@20 change is+3/113 with95% interval[0,0.06195]; the MRR change is+0.02249 with interval[-0.03752,0.08206]. These intervals and the overlapping category slices are descriptive on the same cohort.

Ranking units remain separate. Current fusion has 81/113 correct-video successes at original frame positions and 67/113 frozen range/event successes at 20; matched Qwen has 78/113 and 61/113. Frozen range/event rescues are p1_q04, p2_q15, p2_q21, p2_q23, p2_q24, p3_q06 and p3_q26; p3_q14 regresses. These frame-only results do not manufacture or replace historical Packet C timeline evidence.

The current control keeps main's nested max scaling: visual providers are summed before joint scaling, then combined with the established 0.5/0.25/0.25 outer visual/OCR/ASR weights and inherited alpha0 text settings. Alternative transforms use the fixed nominal 0.25 contribution per active provider. Effective coefficients therefore differ; this is a frozen-configuration comparison, not an isolated flat-weight calibration. RRF uses inherited k=60; robust normalization uses median/MAD×1.4826, clip 6 and sigmoid; softmax uses one fixed temperature 1. None is a calibrated probability.

| Alternative vs current | R@20 rescues | R@20 regressions | R@20 change95% interval | MRR change95% interval |
|---|---:|---:|---|---|
| fusion_rrf | 4 | 6 | -0.0177 [-0.0708, 0.0354] | -0.0964 [-0.1400, -0.0546] |
| fusion_minmax_sum | 5 | 8 | -0.0265 [-0.0885, 0.0354] | -0.1004 [-0.1501, -0.0510] |
| fusion_robust_z_sum | 3 | 9 | -0.0531 [-0.1150, 0.0088] | -0.1185 [-0.1718, -0.0692] |
| fusion_softmax_sum | 2 | 3 | -0.0088 [-0.0442, 0.0265] | -0.2256 [-0.2893, -0.1618] |

Every R@20 regression is visible below. A missing alternative rank means the accepted video is absent from that arm's retained 100 frames. A rank above20 means the video survives but is ranked lower. Because the provider lists are fixed and current control contains the video, these are changes introduced after retrieval; the evidence alone does not establish semantic confusion, extraction failure or a particular outlier as the cause.

| Alternative | Query | Current distinct-video rank | Alternative rank |
|---|---|---:|---:|
| fusion_rrf | p0_q17 | 8 | 32 |
| fusion_rrf | p1_q25 | 7 | absent from retained 100 |
| fusion_rrf | p2_q25 | 11 | absent from retained 100 |
| fusion_rrf | p3_q03 | 16 | 26 |
| fusion_rrf | p3_q19 | 18 | absent from retained 100 |
| fusion_rrf | p3_q34 | 17 | absent from retained 100 |
| fusion_minmax_sum | p0_q17 | 8 | 23 |
| fusion_minmax_sum | p1_q22 | 10 | absent from retained 100 |
| fusion_minmax_sum | p1_q25 | 7 | 24 |
| fusion_minmax_sum | p2_q25 | 11 | absent from retained 100 |
| fusion_minmax_sum | p3_q01 | 7 | absent from retained 100 |
| fusion_minmax_sum | p3_q03 | 16 | 22 |
| fusion_minmax_sum | p3_q19 | 18 | absent from retained 100 |
| fusion_minmax_sum | p3_q34 | 17 | absent from retained 100 |
| fusion_robust_z_sum | p0_q17 | 8 | 32 |
| fusion_robust_z_sum | p0_q18 | 4 | 24 |
| fusion_robust_z_sum | p1_q09 | 4 | 23 |
| fusion_robust_z_sum | p1_q25 | 7 | absent from retained 100 |
| fusion_robust_z_sum | p2_q18 | 4 | 21 |
| fusion_robust_z_sum | p2_q25 | 11 | absent from retained 100 |
| fusion_robust_z_sum | p3_q03 | 16 | 33 |
| fusion_robust_z_sum | p3_q19 | 18 | absent from retained 100 |
| fusion_robust_z_sum | p3_q34 | 17 | absent from retained 100 |
| fusion_softmax_sum | p2_q25 | 11 | absent from retained 100 |
| fusion_softmax_sum | p3_q19 | 18 | absent from retained 100 |
| fusion_softmax_sum | p3_q34 | 17 | absent from retained 100 |

Category tradeoffs remain visible in compact_requested_slices.json. ASR-tagged R@20 is 15/18 for current and 16/18 for each alternative, while temporal-or-TRAKE R@20 falls from 46/61 current to 42,40,39 and43. The visual-without-text-or-temporal proxy is17/21 current and18,19,17,18 for the alternatives. Combined visual/text is26/32 current and25,24,25,25. The one hard-negative-tagged query succeeds under current at 20 and fails under every alternative. Existing tags overlap; they are not causal diagnoses or validated routing conditions.

Frozen-contribution removal leaves current normalizers and its candidate union unchanged. Removing Qwen costs a net 39 video successes; removing OCR sparse costs 1, removing ASR sparse costs 3, and removing SigLIP changes none at 20. Other families have some favorable removal diagnostics, but no provider removal improves the globally selected current control. There is no weight search or evidence sufficient to prioritize a calibration integration. Full per-provider normalization/contribution diagnostics and all-layer slices regenerate with the frozen evaluator.

The final consistent Windows replay records wall-time means current 0.5846 ms, RRF 0.4077 ms, min–max 0.2895 ms, robust 0.4313 ms and softmax 0.3310 ms; respective p95 values are 0.6812, 0.4368, 0.3420, 0.6048 and 0.4919 ms. Its process-time clock is quantized at this scale: CPU medians/p95 are zero despite nonzero aggregate CPU means. Zero quantiles do not imply free computation. These timings cover the fusion calculation over saved hits, not model inference, database latency or an interactive service SLA. Earlier local timing hashes are retained as historical provenance; new replays receive new hashes.

Capture validity required the separate reviewed Qwen checkpoint repair. The original loader reported 625 missing and 625 unexpected tensors; invalid attempts produced zero provider rows. The accepted constructor passed exhaustive equality for 625 tensors / 2,127,532,032 values against the pinned checkpoint, with zero loading discrepancies. Execution used 0ee966b8ddfe367fbf5a9bb4ba8301c2d43b5e54; the research PR does not overlay production files. Historical C candidates and corpus/index producer loading lineage remain separately unresolved, and this query-loader repair neither validates nor invalidates them.

Raw capture SHA256 is d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82; run identity is f0d32893564111064d47f6f2f72f7b03dbb14ebbfbb3d05c48e49e30ef165755. RECOVERY.md describes exact raw hydration, full model-free evaluation and strict study reconstruction. The compact per-query file preserves every scored query, all six arms, retained ranks, target coverage and frozen metrics. Do not substitute it for the full study when independently rescoring Packet D.

Six historical TRAKE rows retain provisional submission-derived anchors, and P3 source-text truth remains provisional. No organizer-certified temporal metric, corpus re-embedding, training, new routing policy or production integration is claimed. The single next experiment is a separate proposal in Packet E; it is not implemented here.

Final validation passed 40 fusion/recovery/storage tests and 27 ledger tests. The complete 115-row study was reconstructed byte for byte at SHA256 `ba47bd96eb842d0bb57811e247cbd2ea29de8794c5dd3b289dce24a3032c10b1`; all four final ledger outputs reproduced byte for byte. Independent D review passed 3,599 assertions, including all 113 saved-union and current100 coverage joins. The supervised receipt is [run35112926368](https://github.com/JimmyK300/ai-routing-hub/actions/runs/35112926368); exact proofs and timing sidecar are committed with the data.
