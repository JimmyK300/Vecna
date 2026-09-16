# Vecna retrieval R&D after the 113-query benchmark

**Recommendation:** retain the current fusion rule on the tested configuration; keep the historical reranker experimental or operator-triggered; review the separately verified Qwen loading repair before any fresh use of that wrapper. The native ordered-image result supports a narrow ranking signal on the bounded temporal pool, without evidence of event localization.

**Publication status:** Packets0–D are complete with their recorded limitations, and Packet E is one unimplemented proposal. Source, sparse/dense visibility, the Qwen loading repair and the separate deterministic-tie fix are available on draft review branches. No merge to main is requested or performed.

## Cohort and interpretation

The benchmark preserves 115 canonical query identities and 113 scoreable rows. Exclusions are `p0_q15` and `p3_q09`; empty historical `p2_q17` stays in the denominator. Query rewriting, translation, reranking and non-target text transformations are disabled in the fresh provider capture. Ground truth is scoring-only outside the explicit source-truth review.

The three scoring surfaces below are separate: distinct-video rank, video identity at raw frame positions, and the frozen range/event contract. Historical C and fresh B have different capture provenance and must not be presented as a controlled head-to-head model comparison. The union in D is a diagnostic inventory of observed successes, not a deployable oracle.

## B: current fusion remains the best supported family

The fresh capture includes Qwen visual, SigLIP visual, OCR sparse and ASR sparse, top100 per active provider. OCR/ASR dense are disabled by the frozen main configuration and are audited separately. Every fusion arm uses identical raw provider hits, candidate identity, captured tie order and weights. The current control preserves the actual nested visual score sum and native text eligibility/boost/scaling. It is not an RRF baseline.

Primary metrics are distinct-video scores on 113 queries:

| Arm | R@1 | R@5 | R@10 | R@20 | MRR@20 |
|---|---:|---:|---:|---:|---:|
| Current control | 49/113 | 77/113 | 82/113 | **87/113** | **0.529989** |
| RRF, k=60 | 36/113 | 68/113 | 76/113 | 85/113 | 0.433591 |
| Min-max sum | 36/113 | 67/113 | 79/113 | 84/113 | 0.429601 |
| Robust-z/sigmoid sum | 36/113 | 61/113 | 69/113 | 81/113 | 0.411475 |
| Softmax sum, T=1 | 16/113 | 62/113 | 80/113 | 86/113 | 0.304353 |
| Matched fresh Qwen only | 47/113 | 71/113 | 79/113 | 84/113 | 0.507495 |

The global winner was selected by the frozen ordering: video R@20, then MRR@20, then R@1, then fixed arm order. No per-query winner, weight search or temperature tuning is used.

| Alternative vs current | R@20 rescues / regressions | R@20 delta, percentage points | Paired 95% interval | MRR delta | Paired 95% interval |
|---|---:|---:|---:|---:|---:|
| RRF | 4 / 6 | -1.77 | [-7.08, +3.54] | -0.0964 | [-0.1400, -0.0546] |
| Min-max | 5 / 8 | -2.65 | [-8.85, +3.54] | -0.1004 | [-0.1501, -0.0510] |
| Robust-z | 3 / 9 | -5.31 | [-11.50, +0.88] | -0.1185 | [-0.1718, -0.0692] |
| Softmax | 2 / 3 | -0.88 | [-4.42, +2.65] | -0.2256 | [-0.2893, -0.1618] |

Current fusion versus matched fresh Qwen yields three R@20 rescues and no R@20 regressions: `p0_q02`, `p1_q04`, `p2_q21`. The +2.65-point paired R@20 interval is [0.00, +6.19]. R@1 has 13 gains and 11 losses. MRR has 14 gains and 20 losses, with mean delta +0.022494 and interval [-0.037519, +0.082062]. These results support retaining the control; they do not establish broad superiority over Qwen from a small number of gains.

The lower-level metrics show why the scoring surface matters:

| Arm | Frame-position video R@1/5/10/20 | Frozen range/event R@1/5/10/20 | Frozen MRR@20 |
|---|---|---|---:|
| Current | 49 / 66 / 74 / 81 | 32 / 52 / 63 / 67 | 0.355963 |
| RRF | 36 / 56 / 65 / 75 | 23 / 39 / 51 / 61 | 0.267955 |
| Min-max | 36 / 43 / 50 / 61 | 22 / 28 / 34 / 46 | 0.227732 |
| Robust-z | 36 / 47 / 54 / 60 | 21 / 31 / 39 / 50 | 0.233349 |
| Softmax | 16 / 34 / 37 / 39 | 4 / 19 / 21 / 26 | 0.084650 |
| Matched Qwen | 47 / 65 / 71 / 78 | 31 / 52 / 58 / 61 | 0.352539 |

The original scratch/Linux offline mean fusion CPU times were 0.8113 ms current, 0.7088 RRF, 0.4040 min-max, 0.6188 robust-z and 0.4823 softmax. They exclude retrieval and model inference and are not an isolated performance benchmark. The separate Windows recovery CPU clock is quantized: zero median or p95 readings must not be interpreted as free work. Its wall-clock timings are recorded with that replay. The recovery replay preserves the original capture and all six primary metrics; its timing-dependent study hash is explicitly a new analysis identity.

The complete provider union contains an accepted video for 101/113 queries; current fusion's first 100 frames contain one for 92/113. All-required-target coverage is 81 in the union and 78 in current first 100 frames. Three full-target opportunities remain between those surfaces: `p0_q02`, `p0_q20`, `p2_q07`; `p2_q29` has an additional fractional opportunity from 0 to 0.5.

Selecting a single representative frame per video reduces measured all-target coverage further, but the inspected main searcher returns the full sorted frame list. That representative projection is an analysis convention; it does not establish that a production consumer discards the other frames.

## C: reranker gains do not justify unconditional integration

The saved historical reranker comparison reproduces the frozen scorer:

| Metric | Historical Qwen | Historical reranker |
|---|---:|---:|
| Frozen R@1 | 41/113 | 40/113 |
| Frozen R@5 | 56/113 | 61/113 |
| Frozen R@10 | 65/113 | 64/113 |
| Frozen R@20 | 68/113 | 76/113 |
| Frozen MRR@20 | 0.424340 | 0.432021 |

There are nine frozen R@20 rescues and one regression, `p2_q14`. The paired 10,000-resample bootstrap, seed 82, gives a +1.77 to +12.39 percentage-point interval for R@20 and -0.0659 to +0.0851 for MRR. R@1 and R@10 do not improve.

The artifact retains 20 candidates for each of 114 active reranks despite its top100 filename. All 2,280 retained occurrences are traceable to original baseline candidates. Observed active-call latency averages 28.219 seconds, with p50 28.049 and p95 30.742 seconds. Cold load/warmup cannot be separately recovered.

Keep the reranker experimental or operator-triggered. Capability slices are descriptive; they do not establish a pre-truth routing rule. The current loading defect has its own verified evidence and does not retroactively invalidate the historical reranker comparison.

## A: a narrow native ordered-image gain

The candidate budget was frozen globally at N=3 for the eight established temporal controls. Each representation uses identical candidate windows and matched sampled pixels; there are 24 windows, 72 exact sampled frames and 17 source videos.

| Representation | Correct-video R@1 | Correct-video MRR |
|---|---:|---:|
| Single center frame | 0/8 | 0.125000 |
| Stitched three-frame sheet | 0/8 | 0.104167 |
| Native ordered three images | **2/8** | **0.250000** |

`p0_q23` moves from rank2 to rank1. `p3_q34` moves from rank2 in the center-frame control and rank3 in the stitched control to rank1. No observed ranking regression occurs. Only these two queries have a correct video in the frozen pool, and no required event anchor among the 31 is exposed. The decision is therefore a narrow `POSITIVE_TEMPORAL_SIGNAL` for video ranking, with no demonstrated event localization or causal order sensitivity.

The model/encoding stage takes 193.635 seconds; query encoding 10.698 seconds, image encoding 174.051 and load 4.976. Per 24-image arm image times are 29.114 seconds single frame, 72.001 stitched and 72.936 native. Processor evidence proves three distinct ordered image groups; it does not prove that the gain is caused by order. No N expansion, prompt grid, five-image extension or new video model was launched.

## Supporting #16/#17 review

Temporal review preserves the existing weak truth. It provides source clips, stills and filmstrips for 31 event records: 16 supported representative points and 15 unknown. Event boundaries remain null. The reviewed sources expose, among other limitations, the bread-versus-bottles mismatch alongside noodle cartons in `p2_q30`, shrimp contact preceding the prior `p3_q21` point, and already-visible flame before the `p0_q24` anchor. These are review overlays, not certified ordinary ranges or changes to the benchmark.

The OCR/ASR sample is frozen at 38 query/channel pairs across 30 queries. All 20 OCR images were inspected. Five sampled source gaps are recorded at `p0_q13`, `p0_q19`, `p0_q20`, `p0_q21`, `p1_q24`; the last has answer text elsewhere in the window. These observations are not automatically retrieval-stage failures. All 18 ASR clips are captured and hash-verified but remain unheard; no transcript-fidelity claim or WER/CER is made.

| Frozen visibility sample | OCR sparse | OCR dense | ASR sparse | ASR dense |
|---|---:|---:|---:|---:|
| Query/channel pairs | 20 | 20 | 18 | 18 |
| Accepted video within 100 hits | 7 | 9 | 13 | 14 |
| All current targets within 100 hits | 4 | 7 | 11 | 12 |
| Same-video/exact-text repeat excess | 344/2000 | 243/2000 | 1682/1800 | 1599/1800 |

OCR target coverage has 3 pairs reached by both methods, 4 by dense only, 1 by sparse only and 12 by neither. ASR has 11 both, 1 dense only, 0 sparse only and 6 neither. Dense scoring matched 731/731 checked text projections and reproduced all four output files byte-for-byte. All six consumed BGE files and 389 active tensors / 566,705,152 elements were verified. No frozen query truncated at 1024 tokens.

Sparse equal-score frame order varies with process hash seed. The independent dense audit also finds 36/38 order changes confined to exact equal-score groups, preserving all 38 complete score sequences. ASR main-eligible target R@1 is 4/18 on the captured host order and 4/18, 7/18, 5/18 for seeds 0, 1, 82; R@20 remains9/18. All 152 host/seed score objects were independently reproduced and no favorable seed was selected. Issue #89 tracks the correctness defect separately. Draft PR #90 makes exact text-score ties deterministic by canonical frame ID; nine tests over 13 fixtures and three process seeds pass. The completed Packet82 captures preserve their original observed orders.

## D: unified failure ledger

The completed ledger contains one row for each of the 113 scoreable queries. Its descriptive union records 82 frozen-R@20 successes and 31 remaining misses.

| Primary outcome | Queries | Interpretation |
|---|---:|---|
| Observed success (`none`) | 82 | At least one recorded baseline, reranker or selected fusion arm succeeds. |
| `candidate_generation_missing_video` | 6 | No accepted video in the inspected historical C pool or fresh B active-provider union. |
| `candidate_generation_missing_event` | 18 | An accepted video is observed, but at least one required frame/range/event target is absent from those saved pools. |
| `unresolved` | 7 | Saved target evidence exists; the remaining ranking miss does not establish a more specific cause. |

The six missing-video cases are `p0_q21`, `p1_q18`, `p2_q03`, `p2_q27`, `p3_q11`, `p3_q24`. The seven unresolved cases are `p0_q02`, `p0_q18`, `p1_q14`, `p2_q01`, `p2_q07`, `p3_q03`, `p3_q30`. The full ledger preserves all 18 missing-target IDs, capability/category counts, historical baseline labels, current pool evidence, provider visibility and the smallest follow-up for every row.

Candidate coverage is the established obstruction for 24 of the 31 remaining misses. This describes the inspected saved pools, not a proof of absence from the entire collection or a confident OCR/ASR, visual-semantic or calibration diagnosis.

The cross-run MRR contrast identifies `p1_q09`, `p2_q02`, `p3_q07`, `p3_q28` where fresh fusion improves over the historical reference while the historical reranker regresses. This is separate from the R@20-preservation case `p2_q14`. Seven temporal queries have a correct video in historical top100 but lack the complete event contract: `p0_q23`, `p0_q24`, `p1_q25`, `p2_q29`, `p2_q30`, `p3_q21`, `p3_q34`.

Forty-one queries retain provisional text or historical event-proxy qualifications. Source review did not establish any query as failing mainly because of truth quality; the ledger explicitly leaves that causal attribution unestablished.

An independent join of current C per-query evidence and recovered B scores gives 82/113 observed frozen-R@20 successes and 31 remaining misses. B supplies five successes absent from historical baseline and reranker: `p1_q04`, `p2_q23`, `p3_q13`, `p3_q26`, `p3_q27`. Current fusion retains the historical reranker's regression `p2_q14`. The reranker rescues five historical-baseline misses not reached by current fusion: `p0_q20`, `p2_q11`, `p2_q28`, `p3_q16`, `p3_q29`.

This is a diagnostic union across differently captured experiments. It is not a claim that one deployed method achieves 82/113. Source observations, sparse/dense visibility and tie behavior remain evidence overlays; they do not force confident extraction or calibration diagnoses.

## E: one next experiment, not implemented

Propose one model-free test of provider-balanced admission at the same 100-frame budget. Cycle globally through Qwen, SigLIP, OCR sparse and ASR sparse, admitting the next eligible unseen frame from each saved list. Reuse current fusion scores computed over the full frozen union and its original tie order; do not renormalize after admission.

A positive bounded result requires at least two complete-target rescues, zero complete-target regressions, a positive mean fractional-coverage change and no per-query loss of accepted-video presence. Report every regression and the paired 95% intervals; a strictly positive lower bound is not an attainable gate for a binary endpoint with only three possible rescues.

Only `p0_q02` and `p2_q07` among the three full-target headroom cases belong to D's remaining 31 misses. `p0_q20` is already solved in an observed historical arm, and `p2_q29` offers only partial coverage. This is a cheap test of a small observed loss at admission, not a proposed solution to all 31 misses. The full frozen policy, stop conditions and evidence hashes are in [PROPOSAL.md](outputs/synthesis/PROPOSAL.md) and [decision.json](outputs/synthesis/decision.json).

The bounded candidate-admission headroom is three full-target cases and one partial case. The proposal specifies one fixed provider-balanced admission rule on saved lists at the same 100-frame budget, preserving fusion scores and query text. It will not add a model, retrain, re-embed, change production retrieval or perform a quota/weight grid.

## Validation and review locations

The combined host run passed **40 fusion/recovery/storage tests** and **27 ledger tests**, reconstructed the complete study byte for byte and repeated all four ledger outputs byte for byte. A portable independent reviewer passed **3,611 assertions**, checking schema, source identities, every observed-pool coverage record and all final file hashes. Original A validation passed 31 tests, historical C analysis 12 tests, and the checkpoint repair 12 tests. The separate tie fix passed 9 tests over 13 fixtures and three process seeds.

A fresh archive of the published Git snapshot also passed: remote binary hydration, exact study reconstruction, all 49 inputs and all four published ledger outputs. [Published-snapshot proof](outputs/synthesis/published-snapshot-verification.json).

[REPRODUCE.md](REPRODUCE.md) provides the exact published-snapshot verification command. Per-query evidence, source hashes, lossless capture, timing sidecar, reconstruction proof and complete validation logs are included in the review branches.

- [Packet0/C draft PR83](https://github.com/JimmyK300/Vecna/pull/83)
- [Packet B draft PR84](https://github.com/JimmyK300/Vecna/pull/84)
- [Packet A draft PR85](https://github.com/JimmyK300/Vecna/pull/85)
- [Source, temporal and visibility draft PR87](https://github.com/JimmyK300/Vecna/pull/87)
- [Verified Qwen checkpoint repair draft PR88](https://github.com/JimmyK300/Vecna/pull/88)
- [Deterministic text ties draft PR90](https://github.com/JimmyK300/Vecna/pull/90)
- [Native dataset review draft PR18](https://github.com/JimmyK300/official-dataset-control/pull/18)

Main remains unchanged. Every integration decision remains subject to review of the separate draft PR and its exact evidence.
