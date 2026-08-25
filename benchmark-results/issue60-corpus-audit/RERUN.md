# Rerun instructions

The checker is strictly read-only against the corpus root: it opens files only for reading
and writes exclusively into `--output-dir`. Point `--output-dir` anywhere outside the
corpus to keep the corpus untouched.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe aic51-src\script\audit_corpus_issue60.py --corpus-root "C:\Users\minhc\Code\Vecna" --media-root "D:\Official-Dataset\videos" --collection official_l21_l30_all_v2 --output-dir "C:\Users\minhc\Documents\Codex\2026-08-25\turn-on-actions-runner\worktrees\vecna-issue-60\benchmark-results\issue60-corpus-audit" --deep-sample-videos 32 --content-sample-videos 4
```

Add `--full-headers` for an exhaustive truncation scan of every `.npy` (~1h on this corpus;
the sampled default covers structure for all videos plus headers for a deterministic subset).

Determinism: compare `report_content_sha256` between runs; it excludes wall-clock time.
