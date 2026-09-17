# Fixed English variant on the strongest accepted pipeline

Parent v5: temporal5s100 followed by protected-first OCR/ASR ranking.
Use canonical query plus the first cached English translation from v1, selected
globally before this experiment's scores. No truth-aware text selection,
regeneration, model download, corpus embedding or frame extraction. This tests
cross-language query evidence at reranking, not the prior BM25 variant route.

Keep pre-rerank100 membership and first frame. RRF60 baseline rank weight1;
canonical text-logit rank weight0.5; English text-logit rank weight0.5. Missing
text slots stay fixed; baseline tie order. Averaging the two text terms before
addition preserves exact floating-point order when the two variants agree.
The initial focused equivalence test caught a floating-point addition-order
tie discrepancy; fixed before policy freeze/inference. All115 identical-variant
replays now equal the accepted v5 ranker exactly. Two tests pass. No grid.

CPU float32 batch2 threads8,max1024; canonical scores reused with query hashes,
English scores new. All115 queries have an existing translation; no fallback.
Code, texts, translations, models, parent rankings/caches/truth/scorer pinned
in policy.json. Complete original OCR/ASR texts and source hashes are inherited
by immutable path, not copied. Score only after saving blind rankings. Original
23:50Z bound,23:40Z compute cutoff; completion event triggers verification.

Branch codex/issue-92-overnight-20260916, base
37b321048432ccba5182a66bd39b1ca73c547537, uncommitted; inherited v1 dirty caveat.
115 canonical/113scoreable, excludes p0_q15/p3_q09; same scoring contracts,
provisional/proxy qualifications and repeatedly inspected benchmark. No
generalization claim. No production/parent/friend branch mutation.

From research worktree with C:/Users/minhc/Code/Vecna/.venv/Scripts/python.exe:
```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v8/code -p test_query_rank.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v8/code/prepare.py
python -X utf8 -B benchmark-results/astra-overnight-issue92-v8/code/query_rank.py
```
Exclusive creation; use fresh versioned outputs for reproduction. Completion
requires policy/cache/model/query hashes, unchanged100/first frame, exact v5
control, independent rank replay,113 rescored rows and original PR91 deltas.
