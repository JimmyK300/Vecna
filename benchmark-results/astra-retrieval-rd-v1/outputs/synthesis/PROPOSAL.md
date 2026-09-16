# Packet E — one proposed follow-up

Status: ready for parent review; proposal only. The admission arm has not been implemented or scored. The evidence snapshot binds the completed Packet D ledger and independently checked saved-set headroom report.

Propose one fixed-budget test of provider-balanced frame admission, using the exact saved Packet B rankings. Keep current fusion scoring, its output budget of 100 frames, its stable tie order and its downstream analysis projection fixed. Change only which eligible frames enter that 100-frame set.

Packet B selected `fusion_current_control` under the predeclared global order. Distinct-video R@20 was87/113 and MRR@20 was0.529989; the matched same-capture Qwen control was84/113 and 0.507495. RRF, min–max, robust sigmoid and softmax reached85,84,81 and86 video successes, respectively. None justifies global replacement. Current fusion rescued p0_q02, p1_q04 and p2_q21 at video R@20 with no corresponding loss against its matched Qwen control, while its R@1 comparison still had 13 rescues and 11 regressions. Frozen range/event R@20 had seven rescues and the p3_q14 regression. These tradeoffs do not establish a universal integration or routing rule.

The saved active-provider union contains accepted-video evidence for 101/113 queries and every required target for 81/113. Current fusion's first 100 frames contain accepted videos for 92/113 and all targets for 78/113. This leaves only three possible complete-target admissions—p0_q02, p0_q20 and p2_q07—and one additional partial case, p2_q29, with two of four events present in the union versus zero in current 100. The proposed cyclic policy may recover none of them and may remove currently useful evidence. The ceiling is a measured reason to keep this test small.

The first-video representative projection reduces complete-target coverage from 78 to 50, with some target loss in30 queries. That projection belongs to Packet B analysis. Main returns frame hits; these numbers do not demonstrate a serving defect or a loss in historical Packet C timelines. Increasing representatives would also mechanically increase evidence quantity. A fixed 100-frame admission comparison therefore asks a more concrete question with a controlled budget.

Packet D records 82/113 successes across the observed historical/current arms and 31 remaining misses: 18 have missing required range/event evidence in the named candidate pools, six have missing accepted-video evidence, and seven remain unresolved. This observed-arm union is descriptive; it is not one deployed routing policy. Of the three fresh-B complete-target headroom cases, p0_q02 and p2_q07 are among these 31 misses; p0_q20 is already successful in an observed arm. p2_q29 remains only a partial two-of-four-event opportunity. The proposal cannot solve all remaining failures.

The completed ledger is `outputs/failure-ledger/failure_ledger.jsonl`, SHA256 `f344d6a572fcccaf7ee927774f0f76fd22008820514298f23a7ffeefd16abd6d`; its summary SHA256 is `2a551624bd73867eec85f5b39a9d7a5628665b0dc196e1b8bc50abc03e715b7a`. Saved-set headroom is `outputs/fusion/evaluation/coverage_headroom.json`, SHA256 `ec1728065dfa10ce411fbefff6ca9d4b24c8ceaf976470a9fb1fe2dc35254a36`. The supervised model-free reconstruction at Actions run35112926368 passed 40 fusion/recovery/storage tests, 27 ledger tests, exact study reconstruction and byte-identical regeneration of all four ledger files. Independent D review passed 3,611 assertions, including all 113 provider-union/current100 coverage joins.

Packet A found two bounded correct-video promotions among eight controls, with zero exact sampled-event target exposure across 31 targets. It did not establish temporal order sensitivity or localization. Packet C's historical reranker improved frozen R@20 from 68 to 76/113 with nine rescues and the p2_q14 regression (rank2 to outside20), but R@1 fell41→40 and R@10 fell65→64 at roughly 28 seconds per query. Those historical candidate and timeline surfaces remain separate from fresh Packet B. The source audit reviewed20 OCR frames and found five sampled critical-text gaps;18 ASR clips were captured but unheard. These observations do not establish extraction quality as the dominant blocker for all 113 queries.

## Frozen proposal

Use all 115 original canonical queries and score the unchanged 113. Preserve both exclusions, p0_q15 and p3_q09, all IDs, canonical full query text, phases, task types, capability labels and truth tiers. Historical C's empty p2_q17 is not an empty fresh-B query and remains in the denominator.

Use the four active raw top100 lists already captured: Qwen, SigLIP, OCR sparse and ASR sparse. Preserve the capture's native query/quote eligibility. Restrict admission to exact frame IDs in its exported candidate-tie-order union. Dense providers remain disabled. Reuse current fusion scores computed over that entire frozen union; do not renormalize after admission.

The proposed arm has one global cyclic provider order: Qwen → SigLIP → OCR sparse → ASR sparse. On each provider's turn, advance through its saved list until the next eligible frame that has not been admitted, then admit one frame. Skip exhausted providers. Continue until100 distinct frames have been admitted, or the eligible union is exhausted. No per-video cap, spacing rule, query-specific quota or ground-truth choice is added.

After membership is fixed, sort admitted frames by the existing current-control score, breaking ties by the original exported candidate tie order. Retain the same current-control frame and video projection semantics for secondary ranking metrics. The control is the existing globally selected current-control first 100; the experiment does not reselect a global winner or use a per-query oracle.

## Measurements and decision

The primary outcome is required-target presence in the admitted100 frames before any video representative projection. Report binary all-target coverage and mean fractional target coverage under the same frozen range/event semantics. Separately report accepted-video presence, video R@1/@5/@10/@20 and MRR@20, frame-position video ranks, and frozen range/event metrics. List every gained and lost target/query and every rank regression. Keep provisional temporal truth visible in a separate slice.

A positive bounded result requires at least two complete-target rescues, zero complete-target regressions, a positive change in mean fractional target coverage, and no per-query regression in accepted-video presence within the100 frames. Report ordinary paired-query95% bootstrap intervals with seed82 and10000 resamples. A positive lower confidence bound is not a gate: only three complete-target rescues are possible here, and even all three without a loss yield a zero lower percentile bound for the binary endpoint. This is a small mechanism test, not evidence of generalization or production readiness.

Return negative if no complete-target rescue occurs, or if target coverage fails to improve while required-target regressions occur. Other outcomes are inconclusive. Do not adjust provider order, quotas, depth, spacing, weights or temperature after observing results. A new policy would require a new explicitly frozen experiment.

Stop before scoring if canonical identity, scoreability, source/config/capture hashes, active-provider states, current replay or output budgets disagree. Stop if the recomputed union has no headroom or the proposed admitted sets equal control for every query. Do not collect new providers, rewrite queries, rerank, train, re-embed a corpus or integrate a runtime change as part of this proposal.

The experiment can be run entirely over saved rankings with standard Python. It needs no model allocation, live index access or new inference. Its artifacts should bind the existing capture and scorer, preserve all 115 admission sets and scores, and contain the complete 113 paired result rows plus the decision. No implementation is part of Packet E.

The proposal's input and decision fields are preserved in `decision.json`. The fixed capture is SHA256 `d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82`, with run identity `f0d32893564111064d47f6f2f72f7b03dbb14ebbfbb3d05c48e49e30ef165755`. Both are reused without new retrieval.

