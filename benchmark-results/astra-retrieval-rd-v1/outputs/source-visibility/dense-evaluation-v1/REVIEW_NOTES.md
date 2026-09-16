# Dense visibility: review notes

The frozen 38 query/channel rows completed with the existing cached BGE-M3 encoder: 20 OCR and 18 ASR rows across 30 distinct queries. The source review remains separate: 20 representative OCR frames were inspected, while all 18 captured ASR excerpts remain unheard. No truth, extraction, model, index, or fusion change was made.

| Observation | OCR | ASR |
|---|---:|---:|
| Current accepted target present in dense top100 | 7/20 | 12/18 |
| Current accepted target present in sparse top100 | 4/20 | 11/18 |
| Both / sparse only / dense only / neither at100 | 3 / 1 / 4 / 12 | 11 / 0 / 1 / 6 |
| Dense accepted target at20, observed main order | 5/20 | 9/18 |
| Same-video repeated exact-text excess in dense retained keyframes | 243/2000 | 1599/1800 |

These completed visibility reports supersede the retrieval-stage pending statement in the earlier dataset source-audit return. The frozen source-review ledgers, source annotations, and their hashes remain unchanged.

The overlap compares independently captured candidate pools. It is not a fusion score or evidence for choosing weights from this sample. Four OCR rows and seven ASR rows retain provisional P3 truth. All queries fit within the declared 1024-token limit.

Main's score-only sort changed 36 of 38 observed orders, entirely within equal-cosine groups; all 38 score sequences were preserved. ASR target R@1 changed from 8/18 in raw SDK order to 5/18 in observed main order, and R@5 changed from 9/18 to 8/18. R@20 and R@100 were unchanged. This adds dense evidence to [Vecna #89](https://github.com/JimmyK300/Vecna/issues/89); no preferred hash seed or tie repair was selected.

The run supplied the complete canonical query to pinned main's PyTorch CPU float32, CLS and L2-normalization path. All 389 active encoder tensors, containing 566705152 elements, matched the selected cached checkpoint. All missing, unexpected, mismatched and error loading lists were empty. Every consumed model/tokenizer file was hashed before model use and checked for stable size and modification time afterward. Large file hashes were frozen immediately before loading; their earlier probe pins contained revision, size and modification time rather than preexisting content digests. The full records preserve that distinction.

The matching PyMilvus 3.0.0 release explains why the recorded search parameter dictionary contains an added empty `params` mapping: request preparation mutates that dictionary, then merges the top-level arguments into its wire parameters. This does not independently measure server-effective SCANN settings. See `inputs/dense_sdk_parameter_review.json` for pinned primary-source references.

Both inspected index-generation registry paths were absent. Current query checkpoint identity and healthy collection metadata therefore do not establish historical stored-vector encoder compatibility. Dense target absence means absence from this field's retained100 under the declared current encoder. It does not prove an extraction defect or failure of a proven compatible index. The 731 overlapping indexed/projected text comparisons all matched; that is representation parity, not source transcription fidelity.

Source findings also remain anchor-specific. For example, p0_q20 has a reviewed OCR anchor gap while sparse retrieval still finds a current accepted target at rank1, and p1_q24 has accepted targets in both captured text channels. Retrieval success does not repair or erase those source observations.

Capture ran from source preparation commit `759782480ad4da4927be1e1a383a9323e16906a0` before truth access. Offline scoring used evaluator commit `50984d58a8aa580ebde561718d4ef5504991a3a5`; recovery used wrapper commit `5f2492c3ef8a93a09595d2f13dbc36041b7a5954`. [Capture result](https://github.com/JimmyK300/ai-routing-hub/issues/1#issuecomment-5698675439) and [model-free recovery result](https://github.com/JimmyK300/ai-routing-hub/issues/1#issuecomment-5699118990) retain the execution proof. The four evaluation outputs replayed byte for byte on that host. Raw and scored files are published as ordinary UTF-8 Git blobs with exact original hashes; gzip was used only for lossless transport after the scratch outage.

Reproduction must preserve hash-pinned input bytes. Windows autocrlf and platform-native output newlines can change byte hashes even when parsed JSON is identical. The recovery wrapper restores input files from exact Git objects, applies the capture patch with command-local LF settings, and reconstructs original CRLF log bytes only when the supervisor's exact hash and byte count match. It does not change repository Git configuration or the dataset checkout.
