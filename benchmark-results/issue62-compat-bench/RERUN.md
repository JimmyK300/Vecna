# Rerun issue #62 compatibility bench

One command (PowerShell), full matrix:

```powershell
& "C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe" "C:\Users\minhc\Documents\Codex\2026-08-25\turn-on-actions-runner\worktrees\vecna-issue-62\aic51-src\script\run_issue62_compat_bench.py" --output-dir "benchmark-results\issue62-compat-bench"
```

Partial rerun of specific cells (`--only` takes comma-separated cell-id
substrings; existing records are merged, never discarded):

```powershell
& "C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe" "C:\Users\minhc\Documents\Codex\2026-08-25\turn-on-actions-runner\worktrees\vecna-issue-62\aic51-src\script\run_issue62_compat_bench.py" --output-dir "benchmark-results\issue62-compat-bench" --only "pytorch-directml::image_siglip"
```

Defaults: 12 keyframe workload frames (+4-frame cap for Qwen embed),
batch levels [1, 4, 16, 32, 64], 3 text repetitions.
Offline env vars (`HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`,
`PYTHONDONTWRITEBYTECODE`) are forced by the script; nothing is downloaded
and the shared venvs are used read-only.

Outputs land in `--output-dir` only: `matrix.json`, `matrix.md`,
`measurements.jsonl`, `environment.json`, this file.

Determinism notes:
- identical frame subset (sorted jpg names) and identical fixed query list;
- seeds do not participate (pure inference);
- wall-clock timings vary with machine load; treat throughputs within ~10%
  as ties; error signatures are deterministic for missing deps/unsupported dtypes.
