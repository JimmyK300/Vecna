# Provenance and comparison boundaries

This review packet tracks JimmyK300/Vecna#82 and official-dataset-control#16/#17. All work is on separate review branches. Vecna main is not a publication target.

## Immutable authority

| Surface | Identity |
|---|---|
| Vecna frozen main | `95d63a6abf10c598e0e54af7d2071bedbe542d1e` |
| Dataset frozen main | `1f1ad1baef1e1d31817f6c5a12d4d94133611038` |
| Canonical truth SHA-256 | `63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f` |
| Historical Qwen rankings SHA-256 | `85d5dd169bcd6934ebfa8435b6aee82ce9bc149bac3a704afbdbcb4b986568f0` |
| Historical reranker artifact SHA-256, LF | `4e949d95916c9fed7b11327ace67e207eb9238bb9f3beb4e66ff4873cb3ec8be` |
| Canonical query projection SHA-256 | `bd15d05f6c8f00597cced4f50914547ca0b3de75a9e57ee262a4f4ba292485aa` |

The canonical projection is UTF-8 compact sorted-key JSON of the query-ID-ordered list of `{query_id,query}`, without text normalization. Packet B also hashes a different, explicitly defined ID-to-query-hash serialization; that is not a competing canonical query identity. The control manifest and `inputs/sources.json` pin the 18 source inputs.

There are 115 canonical queries and exactly 113 scoreable queries. The exclusions remain `p0_q15` and `p3_q09`. The empty historical ranking for `p2_q17` remains in the denominator. Query text, IDs, phase, task type, tags, truth tier and truth provenance remain unchanged.

## Distinct experiments

**Packet C is historical saved evidence.** Its baseline and reranker outputs were produced before this execution. The saved reranker filename says top100, but the available reranker artifact retains 20 candidates for each of 114 active queries. All 2,280 candidate occurrences were traced to original baseline ranks. The archived September 14 loading log materialized 625 `model.*` tensors without the current newly-initialized warning. It does not contain the package, loaded-state and corpus-extraction evidence needed to certify that older runtime completely.

**The current Qwen defect is independently demonstrated.** In the current SentenceTransformers 5.4.0 / Transformers 4.57.6 / Torch 2.8.0 CPU environment, the original wrapper reported 625 missing and 625 unexpected keys. Model construction alone was therefore an inadequate acceptance condition. PR #88 supplies a targeted checkpoint key mapping and imported production-path regression tests. Verification used one ordinary model instance and compared every loaded value to the pinned safetensors checkpoint in bounded chunks: 625 tensors, 2,127,532,032 elements, all equal after the prescribed BF16-to-float32 conversion, and all four loading diagnostics empty. Checkpoint revision is `9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda`; checkpoint SHA-256 is `c73fa9caeddeb3ff831d46c085a7a5708343248ca777e90f2d486964464509c1`. The verification report SHA-256 is `8f459c0f25c62a712acea1ef59e4855e0d8d7428dc8623407ec6db9300790eb8`. This current defect does not prove that C or the existing corpus vectors are contaminated.

**Packet B is fresh matched provider evidence.** Its execution commit is `0ee966b8ddfe367fbf5a9bb4ba8301c2d43b5e54`. It adds only the two separately reviewed loading-repair files to the frozen research implementation. Full capture collected 115/115 query rows without reading ground truth, in 322.797 seconds of supervised child time. Raw rankings are 27,146,363 bytes with SHA-256 `d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82`. Its run identity is `f0d32893564111064d47f6f2f72f7b03dbb14ebbfbb3d05c48e49e30ef165755`. [Original capture](https://github.com/JimmyK300/ai-routing-hub/actions/runs/35103784571).

Four providers are active: Qwen visual, SigLIP visual, OCR sparse and ASR sparse. Both dense weights are zero in the frozen main configuration; they are explicitly disabled in B. The separate 38-row dense text audit is not retroactively inserted into B. The current control preserves the nested visual sum and scaling, native text eligibility/boost/scaling, fixed outer weights, frame-level fusion and captured candidate tie order. It is not an RRF baseline. Alternative transformations use the same raw hits and frozen weights; no weight or temperature search was performed.

Video R@K, frame-position video R@K and frozen range/event R@K are different scoring surfaces. The first-unique-video projection is an analysis convention. The inspected main `_similarity_search` returns the full sorted frame list; the measured loss after selecting one representative frame per video is not proof of a serving defect.

**Packet A is a bounded matched representation test.** The global pool is three candidate windows per query for all eight established temporal controls, frozen before scoring because the earlier native pilot was expensive. The test uses the same 72 exact sampled frames from 17 videos, with matched 384x216 image pixels and chronological past/center/future order. Native and stitched conditions expose 252 visual tokens; the single-frame control exposes 84. The native processor proof confirms three distinct image groups. A narrow ranking gain is not evidence of causal temporal reasoning or event localization: only two queries have a correct video in this frozen pool and none of the 31 required event anchors is exposed.

## Dataset review boundaries

The temporal source review covers 31 event records over eight queries, using native-FPS clips, 93 stills and eight filmstrips. Sixteen records have a supported representative point and fifteen remain unknown. Boundary fields remain null; representative points are not ordinary event ranges or certified first-occurrence labels. The original provisional truth tier and exclusions are not promoted. The reviewed ledger SHA-256 is `0ab32900e7389cc58e981d6e415000755a76c68b110389952fcc8e76657324f4`.

The frozen OCR/ASR sample contains 38 query/channel pairs across 30 unique queries: 20 OCR and 18 ASR. All 20 OCR images were inspected. All 18 ASR audio clips were captured and hash-verified but remain unheard; no manual transcript, WER or CER is claimed. Five OCR sample gaps are observations at the sampled source locations, not five retrieval failures. Thirty-seven archived source JSON files and 61 host-decoded projected text matches were verified. The source cache is reproducibly hydrated from pinned dataset Git blobs rather than duplicated.

Sparse visibility uses 38 unchanged queries and 3,800 raw hits. Equal-score ordering varies with Python hash seed because main uses a set before sorting by score; issue #89 records this separately. All host/0/1/82 tie observations are retained without choosing a favorable seed.

Dense visibility is a separate completed 38-row capture. Its raw rankings SHA-256 is `097bc5f7680457d068fe075372f67dd03b17d2fac745d7e5a68a85f7195bcfc2`. The BGE-M3 snapshot is `5617a9f61b028005a4858fdac845db406aefb181`; all six consumed files are pinned, and 389 active encoder tensors / 566,705,152 elements match the cached checkpoint. Main's CPU float32 CLS/L2 path is preserved. The evaluator accepts only the exact observed SDK-added empty `params:{}` form alongside the already-checked search parameters. Client arguments alone do not independently establish server-side effective parameters. [Original dense capture](https://github.com/JimmyK300/ai-routing-hub/actions/runs/35105076396).

Collection identity is `official_l21_l30_all_v2`, 322,924 rows. Schema/index metadata and sampled projected text are recorded. They are not a complete vector-content fingerprint. Sampled native corpus lineage records are absent, so corpus encoder compatibility is unresolved.

## Recovery, timing and publication

The scratch execution environment disconnected after both full model captures completed. Recovery uses exact Actions artifacts, Git-pinned code and model-free evaluation on the authorized host. Original and regenerated analysis identities are kept separate because offline timing fields may differ. No model capture is rerun for recovery.

The broker's Windows patch envelope is normalized to LF before its expected patch SHA is checked. File newline restoration is accepted only when the original expected byte count and SHA agree. Logs may require exact CRLF reconstruction. This is a transport operation, not a query, ranking or scoring change.

Broker runs export review artifacts from disposable clones with unchanged final HEAD. GitHub publication is performed separately on owned review branches. Artifact retention is finite; published manifests and lossless payloads must be sufficient to reconstruct results without relying only on an expiring Actions run. Timings came from a shared CPU host and are not isolated performance benchmarks.

No main merge, model training, full-corpus re-embedding, query rewriting, production fusion integration or new model-family experiment is included. Packet E is a proposal only.
