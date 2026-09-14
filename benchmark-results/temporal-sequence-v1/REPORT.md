# Temporal sequence retrieval v1 (Vecna issue #79)

This is an experiment-side comparison over the existing Qwen frame embedding surface. It does not change production retrieval, create ground truth, or re-embed the corpus.

- Control: 113 rows = 78 frozen P0-P2 + 35 provisional P3.
- Exclusions: `p0_q15`, `p3_q09`.
- Query-only decompositions: 113; temporal-eligible: 57; live complete: 8.
- Live comparison subset: p0_q22, p0_q23, p0_q24, p1_q25, p2_q29, p2_q30, p3_q21, p3_q34; the other 49 eligible rows have no live event streams.
- Range-score caveat: 6/8 live rows are TRAKE/video-only and have no reviewed frame-range truth; range recall is not a temporal-truth measure for those rows.
- Search surface: `official_l21_l30_all_v2` / `qwen_vl`, top-100, `nprobe=32`.
- Model surface: `C:\Users\minhc\.cache\huggingface\hub\models--Qwen--Qwen3-VL-Embedding-2B\snapshots\9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda`; device is recorded in `surface_manifest.json`.
- Surface parity: `top1_and_top20_overlap`; top-20 overlap=1.0.

## Reproduction commands

```powershell
py -3.12 aic51-src/script/temporal_sequence_v1.py --stage build --out-dir C:\Users\minhc\Code\Vecna\.worktrees\issue79-temporal\benchmark-results\temporal-sequence-v1
py -3.12 aic51-src/script/temporal_sequence_v1.py --stage search --out-dir C:\Users\minhc\Code\Vecna\.worktrees\issue79-temporal\benchmark-results\temporal-sequence-v1 --query-ids p0_q22,p0_q23,p0_q24,p1_q25,p2_q29,p2_q30,p3_q21,p3_q34 --encode-batch-size 4
py -3.12 aic51-src/script/temporal_sequence_v1.py --stage score --out-dir C:\Users\minhc\Code\Vecna\.worktrees\issue79-temporal\benchmark-results\temporal-sequence-v1
```

## Arm summary

| arm | n | video R@1 | video R@5 | video R@20 | range R@20 |
|---|---:|---:|---:|---:|---:|
| baseline | 113 | 0.504 | 0.619 | 0.735 | 0.611 |
| baseline_live_subset | 8 | 0.000 | 0.250 | 0.750 | 0.000 |
| independent_max@20 | 8 | 0.125 | 0.250 | 0.500 | 0.000 |
| ordered_chain@20 | 8 | 0.000 | 0.000 | 0.000 | 0.000 |

## Interpretation boundary

Independent-max is an unordered union of per-event ranked frames. Ordered-chain emits one result per video only when one hit per event can be selected with strictly increasing frame numbers; its score is the mean event cosine distance. These choices are fixed in code and are not tuned against ground truth.

P3 truth is provisional source-text evidence and historical TRAKE truth remains development evidence. Results are therefore a retrieval diagnostic, not an organizer score. Inspect `scored_variants.jsonl`, `event_rankings.jsonl`, and `mapping_ledger.jsonl` before making a claim.

If surface parity is `diagnostic_mismatch`, the independent-max and ordered-chain numbers are diagnostic only and must not be interpreted as a valid comparison against the saved baseline.
