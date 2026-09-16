# Packet A — native multi-image Qwen audit

**POSITIVE_TEMPORAL_SIGNAL — exploratory correct-video ranking only.** Native3 promoted the accepted video to rank 1 in 2/8 queries, versus 0/8 for both matched controls. Event localization and causal use of chronological order remain unestablished. The original cached Stage2b run remains incomplete and is documented separately below.

## New matched result

All eight queries have the same three candidate identities in every arm; all eight query vectors and 72 image vectors were newly encoded with the same float32 model/runtime. The truth file was read only after complete coverage passed. Candidate construction ignored truth/status/metric fields in the current export.

| Arm | Pool video R@1 | Pool video MRR | Center event-proxy R@1 | Equal sampled-window event-proxy R@1 |
|---|---:|---:|---:|---:|
| contact_sheet | 0.000 | 0.104 | 0.000 | 0.000 |
| native3 | 0.250 | 0.250 | 0.000 | 0.000 |
| single_center | 0.000 | 0.125 | 0.000 | 0.000 |

`p0_q23` improved from original baseline/center/sheet rank 2 to native3 rank 1. `p3_q34` improved from original baseline/center rank 2 and sheet rank 3 to native3 rank 1. There were two clean top-1 promotions and no observed accepted-video rank regression. Six other queries lack their accepted video in top3, so those rows cannot establish robustness to ranking regressions.

Native3 reaches the fixed pool's video ceiling: 2/8. Pool video R@3/R@5/R@10 are 2/8 for every arm and are coverage checks, not improvements. None of the 31 provisional event targets occur among the center frames or the three exact sampled frames. Localization is therefore uninformative in this pool; the zero score is not evidence that native3 cannot localize events. Both native3 video successes still miss the requested event frames.

The A5 gate in `reference/issue82.md` explicitly accepts meaningful ranking gains without broad regressions. These two clean promotions support the positive label for this bounded video-ranking comparison. The sample has only two informative accepted-video cases; there is no shuffled/reversed-image control, so chronological-order causality and generalization remain untested.

Global N=3 was fixed before scoring, using the existing 72 decoded frames after the earlier 90.6-minute native pilot made a larger run impractical. The new float32/resolution smoke made this bounded run feasible. Top-10 feasibility was not measured under the optimized runtime; N was not enlarged after observing outcomes. Native5 and a new video model were not started.

| Arm | Measured forward/pooling total, 24 candidates | Mean per candidate |
|---|---:|---:|
| contact_sheet | 72.001s | 3.000s |
| native3 | 72.936s | 3.039s |
| single_center | 29.114s | 1.213s |

The measured model-load/encoding interval was 193.635s, including 10.698s for all eight query vectors and 174.051s for 72 image forward/pooling operations. Pre-run source/weight hashing and parent-broker overhead are outside that interval. Full-run timing may include concurrent Packet B load and fixed arm-order effects; the similar native/sheet means are observations, not an isolated speed comparison.

Model weights were hashed and loaded with no missing/unexpected keys: `Qwen/Qwen3-VL-Embedding-2B`, revision `9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda`, weight SHA256 `c73fa9caeddeb3ff831d46c085a7a5708343248ca777e90f2d486964464509c1`. Config and processor hashes, actual CPU/float32 parameters, environment, and execution code hash are in `matched-v1/run_manifest.json`. The subsequent scoring-only Windows-path portability fix is distinguished from the executed encoder in `matched-v1/recovery_integrity.json`.

Every candidate's original/final ranks, query hash, exact frame identities, model-output reference, score and input/model hashes are joined in `matched-v1/candidate_results.jsonl`; event exposure is in `matched-v1/query_exposure.json`. Raw vectors exactly match the Windows manifest hashes, with no newline restoration needed. Source timestamps are recorded only when independently recovered; no FPS is guessed.

**Next decision:** retain native3 as a viable representation candidate and propose a separately frozen, query-blind candidate-pool experiment in Packet E. Further reranking of these same sampled frames cannot repair absent event targets. Do not expand this completed sample or promote a production model from this result.

Timestamp provenance: **72/72 sampled frames** have exact selected-frame presentation timestamps from the original video streams. They are attached to every candidate/arm record. Any nominal frame/FPS value is separately labeled and is not used as exactPTS. These timestamps do not change the frozen frame-based scorer or its P3 tolerance.

Native input support on the cached pilot: `True`. Current processor proof: `PASS`.

The historical cache has 10 contact-sheet embeddings and 1 native3 embedding. The prepared manifest has 48 candidate/window rows: eight queries × three baseline candidates × two window specifications. Each primary arm requires 24 embeddings. `status=complete` applies to the one-candidate retry; `completed_count=11` counts the whole cache. The retry launcher still says `in_progress` and is stale.

The completed native3 request took 5433.101 seconds (90.6 minutes) on the reported CPU path. The exact implementation hardcodes BF16 and does not move the model to an accelerator. CPU BF16 and the larger native input are plausible cost drivers; their individual causal effects have not been timed.

The original native path passes full decoded images. Contact sheets first resize every tile to 384×216. Original native-versus-sheet results therefore conflate input format with resolution/token budget. The processor probe checks original native, native with matching resized pixels, the original sheet, and the matched center image without loading weights.

## Cached completion

| Query | Sheet / 3 | Native3 / 3 | Native5 / 3 | Paired complete |
|---|---:|---:|---:|---|
| p0_q22 | 3 | 0 | 0 | False |
| p0_q23 | 3 | 0 | 0 | False |
| p0_q24 | 1 | 0 | 0 | False |
| p1_q25 | 0 | 0 | 0 | False |
| p2_q29 | 0 | 0 | 0 | False |
| p2_q30 | 0 | 0 | 0 | False |
| p3_q21 | 0 | 0 | 0 | False |
| p3_q34 | 3 | 1 | 0 | False |

A **linear estimate**, based on only 1 observed native3 candidate, is 36.2 hours for 24 native3 encodings (34.7 hours remaining). This is not a measured sweep and excludes new single-center/sheet/query work and extraction overhead.

The new supervised CPU float32 / six-thread smoke on the same snapshot and matched 384×216 frames completed: model load **4.671s**, forward/pooling **6.954s**, complete child process **19.672s**. It produced a finite, normalized 2048-dimensional vector. Dtype and input resolution changed jointly; neither change alone has a measured causal speedup. This timing supports running the complete matched development probe in a new cache.

Processor inspection verified three distinct image patch groups in the supplied temporal order, with three image grids and all image tokens retained. Each batched patch chunk exactly equals processing that corresponding image alone. The contact sheet equals the three resized frames pasted left-to-right.

| Input | Image grids | Image tokens | Sequence tokens |
|---|---:|---:|---:|
| contact_sheet_original | 1 | 252 | 274 |
| native3_matched_384x216 | 3 | 252 | 278 |
| native3_original | 3 | 2640 | 2666 |
| single_center_matched_384x216 | 1 | 84 | 106 |

This processor reconstruction uses torch `2.8.0+cpu` and transformers `4.57.6` on `AVX2`. Stage2a reported torch 2.4.1+cpu / transformers 4.57.1; Stage2b did not record versions. The current inspection proves delivery of ordered images, not learned temporal reasoning or exact reproduction of an unrecorded historical environment. Model identity is pinned by snapshot path and config hash; the processor-only probe does not hash or load weight bytes.

## Surface and metric limits

All eight selected queries retain the same top-three candidate sets between the historical control and the current Qwen export. For `p3_q34`, ranks 2 and 3 swap. Reuse decoded frames by source video/frame identity; rank-coded candidate IDs and scores are not current-surface evidence.

The legacy scorer permits different available-query denominators for each mode and scores incomplete candidate pools. It also leaves baseline `video_rank_in_pool` at zero. Its output must not be used for a paired conclusion. This audit requires all three candidates per compared mode before a query can count as paired.

With only three candidates, video R@5 and R@20 are invariant to reranking. Use paired pool R@1/rank and scoreable range/event evidence. Event hits remain submission-derived development proxies. No retrieval-quality metrics are emitted for the incomplete historical cache.

## Reproduction

The runnable `code/temporal_matched.py` defaults to planning with no inference. Its explicit encode stage pins the current eight-query top-three pool, hashes actual weights and all input frames, uses CPU float32/six threads for all 8 query vectors and 72 image vectors, and writes a new cache only. Its separate score stage refuses incomplete or stale caches before opening truth and uses the pinned frozen scorer. The supervised timing smoke passed, and the complete matched execution finished successfully with all 8 query vectors and 72 image vectors. Reproduction commands remain in `RUNBOOK.md`.

Full matched-run latency is observed with possible concurrent Packet B load on the host; it is not an isolated microbenchmark. The earlier one-candidate smoke is a separate run. See `runtime_context.json`.

No production retrieval code, existing cache, model family, or corpus index is changed.
