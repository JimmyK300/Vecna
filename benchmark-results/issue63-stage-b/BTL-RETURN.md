# Issue #63 Stage B — return packet to Browser Task Lead

Returned 2026-08-30. This is the bounded Stage B completion. No merge to `main`. No retrieval follow-up.

## 1. Branch and commit

- Branch: `codex/issue-63-stage-b`
- Commit: `b1856c647d3910a4ab0a934bfc1c4d696e0a47a1`
- Started from reviewed Stage A `f0532c1be14b02b6da73d4b23e2d773591a48f97` plus cherry-picked Issue #58 evaluation artifacts `d712fcf35b22fc3efff1f70ca4cd70eaf836ecc6` (donor `cb5216b6f80826f626d61e01496589179520dfa4`).

## 2. Artifact paths and SHA-256

Directory: `benchmark-results/issue63-stage-b/`

| file | sha256 |
|---|---|
| reconstructed-truth.json | `016e13507071b05df1a5474f125d18755fc8ce0b58ce3a71b6f217c670abc782` |
| expanded-inventory.json | `06a2c1528a29152f664005749f698696d17cd9aaf126bbbfddd1bf7af6782c99` |
| legacy-canonical.csv | `b732a623deba352db037bcb8acb5f99923ba9cd01e761ad3f4417307de42057c` |
| old-results.jsonl | `3867609db752e2337fa80ee3c3fd71afd4e83379e0ee4e34c4e184ed31e22ac7` |
| reconstructed-results.jsonl | `b5fa4725642bd0f2e0edd7ff7a19a0b62ccc9a28c99258b3adb68194ed7fd9fc` |
| expanded-results.jsonl | `409b7fdf63b5d609d75f4705b25081e7474c6e5edad69888d2a01be77699802e` |
| summary.json | `fb07aacc5fa18851bfe8a2528cb5cc57be9cefe30ad0ae7cd1a592fd6d039677` |
| run.json | `76f9840ecad6174725a737eacc124d20545cf023545818be1e371febba09861b` |
| PROTOCOL.md | `9807d422d436e9b12fc87f7066c38ab51981a18a4dd801ea8578b417bccca8b4` |
| README.md | `9c093ab63f610550f370b6ae1c2a0bf53cbe26de5b005e3dcf43e2227464c8ff` |
| RERUN.md | `612566402ee1e1d7f5fe54afc868daf9769ab823a07e2c96f5331c8a67305fef` |
| TESTS.md | `628d4d2bfd16c247cf4470249dbe459fe8105968a101546e2c314b499317922b` |

Schema/provenance: reconstructed records are source-qualified (`submission::p1-*`), carry reviewer decision, reviewed ranges, source CSV hash, and `review_tier=reconstructed_round1_human_reviewed`. Legacy Issue #34/#58 CSV is copied unchanged (`legacy-canonical.csv`). Cross-source bare `p1-*` IDs are not merged.

## 3. Scorer / harness and exact rerun

- `aic51-src/script/issue63_stage_b_scoring.py`
- `aic51-src/script/run_issue63_stage_b.py`
- `aic51-src/tests/test_issue63_stage_b.py`
- Live scoring for the counted run used the Issue #58 donor `headless_benchmark.py` interval matcher for reconstructed records (point/timeline frame inside any accepted interval, endpoints inclusive). The pure scorer also supports explicit segment overlap; this run graded emitted point/timeline frames.

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' aic51-src\script\run_issue63_stage_b.py --execute --overwrite
```

This command re-runs 69 searches. Do not execute it unless a new counted run is authorized.

## 4. Tests

From `C:\Users\minhc\Code\vecna-issue-63`:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' -B -m unittest discover -s aic51-src\tests -p test_issue63_stage_b.py -v
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' -B aic51-src\script\run_issue63_stage_b.py --smoke
```

Result: 7/7 unittest OK (0.097s); deterministic smoke PASS. `pytest` is not installed; the BTL-required cases were run via stdlib `unittest`.

## 5. Counts

- Old/legacy scoreable: **21**
- Added reconstructed scoreable: **48**
- Expanded scoreable total: **69**
- Reconstructed excluded / non-scoreable: **1** (`testing88_submission633::p1-21`, missing `L21_V004.mp4`)
- Legacy excluded: **1** (`p1_q22`)

`testing88_submission633::p1-21` is present in frozen truth with empty ranges and `scoreable=false`. It was not searched and is in no metric denominator.

## 6. Same-runtime metrics (`clip_siglip_qwen_sparse`, rerank OFF)

| set | n | R@1 | R@5 | R@20 | MRR@20 | no-hit@20 |
|---|---:|---:|---:|---:|---:|---:|
| old | 21 | 0.52381 | 0.630952 | 0.797619 | 0.58868 | 3 |
| reconstructed only | 48 | 0.270833 | 0.479167 | 0.6875 | 0.367793 | 15 |
| expanded | 69 | 0.347826 | 0.525362 | 0.721014 | 0.435019 | 18 |

Historical Issue #58 guardrail on 21 scoreable queries: R@1 `0.523810`, R@5 `0.630952`, R@20 `0.797619`, MRR@20 `0.588680`. After preserving legacy TRAKE **fractional** event coverage in aggregation, current old-set drift is **0.0** on all four metrics. Per-query first-correct ranks and recalls for the 21 overlapping IDs match the Issue #58 `p20-clip_siglip_qwen_sparse.jsonl` records. The comparison is interpretable.

A post-run resummary (`run.json:post_run_resummary`) corrected only the aggregate of already-stored per-query recalls; it did not call retrieval again. An earlier binary-recall draft had appeared to improve R@5/R@20; that was an aggregation error, not a ranking change.

## 7. Slices (metadata that exists)

Source:

| source | n | R@1 | R@5 | R@20 | MRR@20 | no-hit |
|---|---:|---:|---:|---:|---:|---:|
| p1.txt (legacy) | 21 | 0.52381 | 0.630952 | 0.797619 | 0.58868 | 3 |
| final_round1_10_4of13 | 25 | 0.28 | 0.48 | 0.72 | 0.377285 | 7 |
| testing88_submission633 | 23 | 0.26087 | 0.478261 | 0.652174 | 0.357475 | 8 |

Task type (reconstructed task labels are the supplied Stage A labels; not inferred):

| task_type | n | R@1 | R@5 | R@20 | MRR@20 | no-hit | small-n |
|---|---:|---:|---:|---:|---:|---:|---|
| kis | 37 | 0.351351 | 0.567568 | 0.72973 | 0.443887 | 10 | no |
| tkis | 16 | 0.625 | 0.6875 | 0.875 | 0.668876 | 2 | no |
| qa | 9 | 0.111111 | 0.444444 | 0.666667 | 0.243177 | 3 | yes |
| trake | 7 | 0.0 | 0.035714 | 0.392857 | 0.100275 | 3 | yes |

Truth tier: legacy_existing_contract n=21 as old row; reconstructed_round1_human_reviewed n=48 as reconstructed-only row.

## 8. Machine-readable per-query results

- `old-results.jsonl` (21), `reconstructed-results.jsonl` (48), `expanded-results.jsonl` (69)
- Each row includes `query_id`, `query_text`, `first_correct_rank`, `recall_at_{1,5,10,20}`, `reciprocal_rank`, `no_hit_within_20`, `latency_ms`, `top_results`.

## 9. Failures / no-hit changes / interpretation

- Failed searches: **0**. Retries: **0**. Search calls: **69/69**.
- Old no-hit IDs unchanged vs Issue #58: `p1_q16`, `p1_q20`, `p1_q21`.
- Reconstructed no-hit IDs (15): `final_round1_10_4of13::{p1-1,p1-2,p1-3,p1-18,p1-19,p1-23,p1-24}`; `testing88_submission633::{p1-4,p1-9,p1-15,p1-16,p1-17,p1-22,p1-24,p1-25}`.
- Material interpretation: expanded metrics are lower because reconstructed Round-1 human-reviewed interval truth is harder than the old 21-query provisional set, not because retrieval was changed. Semantic-interval scoring is used only for reconstructed records; legacy TRAKE fractional coverage is preserved. Same bare `p1-*` IDs from the two sources remain independent (example: `final_round1_10_4of13::p1-4` rank 1 vs `testing88_submission633::p1-4` no-hit).

## 10. Runtime / config / collection / index identity

- Live runtime root: `C:\Users\minhc\Code\Vecna`
- Serving git: `fd879fb0529165a441745374ab72244df8aadd5e` on `masterplan/ox-alpha-20260824` (dirty worktree; status hash `347d698d7443336f4113dfc037a834312aac747a50fc43a6de0d205bb989fd19`)
- Cell: `clip_siglip_qwen_sparse`; rerank OFF; OCR/ASR 0.25/0.25; nprobe 32; temporal_k 2000; query expansion/translation OFF
- Collection: `official_l21_l30_all_v2`, 322924 rows
- Index generation: `idx_6baede5b9bc447e099c0004d8428ca7e` (same as Issue #58)
- Encoders: CLIP / SigLIP / Qwen-VL on **cpu**
- Python 3.12.1 / CPython / Windows-11-10.0.26200-SP0; aic51 2.0.1; torch 2.8.0; pymilvus 3.0.0
- Critical hashes before **and after** (unchanged):
  - config `d8a5fbc1ec0eff59e6beb134656c9449c9bb0eab264f8639653cc31f893adba8`
  - headless_benchmark `39d4196b16f191dc7eda9749b28ce76d8acd776eeed2b34892e312c01b1d6233`
  - p20_runner `fb758833989dd17393a07a1e187dd5344bb86cdd77f197c234d01b63e5b15f12`
  - searcher `db19d47647ddf1e014992d08dad322cd4bafb583b1dd824f0b5807c34690c0a7`
- `production_files_unchanged`: true
- Canonical query CSV content hash: `1aba0cf592976a7ec3e2417ff7e9c46628ad2269dc786125fa07c26e0a34470e` (matches Issue #58)

## 11. No-tuning confirmation

No retrieval, model, fusion, index, query-expansion, translation, or production configuration behavior was tuned or changed after seeing results. Stage B wrote only harness/scorer/tests and `benchmark-results/issue63-stage-b/**`. The live Vecna runtime was used read-only for the 69 searches.

## 12. Blockers / remaining uncertainty

- `testing88_submission633::p1-21` remains non-scoreable (`L21_V004.mp4` absent).
- `testing88_submission633` numeric submission ID `633` is still a description-based label, not independently verified.
- `testing88_submission633::p1-4` retains `official_text_unmappable`; query label was not upgraded.
- The frozen preliminary-question parser retained the next task-section label as a final line of `final_round1_10_4of13::p1-17` (`...TRAKE`) and `::p1-25` (`...Q&A`). Exact used `query_text` is in `reconstructed-results.jsonl`. Exactly-once protocol forbade a retry.
- Reconstructed truth is human-reviewed semantic interval evidence, not organizer truth. Frame IDs are FPS projections.
- This run grades point/timeline frames; explicit returned-segment overlap is implemented in the pure scorer but was not emitted by the runtime.
- Latency is machine-load dependent and is not a quality claim.
- Serving stack is dirty relative to `fd879fb`; quality still reproduced the Issue #58 old-set guardrail, so the expansion delta is interpretable.
