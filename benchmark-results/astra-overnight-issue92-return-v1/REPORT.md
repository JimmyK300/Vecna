# Vecna Issue92 overnight results

Accepted exploratory arm: **v5, temporal5s deduplication plus protected-first full100 OCR/ASR text reranking**. All21 complete arms were re-scored against exact PR91. ASR-only v11 stopped at the planned compute cutoff with104/115 caches and is incomplete; no partial benchmark score is reported.

Source: PR91 / btl/issue-82-failure-ledger-and-proposal at37b321048432ccba5182a66bd39b1ca73c547537. Research branch codex/issue-92-overnight-20260916; worktree C:/Users/minhc/Code/Vecna-issue92-overnight. No research commit, push or production merge. No remote SHA for these changes. Inherited Packet0-D inputs and ledger were reused, not rerun.

## Accepted result against exact PR91

Counts R1/R5/R10/R20: **49/77/85/90**, versus **49/77/82/87**. MRR@20 **0.5406434596816525**, versus0.5299890165650186; delta **+0.01065444311663386**. R20 delta **+3/113 (+2.654867 percentage points)**. Candidate accepted-video coverage92→94; complete-target coverage78→80.

R20 rescues: **p2_q07, p2_q16, p3_q15, p3_q35**. Regression: **p3_q34**. MRR paired95% bootstrap interval[-0.004895938213255127,0.026729442161474538]; R20 interval[-0.008849557522123894,0.07079646017699115]. Both include zero. Repeated benchmark with no pristine holdout; exploratory point improvement, not proven generalization.

100 frames retained. Original fusion scoring remains unchanged; admission uses one frame per video/time5s bin, followed by the explicitly tested protected-first text rank stage. No answer-dependent thresholds or query-specific tuning. Grounded semantic arms v6/v9 reach92/113 but lose complete-target coverage against v5 (80→79/78); neither passes the original sequential-parent guardrail.

## Complete-arm table

All recall counts out of113. The source control is49/77/82/87, MRR0.5299890165650186. Common-control deltas do not override each arm's frozen sequential-parent guardrail.

| Arm | R1 | R5 | R10 | R20 | MRR20 | R20 delta | MRR delta | Complete targets |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|v1/packet-e|49|77|81|83|0.533912228381255|-4|+0.003923211816236|71|
|v1/segment-v2|49|77|82|87|0.529989016565019|+0|+0.000000000000000|78|
|v1/semantic|10|21|25|29|0.128599522404832|-58|-0.401389494160187|12|
|v1/semantic-integrated|47|62|77|84|0.483334478870658|-3|-0.046654537694361|73|
|v1/yolo|50|76|82|87|0.537068662582718|+0|+0.007079646017699|78|
|v1/query-variants|48|63|75|83|0.489140467763512|-4|-0.040848548801506|73|
|v1/semantic-dense|26|42|49|61|0.297818384836865|-26|-0.232170631728154|23|
|v1/semantic-dense-integrated|41|65|80|88|0.472808896956476|+1|-0.057180119608542|74|
|v1/query-translation/provider|17|25|28|33|0.181450825477374|-54|-0.348538191087644|19|
|v1/query-translation|45|61|72|80|0.469376181687478|-7|-0.060612834877541|73|
|v1/semantic-grounding/provider|26|42|49|61|0.297818384836865|-26|-0.232170631728154|42|
|v1/semantic-grounding|44|64|74|89|0.468521607764121|+2|-0.061467408800897|75|
|v2|45|72|82|87|0.508796341318465|+0|-0.021192675246553|78|
|v3|46|77|84|87|0.514803084011829|+0|-0.015185932553189|78|
|v4|49|77|82|88|0.530669751759028|+1|+0.000680735194010|80|
|v5|49|77|85|90|0.540643459681653|+3|+0.010654443116634|80|
|v6|49|75|83|92|0.540839330141777|+5|+0.010850313576758|79|
|v7|49|77|85|90|0.540643459681653|+3|+0.010654443116634|80|
|v8|49|78|85|88|0.538243049968714|+1|+0.008254033403695|80|
|v9|49|75|83|92|0.540732787757706|+5|+0.010743771192688|78|
|v10|49|72|81|86|0.523142217069790|-1|-0.006846799495228|80|

## Evidence and limits

ALL_ARMS_VS_PR91.json contains full-precision metrics and all metric/coverage rescue and regression IDs. comparisons/ retains21 complete ranking/per-query/summary comparisons including frame/range/event layers, distinct-video layers, and paired bootstrap evidence. Prior source manifests bind runnable code, tests, configurations and immutable input paths/hashes. ARCHIVE_INTEGRITY.json verifies every manifested file in all11 archives. WORKLOADS.json preserves available arm workload records; full source summaries remain authoritative.

Packet E was negative: R20 87→83, losses p1_q25,p2_q25,p3_q19,p3_q34, no rescues; complete-target coverage78→71. Existing segment mapping was too sparse; the initial padding-mismatch output is retained as invalid and excluded, with corrected segment-v2 used. Historical multimodal reranker caches did not match the current candidates, so no fresh multimodal result was fabricated.

All canonical115 queries retain provenance. Scoring excludes p0_q15/p3_q09, leaving113; inherited41 provisional/proxy qualifications remain. No truth, corpus or index mutations. One permitted semantic embedding job used2956 documents+115 queries; no additional extraction/embedding job or model download. Text reranking used the existing BGE model, CPU float32, batch2, threads8, max1024. v5:10823 pair scores,8524 new/2299 reused,12 new truncated,4970.1720394 same-session seconds. Timing is noisy and not an isolated production speed comparison.

v11 reached104/115 saved query caches. Partial counts and lower-bound timing are in ../astra-overnight-issue92-v11/validation/incomplete_verified.json. Work within the interrupted next query is not measured. The frozen policy prose accidentally says "v5 ASR+ASR"; executable code and input hashes reference the actual combined OCR+ASR v5 control. This prose typo is disclosed without changing the frozen policy.

Focused tests and arm-specific independent verification passed as recorded in each archive. Final common-control rescoring covers21×113 scored rows and21×115 saved rankings. ASR partial verification checks source/policy hashes, exact text transformation, query ordering, finite scores and reuse identities; it is not scientific acceptance of a complete arm.

## Usage, duration and transport

Authorized window2026-09-16T15:50Z–23:50Z, compute cutoff23:40Z. v11 exited23:40:02Z after respecting cutoff; no new inference was launched. Closure performed within the original bound. Completion callbacks resumed the exact originating thread; terminal exit0 was verified separately from task acceptance. Earlier deadline standby was superseded by the user and substantive work resumed. All negative results remain archived.

Latest harness counter delta since the last pre-start event: `{"input_tokens": 16169828, "cached_input_tokens": 14865664, "cache_write_input_tokens": 0, "output_tokens": 129974, "reasoning_output_tokens": 16798, "total_tokens": 16299802}`. These counters include repeated/cached context and are not a dollar bill or exact API request count. Full rate-limit evidence, timestamps, model identifiers and source session are in usage_final.json. No quota-terminal error observed; termination reason is the time bound.

Experiment archive storage: 407665531 bytes, below30GB. No model downloads.

## Hashes and reproduction

Exact parent input SHA256: provider rankings d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82; study ba47bd96eb842d0bb57811e247cbd2ea29de8794c5dd3b289dce24a3032c10b1; run identity f0d32893564111064d47f6f2f72f7b03dbb14ebbfbb3d05c48e49e30ef165755.

Accepted v5 policy SHA2561ebb454de5206d425efec699933a940d4a519277a7c4a487b5f16d9e0058b867; archive manifest SHA256c883670a070453de9ecb912b99576c5552eb7c08f0bd0b033885fa0699c91d6b. Full manifest hashes for all arms: ARCHIVE_INTEGRITY.json.

Use the existing C:/Users/minhc/Code/Vecna/.venv/Scripts/python.exe with -X utf8 -B. Each arm README has preparation, inference and focused-test commands. code/build_comparisons.py reconstructs this common-control comparison from saved rankings. Outputs use exclusive creation; reproduce in a fresh versioned directory, never overwrite this evidence. The external model/dataset paths must still match their SHA256 pins.

Dirty-state caveat: parent PUBLICATION_CHECKPOINT.json metadata changed with unknown ownership and is preserved; v1/provenance contains its snapshot/diff. The expected hydrated raw-provider and study files are untracked but hash-verified. No friend/browser branch was modified. The old v1 return selecting the control predates subsequent research and is superseded by this report.
