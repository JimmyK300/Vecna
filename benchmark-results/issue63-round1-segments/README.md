# Issue #63 - Stage A output (Round-1 segment reconstruction)

**Status: STAGE A HUMAN REVIEW COMPLETE. Minh accepted 48 records and marked one record ambiguous.**
**No Stage B execution or benchmark-truth writeback was performed. The downstream owner must explicitly handle the missing-video ambiguity.**

## Inputs (identified, hashed, untouched)

| Label | Artifact | SHA-256 |
|---|---|---|
| `final_round1_10_4of13` | `C:\Users\minhc\Downloads\submission-final-round1.zip` (25 CSVs, incl. extra `query-p1-3-qa.csv`) | `802732A492A3AA1C09189720D248BA430132AEB55B2913E0A4665BCDCBBA0158` |
| `testing88_submission633` | `C:\Users\minhc\Downloads\submission-testing8.8\submission\` (24 CSVs) | per-CSV hashes in `anchors.json` |

Identification notes:
- Artifact 2 is identified **by description match** ("submission testing 8.8" / "the 8.8 result").
The numeric id "633" could not be confirmed from any local manifest; the test-round
`manifest.csv` (test-round submissions #1-#14, scores 5.6-8.8) does not contain a 633.
- The final zip is not present in the test-round manifest either; it is dated 2026-08-26 and
is treated as the ~10.4/13 Round-1 final per the issue text.

## What was produced

- `segments/*.yaml` - 49 machine-readable review records (25 final + 24 testing8.8), each with
  query, video, anchor frame(s), derived timestamps, QA answers verbatim, proposed
  correct range(s) in frame+time coordinates, confidence, boundary reasoning, conflict notes,
  `review_status: NEEDS_MINH_REVIEW`.
- `review/index.html` + `review/review_server.py` - local one-record-at-a-time review tool with
  video seeking, projected-frame stepping, markers, decisions, and atomic autosave.
- `review/reviewed-ranges.json` - Minh's machine-readable verdict: 48 `accept`, one
  `ambiguous` (`testing88_submission633::p1-21`).
- `review/legacy-index.html` - preserved original static contact-sheet review.
- `review/preliminary-round1-questions.txt` - Minh-supplied 25-question text for
  **Preliminary Round 1 · 10.4/13** (SHA-256
  `788D75505867B4C98737A7F09A5E0B1D28A4E3253CEA2100093918F1C03A00F1`).
- `review/stills/<submission>/<qid>/` - stills: `anchor_*.jpg` (exact submitted frame),
  `sheet_*.jpg` (fine window), `wide/*.jpg` (wide window).
- `anchors.json` - parsed submission rows (row 1 = submitted answer) + CSV hashes.
- `review/provenance.json` - artifact hashes + ffprobe data (fps/duration) per video.
- `stage_a_tools/` - reproducible scripts (parse, filmstrips, wide sheets, record generator).

## Headline findings (preserved, not reconciled)

1. **The two submissions disagree on nearly every query** - different videos AND different
   task types (p1-4 kis/trake, p1-17 kis/qa, p1-18 kis/trake, p1-19 kis/qa, p1-22 kis/qa).
2. The **final zip contains `query-p1-3-qa.csv`**, which does not exist in the official
   24-query test-round list, and **duplicates the p1-8 answer for p1-14** (same video+frames).
3. The recovered packet originally lacked Round-1 question text. Minh later supplied the
   complete 25-question Preliminary Round 1 list; the local reviewer attaches it to the
   `final_round1_10_4of13` records while preserving the packet's original reasoning/conflicts.
4. **Blocker:** testing8.8 p1-21 → source video `L21_V004.mp4` missing from
   `Official-Dataset\videos\L21\` (V004 and V020 absent).
5. Official capture OCR garbles several texts; notable: p1-9 "dừa/dứa" (coconut vs pineapple -
   anchor scene is pineapple harvest and matches structurally), p1-5 "cho dỗ ăn" = feeding goats.
6. Frame→time projection uses ffprobe avg fps; provenance v1 marks
   `legacy_time_projection_quality: unknown` - small drift possible.

## Acceptance criteria (Stage A)

- [x] Both Downloads submission files identified (with the 633-id caveat above).
- [x] Exact filenames + SHA-256 preserved (zip + every CSV).
- [x] Every usable submitted answer mapped to query, video, anchor frame(s), timestamp
      (48/49; 1 explicit blocker: missing L21_V004).
- [x] Every candidate has proposed range(s) or explicit blocker/ambiguity.
- [x] Review evidence: fine + wide contact sheets with labeled frame ids/timestamps,
      exact-anchor stills, one-click HTML surface.
- [x] Disagreements between submissions preserved verbatim (see conflict notes).
- [x] No headless benchmark ground-truth file created/modified.
- [x] No retrieval/model/index/fusion behavior changed.

## Human-review verdict

- Minh found the proposed frame ranges decent and accepted 48/49 records.
- `testing88_submission633::p1-21` is **ambiguous**: `L21_V004.mp4` is absent from the
  recovered/local dataset, so the exact score and frame range cannot be verified.
- Browser-task lead / companion: review `review/reviewed-ranges.json` and the linked evidence.
  Do not silently convert the ambiguous record into an accepted range or benchmark truth.
