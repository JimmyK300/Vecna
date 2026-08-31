# Issue #76 — Browser Task Lead completion packet

**Status:** bounded implementation complete; ready for review.  
**Branch:** `btl/issue-76-headless-vnext-scorer`  
**Stack base / approved #75 contract:** `2344023ea4e2a152d1e9dc15778d8feb436dc396`  
**Verified implementation state:** `e759a8715efa2d256c673f8a92858eec6fce3ab3`  
**Temporary CI cleanup commit:** `9aacf1a5fc3ea37aae1cbfc41d73b1f730c9d270`

No Qwen, fusion, retrieval, model, index, corpus, or production-search run was performed. This issue stops at scorer + manifest + deterministic saved-ranking validation.

## Completion

Implemented the model-independent Headless vNext scoring layer requested by #76:

- frozen 48-query P0/P1 manifest generated additively from accepted Issue #63 truth;
- canonical identities:
  - P0 `test_round_8_8::*` while preserving `testing88_submission633::*` provenance;
  - P1 `actual_p1_10_4::*` while preserving `final_round1_10_4of13::*` provenance;
- P2 absent;
- all 48 rows video-scoreable;
- 44 non-TRAKE rows ordinary range-scoreable;
- 4 TRAKE rows separated from ordinary range recall;
- 15 submitted TRAKE event anchors materialized as inclusive `[F-5,F+25]` provisional proxy windows;
- QA answer correctness explicitly `not_evaluated`;
- saved-ranking JSON/JSONL input independent of retrieval provider/model;
- complete supplied top-K rankings preserved in scored output;
- explicit saved `rank` values honored, including ranking gaps;
- real benchmark arms require all 48 query ranking rows by default; missing rows hard-fail rather than becoming false retrieval misses;
- `--allow-partial` exists only for fixtures/debug and labels summaries `partial_fixture` with separate manifest/scored denominators.

## Durable artifacts

- `benchmark-results/headless-vnext/manifest.json` — materialized frozen manifest.
- `benchmark-results/headless-vnext/PROTOCOL.md` — identity, denominator, TRAKE proxy, saved-ranking, and command contract.
- `aic51-src/script/build_headless_vnext_manifest.py` — deterministic manifest projection with frozen-source hash/count invariants.
- `aic51-src/script/score_headless_vnext.py` — retrieval-independent scorer.
- `aic51-src/tests/test_headless_vnext.py` — focused deterministic tests.
- `benchmark-results/headless-vnext/example-rankings.jsonl` — two-query synthetic compatibility fixture.
- `benchmark-results/headless-vnext/example-output/{scored.jsonl,summary.json}` — materialized synthetic scoring evidence.

The temporary `.github/workflows/issue76-headless-vnext-build.yml` used only to execute/materialize deterministic evidence was removed before handoff.

## Frozen counts / identity evidence

Materialized manifest invariants:

| field | count |
|---|---:|
| execution rows | 48 |
| P0 scoreable rows | 23 |
| P1 scoreable rows | 25 |
| P2 rows | 0 |
| video-scoreable | 48 |
| ordinary non-TRAKE range-scoreable | 44 |
| TRAKE queries | 4 |
| TRAKE event anchors | 15 |

`official-dataset-control` is pinned at `646ec85c75141bb68078fa94ec26b9a1dbef6d04`:

- P0 canonical source `test_round_8_8`, `operational_phase: P0`, Vecna provenance source `testing88_submission633`;
- P1 canonical source `actual_p1_10_4`, `operational_phase: P1`, Vecna provenance source `final_round1_10_4of13`.

## Metric behavior

### Video — 48-query denominator on a complete real arm

- `video_R@1`, `video_R@5`, `video_R@20`;
- `video_MRR@20`;
- per-query first correct-video rank.

### Ordinary range — 44-query denominator on a complete real arm

- `range_R@1`, `range_R@5`, `range_R@20`;
- `range_MRR@20`;
- per-query first range-valid rank;
- first correct-video distance-to-range;
- nearest correct-video distance-to-range @K;
- video→range rank delta;
- correct-video-found-but-range-missed @K;
- conditional range success with explicit eligible-video denominator;
- simple result/correct-video crowding before first range-valid result.

A missing correct video has null localization distance with explicit status; it is not assigned a giant numeric localization error.

### TRAKE — separate 4-query / 15-event provisional surface

For each submitted anchor `F`, proxy truth is `[max(0,F-5), F+25]`, inclusive, tier `provisional_submission_anchor`.

Reported separately:

- event coverage @1/@5/@20;
- all-events-covered @1/@5/@20;
- first event-hit rank;
- distance to proxy window;
- absolute distance to original submitted frame.

These proxies are explicitly not organizer GT and can be rescored/replaced later without rerunning the retrieval provider because saved rankings are preserved.

## Verification

Successful independent GitHub Actions run: `33367019845` on verified implementation state `e759a8715efa2d256c673f8a92858eec6fce3ab3`.

Commands executed successfully:

```bash
python aic51-src/script/build_headless_vnext_manifest.py
python -m unittest discover -s aic51-src/tests -p 'test_headless_vnext.py' -v
python aic51-src/script/score_headless_vnext.py benchmark-results/headless-vnext/example-rankings.jsonl --allow-partial --out-dir benchmark-results/headless-vnext/example-output
```

Evidence:

- manifest builder printed exactly `48 / 23 P0 / 25 P1 / 0 P2 / 44 range / 4 TRAKE / 15 TRAKE events / 48 video`;
- **11/11 unittest PASS**;
- synthetic saved-ranking scorer PASS;
- synthetic output explicitly reports `input_status: partial_fixture`, frozen manifest counts `48/44/4`, and actual scored counts `2 queries / 1 range / 1 TRAKE / 4 events`;
- synthetic P1 row demonstrates correct-video/range at explicit rank 2;
- synthetic P0 TRAKE row exposes 3/4 event proxies within top 5/20 and does not claim all-events-covered.

Tests cover:

1. correct video + accepted range hit;
2. explicit saved-rank gaps preserved;
3. frame just outside range + exact distance;
4. no correct video → null localization distance;
5. segment overlap + multiple accepted ranges;
6. TRAKE partial event coverage + absolute submitted-frame distance;
7. QA answer remains not evaluated;
8. real manifest count/identity invariants;
9. incomplete real arm hard-fails by default;
10. explicit partial fixture uses subset denominators and is labeled partial;
11. ordinary range aggregation excludes TRAKE.

## Provenance discrepancy discovered and resolved

The old Issue #63 Stage-B return text reported `reconstructed-truth.json` SHA-256 `016e1350…`. A clean Issue #76 checkout independently recomputed the accepted file bytes as:

`92a4c14cdb075f43a444e7e105cc7680a491188e307cfe2562fff2b51cfe6603`

Comparison of accepted Issue #63 result commit `b1856c647d3910a4ab0a934bfc1c4d696e0a47a1` to branch-head/return commit `ec4a38d397c9a3a49a821812b37db47f52327049` shows only `BTL-RETURN.md` was added, so `reconstructed-truth.json` itself did not change between those accepted commits. #76 pins and verifies the actual accepted bytes rather than trusting the stale quoted hash. The historical text discrepancy remains documented evidence, not a benchmark blocker.

## Scope / stop confirmation

- No retrieval tuning.
- No production retrieval or model code changed.
- No Qwen/fusion/semantic-provider run.
- No index or corpus mutation.
- No P2 truth promotion.
- Issue #63 frozen truth was read/pinned, not rewritten.
- No expensive benchmark execution.

## Next enabled completion

After BTL/Companion review accepts #76, freeze the actual retrieval/model arms and create the Qwen-specific execution packet. Each arm should emit the complete 48-query saved-ranking contract; this scorer can then score/rescore those rankings without rerunning the model.
