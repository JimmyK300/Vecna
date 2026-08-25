# Issue #58 baseline sweep -- deterministic rerun

## One-command rerun

From this worktree root (`codex/issue-58-baseline-sweep`), using the live-stack virtualenv from the primary checkout (read-only reference environment):

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'   # never write bytecode into the primary checkout
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' aic51-src\script\run_issue58_baseline_sweep.py --overwrite
& 'C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe' aic51-src\script\classify_issue58_failures.py
```

`run_issue58_baseline_sweep.py` delegates to the official headless path `aic51-src/script/run_p20_p21_measurement.py --mode quality --cell clip_siglip_qwen_sparse` (docs/baseline-v1.md runner) executed inside the primary workspace; all artifacts land in `benchmark-results/issue58-baseline-sweep/` of THIS worktree. Milvus standalone (docker, `localhost:19530`) and the canonical query CSV are the only external inputs.

## Recorded identity at last run

- Sweep started/ended: `2026-08-25T15:00:12.782549+00:00` / `2026-08-25T15:04:07.719510+00:00`
- Serving stack git SHA: `fd879fb0529165a441745374ab72244df8aadd5e` (dirty=True; live primary workspace)
- Serving stack status hash: `98e56cc5674327660c6d186daad75583d976cbee803baf753de3e2cfd0477afa`
- Worktree (this benchmark): `9b8a871e8531aae85de6eb87fea400bef8669d48` on branch `codex/issue-58-baseline-sweep` (harness only; no retrieval code changed)
- Collection: `official_l21_l30_all_v2` rows=322924
- Indexes: `image_clip_pe_l_14_336_SCANN, image_siglip_so400m_384_SCANN, qwen_vl_SCANN, ocr_BM25, asr_BM25, ocr_dense_SCANN, asr_dense_SCANN`
- Index generation: `idx_6baede5b9bc447e099c0004d8428ca7e` (state=resolved)
- Workspace config sha256: `d8a5fbc1ec0eff59e6beb134656c9449c9bb0eab264f8639653cc31f893adba8`
- Query CSV sha256: `b732a623deba352db037bcb8acb5f99923ba9cd01e761ad3f4417307de42057c`
- Canonical issue34 content sha256: `1aba0cf592976a7ec3e2417ff7e9c46628ad2269dc786125fa07c26e0a34470e` (matches pinned `1aba0cf592976a7ec3e2417ff7e9c46628ad2269dc786125fa07c26e0a34470e`)
- Params: rerank OFF; nprobe=32, temporal_k=2000, ocr_weight=0.25, asr_weight=0.25; target_features=image_clip_pe-l-14-336,image_siglip_so400m-384,qwen_vl
- Query-encoder devices: {'image_clip_pe-l-14-336': 'cpu', 'image_siglip_so400m-384': 'cpu', 'qwen_vl': 'cpu'}
- Runtime: python 3.12.1 / torch 2.8.0
- Critical code hashes: headless_benchmark=39d4196b16f191dc7eda9749b28ce76d8acd776eeed2b34892e312c01b1d6233; searcher=db19d47647ddf1e014992d08dad322cd4bafb583b1dd824f0b5807c34690c0a7

## Result hashes

- Per-query JSONL `results_sha256`: `bd4d33b37da50467fea610223744c7979c2d56cff0a08b57e29a65b62f4b3061`
- Summary sha256: `9d65b9d80849f56e50901462e466e891be0478ecd2160d41aacb79f92e836d84`

Quality metrics reproduce the baseline-v1 guardrail bit-for-bit (R@1 0.523810, R@5 0.630952, R@10 0.738095, R@20 0.797619, MRR@20 0.588680, no-hit 3/21); latency is machine-load dependent and is expected to differ between runs.
