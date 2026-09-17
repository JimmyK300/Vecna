# Deeper text reranking on the accepted temporal5s arm

Parent experiment: v4 temporal5s, R@20=88/113, MRR=0.5306697517590282,
complete-target pool80/113. This continues from the strongest supported arm,
not the obsolete v3 text arm or main.

Hypothesis: deeper existing OCR/ASR can rescue lower-ranked correct videos,
while a fixed first-frame protection gate avoids earlier first-rank losses.
Preserve frame1. Score nonempty text for frames2..100, then permute only these
covered slots by equal RRF60 of baseline order and cross-encoder scalar-score
order; baseline breaks ties. Empty text slots stay fixed. All100 candidate
identities remain unchanged. This tests one global gate/blend, not a grid or
query-specific rule. Compare both against temporal5s and the exact PR91 control.

code/prepare.py snapshots scalar existing OCR/ASR strings and source hashes,
then freezes policy.json before inference. No query-dependent text selection,
truth access, frame extraction, corpus embedding, download, or index writes.
Truth is scoring-only after rankings are saved. Candidate coverage is invariant;
R@1 is invariant because the first frame is protected. R@5/10/20 and MRR remain
informative. All inherited provenance and repeated-benchmark caveats apply.

Reuse v3 pair logits only for matching query hash, frame ID and identical text.
Both runs pin the same local model/tokenizer and CPU float32/batch2/max1024
settings. Policy binds v3 caches and model files. Reuse counts are separate
from new inference. Token counts/truncation/timing refer to new pairs only.
Pair padding may differ from v3, so reuse assumes padding-invariant model
semantics; no same-session speed comparison between reused and new scores.

Two focused protection/slot/membership tests passed before launch. Completion
requires 115 query caches, hashes, exact parent comparison, deterministic
ranking replay, preserved first frame and100 membership, and rescoring all113
scoreable rows. No process-exit-only acceptance. Negative results remain.

Use C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe from worktree
C:\Users\minhc\Code\Vecna-issue92-overnight:

```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v5/code -p test_frame_text.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v5/code/prepare.py
python -X utf8 -B benchmark-results/astra-overnight-issue92-v5/code/frame_text.py
```

Preparation and completed outputs are non-overwriting; use a new versioned
copy for reproduction. Branch codex/issue-92-overnight-20260916, source base
37b321048432ccba5182a66bd39b1ca73c547537; code is uncommitted. Original23:50Z
deadline remains, with23:40Z compute cutoff. Completion transport resumes
validation and substantive research; no idle deadline timer.
