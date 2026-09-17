# Five-second temporal-neighborhood admission: narrow positive result

This is a new fixed admission hypothesis after the existing five-video shot
map produced no measurable change. It is not a rerun of the shot-map arm and
does not claim that five-second intervals identify shots or semantic events.

Traverse the complete inherited provider union by unchanged current-fusion
score and inherited stable tie order. Keep the first frame in each video and
five-second bin, floor(frame_number/(rounded_fps*5)); continue until100 frames.
Unknown FPS would retain singleton identity, but there were no unknown FPS
frames in the tested union. No interval sweep or answer-conditioned policy.
No new retrieval, inference, embeddings, frame extraction or index mutation.

Two focused tests passed. All frozen policy hashes passed; an independent
dictionary-based admission replay matched all115 query outputs. Exact PR91
control rows reproduced. Every arm retained100 frames and unchanged fusion
scores. Independent 113-row rescoring reproduced all metrics and paired
results. See validation/accepted.json and validation/recomputed/.

| Metric | PR91 control | Temporal5s |
|---|---:|---:|
| Distinct-video R@1/@5/@10 counts | 49/77/82 | 49/77/82 |
| Distinct-video R@20 count | 87 | 88 |
| MRR@20 | 0.5299890165650186 | 0.5306697517590282 |
| Candidate correct-video presence | 92 | 94 |
| Complete required-target presence | 78 | 80 |
| Fractional target-coverage sum | 79 | 81 |

The only video-ranking rescue is p3_q35, newly at rank13; no video-ranking
regressions. R@20 delta +1/113, paired bootstrap95% interval [0,3/113].
MRR delta +0.0006807351940095304, interval [0,0.002042205582028591].
Correct-video pool rescues: p2_q07,p3_q35. Complete-target rescues:
p0_q02,p2_q07. No complete-target losses. Fractional coverage additionally
gains on p2_q29 but regresses on p2_q30; this negative evidence is retained.

The frozen promotion gate passes. This becomes the working best arm for the
next experiment, with narrow exploratory support only: one R@20 rescue,
repeated benchmark exposure, inherited provisional/proxy truth, no pristine
holdout and intervals touching zero. No production recommendation or merge.

Policy SHA-256:
3c29fc99e2f55c2049ac719c254fcf5e8d5015eb74d74013c2ed66a268f8c580.
policy.json binds complete provider rankings, exact control, config, FPS map,
code and scoring inputs by absolute path and SHA-256. Full output rankings,
per-query scores, rescue/regression evidence and summary are retained.
Recorded in-process admission/fusion wall time:0.1839978 seconds over115 queries;
this excludes file loading/scoring and is not comparable to production latency.

Worktree C:\Users\minhc\Code\Vecna-issue92-overnight, branch
codex/issue-92-overnight-20260916, base37b321048432ccba5182a66bd39b1ca73c547537.
Uncommitted research; inherited dirty-state caveat in v1 provenance remains.

Using C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe from the worktree:

```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v4/code -p test_temporal_bins.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v4/code/temporal_bins.py
```

Output directories are exclusive-create: preserve the completed run and use
a separate versioned output for reproduction. Rankings are saved before truth
is opened. The113/115 scoring/exclusion contract is unchanged from PR91.
