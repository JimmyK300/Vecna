# Current-main text ranking tie proof

The completed 38-row BM25 responses were replayed through the same pinned main text method in three local processes with predeclared PYTHONHASHSEED=0,1,82. Replays read no truth, ran no models and made no network/retrieval calls. Scoring joined unchanged canonical truth after these outputs were frozen.

All 38 query/channel rows have different effective orders across the host and these seeds. Every replay preserves the identical candidate membership and complete BM25 score sequence. Main builds a frame-ID set, iterates it into results, and sorts by final score alone; equal-score groups therefore retain process-dependent set order.

| Channel | Order | Frozen range/event R@1 | R@5 | R@20 | MRR@20 |
|---|---|---:|---:|---:|---:|
| OCR | host | 1 | 3 | 3 | 0.087500 |
| OCR | 0 | 1 | 3 | 3 | 0.087500 |
| OCR | 1 | 1 | 3 | 3 | 0.087500 |
| OCR | 82 | 1 | 3 | 3 | 0.087500 |
| ASR | host | 4 | 6 | 9 | 0.281250 |
| ASR | 0 | 4 | 7 | 9 | 0.285185 |
| ASR | 1 | 7 | 7 | 9 | 0.396635 |
| ASR | 82 | 5 | 6 | 9 | 0.311482 |

The numbers describe this fixed diagnostic sample and its frozen truth, including provisional P3 rows. They do not select a preferred seed or claim a retrieval improvement. A stable tie policy would improve repeatability; its choice and resulting ranking change require explicit review. No production ranking code was changed here.
