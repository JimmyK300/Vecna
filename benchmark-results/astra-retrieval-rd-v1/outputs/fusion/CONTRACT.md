# Packet B frozen fusion contract

Implementation is ready; no full-surface fusion result is asserted until the
115-row provider export passes its source replay and identity checks. The
parent scorer supplies the unchanged 113-scoreable mapping after transforms.

## Exact current control

Source: `JimmyK300/Vecna@95d63a6abf10c598e0e54af7d2071bedbe542d1e`,
`aic51-src/aic51/packages/search/searcher.py`, Git blob
`10b4e62ea7a9ea7762a44dbe4a5602ae1a15cffd`, SHA256
`6f94bdd147c4b2b29b522a1f4bbbf004fb726fdfdf68a7cb316a4aec9e869e51`.

For each frame, main sums the available raw visual scores **before** max
scaling their joint bucket. Text first max-scales sparse and dense scores
independently, blends them with the configured alpha, then max-scales the
blended modality again. The final score is the weighted sum of visual/OCR/ASR.
Max scaling divides by the maximum if positive, otherwise assigns zero;
negative cosine scores remain negative when the maximum is positive.
The misleading min-max description in `docs/searcher.md` is not code authority.

Main sorts by descending unrounded score, stably over a Python set iteration.
Its tie order can vary across processes. The collector exports that exact
pre-sort order and all five arms reuse it; no frame-ID tie-break is substituted.
Provider ranks retain their original order, including tied provider scores.

Public `_advance_search` requests at least 200 visual candidates and performs
segment diversification. This experiment instead calls `_similarity_search`
directly with the unchanged full canonical text and bounds every raw provider
request to 100. Native quote stripping, exact-phrase eligibility and 1.5 boost
remain intact. Native text request sizes (200 or 500) are recorded alongside the
effective cap. Thus this is **the exact main fusion transform on a frozen
top100 raw-provider surface**, not a claim to reproduce historical UI output.
Quote filters can leave fewer than 100 eligible text hits.

Every arm sorts the same eligible frame union, takes the first 100 frames,
then retains the first occurrence of each video. It does not accumulate scores
from different frames into one video. Frame flooding therefore remains visible.
Raw duplicate frame hits within a provider fail closed rather than silently
receiving extra votes; this harness does not claim support for such malformed
provider lists, although main would sum them.

## Frozen comparison

Outer weights visual/OCR/ASR = 0.5/0.25/0.25 come from the archived P3
`all_fusion_v1.run.json` (blob `c63d742d2132458556d2b6f995fdc53d27cce152`).
That artifact omits text alphas. The experiment explicitly adopts current main
defaults alpha=0 before collection; it does not infer historical hidden values.
The primary surface therefore has four active providers; both dense states are
explicitly disabled. Six active providers require separately established
weights/alphas and a new predeclaration.

Alternative transforms operate on individual providers with fixed nominal
weights 0.25 each for Qwen, SigLIP, OCR sparse, ASR sparse. Equal visual shares
follow the declared #64 experimental donor path, not an assertion that #64 was
merged. Missing providers never trigger weight renormalization. Main's nested
normalization induces different effective coefficients; this distinction is
preserved and disclosed rather than calling its control a flat weighted sum.

- RRF: weighted `1/(60+rank)`; k=60 is inherited from the dataset candidate script.
- Min-max: `(score-min)/(max-min)`; a nonempty equal-score list contributes 1.
- Robust: median, `1.4826*MAD`, clip z to ±6, sigmoid. Zero MAD falls back to
  maximum absolute deviation; an all-equal list contributes 0.5.
- Softmax: one fixed global temperature 1.0, stable maximum subtraction. The
  resulting relative mass is not calibrated confidence or cross-entropy.

## Collection and replay

`frozen_config.json` binds the exact canonical ID/text-hash projection; no truth
fields enter `queries.jsonl`. Query expansion, translation, reranking, YOLO,
temporal parsing and segment clustering are off. The collector imports the
inspected main source from an isolated checkout and builds a Searcher with
`__new__` and a search-only database adapter. It never constructs MilvusDatabase
or creates, inserts, loads, releases, reindexes or embeds the corpus. A missing
collection, wrong row count, file/Lite database URI, unknown tokenizer identity,
failed active provider or source parity mismatch stops collection.

Run identity binds exact loaded weights, tokenizer/processor configuration,
model and helper source/package identities, collection/index descriptions,
config, canonical projection and collector code. Offline execution requires a
completed collector manifest and exact rankings/query hashes; mixed runs fail.
Provider states remain `ok`, `empty`, `disabled`, `unavailable`, `failed` or
`not_attempted` where applicable. Failed active providers cannot masquerade as
empty inputs. CPU and wall timing are separate; replay verification is outside
the measured fusion section. Collection wall time includes instrumentation.

Older `unknown-query-candidate-generation-v0` artifacts cover 97 unknown queries
and 966 formulation lists, not this frozen 115-query/full-canonical-text surface.
P3 `all_fusion_v1` covers 36 rows and contains already-fused output. Neither can
silently supply the missing current raw provider lists or the full denominator.

Validation: `python -m unittest discover -s tests -p test_fusion_study.py -v`.
Tests execute extracted functions from the exact main source for independent
parity, including mixed dense/sparse text and quotes; they also cover state/hash
gates, ties, truncation, negative scores, tokenizer identity and run mixing.
