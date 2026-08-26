# Issue #64 — OpenCubee donor 1: model-weighted late fusion

## Decision under test

Do **not** migrate Vecna to OpenCubee. Test exactly one donor behavior: OpenCubee's explicit per-model weighted late fusion for visual retrieval.

This slice remains experimental and default-off until the repaired local Vecna stack produces confirmatory evidence.

## Exact donor source

Frozen donor identity:

- repository: `k19tvan/Opencubee2`
- commit: `f8045a6961de65b38436824606b493a12e73f89a`
- implementation: `backend/services/search.py::fuse_results`
- live call site: `backend/api/search.py::_vector_stage`

Observed donor behavior:

1. each configured visual model runs independently and returns its own ranked result list;
2. only models that actually returned results are active in fusion;
3. configured active-model weights are normalized to sum to one;
4. candidates are unioned by frame identity;
5. a model that did not return a candidate contributes zero for that candidate;
6. final score is the weighted sum of model-specific scores;
7. results are sorted by the fused score.

The first Vecna donor adapter intentionally copies **only that late-fusion behavior**. It does not copy Qdrant, Meilisearch, model workers, async orchestration, spatial search, similarity labels, DRES, realtime UI, or other OpenCubee architecture.

## Why this is a meaningful difference from current Vecna

Current Vecna's `_similarity_search` loops over selected visual target features, sums their raw distances into one `clip_raw_scores` map, then normalizes that aggregate as one visual channel before combining it with OCR/ASR.

The donor experiment instead preserves each visual model as an explicit arm until the late-fusion boundary. That makes model contribution auditable and permits a bounded A/B without changing OCR/ASR, indexes, embeddings, or ground truth.

## Browser implementation

Branch: `btl/issue-64-opencubee-late-fusion`

Added:

- `aic51-src/aic51/packages/search/experimental_fusion.py`
  - pure donor adapter;
  - no production import/call site;
  - deterministic frame-ID tie break;
  - donor identity embedded in experimental output metadata;
  - exact `legacy` switch returns the original legacy result sequence unchanged.
- `aic51-src/tests/test_experimental_fusion.py`
  - weight normalization;
  - inactive/missing model handling;
  - zero contribution for missing candidate;
  - deterministic ties;
  - no input mutation;
  - default-off compatibility;
  - invalid strategy/input rejection.
- `aic51-src/script/evaluate_issue64_opencubee_fusion.py`
  - offline confirmatory evaluator over frozen per-model headless JSONL arms;
  - validates identical query/ground-truth identity across arms;
  - validates candidate ground-truth flags do not disagree;
  - freezes weights before scoring;
  - emits raw fused JSONL, run hashes, aggregate metrics, and per-query rank deltas;
  - labels latency as unresolved by offline replay rather than fabricating a production-latency claim.

No production `Searcher`, config, index schema, frontend, model, or corpus file changes in this browser slice.

## Frozen confirmatory policy

Before looking at donor outcomes:

- baseline: current repaired Vecna default headless result arm;
- donor inputs: one headless ranking arm per current visual model (`clip`, `siglip`, `qwen` naming may be mapped to exact local feature names in the run manifest);
- weights: equal `1.0 / 1.0 / 1.0` unless a different policy was already frozen before the first confirmatory run;
- top-k: 20;
- no post-result weight tuning in Issue #64;
- current Issue #58 benchmark is acceptable if Issue #63 expanded truth is not yet frozen; label such a result `pre-expansion`.

Required local evidence:

1. run the repaired local stack and preserve exact commit/status/config/index-generation identity;
2. produce the current/default arm and single-visual-model arms on identical queries/truth/config except the isolated visual target;
3. invoke `evaluate_issue64_opencubee_fusion.py` over those frozen arm files;
4. preserve raw JSONL + summary + run manifest together;
5. run `tests/test_experimental_fusion.py` in the repaired environment;
6. if donor quality is good enough to consider promotion, run a separate runtime microbenchmark before changing production defaults. Offline replay is not latency evidence.

## Acceptance interpretation

### `REJECT_DONOR`

Use if donor fusion materially worsens retrieval, loses important top-20 hits, or only helps by requiring result-dependent weight tuning.

### `KEEP_EXPERIMENTAL`

Use if evidence is mixed/underpowered or quality improves but promotion still lacks runtime/provenance evidence. Keep the helper/harness available but do not wire production.

### `PROMOTE_CANDIDATE`

Use only if the frozen donor arm produces a material retrieval improvement with no important regression and a separate runtime check shows acceptable overhead. Promotion must be a new bounded integration target; Issue #64 itself does not silently change production defaults.

## Provenance / traceability rule

The experimental donor changes ranking composition, so any future production integration must make the fusion strategy and material model weights part of `ServingComposition` identity. Until then, the offline result artifact identifies the strategy and donor source explicitly and must not be presented as a normal production search response.

## Rollback

Current rollback is trivial: delete the three Issue #64 experimental files/commits. No production behavior, database, index, corpus, or configuration was changed.
