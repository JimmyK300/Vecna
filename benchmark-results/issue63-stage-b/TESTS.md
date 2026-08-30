# Stage B deterministic verification

Executed from `C:\Users\minhc\Code\vecna-issue-63` with bytecode writes disabled:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' -B -m unittest discover -s aic51-src\tests -p test_issue63_stage_b.py -v
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' -B aic51-src\script\run_issue63_stage_b.py --smoke
```

Result: 7 tests passed in 0.107 seconds; deterministic smoke passed.

The tests cover the 48 accepted plus one ambiguous reconstructed inventory, unique source-qualified IDs, exclusion of `testing88_submission633::p1-21`, inclusive endpoints, alternative intervals, outside/wrong-video misses, explicit segment overlap, preservation of legacy point/interval matching and fractional TRAKE aggregation, and the fixed no-tuning baseline contract.
