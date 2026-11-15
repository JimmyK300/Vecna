# Fusion sweep on the 113-query development benchmark

Summary copied from the evidence packet at commit
[`37b3210`](https://github.com/JimmyK300/Vecna/blob/37b321048432ccba5182a66bd39b1ca73c547537/benchmark-results/astra-retrieval-rd-v1/REPORT.md)
(branch `btl/issue-82-failure-ledger-and-proposal`, draft PR #84 / #91).
This file contains query IDs only. It does not include contest query text, frames or OCR/ASR text.

## Setup
- **Cohort:** 115 canonical query identities and 113 scoreable rows. `p0_q15` and `p3_q09` are excluded, and the empty `p2_q17` stays in the denominator.
  The ground truth is a team-built development control, not organizer gold.
- **Providers:** one fresh capture of Qwen3-VL visual, SigLIP2 visual, OCR sparse (BM25) and ASR sparse (BM25), top-100 per provider.
  Query rewriting, translation and reranking are disabled.
- **Controlled comparison:** every arm sees identical raw provider hits, candidate identities, tie order and weights. Only the fusion rule changes.
  The winner is picked by a frozen ordering (R@20, then MRR@20, then R@1), with no per-query selection, weight search or temperature tuning.
- **Primary metric:** distinct-video recall at k and MRR@20.

## Results (distinct-video)

| Arm | R@1 | R@5 | R@10 | R@20 | MRR@20 |
|---|---:|---:|---:|---:|---:|
| **Current control (weighted score sum, shipped)** | 49/113 | 77/113 | 82/113 | **87/113** | **0.529989** |
| RRF, k=60 | 36/113 | 68/113 | 76/113 | 85/113 | 0.433591 |
| Min-max sum | 36/113 | 67/113 | 79/113 | 84/113 | 0.429601 |
| Robust-z/sigmoid sum | 36/113 | 61/113 | 69/113 | 81/113 | 0.411475 |
| Softmax sum, T=1 | 16/113 | 62/113 | 80/113 | 86/113 | 0.304353 |
| Matched fresh Qwen only | 47/113 | 71/113 | 79/113 | 84/113 | 0.507495 |

## Paired comparison against the current control
Paired bootstrap, 95% intervals:

| Alternative | R@20 rescues / regressions | R@20 Δ (pp) | 95% CI | MRR Δ | 95% CI |
|---|---:|---:|---:|---:|---:|
| RRF | 4 / 6 | −1.77 | [−7.08, +3.54] | −0.0964 | [−0.1400, −0.0546] |
| Min-max | 5 / 8 | −2.65 | [−8.85, +3.54] | −0.1004 | [−0.1501, −0.0510] |
| Robust-z | 3 / 9 | −5.31 | [−11.50, +0.88] | −0.1185 | [−0.1718, −0.0692] |
| Softmax | 2 / 3 | −0.88 | [−4.42, +2.65] | −0.2256 | [−0.2893, −0.1618] |

## Reading
- The shipped weighted-sum fusion is the best of the five fusion families tested, and its MRR margin over each alternative has a 95% interval that excludes zero.
- Against Qwen-only, current fusion gives 3 R@20 rescues and 0 regressions (+2.65 pp, CI [0.00, +6.19]), but the MRR difference is not significant (+0.022, CI [−0.038, +0.082]).
  This supports keeping the fusion. It does not show broad superiority over Qwen alone.
