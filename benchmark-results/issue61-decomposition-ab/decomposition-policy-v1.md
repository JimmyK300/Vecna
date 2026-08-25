# Issue #61 frozen decomposition policy — `issue61-decomposition-v1`

**Status: FROZEN at 2026-08-25T18:20:30.000Z (rev 1) — before any Arm A/B confirmatory scoring of this experiment.**

Machine-readable source of truth: `decomposition-policy-v1.json` (sha256 recorded in
`policy-freeze.json`; the harness aborts unless the hash matches at run time).

> Rev 1 (pre-scoring, zero search results seen): the freeze dry-run revealed
> `hb.load_cases` drops the declared metadata columns, which would have silenced
> complexity rules C2–C4. Fix: harness joins `evidence_visual`, `evidence_ocr`,
> `evidence_asr`, `semantic_constraint_types`, `temporal_requirement` from the same
> canonical CSV by `query_id`. TRAKE rule kept verbatim-all-event-lines (bilingual
> VI+EN event lines both retained).

Deterministic, rule-based, offline-measurement-only. No LLM calls, no free-form iterative
rewriting, no result-dependent tuning, no production changes.

## Inputs allowed

Original Q0 query text + declared CSV category/modality fields only:
`task_type`, `temporal_requirement`, `semantic_constraint_types`,
`evidence_visual`, `evidence_ocr`, `evidence_asr`, `scoreable`, `evaluation_scope`, `query_mode`.

## 1) Complexity classifier (frozen)

COMPLEX iff any of:

- C1 `task_type ∈ {trake, qa}`
- C2 `temporal_requirement ∈ {exact_boundary_multi_event, ordered_sequence, multi_scene_sequence, long_temporal_relation}`
- C3 ≥ 5 non-empty `;`-separated entries in `semantic_constraint_types`
- C4 `evidence_ocr == strong` or `evidence_asr == strong`

else SIMPLE (single-scene KIS-style: tkis, temporal ∈ {segment, segment_start, video},
no strong OCR/ASR evidence, ≤ 4 constraint types). SIMPLE rows form the
"decomposition adds no value" control group.

Predicted assignment (recorded pre-run): complex = p1_q01, q02, q03, q06, q07(no—see below)…
computed by the harness; the classifier above is the binding rule.

## 2) Fragment derivation (text rules only)

Shared preprocessing: normalize CRLF→LF; split lines; within a line split after `.!?`;
drop META sentences (`ends with ?` OR matches `^(find|hãy tìm|tìm)\s+(the\s+)?(clip|video)\b`
with ≤ 12 words); classify each kept sentence TEXTY iff it contains a digit, a `"`, or ≥ 2
mid-sentence uppercase-initial tokens; else VISUAL.
All fragments sanitized: `/` and `\` → space, whitespace collapsed (keeps every fragment call
on the same similarity code path; Arm A always gets the RAW query).

- **TRAKE** (`task_type=trake`): one event fragment per line matching `^E\d+[:.]` (verbatim,
  label kept); preamble dropped; < 2 events ⇒ generic rule.
- **Generic COMPLEX**: V = join(VISUAL sentences), T = join(TEXTY sentences).
  If OCR or ASR evidence is strong, or task is QA: fragments = [V?, T?].
  Else fragments = [V?] only (tests removing entity/fact clauses on pure visual surfaces).
  Guard: any fragment < 3 words ⇒ identity fallback.
- **SIMPLE (control)**: identity fragment (sanitized full query). Confirmatory Arm B therefore
  replicates Arm A up to whitespace normalization — the gate itself is under test.
  **Pre-declared diagnostic:** forced decomposition via the generic rule is additionally run and
  recorded separately (`armB-diagnostic-simple.jsonl`, excluded from headline deltas).
- **Unscoreable** (p1_q22): run for latency parity, never scored.

## 3) Routing per fragment kind (existing searcher parameters only)

| kind | ocr_weight | asr_weight | surfaces |
|---|---|---|---|
| event / visual | 0.0 | 0.0 | CLIP + SigLIP + Qwen visual only |
| text | 0.25 | 0.25 | baseline weights; OCR/ASR sparse active (visual channel cannot be suppressed via API — recorded approximation) |
| identity | 0.25 | 0.25 | exact Arm A replica |

Every call otherwise identical to Arm A: features CLIP/SigLIP/Qwen, top_k 20, nprobe 32,
temporal_k 2000, max_interval 1000, no translation, rerank OFF.

## 4) Fusion (frozen)

RRF k=60 over per-fragment top-20 lists: `score(d)=Σ 1/(60+rank_f(d))`; dedup by
`(video_id, frame_id)` first-wins with deterministic tie-breaks; truncate to 20; score against
the ORIGINAL case ground truth with the official matcher (`hb.metrics_for_results`).
The original full query is preserved for final evaluation.

## 5) Execution protocol

One discarded warmup call; then per query interleaved Arm A → Arm B → (pre-declared simple
diagnostic) on ONE searcher instance; determinism probe re-runs Arm A for the first two
scoreable queries and compares ranking fingerprints; per-call latencies recorded
(Arm B latency = max fragment latency; sum reported separately; extra_calls = fragments − 1).

## 6) Failure taxonomy on miss (frozen, issue58-compatible)

`correct_result_outside_top20` always on miss; `knowledge_bridge_requires_llm` if
`world_knowledge_bridge` declared; flags: `temporal_understanding_required`,
`poor_frame_sampling` (nearest gold delta > 10 s), `gold_video_absent_from_top20`.

## 7) Recommendation mapping (frozen)

- **no benefit**: complex ΔR@20 ≤ +0.05 and ΔMRR@20 ≤ +0.03, or negative.
- **conditional benefit**: positive gains concentrated in a declared slice without cross-slice harm beyond noise (−0.05 R@20 / −0.03 MRR), or gating needed to avoid simple-control harm.
- **strong benefit**: complex ΔR@20 ≥ +0.15 and ΔMRR@20 ≥ +0.08 with no gated-control harm.

Small n (21 scoreable, provisional GT) caps any recommendation below *strong* from justifying
integration without owner-side ground-truth validation.
