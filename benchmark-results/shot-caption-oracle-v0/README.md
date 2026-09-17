# Gemini shot-caption oracle sufficiency v0

Tracker: `JimmyK300/Vecna#95`

## Question

Given a benchmark interval that is already known to contain the needed evidence, can a **query-independent** `gemini-3.8-flash` caption preserve enough literal visual/audio evidence for the corresponding benchmark query to be recoverable later from the caption?

This isolates caption quality from retrieval quality and shot-boundary quality.

## Authority

- Current benchmark authority: Vecna PR #80 / `btl/issue-34-current-115-authority`.
- Canonical surface: 115 rows, 113 scoreable; exclusions `p0_q15`, `p3_q09`.
- Ground-truth projection consumed by this experiment: `benchmark-results/issue34-current-115/ground_truth_current_115.jsonl`.
- Post-caption query decomposition authority: `JimmyK300/official-dataset-control@1f1ad1baef1e1d31817f6c5a12d4d94133611038`, `experiments/temporal-sequence-retrieval-v1/decompositions_113.jsonl`, blob `caf0a7b30a275b9ed47cab354fbb21bda00bf899`.

Truth may select the oracle interval. Query text, query semantics, query atoms, capability labels and accepted answers are forbidden from caption generation.

## Frozen pilot

`pilot_config.json` fixes 30 queries before caption results. The pilot spans visual objects/attributes, actions, fine-grained recognition, counts, spatial relations, OCR, ASR, entities, scenes, sequences, tracking/motion, slides, QA, negation and transient visual events where available.

Caption processing is initially fixed to:

- model: `gemini-3.8-flash`;
- video processing: `static`;
- sampling: `4.0 fps`;
- window: union of legitimate accepted intervals with explicit second offsets;
- prompt families: `dense-natural`, `structured-evidence`, `structured-temporal`.

The first stage is a prompt-family comparison, not a parameter sweep. Window robustness (`exact`, `+2s`, `+5s`) comes only after the prompt is frozen.

## Prompt families

Prompts are hashable files under `prompts/` and are generic across all clips.

1. `dense-natural.txt` — exhaustive literal prose.
2. `structured-evidence.txt` — objects/actions/attributes/counts/spatial/OCR/audio/fine detail/uncertainty.
3. `structured-temporal.txt` — structured evidence plus chronology, start/end state, state changes and transient events.

All three instruct the model to prefer literal evidence over inference and to mark uncertainty instead of guessing.

## Harness

`code/shot_caption_oracle.py` has four stages.

### 1. Build oracle manifest

```bash
python benchmark-results/shot-caption-oracle-v0/code/shot_caption_oracle.py build-manifest
```

Rows without a legitimate single-video interval expressed in seconds are retained as ineligible with a reason; no timestamp is invented.

### 2. Extract exact clips

On the Windows/WSL host where `D:\Official-Dataset` is visible:

```bash
python benchmark-results/shot-caption-oracle-v0/code/shot_caption_oracle.py extract-clips \
  --dataset-root /mnt/d/Official-Dataset
```

Each clip is hashed. The source video, interval and ffmpeg identity are retained.

### 3. Caption

Requires the modern `google-genai` package and `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the process environment.

```bash
python benchmark-results/shot-caption-oracle-v0/code/shot_caption_oracle.py caption \
  --prompt all \
  --model gemini-3.8-flash \
  --fps 4
```

Cache identity is `model + video-processing config + prompt hash + clip hash`. Query text is not loaded by this stage. Each response preserves raw output, parsed JSON where applicable, interaction ID, timing and usage metadata when exposed.

### 4. Freeze post-caption evaluation packets

Only after captions exist:

```bash
python benchmark-results/shot-caption-oracle-v0/code/shot_caption_oracle.py build-eval-packets \
  --decompositions /path/to/decompositions_113.jsonl
```

This is the first stage that joins query text/requirements to the already-frozen caption.

## Evaluation contract

For each existing query requirement, judge caption evidence as one of:

- `SUPPORTED`
- `PARTIAL`
- `MISSING`
- `CONTRADICTED`
- `UNVERIFIABLE`

Primary metrics:

- all-requirements-covered rate;
- atomic requirement recall;
- contradiction/unsupported-claim rate where reviewable;
- exact OCR/text/number/count correctness;
- capability-tag and task-type slices;
- per-query missing-evidence ledger.

A fixed manual subset must audit any LLM-assisted judge. Judge feedback may never be used to regenerate or tune individual captions.

## Current host preflight

A read-only broker preflight on 2026-09-17 established:

- `D:\Official-Dataset` visible from the WSL host path;
- Windows `ffmpeg` available;
- Windows Python launcher available;
- a user-scoped `GEMINI_API_KEY` entry is present.

No credential value was read into the experiment artifacts or printed. No Gemini generation call has been made by this experiment at the time of this checkpoint.

## Scope

- no production retrieval changes;
- no full-corpus Gemini pass;
- no TransNetV2 dependency in this oracle-caption ceiling test;
- no query leakage into caption generation;
- no per-query prompt/window tuning;
- no merge to `main`.
