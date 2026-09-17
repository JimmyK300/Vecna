# Existing OCR/ASR frame-text ranking

This follow-up retains the exact PR91 control after v2's negative semantic
cross-encoder result. It tests whether existing frame-local OCR/ASR provides
better grounded lexical evidence than semantic descriptions. It does not
choose or rewrite queries based on answers.

For every canonical query, score the nonempty OCR/ASR text of the original
top30 control frames. OCR then ASR are concatenated with fixed labels. Equal
RRF60 combines covered-frame baseline order and the cached BGE cross-encoder's
scalar-logit order; baseline order breaks ties. Only covered top30 slots can
permute. Empty text, missing files, and the remaining 70 slots retain baseline
positions. All original candidate identities and the 100-frame budget remain.
Distinct-video output is the first-occurrence projection of the resulting
frame list, with the inherited exact 113-scoreable/115-query scoring contract.

Inputs are snapshotted strings from scalar, non-pickled local OCR/ASR npy
files. Their exact paths and SHA-256 hashes, plus missing paths, are preserved
in inputs/source_hashes.json. policy.json binds the text snapshot, code,
model, query/control/truth/scorer dependencies before inference. No downloads,
new corpus embeddings, new frame extractions, index writes, or truth edits.
Truth is loaded only after final rankings are saved. Repeated-benchmark and
inherited provisional-truth qualifications remain.

Runtime is local CPU float32, eight threads, batch2, maximum1024 tokens;
record actual truncation and pair counts. Per-query caches are bound to the
policy. The original overnight deadline is 2026-09-16T23:50Z; computation has
an earlier 23:40Z cutoff for validation. No idle deadline timer is scheduled.

Worktree: C:\Users\minhc\Code\Vecna-issue92-overnight.
Branch: codex/issue-92-overnight-20260916.
Base: 37b321048432ccba5182a66bd39b1ca73c547537.
Uncommitted research; inherited dirty-state provenance remains in v1.

Use C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe from the worktree:

```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v3/code -p test_frame_text.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v3/code/frame_text.py
```

Two focused tests passed before launch. Do not rerun a completed inference job.
Acceptance requires complete output hashes, 115 unique query caches, exact
control replay and unchanged membership/slot checks; process exit alone is
insufficient. Per-query rescues/regressions and all negative results remain.
