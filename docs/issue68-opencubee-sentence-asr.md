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

Therefore this donor is **not** defined as a modification to OpenCubee's ordinary visual fusion, and the Vecna integration must not alter ordinary `search_multimodal` behavior.

## Vecna connection

Vecna's existing WhisperX extractor already produces timed text segments, but the indexed representation projects a segment's text onto multiple keyframes. The #59 TRAKE audit independently found `same-transcript keyframe slot flooding` and proposed `ASR dedup accounting` as a falsifiable follow-up.

The donor deliberately uses the already-indexed text. No transcription, embedding, index, corpus, or provenance regeneration is permitted.

## Frozen approximation

A first-pass sentence/utterance identity is:

```text
(video_id, lowercase(collapse_whitespace(asr_text)))
```

This can merge two distinct occurrences of literally identical text in one video. No temporal-gap rule is added because doing so would introduce a second semantic variable.

One depth-1000 `asr_sparse` BM25 exposure is used. From that same exposure:

- **Raw mode (default):** individual frame hits.
- **Sentence mode (explicit opt-in):** group hits by the frozen key, score each group by its maximum member BM25 score, retain all member frames.

## Frozen evaluation result

Local A/B on the accepted repaired runtime (`fd879fb0529165a441745374ab72244df8aadd5e`) passed the safety gate.

Across `p1_q02`, `p1_q14`, and `p1_q16`:

- raw top-20 slots: 60;
- effective unique sentence units in those raw slots: 4;
- duplicate raw slots removed by grouping: 56;
- raw unique-video exposure: effectively 1 video/query;
- sentence-group mode: 8–9 videos/query;
- correct-video exposure: 0/3 raw → 0/3 grouped;
- ±2s gold-event exposure: 0/12 raw → 0/12 grouped.

Thus grouping **clearly reduced inspection flooding without worsening the measured truth exposure**. It did not prove better relevance, because neither arm found the gold events. Under the frozen Issue #68 policy this earned `PROMOTE_CANDIDATE` as an **operator feature**, not as a new ranking default.

Evidence artifact from the frozen experiment:

`benchmark-results/issue68-sentence-asr/ab.json`

SHA-256:

`F2EAA1A682C621FB05FA0DA5236E4803090A114B85326FCD9A25CFDE33B3C928`

## Promotion implementation

The candidate is exposed as a dedicated operator surface rather than changing the main search route:

- `aic51-src/aic51/packages/search/asr_operator.py`
  - performs one existing ASR BM25 search;
  - raw mode is default;
  - grouped mode reuses the frozen exact-text grouping helper;
  - no Milvus write path.
- `aic51-src/aic51/packages/webui/backend/search_issue68.py`
  - imports the normal search FastAPI app unchanged;
  - registers only `/api/search_asr_operator`;
  - `sentence_level=false` is the API default.
- `aic51-src/aic51/packages/webui/backend/__init__.py`
  - points the search server at the thin extension app so all normal routes remain intact.
- `aic51-src/aic51/packages/webui/frontend/src/routes/AsrSearch.jsx`
  - dedicated `/asr` page;
  - raw-frame mode is visibly the default;
  - sentence grouping is an explicit checkbox;
  - grouped results retain and show all member frame IDs.
- `aic51-src/aic51/packages/webui/frontend/src/main.jsx`
  - registers `/asr` only; existing `/search` and `/similar` routes are unchanged.

## Safety invariants

- `Searcher.search_multimodal` is not modified.
- Existing `/api/search_multimodal` and `/api/search_image` implementations are not modified.
- Main `/search` frontend route is not modified.
- Sentence grouping is structurally unreachable unless `/api/search_asr_operator` is invoked.
- Raw ASR operator mode is the default (`sentence_level=false`).
- No re-transcription, re-embedding, reindexing, corpus mutation, or Milvus write is part of the feature.

## Remaining promotion gate

Before merge/promote to the repaired local line, run:

1. focused tests for the original grouping helper and promoted operator helper;
2. frontend build;
3. one live smoke against the accepted repaired collection showing:
   - `/api/search_asr_operator` raw mode works;
   - `sentence_level=true` returns grouped results with member frames;
   - ordinary `/api/search_multimodal` remains callable and unchanged in behavior for an identity-pinned canary;
   - primary Git/config/collection/index identity is unchanged before/after.

Terminal promotion verdict after that smoke: `PROMOTED` or `BLOCKED`.
