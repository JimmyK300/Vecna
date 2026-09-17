# Existing object evidence on the accepted text pipeline

Source branch codex/issue-92-overnight-20260916, base
37b321048432ccba5182a66bd39b1ca73c547537; uncommitted. Inherited dirty-state
caveat: v1/provenance. Versioned, exclusive-create experiment; do not overwrite.
Parent is accepted v5 (temporal5s admission plus protected OCR/ASR ranking).

Keep100 candidates and first frame. Tail ranking uses61/(60+accepted rank)
plus0.05 times fraction of mentioned object categories supported by existing
YOLO detections. Inherit the fixed dictionary,confidence0.5 and negation guard;
missing detections contribute zero, never absence evidence. Original fusion
scores remain attached unchanged; this adds a rank-based soft evidence stage.
No count/color/relation inference, extraction, download or truth/index changes.
Policy frozen before detection reads/scoring. Evidence and exact detection
hashes are archived; no query-specific tuning. No parameter sweep.

Two focused tests passed. Independent sorting replay, control/membership/first
frame, policy/detection hashes and all113 rescored rows passed in validation.
115 canonical queries,113 scoreable, exclusions p0_q15/p3_q09; retain inherited
provisional/proxy truth qualifications and exact joins. Rankings saved before
truth is loaded. Runnable commands from the research worktree using Vecna's
.venv/Scripts/python.exe:

```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v7/code -p test_object_rank.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v7/code/object_rank.py
python -X utf8 -B benchmark-results/astra-overnight-issue92-v7/code/verify.py
```

Reproduction requires a fresh versioned output directory; all inherited
rankings/query/truth/scorer and external detections use hash-bound paths.
Result: INCONCLUSIVE, no video accuracy change:49/77/85/90, MRR
0.5406434596816525; complete80, video pool94. No video rescues/regressions.
Frame/event layer disagreements remain in outputs/per_query.jsonl/summary.json.
No promotion. Workload875 detection files,38 applicable queries,30 with
coverage,12 supported frame appearances;4.6515557seconds this session, no
new inference. Sparse coverage limits interpretation. All negative evidence
is preserved; v5 remains selected.
