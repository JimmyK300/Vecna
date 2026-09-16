# Frozen OCR/ASR sample: sparse BM25 visibility

All 38 predeclared query/channel rows were searched independently against the existing 322,924-frame collection. Capture used exact canonical query strings and no truth, model loading, collection writes, or query rewrites. Scoring occurred after the completed ranking file was frozen and checksummed.

This is a dataset #17 diagnostic. Each raw BM25 request retained 100 keyframes. Pinned main's exact ASCII-quote eligibility, 1.5 boost and maximum-score normalization ran on that retained pool. Main normally asks for 200 raw rows, or 500 for ASCII-quoted queries; this bounded capture records those native requests but fetches only 100. It therefore does not reproduce the complete production text-search candidate expansion.

| Channel | Cases | Raw video @20 / @100 | Eligible video @20 / @100 | Eligible any target @20 / @100 | Eligible all targets @20 / @100 |
|---|---:|---:|---:|---:|---:|
| OCR | 20 | 4 / 7 | 4 / 7 | 3 / 4 | 3 / 4 |
| ASR | 18 | 12 / 13 | 12 / 13 | 9 / 11 | 9 / 11 |

Video positions above remain keyframe positions, so repeated video frames consume slots. A separate distinct-video diagnostic is retained per query. Historical TRAKE requires all events; P3 retains its provisional fractional target contract in the JSON metrics. Any-target and strict-all columns are explicit supplemental diagnostics. These sample counts are not a full-benchmark score or an extraction failure rate.

None of the 38 frozen canonical queries contains an ASCII double-quoted phrase. Main therefore removed no candidates through exact-phrase filtering; curly quotation marks do not activate that existing hard filter. The observed raw-to-main order differences are confined to equal BM25 scores. Main builds results by iterating a frame-ID set and then sorts by score alone, so tied candidates inherit set order. ASR any-target R@1 changed from 6/18 in SDK raw order to 4/18 in the captured main order; R@5 changed from 7/18 to 6/18. This observed tie behavior is separate from phrase eligibility or score boosting.

| Query | Channel | ASCII phrase filter | Raw → eligible hits | Eligible first video | Eligible first target | Eligible all targets @100 | Same-video identical-text excess |
|---|---|---|---:|---:|---:|---|---:|
| p0_q13 | ocr | no | 100 → 100 | — | — | no | 18 |
| p0_q19 | ocr | no | 100 → 100 | — | — | no | 26 |
| p0_q21 | ocr | no | 100 → 100 | — | — | no | 5 |
| p1_q17 | ocr | no | 100 → 100 | — | — | no | 27 |
| p1_q18 | ocr | no | 100 → 100 | — | — | no | 0 |
| p1_q24 | ocr | no | 100 → 100 | 41 | 62 | yes | 13 |
| p1_q21 | ocr | no | 100 → 100 | — | — | no | 34 |
| p2_q15 | ocr | no | 100 → 100 | 1 | 2 | yes | 1 |
| p2_q26 | ocr | no | 100 → 100 | — | — | no | 12 |
| p2_q25 | ocr | no | 100 → 100 | — | — | no | 5 |
| p3_q04 | ocr | no | 100 → 100 | — | — | no | 20 |
| p3_q02 | ocr | no | 100 → 100 | 72 | — | no | 2 |
| p3_q05 | ocr | no | 100 → 100 | 26 | — | no | 14 |
| p3_q35 | ocr | no | 100 → 100 | — | — | no | 12 |
| p0_q20 | ocr | no | 100 → 100 | 1 | 1 | yes | 28 |
| p1_q03 | ocr | no | 100 → 100 | — | — | no | 38 |
| p1_q23 | ocr | no | 100 → 100 | — | — | no | 34 |
| p2_q13 | ocr | no | 100 → 100 | — | — | no | 29 |
| p2_q23 | ocr | no | 100 → 100 | 1 | — | no | 16 |
| p2_q24 | ocr | no | 100 → 100 | 1 | 4 | yes | 10 |
| p0_q02 | asr | no | 100 → 100 | 1 | 15 | yes | 93 |
| p0_q19 | asr | no | 100 → 100 | 1 | 10 | yes | 94 |
| p1_q17 | asr | no | 100 → 100 | — | — | no | 94 |
| p1_q24 | asr | no | 100 → 100 | 13 | 16 | yes | 93 |
| p2_q26 | asr | no | 100 → 100 | — | — | no | 93 |
| p2_q28 | asr | no | 100 → 100 | — | — | no | 94 |
| p3_q04 | asr | no | 100 → 100 | 1 | 3 | yes | 93 |
| p3_q08 | asr | no | 100 → 100 | 1 | 2 | yes | 94 |
| p3_q18 | asr | no | 100 → 100 | 1 | 1 | yes | 94 |
| p0_q16 | asr | no | 100 → 100 | 1 | 34 | yes | 94 |
| p0_q20 | asr | no | 100 → 100 | 98 | — | no | 92 |
| p2_q23 | asr | no | 100 → 100 | 1 | 24 | yes | 95 |
| p2_q21 | asr | no | 100 → 100 | 1 | 1 | yes | 95 |
| p3_q06 | asr | no | 100 → 100 | 1 | 1 | yes | 92 |
| p3_q14 | asr | no | 100 → 100 | 1 | — | no | 94 |
| p0_q01 | asr | no | 100 → 100 | 1 | 1 | yes | 92 |
| p3_q24 | asr | no | 100 → 100 | — | — | no | 94 |
| p3_q05 | asr | no | 100 → 100 | — | — | no | 92 |

A dash means no match was observed within this retained pool. It does not prove that the frame or video is absent from the index. Full indexed text, BM25 scores, raw and eligible ranks, matching candidates, and the nearest five candidates outside current truth are retained per case in `sparse_visibility.jsonl`. P3 candidate mismatches are relative to provisional truth.

Observed identical-text occupancy is recorded from actual retrieval candidates. It can motivate a deduplication experiment, but no causal effect on the Qwen baseline, reranker or fusion has been demonstrated. The 20 reviewed OCR stills remain representative anchors; all 18 captured ASR clips remain unheard. No CER/WER, native alignment verdict, truth repair or extraction fix is asserted.

Index/projected-text comparisons overlap only this sample's already pinned source videos: 621 query/frame comparisons, including 621 matching, 0 mismatching and 0 absent projected-frame records. This is stored-text parity, not source transcription fidelity.

Dense text visibility is not measured by this artifact. Sparse visibility completed independently of visual model availability.

Capture rankings SHA-256: `b1c1bcbdaacdea94c9fe77d0e67d8ac994504123195cf043305b9def2cf9bd19`. Canonical truth SHA-256: `63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f`. Source review SHA-256: `c3800092585e7c9f4e04d2ae3a78c8d3f050d4b0daa571285bbee7b3ef2ddd9d`. All file pins and collection identity are in `evaluation_manifest.json`.
