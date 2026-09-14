# Provenance: temporal sequence retrieval v1

## Identity and scope

- Experiment: `temporal-sequence-retrieval-v1`
- Vecna issue: `#79`
- Hypothesis: event decomposition plus ordered sequence search may recover
  temporal signal using existing embeddings.
- No-go constraints: no new video model, no full-corpus re-embedding, and no
  production retrieval rewrite.
- Continuation: reproduce the 113-query temporal control, build auditable
  query-only event decompositions, and compare independent-max with
  ordered-chain retrieval.
- Result boundary: diagnostic evidence, not an organizer score or a claim of
  temporal ground-truth recovery.

## Source and publication provenance

- Source repository: `https://github.com/JimmyK300/Vecna.git`
- Source branch: `codex/issue-79-temporal`
- Source base commit before this archive: `e0981b9`
- Source file: `aic51-src/script/temporal_sequence_v1.py`
- Archived runner: `runner/temporal_sequence_v1.py`
- Source SHA-256: `9441fc93c792ca0c548061967676eb329e2f71bafb63fa1ce7a064414047eef`
- The Vecna primary checkout had unrelated dirty work; this experiment was
  executed and published from the isolated `issue79-temporal` worktree.
- The Official-Dataset publication copy is intended to live under
  `experiments/temporal-sequence-retrieval-v1/` with its own Git history.

## Control construction

- Control size: 113 unique query IDs.
- Composition: 78 historical P0-P2 rows and 35 provisional P3 rows.
- Excluded rows: `p0_q15`, `p3_q09`.
- Query-only decompositions: 113 rows, 354 total events.
- Temporal-eligible rows: 57.
- Live-complete rows: 8; their exact IDs are:
  `p0_q22,p0_q23,p0_q24,p1_q25,p2_q29,p2_q30,p3_q21,p3_q34`.
- The remaining 49 eligible rows have no independent live event streams and
  are retained as explicit non-live evidence rather than silently omitted.
- Ground truth was not used to create decompositions or search queries. It was
  used only by the scoring stage to measure the saved outputs.

## Inputs and immutable hashes

The control was assembled from the following exact files. These paths are
machine-local, so the SHA-256 values are the portable identity.

| input | SHA-256 |
|---|---|
| `C:\Users\minhc\Code\Official-Dataset\evaluation\headless-current-p0-p1-p2-p3-qwen-only-top100-v0\ground_truth_current_115.jsonl` | `79393a95aae8e51b6b475e1b35f3b5ccfef278ee05a3f444eaedc0b0f4f90819` |
| `C:\Users\minhc\Code\Official-Dataset\evaluation\headless-current-p0-p1-p2-p3-qwen-only-top100-v0\qwen_only_top100.jsonl` | `85d5dd169bcd6934ebfa8435b6aee82ce9bc149bac3a704afbdbcb4b986568f0` |
| `C:\Users\minhc\Code\Official-Dataset\evaluation\queries\p3-round3-benchmark-v1\baselines-20260913\qwen_only_v1.jsonl` | `bd7ae6589996bc35d880df8160dabf40626c55c2b6796f86d7a6ccaedfd1e338` |
| `C:\Users\minhc\Code\Vecna\.worktrees\shot-clustering\benchmark-results\headless-vnext-p0-p1-p2-v1\manifest.json` | `09df9bdbd9782492dcf81e8da3fad5e07a1ae25b2bc7aeca9cd2cda4045be9bd` |
| `C:\Users\minhc\Code\Vecna\.worktrees\shot-clustering\benchmark-results\headless-vnext-p0-p1-p2-v1\scored-combined\scored.jsonl` | `314c451c6bfb750d9e2cbf8657d312ec7792a3a22ba1a8904e6c48fa001d1bb6` |

The same input map is preserved in `control_manifest.json`.

## Retrieval surface and runtime

- Collection: `official_l21_l30_all_v2`
- Vector field: `qwen_vl`
- Search metric: the existing collection metric, queried with top-100 and
  `nprobe=32`.
- Milvus endpoint: `http://127.0.0.1:19530`.
- Model snapshot:
  `C:\Users\minhc\.cache\huggingface\hub\models--Qwen--Qwen3-VL-Embedding-2B\snapshots\9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda`
- Model configuration SHA-256:
  `9172f55b0b9cce70b7f67b10c58a408ccf3ec15c587e6efd4d5f41631237fded`.
- Device: CPU.
- Runtime recorded in `surface_manifest.json`: torch `2.4.1+cpu`,
  transformers `4.57.1`, pymilvus `3.0.1`.
- Surface parity control: query `p3_q01` matched the saved baseline at top-1
  and had 20/20 top-20 overlap (`1.0`).
- The archive records `reembedding=false` and
  `production_retrieval_rewrite=false`.

## Encoding and search contract

The experiment uses the existing production query contract exactly:

`Retrieve images or text relevant to the user's query.`

The runner uses the Qwen chat template with system and user messages,
`add_generation_prompt=True`, the final non-padding token, L2-normalized
embeddings, and CPU bfloat16 inference. Event queries are encoded in batches;
the search is direct against the existing Milvus collection. No corpus vectors
are regenerated.

## Compared arms

- `baseline`: the saved 113-query video retrieval baseline.
- `baseline_live_subset`: the same saved baseline restricted to the eight live
  queries, so arm comparisons share an identical evaluated subset.
- `independent_max@20`: retrieve each event independently, union and dedupe
  frame hits, and rank each video by its maximum event-hit score.
- `ordered_chain@20`: require one selected hit for every event with strictly
  increasing frame numbers; rank a video by the mean selected event score.

The two temporal scoring rules are fixed in code and were not tuned against
ground truth.

## Observed metrics

| arm | n | video R@1 | video R@5 | video R@20 | range R@20 |
|---|---:|---:|---:|---:|---:|
| baseline | 113 | 0.504 | 0.619 | 0.735 | 0.611 |
| baseline_live_subset | 8 | 0.000 | 0.250 | 0.750 | 0.000 |
| independent_max@20 | 8 | 0.125 | 0.250 | 0.500 | 0.000 |
| ordered_chain@20 | 8 | 0.000 | 0.000 | 0.000 | 0.000 |

Six of the eight live rows are TRAKE/video-only and have no reviewed
frame-range truth. Their range metrics are therefore not temporal-truth
measurements. P3 truth is provisional source-text evidence, and historical
TRAKE truth remains development evidence.

## Validation and reproduction

Validation completed before publication:

- Python compilation of the runner passed.
- Control cardinalities, unique IDs, decomposition count, and event count
  were checked.
- Event-ranking keys are unique and use the exact production instruction.
- Surface parity passed at top-1 and top-20.
- `git diff --check` passed before publication.

From the Vecna repository, the saved run can be reproduced with:

```powershell
py -3.12 aic51-src/script/temporal_sequence_v1.py --stage build --out-dir C:\Users\minhc\Code\Vecna\.worktrees\issue79-temporal\benchmark-results\temporal-sequence-v1
py -3.12 aic51-src/script/temporal_sequence_v1.py --stage search --out-dir C:\Users\minhc\Code\Vecna\.worktrees\issue79-temporal\benchmark-results\temporal-sequence-v1 --query-ids p0_q22,p0_q23,p0_q24,p1_q25,p2_q29,p2_q30,p3_q21,p3_q34 --encode-batch-size 4
py -3.12 aic51-src/script/temporal_sequence_v1.py --stage score --out-dir C:\Users\minhc\Code\Vecna\.worktrees\issue79-temporal\benchmark-results\temporal-sequence-v1
```

The saved artifacts, manifests, and per-query rows—not just the aggregate
table—are the audit record. `SHA256SUMS.txt` binds the archived non-document
files to the published packet.
