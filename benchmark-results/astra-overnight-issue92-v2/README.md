# Issue 92 continued research: semantic text cross-encoder

The user rejected the premature deadline standby. Active research resumed on
2026-09-16 at 17:22 UTC. The original deadline remains 23:50 UTC; this is not a
new eight-hour allocation. The v1 report's standby plan is superseded. All v1
scientific artifacts and negative results remain preserved.

## Frozen hypothesis

For each of the exact PR91 control's first 20 distinct videos with semantic
coverage, select its single highest cached BGE-M3 cosine record. Score that
record against the unchanged canonical query with the locally cached
BAAI/bge-reranker-v2-m3 text cross-encoder. Fuse the covered video orders with
equal reciprocal rank fusion, constant 60. Only covered top-20 slots may move;
uncovered videos and the tail retain their positions. Retain all original
candidate frames (up to 100), group them by resulting video order, and preserve
within-video frame order. This is a text-semantic experiment, not the historical
Qwen multimodal reranker.

R@20 and candidate-pool coverage are invariant by design. The informative
outcomes are MRR and R@1/5/10. The reused evaluator's strict R@20-improvement
promotion gate cannot promote this arm; its verdict must not be mistaken for
evidence that MRR cannot improve. Grouping frames also changes their positions:
frame-ranking effects require a grouping-only control before attribution to
the cross-encoder. Distinct-video control metrics are unaffected by grouping.

No truth enters record selection, model inputs, or ranking. The unchanged
113-scoreable/115-query contract excludes p0_q15 and p3_q09. The existing
provisional truth qualifications and repeated-benchmark selection caveats
remain. Policy and model/input/code SHA-256 bindings are in policy.json,
frozen before inference. No downloads, corpus embeddings, external retrieval,
index writes, corpus edits, or truth edits are part of this experiment.

## Work location and reproduction

Branch: codex/issue-92-overnight-20260916.
Source commit: 37b321048432ccba5182a66bd39b1ca73c547537.
Worktree: C:\Users\minhc\Code\Vecna-issue92-overnight.
Code is uncommitted. Inherited dirty-state caveats are recorded in the frozen
v1 provenance; no remote SHA is claimed. Inputs are exact local paths with
hashes, including the v1 manifest, 768 cached vector batches, model files,
canonical queries, control rankings, scoring code and truth.

From the worktree, use C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe:

```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v2/code -p test_semantic_crossencoder.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v2/code/semantic_crossencoder.py
```

The three focused tests passed before launch. Inference is local-only CPU
float32, two pairs per batch, eight threads, maximum 1024 tokens. Token counts,
truncation, pair counts and same-session inference time are recorded. Per-query
files support recovery with the identical frozen policy; a completed job must
not be relaunched. Rankings are saved before loading truth. Once complete,
verify summary/ranking/cache hashes and independently rescore the control and
candidate membership before scientific acceptance.

## Transport

Active inference job: 20260916T172450Z-ea757ee98d, started 17:24:51 UTC.
Evidence: C:\Users\minhc\.codex\notified-jobs\20260916T172450Z-ea757ee98d.
One startup state inspection confirmed running (worker 34988).
The terminal callback resumes validation and substantive research.

Cancelled timer job: 20260916T164826Z-aa901c4230. Its exact owned worker 31536
was stopped at 17:22:16 UTC. Exit 4294967295 is deliberate cancellation, not
an experiment failure. Its old closing next_action is superseded by the user;
do not close the overnight run when that cancellation callback arrives.
