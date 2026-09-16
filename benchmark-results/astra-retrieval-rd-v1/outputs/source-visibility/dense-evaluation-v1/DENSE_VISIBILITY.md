# Frozen OCR/ASR sample: dense BGE-M3 visibility

The existing cached BGE-M3 checkpoint encoded all 38 frozen canonical query/channel rows through pinned main's PyTorch CPU float32, CLS, L2-normalized, 1024-token path. Every active encoder parameter was compared with the cached checkpoint before queries ran. Raw COSINE top100 and main eligibility/boost/max normalization were retained separately; no visual model, truth-directed query, new model, extraction, index mutation or fusion change was used.

The current query checkpoint is identified and verified. Historical stored-vector encoder/index-generation compatibility remains unresolved. Target absence therefore means absent from this dense field's retained100 under this declared encoder; it does not establish an extraction error or failure of a proven compatible dense index. Source-image observations and the 18 unheard ASR clips retain their separate limits.

| Channel | Cases | Eligible video @20 / @100 | Eligible any target @20 / @100 | All targets @100: both / sparse only / dense only / neither |
|---|---:|---:|---:|---:|
| OCR | 20 | 6 / 9 | 5 / 7 | 3 / 1 / 4 / 12 |
| ASR | 18 | 10 / 14 | 9 / 12 | 11 / 0 / 1 / 6 |

These are sample visibility counts at keyframe positions, including provisional P3 truth. The sparse/dense overlap counts compare independent candidate pools and are not a fusion score. Main's normal raw pool expansion to200/500 was not fetched. Full ranks, query vectors' checksums, token counts/truncation, indexed text, nearest candidates outside current truth, source parity, and repeated-text occupancy are in `dense_visibility.jsonl`.

| Query | Channel | Dense first video | Dense first target | Sparse first target | Coverage at100 |
|---|---|---:|---:|---:|---|
| p0_q13 | ocr | — | — | — | neither |
| p0_q19 | ocr | — | — | — | neither |
| p0_q21 | ocr | — | — | — | neither |
| p1_q17 | ocr | 22 | 22 | — | dense_only |
| p1_q18 | ocr | — | — | — | neither |
| p1_q24 | ocr | 4 | 4 | 62 | both |
| p1_q21 | ocr | — | — | — | neither |
| p2_q15 | ocr | 1 | 1 | 2 | both |
| p2_q26 | ocr | — | — | — | neither |
| p2_q25 | ocr | — | — | — | neither |
| p3_q04 | ocr | 1 | 1 | — | dense_only |
| p3_q02 | ocr | 29 | — | — | neither |
| p3_q05 | ocr | 7 | 56 | — | dense_only |
| p3_q35 | ocr | — | — | — | neither |
| p0_q20 | ocr | — | — | 1 | sparse_only |
| p1_q03 | ocr | 1 | 1 | — | dense_only |
| p1_q23 | ocr | — | — | — | neither |
| p2_q13 | ocr | 71 | — | — | neither |
| p2_q23 | ocr | — | — | — | neither |
| p2_q24 | ocr | 1 | 4 | 4 | both |
| p0_q02 | asr | 1 | 1 | 15 | both |
| p0_q19 | asr | 1 | 8 | 10 | both |
| p1_q17 | asr | 56 | 82 | — | dense_only |
| p1_q24 | asr | 76 | 76 | 16 | both |
| p2_q26 | asr | — | — | — | neither |
| p2_q28 | asr | — | — | — | neither |
| p3_q04 | asr | 1 | 1 | 3 | both |
| p3_q08 | asr | 1 | 2 | 2 | both |
| p3_q18 | asr | 1 | 1 | 1 | both |
| p0_q16 | asr | 1 | 1 | 34 | both |
| p0_q20 | asr | 24 | — | — | neither |
| p2_q23 | asr | 1 | 1 | 24 | both |
| p2_q21 | asr | 1 | 2 | 1 | both |
| p3_q06 | asr | 39 | 39 | 1 | both |
| p3_q14 | asr | 1 | — | — | neither |
| p0_q01 | asr | 1 | 2 | 1 | both |
| p3_q24 | asr | — | — | — | neither |
| p3_q05 | asr | — | — | — | neither |

No CER/WER, source transcript, truth promotion, model repair or extraction fix is asserted. Existing source gaps remain anchor-specific, even if another candidate in the accepted window is retrieved.

Current cached revision: `5617a9f61b028005a4858fdac845db406aefb181`. Rankings SHA-256: `097bc5f7680457d068fe075372f67dd03b17d2fac745d7e5a68a85f7195bcfc2`. Model loading, all consumed-file hashes and checkpoint parameter proof are in the capture manifest and `model_initialization.json`; lineage and checksum qualifications are preserved there.
