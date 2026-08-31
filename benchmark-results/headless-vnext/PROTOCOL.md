# Headless vNext scorer protocol — Issue #76

This packet implements the approved Issue #75 metric contract plus Minh's TRAKE amendment. It is a **scoring-only** layer over saved rankings. It does not import or invoke Vecna retrieval/model code.

## Frozen truth and identity

- Issue #63 reconstructed truth: `benchmark-results/issue63-stage-b/reconstructed-truth.json`, SHA-256 `92a4c14cdb075f43a444e7e105cc7680a491188e307cfe2562fff2b51cfe6603`, accepted lineage through `ec4a38d397c9a3a49a821812b37db47f52327049`.
- Issue #75 approved contract commit: `2344023ea4e2a152d1e9dc15778d8feb436dc396`.
- `official-dataset-control` identity commit: `646ec85c75141bb68078fa94ec26b9a1dbef6d04`.
- P0 canonical source `test_round_8_8` maps to immutable Vecna provenance source `testing88_submission633`.
- P1 canonical source `actual_p1_10_4` maps to immutable Vecna provenance source `final_round1_10_4of13`.
- P2 is absent.

`build_headless_vnext_manifest.py` verifies the Issue #63 truth bytes before projecting the accepted 48 rows into the additive vNext manifest. Frozen Issue #63 artifacts are never rewritten. The byte hash above was independently recomputed by the Issue #76 CI checkout; the older Stage-B return text quoted `016e1350…`, but `b1856c6…` and `ec4a38d…` differ only by `BTL-RETURN.md`, so the accepted truth file itself is unchanged across those commits.

## Denominators

- video: 48 rows;
- ordinary semantic range: 44 non-TRAKE rows;
- TRAKE: 4 queries / 15 mechanically recovered submitted event anchors.

A count mismatch is a hard error, not an automatic denominator adjustment.

## TRAKE development proxy

Each submitted event anchor frame `F` yields `[max(0,F-5), F+25]`, inclusive. Tier: `provisional_submission_anchor`. This is development truth only, not organizer GT. The manifest preserves the submitted frame, Issue #63 provenance, proxy distance, and absolute distance to the submitted frame so saved rankings can be rescored after later truth replacement.

TRAKE rows do not enter ordinary `range_R`.

## Saved-ranking input

JSONL (or JSON `queries` list), one query per object. Query identity may be canonical or immutable Vecna provenance. Results live in `results` or Issue-63-compatible `top_results` and contain:

- explicit `rank` when available; rank gaps are preserved rather than compacted;
- `video_id` (or `video`);
- point identity via `frame_id`, `frame`, or `time_line` / `timeline`; and/or
- explicit `start_frame` + `end_frame` segment;
- arbitrary provider/scores/provenance fields are preserved untouched.

The scored JSONL preserves the complete supplied top-K ranking. Duplicate ranks, duplicate query rows, unknown query IDs, or supplying both canonical and provenance aliases for the same query are hard errors.

### Coverage safety

A real benchmark arm is **strictly complete by default**: all 48 manifest queries must have a saved-ranking row. Missing rows raise an error rather than being counted as retrieval misses.

`--allow-partial` exists only for synthetic/debug fixtures. A partial summary is labeled `input_status: partial_fixture` and reports both frozen `manifest_counts` and actual `scored_counts`; subset rows therefore cannot masquerade as a full benchmark denominator.

## Metrics

All 48: `video_R@1/5/20`, `video_MRR@20`, first correct-video rank.

44 non-TRAKE: `range_R@1/5/20`, `range_MRR@20`, first range-valid rank, video-found/range-missed, conditional range success with explicit denominator, first/nearest correct-video distance to range, video→range rank delta, and simple crowding slots before first range hit. Wrong-video-only results have null localization distance with explicit status.

TRAKE: event coverage and all-events-covered at 1/5/20, per-event first hit, distance to proxy window, and absolute submitted-anchor distance. Ordered-event scoring is intentionally omitted from this minimal implementation.

QA answer correctness is not evaluated; `qa_answer.status = not_evaluated`.

## Commands

```bash
python aic51-src/script/build_headless_vnext_manifest.py
python -m unittest discover -s aic51-src/tests -p 'test_headless_vnext.py' -v
# synthetic two-query fixture only
python aic51-src/script/score_headless_vnext.py benchmark-results/headless-vnext/example-rankings.jsonl --allow-partial --out-dir benchmark-results/headless-vnext/example-output
# real arm: no --allow-partial
python aic51-src/script/score_headless_vnext.py path/to/full-48-query-rankings.jsonl --out-dir path/to/scored-output
```

No command above runs retrieval or a model.
