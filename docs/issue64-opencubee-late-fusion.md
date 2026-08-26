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

## Mapping into Vecna

Current Vecna's `_similarity_search` loops over selected visual target features, sums their raw distances into one `clip_raw_scores` map, then normalizes that aggregate as one visual channel before combining it with OCR/ASR.

The donor experiment instead preserves each visual model as an explicit arm until the late-fusion boundary. To preserve Vecna's existing outer channel contract, the experimental adapter fuses each model's **existing Vecna-normalized visual score** with equal active-model weights, then applies the unchanged Vecna visual/OCR/ASR outer weights. OCR and ASR each execute once; they are not re-fused per visual model.

This is an adaptation of the OpenCubee late-fusion pattern, not a claim that Vecna copied OpenCubee's entire scoring stack byte-for-byte.

## Browser implementation

Branch: `btl/issue-64-opencubee-late-fusion`

Added:

- `aic51-src/aic51/packages/search/experimental_fusion.py`
  - pure donor late-fusion helper;
  - deterministic frame-ID tie break;
  - active-model weight normalization;
  - donor identity embedded in experimental output metadata;
  - exact `legacy` switch returns the original legacy result sequence unchanged.
- `aic51-src/aic51/packages/search/experimental_searcher.py`
  - default-off `OpenCubeeFusionSearcher` subclass;
  - reuses production component retrieval through `super()._similarity_search`;
  - visual models run as isolated visual-only arms;
  - OCR and ASR run once each through existing Vecna logic;
  - only visual model fusion differs from legacy semantics.
- `aic51-src/tests/test_experimental_fusion.py`
  - weight normalization;
  - inactive/missing model handling;
  - zero contribution for missing candidate;
  - deterministic ties;
  - no input mutation;
  - default-off compatibility;
  - invalid strategy/input rejection.
- `aic51-src/script/run_issue64_opencubee_fusion.py`
  - treats `C:\Users\minhc\Code\Vecna` (or supplied primary root) as a read-only repaired runtime;
  - loads only the experimental files from this worktree into the primary package namespace;
  - swaps the `Searcher` symbol in-memory before importing the primary P20/P21 runner;
  - runs the existing `clip_siglip_qwen_sparse` quality cell unchanged;
  - records primary runtime/config/query hashes and Git state before/after;
  - fails the safety gate if the primary checkout changes.
- `aic51-src/script/evaluate_issue64_opencubee_fusion.py`
  - compares the real legacy and donor headless JSONL runs;
  - validates identical query/ground-truth identity;
  - rejects a legacy arm containing donor markers;
  - requires donor result markers proving the experimental Searcher actually ran;
  - reports R@1/R@5/R@20/MRR, task-type slices, per-query rank deltas, gained/lost top-20 hits, and observed end-to-end latency.
- `docs/issue64-opencubee-late-fusion.md`
  - donor mapping, frozen policy, evidence gate, interpretation and rollback.

No production `Searcher`, config, index schema, frontend, model, corpus, or provenance file is modified by this browser slice.

## Frozen confirmatory policy

Before looking at donor outcomes:

- baseline: current repaired Vecna default headless result arm;
- donor: the same headless quality cell with `OpenCubeeFusionSearcher` injected in-memory;
- visual model weights: equal across active selected visual target features;
- outer weights/config/query truth/index identity: identical to baseline;
- top-k and temporal settings: identical to the current baseline runner;
- reranker: unchanged from the baseline cell (currently default-off for this baseline);
- no post-result weight or donor-logic tuning in Issue #64;
- current Issue #58 benchmark is acceptable if Issue #63 expanded truth is not yet frozen; label the result `pre-expansion`.

## Required local evidence

1. record exact repaired primary HEAD/branch/dirty status, config hashes and index-generation identity;
2. use the existing current/default baseline arm, or rerun it if its runtime identity no longer matches the donor run;
3. run `run_issue64_opencubee_fusion.py --overwrite` from an isolated checkout/worktree of this branch;
4. confirm `primary_unchanged=true` in `issue64-run.json`;
5. run `tests/test_experimental_fusion.py` in the repaired environment;
6. compare legacy vs donor with `evaluate_issue64_opencubee_fusion.py`;
7. preserve both raw JSONL files, runner manifests, A/B summary and exact hashes together.

The donor runner itself produces real end-to-end query latency, so latency can be compared against an identity-matched legacy run. Do not compare latency across materially different runtime/config/dirty states.

## Acceptance interpretation

### `REJECT_DONOR`

Use if donor fusion materially worsens retrieval, loses important top-20 hits, or only helps by requiring result-dependent weight tuning.

### `KEEP_EXPERIMENTAL`

Use if evidence is mixed/underpowered, if quality moves little, or if a possible gain remains confounded by runtime identity. Keep the helper/harness available but do not wire production.

### `PROMOTE_CANDIDATE`

Use only if the frozen donor arm produces a material retrieval improvement with no important regression and acceptable identity-matched runtime overhead. Promotion must be a new bounded integration target; Issue #64 itself does not silently change production defaults.

## Provenance / traceability rule

The experimental donor changes ranking composition, so any future production integration must make the fusion strategy and material model weights part of `ServingComposition` identity. The current experimental result carries donor markers in its score diagnostics and a separate run manifest; it must not be presented as ordinary production search without that qualification.

## Rollback

Current rollback is trivial: remove the six Issue #64 experimental files/commits. No production behavior, database, index, corpus, or configuration is changed.
