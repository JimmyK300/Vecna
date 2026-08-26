# Issue #68 — OpenCubee sentence-level ASR donor

## Decision target

Determine whether presenting ASR retrieval as **sentence/utterance groups** is a useful operator mode for Vecna, without changing normal multimodal retrieval.

## Donor mapping

Frozen OpenCubee source: `k19tvan/Opencubee2@0412b55a0f9a3c9642805a669efd871fddf3e970`.

The relevant behavior is spread across:

- `src/tools/extract_asr.py`: creates timed sentence records;
- `src/tools/build_scene_frame_mapping.py`: maps one sentence interval to the keyframes inside it;
- `backend/services/search.py::search_semantic_asr_*`: selects the sentence-level mapping/index when `sentence_level=true`;
- `opencubee2-ui/src/App.jsx`: uses the toggle for pure semantic-ASR search and candidate-scoped ASR filtering.

Therefore this donor is **not** defined as a modification to OpenCubee's ordinary visual fusion, and the Vecna experiment must not alter ordinary `search_multimodal` behavior.

## Vecna connection

Vecna's existing WhisperX extractor already produces timed text segments, but the indexed representation projects a segment's text onto multiple keyframes. The #59 TRAKE audit independently found `same-transcript keyframe slot flooding` and proposed `ASR dedup accounting` as a falsifiable follow-up.

The experiment deliberately uses the already-indexed text. No transcription, embedding, index, corpus, or provenance regeneration is permitted.

## Frozen approximation

A first-pass sentence/utterance identity is:

```text
(video_id, lowercase(collapse_whitespace(asr_text)))
```

This is an explicit experimental approximation. It can merge two distinct occurrences of literally identical text in one video. No temporal-gap rule is added because doing so would introduce a second semantic variable.

One depth-1000 `asr_sparse` BM25 exposure is used per frozen query. From that same exposure:

- **Raw arm:** first 20 valid frame hits.
- **Sentence arm:** group all valid depth-1000 hits by the frozen key, score each group by its maximum member BM25 score, retain all member frames, return top 20 groups.

This mirrors OpenCubee's operator-level idea that one semantic ASR unit can map back to multiple keyframes.

## Frozen query and truth sources

Queries: `p1_q02`, `p1_q14`, `p1_q16`, resolved at run time from the accepted repaired runtime's canonical `aic51-src/benchmark/issue34_headless_queries.csv`; exact path and SHA-256 are recorded before search.

Gold event metadata comes from #59 commit `6f81433a437c9aef1fbc86efb8c655199662dcf6`, `benchmark-results/issue59-trake-audit/trake-audit.jsonl`, blob `df52e74211b71e766d79a74f94959aa76c8eeb88`. The same ±2-second event exposure contract is used.

## Measurements

For each query:

- unique sentence identities occupying raw top 20;
- largest repeated-sentence slot count in raw top 20;
- unique videos in both arms;
- first correct-video rank in both arms;
- number and ranks of gold events exposed in both arms;
- sentence-group member counts and exact member frames.

The sentence arm can expose a gold frame through any member of a top-level sentence group. This is intentional: OpenCubee's sentence unit likewise maps one ASR unit to all keyframes in its interval. It should be interpreted as **operator inspection exposure**, not a claim that each member independently earned the top-level score.

## Terminal policy

- `REJECT_DONOR` if flooding is not materially reduced or correct-video/event exposure worsens.
- `KEEP_EXPERIMENTAL` if flooding improves but exposure/inspection value does not materially improve.
- `PROMOTE_CANDIDATE` only if flooding clearly improves while correct-video/event exposure is maintained or improved and the top-level result unit is visibly easier to inspect.

No post-result tuning is allowed inside #68.

## Safety

The experiment branch adds only:

- `aic51-src/aic51/packages/search/experimental_sentence_asr.py`
- `aic51-src/tests/test_experimental_sentence_asr.py`
- `aic51-src/script/run_issue68_sentence_asr.py`
- this document

No existing production file is modified. The runner uses read-only Milvus `search`/count/index metadata and records primary Git/config/collection/index identity before and after.
