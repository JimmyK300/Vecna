# Gemini shot-caption oracle sufficiency v0 — blocked run

Tracker: `JimmyK300/Vecna#95`

## Result

`BLOCKED`: the fixed caption run cannot finish with the currently available Gemini account quota. The declared `gemini-3.8-flash` model and key are valid—five frozen captions completed—but subsequent calls repeatedly returned HTTP 429 for `generativelanguage.googleapis.com/generate_content_free_tier_requests`, limit 20. Six bounded retries over 442.7 seconds did not clear the quota.

No substitute model was used. The prompt comparison, atom-level scoring, prompt freeze, and window-robustness stage were not run because the full caption set is not frozen.

## Completed proof

- Harness syntax and CLI checks passed under Python 3.12 and `google-genai==2.24.0`.
- Fixed pilot manifest: 30 rows, 28 eligible.
- Ineligible rows: `p3_q12` and `p3_q29`, both `no_legitimate_interval_with_seconds`; no timestamps were invented.
- Clip extraction: 28 clips, 28 unique clip SHA-256 values, 27 unique source videos with source SHA-256 values, 380,423,946 total clip bytes.
- All 28 ffprobe durations matched the requested interval within 0.25 seconds.
- Caption cache: 5 successful model/prompt/clip records and 2 preserved error records (the initial 429 plus the bounded-retry record).
- Successful frozen captions: all three prompt families for `p0_q01`; `dense-natural` and `structured-evidence` for `p0_q03`.
- The exact post-caption decomposition authority was fetched from `JimmyK300/official-dataset-control@1f1ad1baef1e1d31817f6c5a12d4d94133611038`; Git blob `caf0a7b30a275b9ed47cab354fbb21bda00bf899` is retained as `evaluation_inputs/decompositions_113.jsonl`.

## Reproducibility corrections

The supplied harness was corrected before or during execution to:

- retain source-video SHA-256 values with per-source hash caching;
- include `resolution=high` in both the Gemini request and cache identity;
- preserve failed attempts rather than treating an error file as a completed cache entry;
- apply bounded exponential retries to transient 429/5xx/timeouts while recording every attempt;
- carry task type and decomposition SHA-256 into post-caption evaluation packets.

The post-freeze judge and deterministic metric aggregator are implemented but intentionally unexecuted until all 84 caption cache entries succeed.

## Exact blocker and resume

The complete API error and all six retry errors are preserved in the two `p0_q03__structured-temporal__0f37191fd0b2feb3*.json` records under `captions/`. The error identifies the free-tier request metric, limit 20, model `gemini-3.8-flash`, and HTTP 429.

After quota is raised or reset, resume without `--force`:

```powershell
.\.venv-issue95\Scripts\python.exe benchmark-results/shot-caption-oracle-v0/code/shot_caption_oracle.py caption --prompt all --model gemini-3.8-flash --fps 4 --resolution high --stop-on-error
```

Successful cache keys will be skipped. Once 84 successful caption records exist, run `build-eval-packets`, then `evaluate_caption_sufficiency.py judge`, perform the predeclared nine-packet manual audit, and run `aggregate`.

## Scope check

- Child branch only; no merge to `main`.
- No full-corpus pass, production retrieval change, TransNetV2 work, prompt/window sweep, per-query tuning, answer-aware regeneration, or alternate Gemini model.
- Caption generation never loaded or sent query text, answers, capability tags, or decomposition atoms.
- Clips remain local and are ignored by Git; their provenance and hashes are archived in `clips/clips.jsonl`.

## Uncertainty

The observed error proves current quota exhaustion, but not whether the account needs billing/quota configuration or a later reset. Repeated waits longer than the advertised retry intervals did not restore access.

Next state: `BLOCKED`.
