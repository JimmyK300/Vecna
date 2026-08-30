# Issue #63 Stage B result packet

Stage B completed with `clip_siglip_qwen_sparse`, reranking OFF. No production retrieval, model, fusion, index, query-expansion, or translation behavior was changed.

## Counts

- Legacy scoreable: 21
- Reconstructed scoreable added: 48
- Expanded scoreable total: 69
- Reconstructed excluded: 1 (`testing88_submission633::p1-21`)
- Legacy excluded: 1

## Same-runtime metrics

| set | R@1 | R@5 | R@20 | MRR@20 | no hit |
|---|---:|---:|---:|---:|---:|
| old | 0.52381 | 0.630952 | 0.797619 | 0.58868 | 3 |
| reconstructed only | 0.270833 | 0.479167 | 0.6875 | 0.367793 | 15 |
| expanded | 0.347826 | 0.525362 | 0.721014 | 0.435019 | 18 |

The old metrics reproduce Issue #58 exactly. See `summary.json` for slices/no-hit IDs, `run.json` for runtime/index/config identity, and JSONL files for top-20 results and first-correct ranks.

## Limitations

- Reconstructed truth is human-reviewed semantic interval evidence, not organizer truth.
- `testing88_submission633::p1-4` retains `official_text_unmappable`; its available query label is not silently upgraded.
- The exactly-once run retained a task-section label at the end of the supplied text for `final_round1_10_4of13::p1-17` and `::p1-25`. The exact used text is preserved; no retry was made.
- Frame coordinates are FPS projections; exact decoded-frame validation requires FFmpeg `select=eq(n\,FRAME)`.
- Runtime results expose point/timeline frames. Explicit segment-overlap support exists in the pure scorer, but this run grades emitted point/timeline frames.
- Latency is machine-load dependent.
