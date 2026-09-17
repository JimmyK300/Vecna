# Video-preserving semantic admission

Parent is accepted v5: temporal5s admission plus protected-first text ranking.
The v6 semantic minority experiment improved video R20 but lost complete-target
coverage and failed the frozen promotion gate. This structural follow-up tests
whether novel-video-only admission makes better use of scarce candidate slots.
It does not select policies or protect frames by query answers or loss IDs.

Start with temporal5s100. Traverse inherited grounded-semantic candidates in
their fixed order. If a semantic video's identity is absent, remove the latest
retained frame whose video still has another retained frame, excluding frame1.
Append the new candidate. Stop after20 additions or no removable slot. Existing
video identities and first frame are guaranteed preserved. Exact target-frame
coverage is NOT guaranteed and remains a measured promotion guardrail.
Retained old frames keep relative order. Apply accepted protected text RRF60
once, using this admitted order. Compare to accepted v5, not rejected v6.

No threshold/quota grid. No truth-dependent admission, changed fusion scores,
new embedding, extraction, download or index mutation. Snapshot existing
OCR/ASR strings and source hashes. Reuse v5 and v6 scalar logits only for
identical canonical query hash, frame and text with pinned model/config;
assert duplicates agree. Infer only missing pairs. Same CPU float32/batch2/
threads8/max1024. Record new/reused counts and new truncation/timing separately.

Two focused tests verify original video preservation, first frame,100 unique
membership,20-new-video cap and refusal to evict unique-video-only candidates.
Policy freezes before inference. Complete rankings are saved before truth load.
115 canonical/113scoreable; same exclusions p0_q15/p3_q09 and provisional/proxy
truth qualifiers. Repeated benchmark; exploratory, no generalization claim.

Branch codex/issue-92-overnight-20260916; source base
37b321048432ccba5182a66bd39b1ca73c547537; uncommitted; inherited v1 dirty-state
caveat. Original deadline23:50Z and compute cutoff23:40Z remain. Completed
outputs are exclusive-create. Use a new versioned directory for reproduction.

From research worktree with C:/Users/minhc/Code/Vecna/.venv/Scripts/python.exe:
```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v9/code -p test_admission.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v9/code/prepare.py
python -X utf8 -B benchmark-results/astra-overnight-issue92-v9/code/frame_text.py
```
Acceptance: all hashes, independent admission/ranking replay, same v5 control,
candidate budget/video and first-frame guarantees, both score-reuse origins,
113 score rows, exact PR91 deltas, per-query rescues/regressions and archive.
