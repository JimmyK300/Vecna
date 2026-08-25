# Issue #61 — frozen A/B decomposition experiment summary

Generated: 2026-08-25T18:22Z (run window 01:15–01:22 local). Status: **COMPLETE**, recommendation per frozen mapping: **`no_benefit`**.

- Policy: `issue61-decomposition-v1` rev 1, frozen **before any scoring** (`policy_json_sha256 = 94db843a6b4e8748c158fd91cec77d2bcc60be673fe9387f798501f3852dc71c`, `derivation_preview_sha256 = 4a5f71c118d9c96beebd5832763fb1344b1cdacbcd4ceb76115a17a6ec8ed8dd`). No LLM calls; deterministic rules only.
- Query set: canonical issue34 CSV (raw sha256 `b732a623…de42057c`; canonical content sha256 verified == pinned `1aba0cf5…470e`), current-scope text queries **n=22, scoreable 21** (p1_q22 unscoreable), provisional GT tier — all absolute numbers carry that caveat.
- Complexity split (frozen classifier): **complex 17 scoreable** (+ p1_q22 unscoreable) vs **simple control 4** (`p1_q04/q05/q06/q07`).
- Identical assets A/B (same process, ONE searcher instance): collection `official_l21_l30_all_v2` (322,924 entities), index generation `idx_6baede5b9bc447e099c0004d8428ca7e`, cell `clip_siglip_qwen_sparse` (rerank OFF, nprobe 32, temporal_k 2000, OCR/ASR 0.25/0.25), encoders CPU. Determinism probe (Arm A re-run, q01+q02): fingerprints identical at depth 20.
- Arm A reproduces published baseline-v1 guardrails exactly: R@20 **0.797619**, MRR@20 **0.58868** ✓.

## Global Q0 (21 scoreable)

| arm | R@1 | R@5 | R@10 | R@20 | MRR@20 | no-hit@20 | mean latency* |
|---|---:|---:|---:|---:|---:|---:|---:|
| A full query | 0.52381 | 0.63095 | 0.73810 | **0.79762** | 0.58868 | 3/21 | 8077 ms (p50 6435) |
| B decomposed | 0.52381 | 0.66667 | 0.76190 | 0.76190 | 0.59014 | 5/21 | 4740 ms (p50 5070); sequential Σfragments mean 7276 ms |

\* q06-A is a 47.8 s outlier (its raw text contains `/`, routing it through the production temporal path).

## Complex group (n=17): Δ(B−A)

| ΔR@1 | ΔR@5 | ΔR@10 | ΔR@20 | ΔMRR@20 |
|---:|---:|---:|---:|---:|
| +0.0588 | +0.0441 | −0.0294 | **−0.0441** | **+0.0282** |

Wins: QA evidence q13 rank 4→1 (QA evidence R@1 0.5→1.0, MRR 0.625→1.0); TKIS q12 3→1, q18 9→3.
Losses: **TRAKE collapses** (below); q10 1→4.
Frozen-mapping check: ΔR@20 −0.0441 ≤ +0.05 ⇒ `no_benefit` (the MRR gain is concentrated in two mid-rank TKIS/QA fixes and does not survive the R@20 loss).

## TRAKE (n=3) — decomposition is actively harmful

| metric | A | B |
|---|---:|---:|
| video R@5 / R@20 | 0.667 / **1.000** | 0.333 / 0.667 |
| video MRR@20 | 0.325 | 0.185 |
| event-candidate R@20 | 0.25 | **0.000** |

Per query (video rank → event ranks within top-20):
- p1_q02: A video@13 / B video@18, events [None×4] — lookalike cooking videos (L26_V208 ×4 slots) flood the fused list.
- p1_q14: A video@3 / B video@**2** but events [None×4] — gold video surfaces yet none of its event frames do; single-event fragments retrieve other lion-dance videos' moments instead.
- p1_q16: A miss / B miss (gold absent from top-20 in both).
Mechanism match to issue #59 P3/P4: each event fragment alone is a generic visual query; RRF fusion promotes wrong-video consensus and dilutes the specific video. The no-decomposition mechanism audit's falsification test resolves AGAINST per-event decomposition for retrieval ranking on this stack.

## Simple control (n=4, gated identity by policy)

R@20 unchanged (1.0→1.0, zero harm at headline level); MRR 0.5644→0.4524 (Δ −0.112) driven entirely by sanitizer effects, not decomposition:
- p1_q06: raw text contains `/` → Arm A takes the production temporal path (rank 1); sanitized identity takes the similarity path (rank 2). Routing semantics shift, not decomposition.
- p1_q07: newline collapse shifts embedding slightly: rank 11→7 (improvement).
Pre-declared forced-decomposition diagnostics (excluded from headline): q04 6→**1** (+5 positions), q05 1→1, q06 2→1, q07 7→8 — i.e., even here gains are rank-position noise on an already-saturated slice (all R@20=1.0), not recall gains.

## Latency / extra-call cost

- Fragment counts: 14×1, 5×2, 3×8 (TRAKE) → **25 extra calls** total (~2.2× on decomposed queries; mean extra_calls 1.19 over 21).
- Visual-only fragment calls are cheap (mean 2713 ms, OCR/ASR channels skipped) but multi-call sums erase the gain (sequential Σ mean 7276 ms ≈ Arm A's 8077 ms); TRAKE pays ~8 calls per query.

## Failure categories after Arm B (remaining misses)

| query | arm | categories |
|---|---|---|
| p1_q02 | B | correct_result_outside_top20, temporal_understanding_required, poor_frame_sampling |
| p1_q14 | B | correct_result_outside_top20, temporal_understanding_required, poor_frame_sampling |
| p1_q16 | A/B | correct_result_outside_top20 (+B: gold_video_absent_from_top20, unresolved_no_gold_evidence_in_top20) |
| p1_q20 | A/B | correct_result_outside_top20, gold absent, unresolved |
| p1_q21 | A/B | correct_result_outside_top20, temporal_understanding_required, poor_frame_sampling |

q19's declared `world_knowledge_bridge` never triggered as a failure (ASR-strong evidence carried it to rank 1 in both arms).

## Verdict

Rule-based query decomposition **does not improve** Vecna retrieval on complex/combined/temporal queries under identical assets; it trades small TKIS/QA rank gains for a large TRAKE regression, adds ~2× call cost, and its only clean win (QA evidence q13) is a single provisional-GT query. Per the frozen mapping: **no benefit**. Any future work should target the TRAKE localization machinery (issue #59 follow-ups 2–5), not query fragmentation.
