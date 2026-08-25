# RERUN — issue61-decomposition-ab

Deterministic re-run instructions (measurement only; no retrieval/config changes).

## Prerequisites (verified 2026-08-25)

- Worktree: branch `codex/issue-61-query-decomposition` @ `9b8a871e8531aae85de6eb87fea400bef8669d48`.
- Primary checkout (READ-ONLY reference): `C:\Users\minhc\Code\Vecna` — provides runtime code, `config.yaml`, canonical query CSV, fps CSV, and the `.venv`. Nothing is written there (`PYTHONDONTWRITEBYTECODE=1`, all artifacts land in this worktree).
- Milvus standalone at `localhost:19530`, collection `official_l21_l30_all_v2` (322,924 entities), index generation `idx_6baede5b9bc447e099c0004d8428ca7e`. Do not stop/restart containers.
- Python: `C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe`.

## Steps

```powershell
cd C:\Users\minhc\Documents\Codex\2026-08-25\turn-on-actions-runner\worktrees\vecna-issue-61

# 1) Freeze (idempotent; writes policy-freeze.json, NO search calls).
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONIOENCODING = "utf-8"
& "C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe" -B aic51-src\script\run_issue61_decomposition_ab.py --phase freeze

# 2) Experiment (interleaved A/B + pre-declared simple diagnostics + determinism probe).
& "C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe" -B aic51-src\script\run_issue61_decomposition_ab.py --phase run
# add --overwrite to replace existing armA/armB JSONL artifacts.
```

The run phase aborts unless the on-disk policy hash and derivation preview match
`policy-freeze.json` (frozen before scoring). Expected wall time ≈ 7 min after model load.

## Outputs

| file | content |
|---|---|
| `decomposition-policy-v1.json/.md` | frozen policy (+ revision log) |
| `policy-freeze.json` | policy hashes + per-query fragment plan preview |
| `armA-full-query.jsonl` | Arm A records (official baseline path) |
| `armB-decomposed.jsonl` | Arm B records incl. every fragment text, routing, latency, RRF fused top-20 |
| `armB-diagnostic-simple.jsonl` | pre-declared forced-decomposition control diagnostics |
| `summary-armA.json` / `summary-armB.json` | aggregates (global / complexity / task slices) |
| `deltas-issue61.json` | paired per-query deltas, recommendation mapping, taxonomy |
| `failure-taxonomy.json` | issue58-compatible failure classification |
| `ab.launcher.json` / `ab.run.json` | provenance: hashes of all runtime inputs, collection/index identity, git state |

## Determinism expectations

Rankings are stable for identical inputs (probe reproduced q01/q02 fingerprints exactly).
Latency varies with machine load; p1_q06-A is slow (~48 s) because its raw text contains `/`
and routes through the production temporal path. Cross-run absolute ranks may shift slightly if
the primary checkout code changes (it is dirty upstream); the pinned input hashes in
`ab.launcher.json` make any such drift detectable.
