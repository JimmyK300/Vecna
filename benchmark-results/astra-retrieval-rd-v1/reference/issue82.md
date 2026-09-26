# Purpose

Create one **agent-executable research queue** for the highest-value remaining Vecna retrieval work. This is a coordination/tracker issue, **not one giant PR**. Each work packet below is a bounded experiment with its own stop condition and return contract.

The intended executor may be Astra or another strong reasoning/coding agent. The issue is deliberately explicit so the worker should not spend expensive reasoning rediscovering project state, mixing completed experiments together, or silently widening scope.

# Current authoritative state

## Repository/runtime

- Repository: `JimmyK300/Vecna`
- Current `main` inspected when this issue was created: `95d63a6abf10c598e0e54af7d2071bedbe542d1e`.
- Do **not** assume experimental work is merged into `main`; use the exact branch/artifact authority stated by the relevant experiment.

## Evaluation surface

The current cross-round analysis has:

- **115 current queries total**;
- **113 scoreable** under the validated mapping;
- **2 currently unscoreable rows**:
  - `p0_q15` / `query-p0-21-kis`;
  - `p3_q09`.

For benchmark work, preserve the existing query IDs, phase, task type, canonical query text, capability tags, truth provenance/tier, and the documented exclusions. Do not silently change the denominator.

Current supporting repository: `JimmyK300/official-dataset-control`.

## Temporal work already completed

Do not repeat these experiments as open-ended exploration.

### Issue #79 — event decomposition + ordered-chain retrieval

The simple hypothesis that temporal information could be recovered by splitting a full query into event subqueries and stitching independently retrieved static frames was **not supported**.

On the 8 live-complete temporal controls:

- full-query baseline video R@20: `6/8 = 0.75`;
- independent event-max: `4/8 = 0.50`;
- ordered event chain: `0/8`.

The live-complete query IDs preserved by the archived experiment are:

`p0_q22, p0_q23, p0_q24, p1_q25, p2_q29, p2_q30, p3_q21, p3_q34`.

Do not revive event-subquery decomposition as the default query representation unless a later issue introduces genuinely new evidence.

### Issue #81 — explicit temporal representation

Stage 1 (existing-embedding temporal windows) is negative on the same 8 controls:

- baseline video R@20: `6/8`;
- every tested existing-embedding temporal arm: `4/8`.

Stage 2a only tested a **stitched contact sheet** on a very small probe (`p3_q34`) and was inconclusive:

- 3-frame contact sheet: target remained rank 3;
- 5-frame contact sheet: target remained rank 3;
- no top-1 rescue.

The remaining bounded question is whether the exact Qwen model/runtime can use **native ordered multiple-image input** better than a stitched raster. This is Work Packet A below.

## Ground-truth limitation that must remain visible

Six historical TRAKE rows use provisional submission-derived event anchors rather than reviewed ordinary event ranges. Do not convert those anchors into organizer-certified truth or fabricate ordinary range metrics.

# Global invariants for every work packet

1. **Ground truth is scoring-only** unless a packet is explicitly a dataset-truth review.
2. No per-query tuning after observing the answer.
3. Preserve exact input/output/config/code hashes sufficient for rerun.
4. Preserve raw per-query evidence, not only aggregate metrics.
5. Separate:
   - candidate-generation failure;
   - ranking/fusion failure;
   - reranker failure;
   - temporal-localization failure;
   - ground-truth/provenance weakness.
6. Do not equate retrieval scores with calibrated probabilities.
7. Missing/disabled/failed/empty providers must remain distinguishable where the runtime supports that distinction.
8. No model training/fine-tuning in this tracker.
9. No full-corpus re-embedding unless a later separately authorized issue explicitly requires it.
10. No production retrieval mutation while running experiments. Integration comes only after evidence.
11. Do not change canonical query text through LLM expansion, translation, or rewriting in benchmark comparisons unless the packet explicitly tests that transformation.
12. Prefer saved rankings/embeddings and bounded candidate-pool experiments before expensive new inference.

# Execution order

The packets are intentionally separable.

- **Packet 0** is mandatory first and should be cheap.
- **Packet A** can run in parallel with B/C after Packet 0 if local model execution is available.
- **Packets B and C** should reuse saved/provider rankings wherever possible.
- **Packet D** consumes the results of A/B/C and builds one failure ledger.
- **Packet E** is decision preparation only. Do not automatically implement the next architecture.

---

# Packet 0 — authority + reproducibility preflight

## Objective

Produce one small machine-readable manifest proving exactly what benchmark, rankings, model/index surface, and code each later packet will use.

## Tasks

- [ ] Record Vecna base/ref and Git SHA.
- [ ] Record official-dataset-control base/ref and Git SHA.
- [ ] Locate the canonical current 115-query ground-truth/mapping artifact.
- [ ] Verify exactly 113 scoreable IDs and the two documented exclusions.
- [ ] Hash canonical query text and truth inputs.
- [ ] Locate the current frozen Qwen-only top-100 ranking artifact.
- [ ] Locate the current Qwen3-VL reranker top-100/result artifact.
- [ ] Locate any saved per-provider rankings needed for fusion (Qwen, SigLIP, OCR sparse, OCR dense, ASR sparse, ASR dense).
- [ ] If provider rankings are not already saved, document the **smallest deterministic retrieval call** that can regenerate them without reranking/query expansion/translation.
- [ ] Record collection/index identity if resolved, including collection row count and relevant vector/text fields.
- [ ] Record model identifier + exact local snapshot/config hash for any model that will be called.
- [ ] Prove query expansion, translation, reranking, YOLO text-path transformations, and other non-target behavior are OFF for frozen baseline calls.
- [ ] Write one `control_manifest.json` / equivalent that later packets consume instead of rediscovering paths independently.

## Acceptance

- [ ] 113/115 mapping reproduces exactly.
- [ ] Every later packet has an immutable path/hash for required inputs.
- [ ] No retrieval result is changed in Packet 0.

## Stop

Stop if current artifacts disagree on query identity, truth identity, collection/index identity, or model loading in a way that makes comparisons non-equivalent. Return the conflict rather than choosing one silently.

---

# Packet A — native ordered multi-image Qwen temporal test

Parent/context: #81.

## Research question

> On the same bounded temporal candidate surface, does presenting 3–5 temporally ordered frames to Qwen as **distinct images** provide temporal ranking/localization signal beyond single-frame and stitched-contact-sheet input?

This is the final cheap multi-frame-Qwen test before considering a true temporal/video model.

## A0 — preflight native multi-image support

- [ ] Recover the exact Qwen model, processor, prompt/scoring path, frame decoder, spacing, and candidate construction used by #81 Stage 2a.
- [ ] Verify from the installed code/runtime that the **same model** accepts multiple distinct images in one example.
- [ ] Run a tiny smoke example and inspect processor/model inputs to prove that 3 images are represented separately rather than concatenated into one raster.
- [ ] Preserve order explicitly: `[past, center, future]` for 3-frame input.
- [ ] Record model snapshot, package versions, device/backend, dtype, processor config, and any input-size transformations.

**Hard stop:** if the exact model/runtime does not genuinely support native multi-image input, return `INCONCLUSIVE_ARCHITECTURE_BLOCKER`. Do not substitute another model and call it the same experiment.

## A1 — freeze candidate pool

Use all 8 established live-complete temporal/TRAKE controls:

`p0_q22, p0_q23, p0_q24, p1_q25, p2_q29, p2_q30, p3_q21, p3_q34`.

Preferred global rule:

- baseline top-10 candidate windows per query;
- no GT-based candidate insertion;
- preserve original baseline rank;
- deterministic existing dedup semantics only.

If top-10 is infeasible, choose one smaller global `N` **before scoring** and record the reason. Never vary N per query.

## A2 — matched representation arms

Evaluate the same full canonical query against the same candidate windows:

1. `single_frame_control`
2. `contact_sheet_3` — matched 3 frames
3. `native_multi_image_3` — primary arm
4. `native_multi_image_5` — only if the 3-image path is valid and compute remains bounded

For 3-frame conditions, use identical actual sampled frames/timestamps in contact-sheet and native-multi-image arms.

Do not run a prompt grid, spacing grid, or per-query prompt adaptation.

## A3 — output per candidate

Preserve at minimum:

- query ID/text hash;
- baseline rank;
- video ID;
- center frame/time;
- exact sampled frame IDs/timestamps in chronological order;
- representation arm;
- raw model output used for ranking;
- transformed ranking score if applicable;
- final rank;
- model/config hash.

## A4 — metrics

Report:

- correct-video presence in frozen pool;
- correct-video rank @1/@3/@5/@10 after reranking;
- TRAKE event exposure/coverage where the current proxy truth mechanically permits it;
- all-events-covered only where meaningful under the frozen scorer;
- correct-video-found-but-event-missed;
- rescue/regression counts versus single-frame and original baseline;
- per-query rank movement.

Do not report ordinary accepted-range metrics for rows that do not have reviewed ordinary ranges.

## A5 — decision gate

Return one of:

- `POSITIVE_TEMPORAL_SIGNAL`: multiple clean temporal rescues / meaningful coverage or ranking gains without broad regressions;
- `NEGATIVE`: flat/worse across the bounded set with no convincing temporal rescue;
- `INCONCLUSIVE`: runtime support or truth quality prevents a fair test.

Do **not** automatically start a video encoder if negative.

---

# Packet B — fusion study: RRF vs normalized score fusion

## Research question

> Given the same provider rankings, is Vecna better served by rank-only fusion (RRF) or by a carefully normalized weighted score sum that preserves strength-of-match information?

This directly addresses the current architectural uncertainty around RRF versus score fusion.

### Terminology rule

Do not call score softmaxing **cross-entropy**. Cross-entropy is a loss/objective. If the intended behavior is “make unusually strong provider scores stand out,” call and implement the transformation explicitly (e.g. softmax/temperature, z-score/sigmoid, etc.).

## B0 — freeze inputs

Preferred provider set when available:

1. Qwen visual
2. SigLIP visual
3. OCR sparse BM25
4. OCR dense BGE-M3
5. ASR sparse BM25
6. ASR dense BGE-M3

Use **identical raw provider result lists** for every fusion arm. No reranker, query expansion, translation, or model change between arms.

Primary provider depth: top-100 per provider. If available cheaply, use top-50 only as a declared truncation-sensitivity check, not as another tuning dimension.

## B1 — preserve current baseline exactly

First implement/replay the exact current frozen Vecna fusion semantics and confirm the saved baseline where possible. This is `fusion_current_control`.

If current semantics cannot be reconstructed exactly from code/config, stop and document the ambiguity before comparing alternatives.

## B2 — comparison arms

At minimum evaluate:

### `fusion_rrf`

Canonical RRF on provider frame/ranking lists, using one fixed `k` inherited from the established project path if one already exists. Do not tune `k` on the 113-query results.

Important: if the canonical project behavior fuses frame hits then collapses to video, preserve that order. Do not sum unrelated frames from one video before the canonical collapse step.

### `fusion_minmax_sum`

For each query/provider list:

- map observed provider scores to `[0,1]` using deterministic min-max normalization over the frozen provider candidate list;
- define behavior for degenerate equal-score lists explicitly;
- use frozen provider weights;
- missing candidate contribution = no contribution, while preserving whether the provider itself was unavailable/failed/empty where possible.

### `fusion_robust_z_sum`

Per query/provider:

- robust-center scores using median;
- robust-scale with MAD or another explicitly documented stable estimator;
- clip extremes with one predeclared global bound;
- map to a bounded monotonic contribution (e.g. sigmoid) before weighted addition.

Purpose: test whether cross-provider scale mismatch, rather than rank fusion itself, is the real problem.

### `fusion_softmax_sum`

Test the “outstanding score should stand out” hypothesis explicitly:

- transform one provider’s frozen score list into a probability-like relative mass using softmax with **one predeclared global temperature**;
- do not call this calibrated probability;
- do not tune temperature query-by-query;
- weighted-add across providers.

If raw provider scores have incompatible orientation/sign conventions, normalize orientation first and document it.

## B3 — weights

Primary comparison should hold weights fixed to an already-declared project configuration so only the **fusion transform** changes.

Do not run a large weight search in this packet.

If evidence strongly suggests weight calibration is the bottleneck, return a separate proposed calibration experiment rather than silently optimizing weights on all 113 queries.

## B4 — candidate semantics

For every arm:

- same provider hits;
- same provider depth;
- same frame/video collapse semantics after fusion;
- same tie-breaking;
- same output K;
- no post-hoc dedup difference unless the arm explicitly tests it.

Preserve provider contribution breakdown for every fused result.

## B5 — evaluation

Use the exact same 113-scoreable surface.

Report:

- video R@1/@5/@10/@20;
- MRR@20;
- median correct rank;
- per-query rank delta;
- rescue/regression matrix versus current fusion and Qwen-only;
- query-category/capability slices;
- OCR-dependent and ASR-dependent slices;
- simple visual versus combined/multimodal slices;
- temporal slice reported separately so temporal ground-truth weakness does not get hidden in aggregate metrics;
- provider contribution/ablation diagnostics;
- latency/CPU cost of fusion itself.

Use paired per-query evidence. Bootstrap confidence intervals or another paired uncertainty summary are desirable; do not overinterpret a one-query aggregate gain.

## B6 — failure diagnostics

For regressions, determine whether the failure comes from:

- normalization dominated by an outlier;
- score compression;
- provider score-scale mismatch;
- weak modality accumulating votes;
- duplicate frames from one video;
- candidate absent from one or more providers;
- rank-only RRF discarding useful score margin;
- score fusion trusting a poorly calibrated provider too strongly.

## B7 — decision output

Return:

- best supported fusion family;
- whether improvement is global or category-specific;
- exact regressions that prevent unconditional integration;
- whether a later weight-calibration issue is justified.

No production change in this packet.

---

# Packet C — Qwen3-VL reranker utility and integration boundary

## Research question

> Does the existing Qwen3-VL reranker add enough value over the frozen Qwen retrieval ranking to justify its latency, and on which query classes does it help or hurt?

Use existing saved artifacts first:

- `qwen_only_top100.jsonl`
- `qwen3_vl_reranker_2b_top100.json`
- `comparison_qwen_vs_reranker.json`

Resolve exact paths/hashes in Packet 0.

## C1 — reproduce current comparison

- [ ] Recompute global baseline/reranker metrics from saved rankings.
- [ ] Verify query join = 113 scoreable rows.
- [ ] Preserve reranker input depth and any candidate truncation.
- [ ] Verify reranker cannot rescue a query whose correct candidate never entered its candidate pool.

## C2 — classify every changed query

For every query whose correct rank changes materially, classify:

- clean rescue;
- clean regression;
- candidate-generation ceiling;
- correct video promoted but wrong temporal moment;
- semantic hard-negative correction;
- visual detail correction;
- OCR/ASR information unavailable to reranker;
- ambiguity/weak truth;
- unresolved.

Preserve representative top candidates and score movement.

## C3 — capability slices

At minimum report reranker deltas for:

- visual object/scene;
- attribute/detail;
- OCR-dependent;
- ASR-dependent;
- combined multimodal;
- temporal/BOUND/TRACK/SEQ;
- hard-negative-heavy queries where tags are available.

## C4 — latency/cost boundary

Measure or recover:

- reranking candidates per query;
- average and p50/p95 reranker latency;
- device/backend;
- model load/warmup versus steady-state cost.

If full latency benchmarking is expensive, use one fixed representative subset and label it as such.

## C5 — integration recommendation

Do not merely report aggregate recall. Answer which of these evidence supports:

1. always-on reranker;
2. conditional reranker for specific query/candidate classes;
3. operator-triggered reranker;
4. keep experimental / insufficient benefit.

Any conditional rule must be based on information available **before seeing ground truth**, not a post-hoc oracle.

No production integration here.

---

# Packet D — unified 113-query failure ledger

## Objective

After A/B/C, create a single query-level ledger that explains **what is actually blocking each remaining miss** instead of opening another model experiment based on intuition.

## Required schema

One row per scoreable query, containing at least:

```json
{
  "query_id": "...",
  "phase": "...",
  "task_type": "...",
  "truth_tier": "...",
  "baseline_rank": null,
  "best_fusion_rank": null,
  "reranker_rank": null,
  "temporal_experiment_status": null,
  "primary_failure": "...",
  "secondary_failures": [],
  "evidence": {},
  "next_smallest_test": "..."
}
```

## Failure taxonomy

Use a controlled vocabulary and expand only when necessary:

- `candidate_generation_missing_video`
- `candidate_generation_missing_event`
- `visual_semantic_confusion`
- `fine_detail_attribute_failure`
- `ocr_extraction_failure`
- `ocr_retrieval_failure`
- `asr_extraction_failure`
- `asr_retrieval_failure`
- `fusion_calibration_failure`
- `fusion_duplicate_flooding`
- `reranker_regression`
- `temporal_representation_failure`
- `temporal_localization_failure`
- `ground_truth_weak_or_provisional`
- `query_ambiguous`
- `unresolved`

## Required report

Produce:

- counts by primary failure;
- counts by query category/capability;
- top recurring failure mechanisms;
- exact queries where fusion rescued but reranker hurt;
- exact queries where reranker rescued but fusion did not;
- exact temporal cases where correct video exists but event evidence remains absent;
- queries whose interpretation is limited mainly by truth quality rather than retrieval.

Do not force every query into a confident diagnosis. `unresolved` with evidence is better than invented certainty.

---

# Packet E — evidence-driven next-step proposal only

Use Packet D to write the next **single smallest valuable experiment**. Do not implement it in this tracker.

Decision examples:

- If native multi-image Qwen is clearly positive: propose a scalable bounded multi-frame reranking path.
- If native multi-image is negative and event evidence remains absent: prepare a Stage-3 comparison of a very small number of true video/temporal encoders; do not run full-corpus encoding.
- If normalized score fusion clearly helps: prepare a separate integration/calibration issue.
- If reranker helps only specific categories: define a GT-blind routing hypothesis before integration.
- If OCR/ASR extraction quality is the dominant blocker: route the problem to `official-dataset-control` rather than adding more Vecna ranking heuristics.

The proposal must cite the failure counts and concrete rescue/regression evidence that justify it.

# Expected artifacts

Names may follow repo convention, but prefer one durable directory such as:

`benchmark-results/astra-retrieval-rd-v1/`

with:

- `control_manifest.json`
- `fusion/`
- `reranker/`
- `temporal-multi-image/`
- `failure_ledger.jsonl`
- `REPORT.md`
- `PROVENANCE.md`
- `BTL-RETURN.md`

Large generated frame/image caches should remain local unless repository convention explicitly allows them; commit manifests/hashes and reproducible generation instructions instead.

# Overall definition of done

This tracker is complete when:

- [ ] Packet 0 freezes reproducible authority.
- [ ] Packet A has a positive/negative/inconclusive native-multi-image result without Stage-3 scope creep.
- [ ] Packet B fairly compares rank fusion and normalized score fusion on identical provider evidence.
- [ ] Packet C explains reranker utility by query class and latency, not just one headline number.
- [ ] Packet D gives a query-level explanation of remaining failures.
- [ ] Packet E proposes exactly one next experiment from evidence.
- [ ] No production retrieval semantics were silently changed.
- [ ] No full-corpus re-embedding/model training occurred.
- [ ] Every result is hash/commit/config reproducible.

# Worker return contract

For each packet, return:

1. **Result** — direct answer to that packet's research question.
2. **Proof** — exact metrics, per-query evidence, tests/commands, hashes.
3. **Uncertainty** — especially provisional temporal truth and candidate truncation.
4. **Work location** — branch/commit/artifact paths.
5. **Scope check** — what was explicitly not changed.
6. **Next state** — `READY_FOR_PARENT_REVIEW`, `BLOCKED`, or `NEEDS_DECISION`.

Do not continue into production integration or a new model family merely because a packet completes.
