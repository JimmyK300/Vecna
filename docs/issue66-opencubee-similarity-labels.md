# Issue #66 — OpenCubee donor 2: on-demand similarity labels

## Decision under test

Keep Vecna's normal retrieval unchanged. Test only the OpenCubee operator concept of labeling strong visual near-duplicates as `DUP`, `INTRO`, or `REUSE`.

## Donor source

Frozen OpenCubee source:

- repository: `k19tvan/Opencubee2`
- commit: `0412b55a0f9a3c9642805a669efd871fddf3e970`
- `backend/services/search.py::classify_similarity_match`
- `backend/services/search.py::find_similar_frames`
- supporting full-corpus builder: `src/tools/build_similarity_matrix.py`

OpenCubee's full-corpus builder compares each block against all frames. Vecna does **not** copy that O(N^2) implementation.

## Vecna adaptation

The experiment performs one read-only Milvus cosine lookup for one selected source frame and one explicit visual feature.

Frozen defaults:

- feature: `image_siglip_so400m-384`
- cosine threshold: `0.985`
- result limit: `20`
- nprobe: `32`
- same-video minimum frame gap: `100`
- opening window: first `300` frames

Classification after the threshold gate:

- different video -> `DUP`
- same video, gap < 100 -> hidden temporal neighbour
- same video, sufficient gap, earlier frame <= 300 -> `INTRO`
- same video, sufficient gap, both later -> `REUSE`

The threshold and chosen visual feature are explicit in every result packet. The labels are operator annotations, not calibrated probabilities and not ranking signals.

## Browser implementation

Branch: `btl/issue-66-similarity-labels`

Additive experiment only:

- `aic51-src/aic51/packages/search/experimental_similarity_labels.py`
  - pure identity parser and classifier;
  - one read-only `Searcher.get` + Milvus `search` seam;
  - no write-capable method calls;
  - deterministic result ordering.
- `aic51-src/tests/test_experimental_similarity_labels.py`
  - canonical identity parsing;
  - cross-video DUP;
  - near-neighbour suppression;
  - INTRO;
  - REUSE;
  - self/malformed suppression;
  - threshold filtering and single read-only search call;
  - deterministic tie ordering.
- `aic51-src/script/run_issue66_similarity_labels.py`
  - loads config/Milvus from the repaired local primary checkout;
  - loads only the experimental helper from the isolated worktree;
  - does not instantiate embedding models;
  - supports exact source frame IDs and deterministic video-prefix samples;
  - records primary Git/config/collection/index state before and after;
  - fails if primary state changes;
  - writes only to the experiment worktree.

No production Searcher, backend route, frontend, config, index, corpus, or provenance file is changed in this experiment.

## Why API/UI integration is not in the first slice

The useful question is first whether the strict donor semantics produce meaningful annotations on Vecna's real vectors at all. Wiring a new route/UI before that evidence would create product surface around an unvalidated threshold.

If the live smoke produces useful labels without false-positive-looking floods, promotion may add a small read-only backend endpoint and consume it from Vecna's existing similarity-search UI. If the smoke is empty or obviously noisy, reject or keep the helper experimental without adding UI.

## Required local evidence

Run the experimental tests and a read-only smoke against the accepted repaired collection.

The smoke should sample a mix of early/mid/late frames across several videos, including at least some videos likely to contain broadcast intros or repeated footage. Preserve:

- exact primary HEAD/branch/dirty state;
- config hash;
- collection + row count + index set before/after;
- exact source frame IDs;
- feature/threshold/nprobe/gap/window values;
- all returned candidates + cosine scores + labels;
- relation counts;
- `primary_unchanged=true`.

No threshold tuning after seeing the first smoke in Issue #66. If 0.985 is useless, report that honestly; a new threshold study would be a separate decision.

## Interpretation

- `REJECT_DONOR`: labels are misleading/noisy or the concept requires expensive corpus-wide processing.
- `KEEP_EXPERIMENTAL`: mechanics work, but the sample is too small/empty to justify UI integration.
- `PROMOTE_CANDIDATE`: strict threshold produces clearly useful annotations with read-only safety; next bounded slice may wire endpoint/UI without changing ranking.

## Rollback

Delete the three experimental files and this document. No production behavior or data state was changed.
