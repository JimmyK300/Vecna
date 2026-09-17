# OCR-only reranker modality ablation

Parent accepted v5 uses concatenated OCR then ASR text. This global ablation
tests whether ASR introduces distracting context. Retain the temporal5s100
candidate set and protect first frame. Rerank only nonempty OCR slots2..100 by
the same equal RRF60 of baseline covered rank and canonical-query score rank;
stable baseline ties. Empty OCR slots remain fixed; no ASR fallback. Compare
directly to v5 final, not an already reranked input. No per-query modality gate.

Text transformation is exactly `OCR: ` plus stripped inherited OCR scalar text,
or empty. All9878 frame records are retained;3827 have nonempty OCR. No truth
access during transformation or inference. Reuse v5 scalar scores only when
the full text was already identical (no ASR), query hash/frame/model/config
match. Infer other pairs on the existing local model CPU float32,batch2,
threads8,max1024. No new extraction, embedding, model download or index change.
Separate reused/new workload and new token truncation/same-session timings.

Two focused slot/protection/membership tests passed before policy freeze.
Code, exact inherited text/source hashes, queries, canonical truth, scorer,
model and reuse caches pinned. Save rankings before scoring113 of115 queries;
exclude p0_q15,p3_q09, retain provisional/proxy truth and repeated-benchmark
caveats. No generalization claim. Same promotion gate; preserve negatives.

Source branch codex/issue-92-overnight-20260916, base
37b321048432ccba5182a66bd39b1ca73c547537; uncommitted with inherited v1 dirty
caveat. Compute cutoff23:40Z, original overnight bound23:50Z. Exclusive-create
artifacts; reproduce only in a fresh versioned output directory.

From research worktree with C:/Users/minhc/Code/Vecna/.venv/Scripts/python.exe:
```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v10/code -p test_frame_text.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v10/code/prepare.py
python -X utf8 -B benchmark-results/astra-overnight-issue92-v10/code/frame_text.py
```
Acceptance requires exact transformation, all hashes, preserved100membership
and first frame, score-reuse identities, independent ranking replay,113-row
rescoring, v5 and PR91 comparisons, per-query evidence and versioned archive.
