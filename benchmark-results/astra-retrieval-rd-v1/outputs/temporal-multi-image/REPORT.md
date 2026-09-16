# Packet A — native multi-image Qwen audit

**INCONCLUSIVE for retrieval quality.** One native3 candidate completed; the eight-query matched experiment did not.

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

With only three candidates, R@5 and R@20 are invariant to reranking. Use paired pool R@1/rank and scoreable range/event evidence. Event hits remain submission-derived development proxies. No retrieval-quality metrics are emitted for this incomplete run.

## Next executable step

The matched plan pins the current eight-query top-three pool and keeps the same model revision. Run a parent-supervised, one-candidate CPU float32 timing smoke using matched 384×216 frames with a 120-second cap. It is timing-only and cannot update the old embedding cache. If feasible, run every primary arm with the same dtype/processor in a new cache and enforce complete paired coverage. If infeasible, keep Packet A inconclusive and defer further temporal inference on this host.

No production retrieval code, existing cache, model family, or corpus index is changed.
