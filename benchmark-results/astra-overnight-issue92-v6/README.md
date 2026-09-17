# Semantic minority admission on the accepted ranking pipeline

Parent architecture is v5: temporal5s admission followed by protected-first
OCR/ASR BGE ranking. It scored90/113 video R@20 and MRR0.5406434596816525.
This experiment tests complementarity of the existing semantic provider's
coverage, whose earlier broad fusion lost ranking quality.

The globally fixed admission rule keeps the first80 temporal5s frames in
their pre-rerank fusion order, then appends the first20 unique frames from the
cached grounded dense semantic provider. If that provider is exhausted, fill
from the old tail. This consumes the same100-frame budget. Apply the accepted
protected-first-frame text RRF60 stage exactly once to the admitted list.
Compare final results to the accepted v5 final rankings. Do not rerank v5's
already-reranked order a second time; that would confound admission with
repeated weighting. There is no80/20 sweep or answer-conditioned injection.

Inference reuses v5 scores only for identical query hash, frame ID and text,
with matching pinned model/tokenizer/config. New candidate text is snapshotted
from existing scalar OCR/ASR files. The semantic rankings are inherited from
v1's hash-bound grounded dense provider; no new embedding, semantic retrieval,
frame extraction, download, truth change or index mutation. Save all ranking
outputs before truth is loaded. Record source hashes and missing files.

Two focused admission tests passed before launch. policy.json freezes exact
inputs, code, model and source identities. Acceptance requires115 cache rows,
all relevant hashes,100 unique candidates, first80 admission prefix, unchanged
first frame, reuse identity verification, exact v5 comparison and PR91-relative
rescoring. Preserve all negative findings and paired disagreement evidence.

Use C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe from
C:\Users\minhc\Code\Vecna-issue92-overnight:

```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v6/code -p test_admission.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v6/code/prepare.py
python -X utf8 -B benchmark-results/astra-overnight-issue92-v6/code/frame_text.py
```

Exclusive-create preparation and completed artifacts must not be overwritten.
Use a new versioned copy for reproduction. Source branch
codex/issue-92-overnight-20260916, base37b321048432ccba5182a66bd39b1ca73c547537;
uncommitted code and inherited v1 dirty-state caveat. Original23:50Z deadline;
compute stops23:40Z for validation. This run remains exploratory on repeatedly
inspected115 queries (113scoreable, exclusions p0_q15/p3_q09), with the same
provisional/proxy truth qualifications and strict scoring/join contract.
