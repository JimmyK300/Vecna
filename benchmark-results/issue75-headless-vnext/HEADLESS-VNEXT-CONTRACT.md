# Issue #75 — Headless current-state audit + vNext contract proposal

**Status:** proposal only — **MINH APPROVAL REQUIRED** before scorer/manifests/benchmark execution change  
**Issue:** `JimmyK300/Vecna#75`  
**Audit base:** `ec4a38d397c9a3a49a821812b37db47f52327049` (`codex/issue-63-stage-b`)  
**Historical control evidence:** `cb5216b6f80826f626d61e01496589179520dfa4` (`codex/issue-58-baseline-sweep`)  
**No benchmark run was performed for Issue #75. No retrieval, model, index, corpus, benchmark truth, or scoring implementation was changed.**

---

## 0. Recommendation in one paragraph

Stop publishing an unqualified `Recall@K` as the main semantic description of Headless. The current result mixes at least three meanings: legacy TKIS/QA temporal matching, legacy TRAKE fractional event-candidate coverage, and reconstructed query-level correct-video + accepted-range exposure. Headless vNext should make **video retrieval** and **semantic-range exposure** first-class, separately named metrics: `video_R@{1,5,20}` / `video_MRR@20` and `range_R@{1,5,20}` / `range_MRR@20`. Add distance-to-range diagnostics that are **null with an explicit status when no correct video is present**, not a giant penalty. Keep TRAKE event coverage separate from ordinary range recall; do not claim the four reconstructed TRAKE-labeled rows are event-scoreable until event-specific truth is structurally validated. Keep QA answer correctness outside retrieval recall. When the newer corpus becomes the main benchmark, preserve the Issue #58 21-row control as a frozen, separately reported regression suite rather than mixing it into the new headline denominator.

---

## 1. Evidence audited

This proposal is grounded in the frozen/accepted surfaces below rather than reconstructed from chat memory.

### Legacy control — Issue #58

- Issue #58 frozen result commit: `cb5216b6f80826f626d61e01496589179520dfa4`.
- `benchmark-results/issue58-baseline-sweep/p20-clip_siglip_qwen_sparse.jsonl` records task-specific scoring fields, top-20 results, `first_correct_rank`, `target_ranks`, latency, and temporal diagnostics.
- `aic51-src/script/run_issue58_baseline_sweep.py` delegates to the then-live official `run_p20_p21_measurement.run_quality` path with the frozen cell `clip_siglip_qwen_sparse`, rerank OFF.
- Frozen result identity: 22 source rows, 21 provisional-scoreable; `p1_q22` excluded for missing answer GT.

Important observed legacy semantics:

1. TKIS interval examples use inclusive interval membership.
2. Legacy point truth uses the headless retrieval point contract (`retrieval_point_tolerance_seconds: 2.0` in the frozen output); e.g. QA `p1_q17` retrieves frame 5585 for point 5580 at 25 fps and counts it as a retrieval hit.
3. TRAKE uses `target_mode: events`; per-event `target_ranks` and fractional `event_candidate_recall_at_K` are recorded. Example `p1_q14` has correct video first at rank 3, event ranks `[3, 7, null, null]`, and `recall_at_20 = 0.5`.
4. TRAKE also contains a task-specific `video_retrieval` diagnostic. Example `p1_q16` retrieves the correct video at rank 7 while all event-candidate recalls remain 0. This is useful precedent, but it is not a standardized all-task video metric.
5. `localization_status` for legacy TRAKE is `not_implemented` and `end_to_end_trake_success` is null: event candidate exposure is not a full ordered/localization evaluator.
6. QA is explicitly evidence retrieval; answer extraction/generation correctness is not part of the headline score.

### Reconstructed benchmark — Issue #63 Stage B

Frozen accepted commits:

- result artifact commit `b1856c647d3910a4ab0a934bfc1c4d696e0a47a1`;
- branch HEAD / return doc commit `ec4a38d397c9a3a49a821812b37db47f52327049`.

Audited files:

- `benchmark-results/issue63-stage-b/PROTOCOL.md`;
- `benchmark-results/issue63-stage-b/reconstructed-truth.json`;
- `aic51-src/script/issue63_stage_b_scoring.py`;
- `aic51-src/script/run_issue63_stage_b.py`;
- `aic51-src/tests/test_issue63_stage_b.py`;
- Stage B completion packet on Issue #63.

Observed reconstructed semantics:

1. Exactly 48 accepted reconstructed records are scoreable; `testing88_submission633::p1-21` remains non-scoreable because `L21_V004.mp4` was unavailable for review.
2. A result is a hit only when normalized `video_id` matches and a returned point/timeline frame falls inside any reviewed interval, endpoints inclusive.
3. The pure reconstructed scorer also treats an explicit returned segment as a hit when it overlaps a reviewed interval. The deterministic test verifies endpoint overlap.
4. Any accepted interval may satisfy the whole reconstructed record (`alternative_intervals: any accepted interval satisfies`).
5. First matching result defines `first_correct_rank`; reconstructed `recall_at_K` is binary from that range-valid rank.
6. The actual Stage B counted runtime exposed point/timeline frames; explicit segment-overlap support existed in the pure scorer but was not exercised by the counted run.
7. The Stage B aggregate deliberately preserves legacy TRAKE fractional recall values while reconstructed rows are binary. Therefore the current 69-row aggregate `Recall@K` is numerically reproducible but **semantically heterogeneous**.

### Corpus identity / P2

Canonical round identity is being audited separately in `JimmyK300/official-dataset-control#11`:

- P0/testing round: 24 source questions, historical ~8.8 source;
- P1/actual Round 1: 25 source questions, ~10.4/13 source;
- raw `p1-*` labels are provenance and must not collapse P0/P1 identity.

`Official-Queries/current-rounds/actual-p2-official.md` preserves exactly 30 P2 texts = 19 KIS + 9 QA + 2 TRAKE and explicitly states that it does **not** establish answers, current-corpus compatibility, exact-frame GT, or benchmark eligibility. P2 therefore remains excluded here.

---

## 2. What current Headless actually means

### Legacy control

The 21 scoreable Issue #58 rows are a historical regression surface, not one uniform metric contract:

- TKIS: temporal interval membership in the correct video;
- QA: evidence-point retrieval in the correct video under the legacy point matching contract; generated answer correctness is not scored;
- TRAKE: event-candidate coverage with fractional per-query recall, plus a TRAKE-only video retrieval diagnostic; no full ordered-event evaluator.

Its published global `Recall@K` therefore already combines different task-level notions of success.

### Reconstructed Issue #63 rows

The 48 accepted reconstructed rows are simpler mechanically: a query is successful when a returned result is in the correct video **and** exposes any reviewed semantic interval. This is useful, but the single `Recall@K` hides two different failure mechanisms:

1. the correct video was never retrieved; or
2. the correct video was retrieved, but the returned frame/segment missed all accepted ranges.

### Mixed 69-row Stage B aggregate

Stage B concatenates 21 legacy + 48 reconstructed records and averages their stored recall values. This preserved the old control exactly, but it means an unqualified `Recall@K` is not a clean semantic primitive for future benchmark decisions.

**Recommendation:** retain old metric fields only for historical reproducibility. In Headless vNext, do not use an unqualified `Recall@K` or `MRR@20` as the primary label.

---

## 3. Current vs proposed metrics

| Concern | Current | Headless vNext recommendation |
|---|---|---|
| Correct video found | Standardized only in some legacy TRAKE diagnostics; not a uniform all-task headline | `video_R@1`, `video_R@5`, `video_R@20`, `video_MRR@20`, `first_correct_video_rank` |
| Correct semantic range exposed | Reconstructed `Recall@K` combines video + range; legacy semantics vary by task | `range_R@1`, `range_R@5`, `range_R@20`, `range_MRR@20`, `first_range_valid_rank` |
| Localization conditional on video | Must be inferred manually | `video_found_but_range_missed@K` + aggregate conditional success/miss rate |
| How far localization missed | Legacy has ad-hoc nearest-gold diagnostics; reconstructed headline has no standardized distance | Two explicit distances: first correct-video result and nearest correct-video result within top K; seconds + frames when reliable |
| Missing correct video vs bad localization | Currently conflated in reconstructed miss | Separate status; distance is null for `no_correct_video_in_topK` |
| TRAKE multi-event | Legacy fractional event candidate coverage; reconstructed rows flattened to query-level `any` ranges | Event-specific coverage/all-events/optional ordered success only for event-scoreable truth |
| QA | Evidence retrieval; no answer correctness | Keep video/range retrieval in Headless; optional answer evaluator is separate and never folded into retrieval recall |
| Generic `Recall@K` | Semantically overloaded | Deprecate as a vNext headline; preserve only as frozen legacy compatibility output |

---

## 4. Exact vNext definitions

### 4.1 Notation

For a scoreable query `q`:

- `V(q)` = accepted correct video set.
- `I(q, v)` = accepted semantic intervals for correct video `v`, each interval `[a_j, b_j]`, inclusive.
- ranked results are `r_1 ... r_N`.
- each result has video `v_i` and either:
  - a point/frame `f_i`; or
  - an explicit segment `[s_i, e_i]`.

If a future query legitimately has multiple correct videos, intervals are associated with the relevant video. Current accepted reconstructed rows effectively have one accepted video each.

### 4.2 Video retrieval

For `K in {1,5,20}`:

`video_hit@K(q) = 1` iff there exists `i <= K` with `v_i in V(q)`.

`first_correct_video_rank(q) = min{i | v_i in V(q)}`, else null within the stored ranking.

`video_R@K = mean(video_hit@K(q))` over **video-scoreable** rows only.

`video_MRR@20 = mean(1 / first_correct_video_rank)` when the rank is <=20, else 0, over video-scoreable rows.

**Why:** this measures whether retrieval found the right source video independently of whether the returned temporal candidate was useful.

### 4.3 Semantic range exposure

A point result matches a range iff:

- `v_i in V(q)`; and
- there exists `[a,b] in I(q,v_i)` with `a <= f_i <= b`.

An explicit segment result matches a range iff:

- `v_i in V(q)`; and
- there exists `[a,b] in I(q,v_i)` with `s_i <= b` and `e_i >= a`.

For `K in {1,5,20}`:

`range_hit@K(q) = 1` iff any result `i <= K` matches a range.

`first_range_valid_rank(q) = min{i | r_i range-matches q}`, else null.

`range_R@K = mean(range_hit@K(q))` over **range-scoreable** rows only.

`range_MRR@20 = mean(1 / first_range_valid_rank)` when rank <=20, else 0, over range-scoreable rows.

This remains an end-to-end retrieval + localization metric, but unlike today's generic recall its name makes the semantic contract explicit.

### 4.4 Conditional localization bridge

For range-scoreable rows:

`video_found_but_range_missed@K(q) = 1` iff `video_hit@K(q)=1` and `range_hit@K(q)=0`.

Report both:

- `% of all range-scoreable rows with video found but range missed @K`;
- `range_success_given_video@K = sum(range_hit@K) / sum(video_hit@K)` over range-scoreable rows where a correct video is present.

The second number directly describes localization quality **conditional on video retrieval**. It must show its denominator (`video_found_n`) because it is not a fixed-denominator recall metric.

### 4.5 Distance to nearest accepted range

Distance is defined only for a result in an accepted correct video and only when temporal coordinates are measurable.

For point `f` and interval `[a,b]`:

`d_point(f,[a,b]) = 0` if `a <= f <= b`; otherwise `a-f` if `f<a`; otherwise `f-b`.

For result segment `[s,e]` and interval `[a,b]`:

`d_segment([s,e],[a,b]) = max(a-e, s-b, 0)`.

For multiple accepted intervals, take the minimum distance over intervals belonging to that result's accepted video.

Report two distinct query diagnostics:

1. **`first_correct_video_distance_to_range`** — distance for the best-ranked result whose video is correct. This answers: *after the system first identifies the correct video, how wrong is its first temporal candidate?*
2. **`nearest_correct_video_distance_to_range@K`** — minimum distance among all correct-video results in top K, with the rank of the result attaining that minimum. This answers: *does top K contain a good localization candidate even if ranking is poor?*

Tie on minimum distance: choose the lowest rank for the recorded `nearest_*_rank`.

#### Missing-video rule

If no correct video occurs in top K:

```text
status = no_correct_video_in_topK
distance_frames = null
distance_s = null
```

Do **not** use infinity, a sentinel giant number, video duration, or an arbitrary penalty. A missing video is a retrieval failure, not a localization error.

If a correct video exists but the result has no trustworthy temporal coordinate:

```text
status = temporal_coordinate_unmeasurable
distance_frames = null
distance_s = null
```

#### Frames and seconds

- Report native frame distance when frame coordinates are reliable.
- Report seconds when accepted time intervals are present or frame→time conversion uses a reliable per-video FPS mapping.
- Preserve the coordinate provenance (`native`, `fps_converted`, `projected`) rather than implying false precision.

#### Aggregate distance summaries

For each distance variant report:

- `n_measured`;
- p50/median;
- p90;
- optional min/max for diagnostics;
- separate frame and second summaries with their own measurable `n`.

Do not invent a benchmark pass/fail tolerance such as ±5 or ±12 frames. If a future report shows `hit_within_X`, `X` must be explicitly labeled as a descriptive diagnostic chosen for that report, not contest truth.

### 4.6 Rank-gap and crowding diagnostics

When both ranks exist:

`video_to_range_rank_delta = first_range_valid_rank - first_correct_video_rank`.

It is always >=0 because a range-valid result is necessarily in a correct video.

Also record:

- `slots_before_first_range_hit = first_range_valid_rank - 1`;
- `correct_video_out_of_range_slots_before_first_range_hit` = count of earlier result slots that are in an accepted video but miss every accepted range.

If the correct video is found but there is no range hit within K, report the latter count over top K and mark `censored_at_K: true` instead of pretending a later range-valid rank is known.

This directly measures a common operator burden: the system knows the video but crowds top ranks with temporally wrong candidates.

---

## 5. Worked scoring examples

The examples below intentionally distinguish frozen legacy behavior from reconstructed behavior. “Legacy” is not one uniform matcher; task type matters.

### A. Correct video + point inside accepted range

Truth: video `V1`, accepted interval `[100,200]`. Rank 2 result = `V1#150`.

- **Legacy TKIS:** hit. TKIS interval membership is inclusive.
- **Reconstructed:** hit. Correct normalized video + point inside any reviewed interval.
- **vNext:** `video_R@5=1`, `range_R@5=1`; both distances are 0 if rank 2 is the first correct-video result.

### B. Correct video + point just outside accepted range

Truth: `V1`, interval `[100,200]`. Result = `V1#201`.

- **Legacy TKIS:** miss: it is outside the interval.
- **Legacy point-target caveat:** a point-target QA/TRAKE case is different; the frozen legacy output uses a 2-second retrieval-point tolerance, so a point slightly away from an exact point may still count. Do not generalize TKIS interval behavior to legacy point truth.
- **Reconstructed:** miss. There is no implicit ±N frame allowance around reviewed intervals.
- **vNext:** video hit = 1, range hit = 0, distance = 1 frame (and seconds if conversion is reliable).

### C. Correct video appears at rank K but every returned frame is far from the accepted range

Truth: `V1`, `[100,200]`; top-20 contains `V1#900`, `V1#1200`, no in-range result.

- **Legacy interval/point headline:** miss for temporal truth. For TRAKE, the task-specific video diagnostic can still be a video hit while event coverage misses; Issue #58 `p1_q16` demonstrates this shape with correct video rank 7 and zero event-candidate coverage.
- **Reconstructed:** miss; current generic recall cannot tell this apart from “wrong video never found.”
- **vNext:** `video_R@20=1`, `range_R@20=0`, `video_found_but_range_missed@20=1`; numeric distance is measured from correct-video candidates.

### D. Wrong video with a visually/semantically similar frame

Truth video `V1`; rank 1 result `V9#150` looks semantically perfect.

- **Legacy:** miss. Accepted video identity is part of truth.
- **Reconstructed:** miss before temporal matching because normalized video differs.
- **vNext:** video hit/range hit are both 0 unless a correct-video result appears later. Distance is not computed for the wrong-video result.

### E. Returned explicit segment overlaps accepted range

Truth `V1:[100,200]`; result segment `V1:[50,100]`.

- **Legacy frozen Issue #58 result surface:** explicit segment results are not established as a scored input shape by the audited frozen output; the preserved ranked candidates are points/timeline frames. Therefore this case is **not a proven legacy scoring surface**, not something to silently label hit or miss.
- **Reconstructed pure scorer:** hit; endpoint overlap is inclusive and deterministic tests cover it.
- **Stage B counted run caveat:** counted runtime emitted point/timeline frames, so segment overlap support was present but not exercised in that run.
- **vNext:** range hit, distance 0.

### F. Multiple accepted intervals

Truth `V1` with alternatives `[100,150]` and `[500,550]`; result `V1#520`.

- **Legacy `target_mode=any` group semantics:** an alternative accepted group can satisfy the record. This is distinct from `target_mode=events`, where targets are not alternatives.
- **Reconstructed:** hit; any reviewed interval may satisfy the record.
- **vNext:** range hit; matched interval ID should be preserved for auditability.

### G. TRAKE with multiple ordered events

Query has E1, E2, E3.

- **Legacy:** `target_mode=events` tracks event candidate ranks separately and may produce fractional recall. `p1_q14` has event ranks `[3,7,null,null]` and R@20=0.5. The frozen surface does not establish full ordered-event success; localization status remains not implemented.
- **Reconstructed:** current Stage B converts reviewed ranges into `target_mode=any`. This can flatten a TRAKE query: one accepted range is enough to mark the whole query hit. `final_round1_10_4of13::p1-16` is an especially important warning: its truth contains a broad continuous performance range plus narrower windows, while its provenance explicitly says event-to-range mapping is not semantic.
- **vNext:** query-level video/range metrics remain valid, but event coverage/all-events/ordered-event metrics are scoreable only when structured event truth exists.

### H. QA retrieval exposes the evidence but does not generate the answer

QA evidence is in `V1` around the accepted point/range; retrieval finds it.

- **Legacy QA:** retrieval/evidence hit. Issue #58 stores an answer string but does not grade generated answer correctness.
- **Reconstructed QA:** range hit if the point/timeline frame exposes the reviewed semantic interval; no generated answer is graded.
- **vNext:** video/range retrieval can pass while `qa_answer.status = not_evaluated`. A future answer evaluator must be reported separately.

---

## 6. TRAKE vNext contract

### 6.1 Do not flatten event truth into ordinary KIS when event semantics are actually available

A TRAKE row may have `m` events. Event truth should be structured as:

```json
{
  "events": [
    {
      "event_id": "E1",
      "accepted_video_ids": ["Lxx_Vyyy"],
      "accepted_ranges": [{"start_frame": 100, "end_frame": 180}],
      "order_index": 1
    }
  ]
}
```

`accepted_ranges` are semantic event regions, not speculative organizer ±N windows.

### 6.2 Metrics

For event-scoreable TRAKE rows:

- `video_R@K`: ordinary query-level correct-video recall.
- `event_exposed(e,K)`: any top-K result matches event `e`'s accepted video/range.
- `event_coverage@K(q) = (# exposed events) / m`.
- `all_events_covered@K(q) = 1` iff every required event is exposed.
- per-event `distance_to_event_range` using the same point/segment distance definition.

### 6.3 Ordered-event success

Only compute an ordered metric if truth explicitly says order is meaningful and event-to-range identity is validated.

Recommended definition:

`ordered_all_events_covered@K = 1` iff there exists one top-K matching candidate per required event such that the chosen candidates' **media timestamps** respect the required event order.

Search rank order is irrelevant; relevance ranking is not temporal order.

If event identity/order is not validated:

```text
event_scoreable = false
ordered_event_scoreable = false
reason = missing_structured_event_truth
```

### 6.4 Current reconstructed TRAKE status

P0/P1 contain four accepted reconstructed TRAKE-labeled rows (P0: 3; P1: 1), but Stage B stores them as query-level reviewed ranges and executes them with `target_mode=any`. The frozen truth schema has no structured event IDs/order mapping. At least `final_round1_10_4of13::p1-16` explicitly warns that event-to-range mapping is not semantic.

**Recommendation:** treat these four as **video-scoreable and range-scoreable but not yet event-scoreable** for vNext. Do not invent event identities from range ordering. A later bounded truth audit may promote individual rows to event-scoreable if the source evidence supports it.

This preserves Minh's accepted policy: semantic event/segment exposure is primary; frame-perfect tolerance is not required.

---

## 7. QA boundary

Headless retrieval should continue to score QA rows for **evidence exposure**:

- video metrics if correct evidence video truth exists;
- range metrics if accepted evidence interval truth exists.

A future answer-generation evaluator is reasonable, but it must be separate, for example:

```text
retrieval.video_R@K
retrieval.range_R@K
qa_answer.status = not_evaluated | evaluated
qa_answer.<future_metric> = ...
```

Do not average QA answer correctness into retrieval `video_R`, `range_R`, or MRR.

**Recommendation:** do not define exact answer-accuracy normalization in Issue #75. QA answers include heterogeneous numeric/textual/free-form targets; answer normalization deserves its own explicit contract if/when an answer generator becomes a benchmark surface.

---

## 8. Corpus / denominator inventory

### 8.1 Definitions

- **source-row count:** literal questions in the source inventory, whether or not benchmark truth is usable.
- **video-scoreable:** accepted correct-video identity exists.
- **range-scoreable:** accepted semantic **interval** truth exists. Do not silently convert legacy point truth into ranges.
- **event-scoreable:** structured event-specific truth exists, including event identity; merely having `task_type=trake` is insufficient.
- **benchmark execution count:** rows actually sent through retrieval in a specific suite/run. This is not automatically equal to every metric denominator.

### 8.2 Current inventory

| corpus | source rows by task | source rows | current video-scoreable | current range-scoreable | current event-scoreable | current relevant execution count | notes |
|---|---|---:|---:|---:|---:|---:|---|
| Legacy Issue #58 | 17 TKIS, 2 QA, 3 TRAKE | 22 | 21 | 16 TKIS interval rows | 3 TRAKE rows | 21 | excluded `p1_q22`; QA/TRAKE use point/event truth, not accepted semantic intervals |
| P0/testing ~8.8 | 18 KIS, 3 QA, 3 TRAKE | 24 | 23 | 23 | 0 under proposed structured-event contract | 23 in Issue #63 Stage B | one KIS row `testing88_submission633::p1-21` excluded/missing video |
| P1/actual Round 1 ~10.4 | 20 KIS, 4 QA, 1 TRAKE | 25 | 25 | 25 | 0 under proposed structured-event contract | 25 in Issue #63 Stage B | all 25 accepted reconstructed rows |
| P2 | 19 KIS, 9 QA, 2 TRAKE | 30 | 0 validated | 0 validated | 0 validated | 0 validated | official query text only; Minh has not validated benchmark truth |

Useful totals:

- P0+P1 source inventory = `24 + 25 = 49` questions.
- Accepted reconstructed scoreable rows = `23 + 25 = 48`.
- Legacy + reconstructed accepted execution in Issue #63 Stage B = `21 + 48 = 69`.
- P0+P1+P2 source inventory = `24 + 25 + 30 = 79`.
- `48 + 30 = 78` is only a **possible future executable count** if all 30 P2 rows become eligible while the one P0 row remains excluded.
- P2 eligibility is not established, so 78 is **not** a validated denominator today.

### 8.3 Why “range-scoreable” differs from “video-scoreable” for legacy

Legacy QA and TRAKE rows have useful point/event truth and can continue to be evaluated under the frozen legacy contract. Issue #75's proposed `range_R` specifically means accepted semantic interval exposure. Recasting legacy points as zero-width or invented semantic ranges would change truth semantics, so the proposal does not do that.

If a later owner-approved annotation converts a legacy point to a genuine semantic interval, that row may then enter the vNext range denominator with new provenance; the frozen legacy control remains untouched.

---

## 9. Proposed per-query result schema

Illustrative schema; field names below are the proposed contract, not implemented code.

```json
{
  "schema_version": "headless-vnext-proposal-1",
  "query_id": "canonical-source-qualified-id",
  "raw_query_id": "p1-16",
  "canonical_round": "p0|p1|p2|legacy",
  "source_id": "...",
  "task_type": "kis|tkis|qa|trake",
  "truth_tier": "...",
  "scoreability": {
    "video": true,
    "range": true,
    "event": false,
    "qa_answer": false,
    "reason": null
  },
  "truth": {
    "accepted_videos": ["L24_V024"],
    "accepted_ranges": [
      {
        "range_id": "R1",
        "video_id": "L24_V024",
        "start_frame": 8550,
        "end_frame": 11700,
        "start_s": 285.0,
        "end_s": 390.0,
        "coordinate_provenance": "fps_projected"
      }
    ],
    "events": null
  },
  "ranking_depth": 20,
  "video": {
    "first_correct_video_rank": 3,
    "hit_at_1": false,
    "hit_at_5": true,
    "hit_at_20": true,
    "mrr_contribution_at_20": 0.333333
  },
  "range": {
    "first_range_valid_rank": 7,
    "hit_at_1": false,
    "hit_at_5": false,
    "hit_at_20": true,
    "mrr_contribution_at_20": 0.142857
  },
  "localization": {
    "first_correct_video": {
      "status": "measured",
      "rank": 3,
      "distance_frames": 250,
      "distance_s": 10.0
    },
    "nearest_correct_video_at_20": {
      "status": "measured",
      "rank": 7,
      "distance_frames": 0,
      "distance_s": 0.0
    }
  },
  "bridge": {
    "video_found_but_range_missed_at_5": true,
    "video_to_range_rank_delta": 4,
    "slots_before_first_range_hit": 6,
    "correct_video_out_of_range_slots_before_first_range_hit": 2,
    "censored_at_20": false
  },
  "trake": {
    "event_scoreable": false,
    "event_coverage_at_20": null,
    "all_events_covered_at_20": null,
    "ordered_all_events_covered_at_20": null,
    "reason": "missing_structured_event_truth"
  },
  "qa_answer": {
    "status": "not_evaluated"
  },
  "latency_ms": 1234.5,
  "results": [
    {
      "rank": 1,
      "video_id": "...",
      "frame_id": 123,
      "start_frame": null,
      "end_frame": null,
      "video_match": false,
      "range_match": false,
      "matched_range_id": null,
      "distance_to_nearest_range_frames": null,
      "distance_to_nearest_range_s": null,
      "scores": {}
    }
  ]
}
```

Result-level flags should be retained so every aggregate metric can be recomputed from the packet without rerunning retrieval.

---

## 10. Proposed aggregate summary schema

```json
{
  "schema_version": "headless-vnext-summary-proposal-1",
  "suite_id": "headless-main-vnext",
  "counts": {
    "source_rows": 49,
    "executed_rows": 48,
    "video_denominator": 48,
    "range_denominator": 48,
    "event_denominator": 0,
    "qa_answer_denominator": 0,
    "excluded": 1
  },
  "video": {
    "R@1": 0.0,
    "R@5": 0.0,
    "R@20": 0.0,
    "MRR@20": 0.0,
    "median_first_correct_video_rank": null
  },
  "range": {
    "R@1": 0.0,
    "R@5": 0.0,
    "R@20": 0.0,
    "MRR@20": 0.0,
    "median_first_range_valid_rank": null
  },
  "bridge": {
    "video_found_but_range_missed_rate@5": 0.0,
    "video_found_but_range_missed_rate@20": 0.0,
    "range_success_given_video@5": {"value": 0.0, "video_found_n": 0},
    "range_success_given_video@20": {"value": 0.0, "video_found_n": 0},
    "video_to_range_rank_delta": {"n": 0, "p50": null, "p90": null},
    "correct_video_out_of_range_slots_before_first_range_hit": {"n": 0, "p50": null, "p90": null}
  },
  "distance": {
    "first_correct_video_to_range_s": {"n_measured": 0, "p50": null, "p90": null},
    "nearest_correct_video_to_range_at_20_s": {"n_measured": 0, "p50": null, "p90": null},
    "first_correct_video_to_range_frames": {"n_measured": 0, "p50": null, "p90": null},
    "nearest_correct_video_to_range_at_20_frames": {"n_measured": 0, "p50": null, "p90": null}
  },
  "trake": {
    "event_scoreable_n": 0,
    "mean_event_coverage@20": null,
    "all_events_covered_rate@20": null,
    "ordered_event_scoreable_n": 0,
    "ordered_all_events_covered_rate@20": null
  },
  "qa_answer": {
    "status": "not_part_of_retrieval_benchmark"
  },
  "slices": {
    "canonical_round": {},
    "source": {},
    "task_type": {},
    "truth_tier": {}
  },
  "excluded_rows": [],
  "provenance": {
    "query_manifest_sha256": "...",
    "truth_sha256": "...",
    "code_commit": "...",
    "config_sha256": "...",
    "collection": "...",
    "index_generation": "...",
    "result_sha256": "..."
  }
}
```

Every metric must carry or inherit an explicit denominator. Small-N slices should continue to be flagged.

---

## 11. Future “main” benchmark vs legacy control

### Recommendation

When Minh approves a future main benchmark:

1. Create a **manifest-level** suite `headless-main-vnext` whose primary corpus is the newer canonical P0/P1 accepted truth (currently 48 scoreable rows).
2. Add P2 only after a separate truth-validation gate establishes eligibility.
3. Preserve Issue #58 as `headless-legacy-v1` / historical regression control, referenced by frozen commit/artifact/hash.
4. Publish legacy results alongside main results when regression comparison is useful, but **do not average the legacy 21 into the main vNext headline denominator**.
5. Do not rename/rewrite frozen Issue #58 or Issue #63 evidence merely to make newer naming cleaner. `official-dataset-control#11` should provide canonical P0/P1 aliases/mapping while raw/frozen source IDs remain reproducible.

### Why this is safer

- The legacy 21 and reconstructed corpus do not share identical truth/scoring semantics.
- A frozen separate control retains long-term regression value without contaminating the meaning of the new headline.
- P0/P1/P2 identity can evolve at the manifest layer without mutating historical artifacts.
- The old 69-row combined run remains valid historical evidence; it simply stops being the preferred semantic definition of “main.”

---

## 12. Approval decisions that genuinely require Minh

The implementation should remain stopped until Minh approves these points.

### Decision 1 — metric naming / headline

**Recommendation:** approve `video_R@K` / `video_MRR@20` and `range_R@K` / `range_MRR@20` as the two primary retrieval families; deprecate unqualified `Recall@K` / `MRR@20` as vNext headline names.

Strong objection considered: two metric families are less compact. Response: the compact single number is exactly what currently hides the retrieval-vs-localization failure mode; the additional surface is decision-useful rather than cosmetic.

### Decision 2 — distance variants

**Recommendation:** approve **both**:

- distance of the first correct-video result;
- nearest correct-video distance among top K.

They answer different questions: initial operator exposure vs candidate availability/ranking quality.

### Decision 3 — legacy point truth in range denominator

**Recommendation:** do **not** turn legacy QA/TRAKE point truth into semantic ranges by fiat. Keep the frozen legacy scorer for those rows; only 16 legacy TKIS interval rows are naturally range-scoreable under the new interval definition unless new human-reviewed intervals are added later.

### Decision 4 — reconstructed TRAKE event scoreability

**Recommendation:** P0/P1 TRAKE-labeled reconstructed rows remain query-level video/range scoreable but event metrics are N/A until structured event truth is validated. Do not infer event IDs/order from the current list of reviewed ranges.

### Decision 5 — future main/legacy representation

**Recommendation:** `headless-main-vnext` = newer accepted corpus; `headless-legacy-v1` = separately frozen 21-row control. Do not mix their primary denominators.

### Decision 6 — P2

**Recommendation:** no change. P2 remains source-only/unvalidated and excluded. A separate validation decision must precede any P2 benchmark denominator.

### QA answer evaluation

No approval is needed to preserve the current boundary: answer correctness stays out of retrieval metrics. If Minh wants answer generation benchmarked now rather than later, that would require a separate answer-normalization/evaluator contract.

---

## 13. Acceptance check against Issue #75

- [x] Video retrieval failure and localization failure are separately measurable in the proposal.
- [x] Current behavior is grounded in frozen Issue #58 / Issue #63 code, protocol, results, and tests.
- [x] No arbitrary frame tolerance is invented.
- [x] Distance uses null + explicit missing-video status rather than conflating retrieval failure with localization error.
- [x] TRAKE multi-event semantics are explicitly proposed, and current reconstructed event-scoreability limitations are surfaced.
- [x] QA evidence retrieval and answer-generation correctness are separated.
- [x] Legacy/P0/P1/P2 source counts and scoreability are reconciled.
- [x] P2 remains unvalidated and excluded.
- [x] 79 source questions vs possible future 78 executable rows is explained.
- [x] Legacy control preservation is explicitly recommended.
- [x] No benchmark run or implementation/scoring mutation was performed.

---

## 14. Hard stop / exact next action

**STOP HERE.**

Minh must approve or amend:

1. metric names and definitions;
2. denominator rules;
3. TRAKE treatment/event-scoreability rule;
4. main-vs-legacy representation;
5. P2 exclusion/entry rule.

Only after that approval should a separate execution packet modify scorer/manifests or run a large benchmark.
