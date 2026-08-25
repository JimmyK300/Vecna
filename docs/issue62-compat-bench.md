# Issue #62 compatibility bench (local)

Reproducible local compatibility matrix of model/harness combinations that
already exist on this machine. Benchmark/report only - no production model or
config changed.

- Harness: `aic51-src/script/run_issue62_compat_bench.py`
- Results: `benchmark-results/issue62-compat-bench/`
  (`matrix.md`, `matrix.json`, `measurements.jsonl`, `environment.json`, `RERUN.md`)

Run:

```powershell
& "C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe" aic51-src\script\run_issue62_compat_bench.py --output-dir benchmark-results\issue62-compat-bench
```

The script forces offline mode (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`,
`PYTHONDONTWRITEBYTECODE=1`), downloads nothing, writes only inside
`--output-dir`, and uses the shared Vecna venvs read-only.
