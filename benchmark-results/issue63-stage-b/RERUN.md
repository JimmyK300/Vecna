# Exact rerun

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' aic51-src\script\run_issue63_stage_b.py --execute --overwrite
```

This overwrites only Stage B result artifacts and performs 69 searches with one Searcher initialization and no retries.
