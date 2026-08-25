# Issue #59 — TRAKE exact-event timing audit (read-only diagnosis)

Status: **ACCEPTED** (diagnosis only; no fixes implemented, no retrieval
parameter/model/index/config changed anywhere)

Generated: 2026-08-25 · Worktree `codex/issue-59-trake-audit` @ `9b8a871e8531aae85de6eb87fea400bef8669d48` (= origin/main HEAD)
Live stack diagnosed: primary checkout `C:\Users\minhc\Code\Vecna` @ `fd879fb` (dirty=True), collection `official_l21_l30_all_v2` (322,924 entities), index generation `idx_6baede5b9bc447e099c0004d8428ca7e`.

---

## 1) Status

`accepted`. Both stop conditions tested and not hit:
- Ground truth is consistent for the analyzed slice (all three queries parse; provisional tier recorded below).
- Tooling exposed enough ranked evidence (k raised 20 → 1000 read-only; deeper ranks visible).
- No fix requires changing production semantics to *state*; all proposed experiments are offline replays.

One environment incident occurred mid-audit (host Docker Desktop engine stopped on its own during a verification re-run; Milvus became unreachable). Search-phase evidence had already completed and is valid. The keyframe-density probe was replaced by a deterministic, cross-validated offline reconstruction (`reconstruct_keyframe_density.py`). Details in §10 and `audit.launcher.json` → `incidents`. No container was stopped or restarted by this audit.

## 2) Frozen set source + TRAKE query count

- Source: `aic51-src/benchmark/issue34_headless_queries.csv` in the primary checkout (the only copy on disk; absent from this worktree's tree at base commit).
  - Raw file sha256: `b732a623deba352db037bcb8acb5f99923ba9cd01e761ad3f4417307de42057c`
  - Canonical issue34-v1 content sha256 (verified this session via `hb.canonical_content_sha256`, asserted == pinned): **`1aba0cf592976a7ec3e2417ff7e9c46628ad2269dc786125fa07c26e0a34470e`** ✅
- Inventory validation: complete (42/42 canonical IDs), schema `issue34-v1`.
- TRAKE rows total: 5.
  - Analyzed: **3** — `p1_q02`, `p1_q14`, `p1_q16` (`evaluation_scope=include_current_dataset`, scoreable).
  - Excluded with reasons: `set1_q03`, `set1_q19` — `evaluation_scope=exclude_different_dataset` (their corpus videos are not in the current index).
- Ground-truth caveat: **provisional tier** (`source_text_verified_needs_corpus_validation`) for all three. Gold points used: p1_q02 → L26_V194 @[4707, 5142, 5430, 5527] @25fps; p1_q14 → L24_V033 @[15945, 16009, 16355, 16900] @30fps; p1_q16 → L26_V072 @[2471, 3136, 3427, 3800] @25fps.

## 3) Video-level vs exact-event success (reported separately)

Matcher: official benchmark contract — TRAKE points hit at |Δt| ≤ 2.0 s (per-video rounded FPS); video-level = any frame of gold video regardless of time.

| metric | issue58 pinned sweep (k=20) | this audit re-run (k=1000 exposure) |
|---|---|---|
| Video R@1 | 0.000 (0/3) | 0.000 (0/3) |
| Video R@5 | 0.667 (q02@2, q14@3, q16 miss) | 0.333 (q02@4; q14@13; q16 first at 70) |
| Video R@20 | **1.000 (3/3)** | 0.667 (q16 not in top-20) |
| Exact-event recall@20 (per event, ±2 s) | 1/12 ≈ 0.083 (q02 [13,–,–,–]; q14 [3,7,–,–]; q16 [–,–,–,–]) | 3/12 = 0.250 (q02 [15,–,–,–]; q14 [13,17,–,–]; q16 [–,–,–,–]) |
| Exact-event recall@1000 (this audit only) | n/a | **6/12 = 0.500** (q02 [15,443,–,–]; q14 [13,17,639,–]; q16 [989,–,–,–]) |
| End-to-end TRAKE success (all events localized) | 0/3 (`localization_status: not_implemented`) | 0/3 |

The headline gap: **video-level success co-exists with near-zero event-level success.** Even granting 10× retrieval depth (k=1000), half the gold events never surface within tolerance at all.

Drift warning: the live primary stack is dirty (`searcher.py` heavily modified since the pinned sweep). q14 video rank moved 3→13 and q16 7→absent-from-top-20 between the pinned artifact and today's re-run. Numbers above should be read per-column, not merged.

## 4) Per-query evidence summary (top candidates / nearest correct / window coverage)

Machine-readable full evidence: `trake-audit.jsonl` (60 serialized candidates + scores per query, depth ladder 1→1000, crowding tables, nearest-correct deltas).

### p1_q02 — asparagus frying (GT L26_V194)
- Top-3 observed: L26_V323#3581 (final .607 = clip .824 **+ asr .782**), L26_V323#3584, L26_V256#33. Correct video enters at rank 4 (#5845 — *after* all four events).
- Event hits: E1 @ rank 15 (#4736, Δ29f = 1.16 s); E2 buried at rank **443**; E3/E4 never within k=1000.
- Nearest correct candidate: rank 15 (above). Index coverage: indexed frames exist at Δ0 / 3 / 15 / 8 frames from E1–E4 — all four windows are populated.
- Crowding above first event hit: L26_V208 ×5 (sister cooking video), V323 ×2, V427 ×2, V313 ×2 …
- Review burden: 15 clips to first event, 443 to second, >1000 for the last two.

### p1_q14 — lion dance (GT L24_V033)
- Top-4 observed: **L24_V025#2492/#2188/#2248/#2644**, final ≈ .594–.598 each = clip ≈ .93 **+ asr .519 where the ASR text is literally "the the"** (degenerate transcription matched against English query tokens).
- Event hits: E1 @13 (#15928, Δ11f inside ±12f too), E2 @17 (#16020, Δ11f), E3 buried at **639**, E4 never within k=1000.
- Nearest correct candidate: rank 13. Index coverage: indexed frames at Δ15 / 11 / 29 / 28 frames from E1–E4.
- GT video holds 182 of 1000 slots but scattered in time; wrong-video crowding above first hit: L24_V025 ×8, V030 ×2, V016/V029 ×1.
- Review burden: 13 / 17 clips for E1/E2; 639 for E3; >1000 for E4.

### p1_q16 — mushroom prep (GT L26_V072)
- Top-3 observed: L26_V341#2812/#2866/#2816 (final ≈ .52–.53 = clip ≈ .59–.61 **+ asr .906**, ASR text "…green onion, we cut 3cm…" from a *different* cooking show).
- Correct video absent from top-20 entirely; first appears at rank **70**; only 19 GT frames in the whole k=1000 list. Sole event hit: E1 @ **989** (Δ5f). E2/E3/E4 never surface despite indexed frames at Δ3 / 7 / 12 frames.
- Crowding above rank 989: ~700 slots across 148 wrong videos (L25_V050 ×74, L25_V015 ×64, L25_V023 ×42, L26_V421 ×35, …).
- Review burden: >989 clips for the only reachable event.

### Window-coverage verdict (all 12 gold points)
Every gold point has an indexed keyframe within **≤ 0.97 s** (max Δ29 frames @30fps), i.e., inside the ±2 s scoring window. Exact-event failure is therefore **not** a frame-sampling problem at benchmark tolerance — every miss is a ranking failure. (At the stricter contest-like ±12-frame diagnostic window, 5 of 12 points would be uncoverable: q02-E3 Δ15f; q14-E1/E3/E4 Δ15/29/28f.)

## 5) Mechanism counts (aggregate; query-level flags, one query can carry several)

From `mechanism-counts.json` (rules fixed before inspection):

| mechanism | count (of 3) |
|---|---|
| `single_vector_multi_event_no_decomposition` | **3/3** |
| `correct_video_but_event_window_missing_from_top20` | **3/3** |
| `event_window_absent_entirely_from_top1000` | **3/3** |
| `visual_semantics_wrong_video_crowding` | **3/3** |
| `duplicate_results_same_video_slot_flooding` | **3/3** |
| `index_frame_gap_at_gold_point_over_2s` | 0/3 (**sampling ruled out**) |
| `unresolved` | 0/3 |

Structural facts backing row 1: `Query._extract_temporal_queries` splits ONLY on `/` or `\`; none of the three TRAKE texts contains either, so all served as ONE similarity vector (`latency_tree.query_mode == "similarity"` recorded for all three runs). The temporal chain combiner exists but is unreachable for these queries, and no code path parses the `E1:/E2:` structure.

## 6) Top recurring failure patterns (≥3, concrete examples)

**P1 — Multi-event paragraph embedded as one vector; temporal machinery unreachable.**
Example: p1_q02's four sentences (batter → oil contact → first spear out → last spear plated) become a single CLIP/SigLIP/Qwen text embedding. Result: E1-like generic frying frames surface; E3/E4-specific moments rank 443+ or never (even at k=1000) although indexed frames sit 0.6 s / 0.32 s from gold. Same shape in all three queries (6 of 12 events missing from top-1000).

**P2 — OCR/ASR sparse fusion promotes transcript junk over visually-best frames (score-fusion inversion).**
Recorded channel scores: p1_q14's true E1 frame has the best visual score in the entire list (clip .983 vs top-1 .936) but zero text score → final .492 → rank 13; eight slots above it are L24_V025 frames whose entire contribution is ASR `"the the"` (BM25 match on query token "the"). p1_q02: true E1 frame clip .950 > top-1 .824, loses after ASR narration boost to an unrelated video (rank 15). With weights 0.5/0.25/0.25 and max-normalization, two junk text channels can outvote the best visual candidate.

**P3 — Near-duplicate videos crowd out the correct video (visual semantics).**
p1_q02: sister kitchen video L26_V208 occupies 5 of the 14 slots above the first true event hit — its frame #4736 even mirrors the true hit's index. p1_q16: mushroom-dish lookalikes (L26_V230/V421 in the pinned run; dozens of L25/L26 cooking videos today) push the GT video to rank 70+. p1_q14: other lion-dance videos fill the top.

**P4 — Duplicate/same-text slot flooding without temporal or diversity control.**
Identical transcripts repeated across adjacent keyframes yield blocks of near-equal scores (e.g., L24_V025#2492/2188/2248/2644 all asr_norm .519; L26_V341 triplets; L25_V023 42 slots). No per-video quota or time-spread logic exists on the similarity path; the dedup/chaining logic that does exist (`_combine_temporal_results`) only runs on the unreachable temporal path.

(Non-recurring but notable: ground-truth quirks — p1_q16's text numbers its events E1,E2,E2,E4; provisional GT tier means all absolute numbers await owner validation.)

## 7) Follow-up experiments (smallest variable + falsification evidence)

All offline replays on the frozen set; none changes production defaults:

1. **Per-event decomposition replay.** Smallest variable: query granularity only — split each Q0 into its E1..E4 sub-queries, search each independently (same cell params, k=20 judged per event). Falsification: if per-event recall@20 does NOT beat 3/12 (whole-paragraph baseline), the decomposition hypothesis dies.
2. **Visual-only ablation replay.** Smallest variable: ocr_weight/asr_weight = 0/0 in a measurement cell (like existing P20 matrix cells; production untouched). Prediction from P2: first-event-correct ranks improve and q16's video re-enters top-20. Falsified if rankings stay equal or degrade (would implicate visual channel instead).
3. **ASR de-duplication accounting (owner-side measurement).** Smallest variable: count identical-transcript adjacent keyframes once when computing slot occupancy. Falsifies P4 if flooding metrics don't drop materially.
4. **Official ±12-frame feasibility ceiling.** Smallest variable: none (pure index math, already computed in `keyframe-density.json`). Establishes max achievable contest-window recall (7/12 points have an indexed frame within ±12f). Any localizer design promising 12/12 under current sampling is falsified by construction.
5. **Ground-truth validation task (owner decision).** Promote the 3 TRAKE rows from provisional to validated/corrected before any optimization is trusted; also fix p1_q16's duplicated "E2" numbering in the source text mapping notes.

## 8) New-vs-already-visible failure modes

Already visible in issue58 artifacts (cited, not re-discovered):
- Video-level vs event-level gap; `localization_status: not_implemented`; TRAKE category note "localization NOT implemented".
- `temporal_understanding_required` flag on failed TRAKE; `incorrect_timestamp_alignment` observations for q02/q14; `poor_frame_sampling` label for q16.

Genuinely new in this audit:
- **Routing proof**: temporal combiner unreachable for TRAKE because the parser splits only on `/`; `E1:` structure is never parsed (explains "why" behind the previously descriptive flags).
- **Fusion inversion quantified** with channel-level scores (visual-best true frames losing to `"the the"`-type ASR matches).
- **Depth-ladder evidence**: events buried at 443/639/989 or absent at k=1000 while index windows are populated.
- **Sampling hypothesis refuted** at benchmark tolerance (was left open by the pinned `poor_frame_sampling` label): max gold-to-indexed-frame distance is 0.97 s across all 12 points.
- **Duplicate-video crowding quantified** per query (slot counts above first correct rank).
- **Baseline drift detection**: live dirty stack ≠ pinned sweep behavior (q14 video 3→13; q16 7→absent@20).

## 9) Scope-violation check

- Files created/modified: ONLY `benchmark-results/issue59-trake-audit/*` (report, JSONL/JSON evidence, two self-contained scripts) + this pointer doc `docs/trake-audit-issue59.md`. Nothing else; `git status` clean apart from these additions.
- Primary checkout: read-only throughout (`PYTHONDONTWRITEBYTECODE=1`, no writes; verified by process discipline, no file writes issued).
- Milvus: search/query reads only; `load_collection` invoked solely via the official `preflight_collection()` path; no create/stop/restart. The engine outage in §10 was host-side and not caused by this audit (a client process cannot stop Docker Desktop).
- Retrieval parameters: baseline cell replicated in-memory exactly as the official runner does (`apply_cell_config`); only `limit` raised 20 → 1000 to expose more ranked results (explicitly permitted; scoring/fusion path unchanged).

## 10) Remaining uncertainty / owner decisions

- **Incident**: Docker Desktop engine on the host stopped by itself during a verification re-run; Milvus stayed down for the rest of the session. Consequence: the density table comes from the validated reconstruction rather than live Milvus queries. Validation is empirical but one-sided (observed frames ⊆ reconstructed set holds for all 3 videos; unseen regions unverified). Owner may re-run `run_issue59_trake_audit.py` (filter already fixed) when the engine returns to replace it with live-query numbers.
- **Rank drift** between pinned sweep and live dirty stack is unattributed (code diff vs SCANN approximation nondeterminism). Owner should re-pin a clean baseline before optimizing.
- **Deep-k ranks are approximate** (SCANN nprobe=32); exact positions like 443/639/989 carry ± noise, though absence-at-1000 conclusions rest on margins far larger than that noise.
- **ASR quality**: "the the" looks like a whisper hallucination on crowd noise; owner audio inspection would confirm.
- All numbers inherit the **provisional ground truth** tier; owner validation could shift gold points and change individual outcomes (unlikely to change the structural findings P1/P2/P3/P4).

## 11) Readiness recommendation

Ready to plan fixes: the dominant mechanisms are identified with concrete falsifiable hypotheses and cheap offline experiments (§7 items 1–2 first). Recommended order: (a) owner validates the 3 provisional TRAKE ground truths; (b) run experiment 1 (decomposition replay) and 2 (visual-only cell) on a pinned, clean stack; (c) decide localization strategy only after those two land. Do not tune production weights/index based on this audit alone — n=3 queries, small-sample caveats apply throughout.
