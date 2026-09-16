# Packet D: unified 113-query failure ledger

113 scoreable queries are preserved; 31 miss the frozen top20 contract across the observed arms. Fusion status: EVALUATED.

| Primary outcome after observed arms | Queries |
|---|---:|
| candidate_generation_missing_event | 18 |
| candidate_generation_missing_video | 6 |
| none | 82 |
| unresolved | 7 |

The success count is a descriptive union across saved arms, not a deployed system score or routing policy. The ledger retains each historical baseline failure and reranker regression even when another arm succeeds. The candidate ceiling describes C's historical Qwen pool; it does not imply that other providers cannot rescue the query.

C's historical saved HTTP Qwen output is paired with its saved reranker result. B uses a fresh raw-provider collection and preserves its own matched Qwen control separately. Candidate identities, collection conditions and timeline evidence differ across B/C, so their comparisons are descriptive. No sequential fusion-to-reranker system was tested.

Ranks use the pinned frozen localization/event scorer at20. Original C timeline evidence is preserved, while B has frame-only candidates. Candidate-position video and deduplicated-video ranks remain separate. Missing observed ranks are censored; unavailable arms are null, with explicit status.

Historical C metrics remain literal saved-rank evidence. Historical package versions, tensor equality and corpus extraction/index lineage remain unverified. A later loader defect and its repair do not retroactively establish C or corpus validity; see the separately pinned C loader-provenance companion.

B's one global development selection is fusion_current_control, verified by distinct-video R20, then MRR20, then R1 and fixed arm order. The selection is exploratory after comparing five arms, with no per-query oracle.

B fusion exceeds C historical MRR while C reranker regresses against its paired baseline: p1_q09, p2_q02, p3_q07, p3_q28.
C reranker improves MRR while B does not exceed the historical baseline: p0_q04, p0_q11, p0_q20, p1_q01, p1_q08, p1_q10, p2_q11, p2_q28, p3_q12, p3_q15, p3_q16, p3_q20, p3_q29.
C reranker R20 rescues with a miss in B's separate fusion capture: p0_q20, p2_q11, p2_q28, p3_q16, p3_q29.

Within B's own collection, selected fusion R20 improvements versus fresh Qwen: p1_q04, p2_q15, p2_q21, p2_q23, p2_q24, p3_q06, p3_q26.
Within that B collection, R20 regressions versus fresh Qwen: p3_q14.

| Provider | Channel | Cases | Eligible video @100 | All current targets @100 | Same-video exact-text repeat excess / retained candidates |
|---|---|---:|---:|---:|---:|
| sparse | OCR | 20 | 7 | 4 | 344 / 2000 |
| sparse | ASR | 18 | 13 | 11 | 1682 / 1800 |
| dense | OCR | 20 | 9 | 7 | 243 / 2000 |
| dense | ASR | 18 | 14 | 12 | 1599 / 1800 |

These are independent sample-pool visibility counts, including provisional truth. Raw and main-eligible orders remain separate. Video rank uses frame positions; any-target visibility, strict all-target visibility and the full frozen range/event score are distinct. MRR remains capped at20. None of these observations changes D's causal labels or observed-arm union.

Sparse host/seed tie replays preserve membership and score sequences but may change ranks and rank metrics. Every observed order is retained without selecting a seed. Dense evidence preserves declared query-model identity and unresolved historical stored-vector compatibility; the exact SDK-added empty params mapping is recorded without claiming independently verified server nprobe.

Temporal correct-video top100 cases with a missing required event: p0_q23, p0_q24, p1_q25, p2_q29, p2_q30, p3_q21, p3_q34.
Temporal correct-video top20 cases with an unsatisfied event contract: p0_q23, p0_q24, p1_q25, p2_q29, p2_q30, p3_q21, p3_q34.

Source evidence includes 20 OCR images inspected, 18 ASR excerpts captured but unheard, and 0 ASR excerpts heard. Preparation rank fields remain separate from source judgements.

Temporal source proposals cover 31 anchors: point=16, unknown=15. Canonical truth, prior anchors and metric eligibility are unchanged.
Truth qualifies 41 queries:35 provisional P3 cases and6 historical TRAKE submission-anchor proxies. The mainly-truth-limited set remains null because source review does not establish dominant retrieval cause.

Counts by capability/category, exact ranks, source evidence and one next-smallest test per query are in failure_ledger.jsonl and summary.json. All consumed-file SHA256 values appear in provenance.json.

Replay after hydrating the final packet artifacts:

    python -m unittest discover -s tests -p 'test_*ledger.py' -v
    python code/build_failure_ledger.py --root . --require-complete
