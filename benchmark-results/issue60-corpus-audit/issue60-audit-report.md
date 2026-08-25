# Issue #60 corpus integrity audit

- Generated (excluded from hash): `2026-08-25T17:32:12.401133+00:00`
- Report content SHA-256: `6c0e2ab56fb04db1ed625621d255d43af5942259c0d06407169d605eb03641b7`
- Active collection: `official_l21_l30_all_v2` generation `idx_6baede5b9bc447e099c0004d8428ca7e`
- Expected videos: **873**, source media: **873**, feature dirs: **873**, frames: **322924**, .npy files: **1291696**
- Deep header-scanned videos: 32 (sampled), content-loaded videos: 4 (sampled)

## Status totals (all categories)

| status | items |
|---|---|
| valid | 0 |
| missing | 4 |
| malformed | 0 |
| legacy_unknown | 8 |
| foreign_unowned | 8 |
| unresolved | 0 |

## Counts by category x status

| category | valid | missing | malformed | legacy_unknown | foreign_unowned | unresolved |
|---|---|---|---|---|---|---|
| duplicates | 0 | 0 | 0 | 0 | 5 | 0 |
| foreign_artifacts | 0 | 0 | 0 | 8 | 3 | 0 |
| provenance_sidecar_store | 0 | 4 | 0 | 0 | 0 | 0 |

## Flagged items

### missing

- `[provenance_sidecar_store]` `provenance/analysis`: new-format provenance store 'analysis/' absent at corpus root; per-video producer/config manifests cannot be dereferenced locally
- `[provenance_sidecar_store]` `provenance/evidence`: new-format provenance store 'evidence/' absent at corpus root; per-video producer/config manifests cannot be dereferenced locally
- `[provenance_sidecar_store]` `provenance/keyframes`: new-format provenance store 'keyframes/' absent at corpus root; per-video producer/config manifests cannot be dereferenced locally
- `[provenance_sidecar_store]` `provenance/sources`: new-format provenance store 'sources/' absent at corpus root; per-video producer/config manifests cannot be dereferenced locally
### legacy_unknown

- `[foreign_artifacts]` `data-index/`: pre-Milvus local sample-era index artifacts; only reference 'sample_video', unrelated to the active L21-L30 collection -- detail: `{"entry_counts_by_status":{"legacy_unknown":6}}`
- `[foreign_artifacts]` `data-staging/audio-chunk-timestamps/`: sample_video-era staging outputs of the documented legacy pipeline; not part of the active collection -- detail: `{"entry_counts_by_status":{"legacy_unknown":2}}`
- `[foreign_artifacts]` `data-staging/audios/`: sample_video-era staging outputs of the documented legacy pipeline; not part of the active collection -- detail: `{"entry_counts_by_status":{"legacy_unknown":2}}`
- `[foreign_artifacts]` `data-staging/clip-features/`: sample_video-era staging outputs of the documented legacy pipeline; not part of the active collection -- detail: `{"entry_counts_by_status":{"legacy_unknown":3}}`
- `[foreign_artifacts]` `data-staging/keyframes/`: sample_video-era staging outputs of the documented legacy pipeline; not part of the active collection -- detail: `{"entry_counts_by_status":{"legacy_unknown":62}}`
- `[foreign_artifacts]` `data-staging/map-keyframes/`: sample_video-era staging outputs of the documented legacy pipeline; not part of the active collection -- detail: `{"entry_counts_by_status":{"legacy_unknown":2}}`
- `[foreign_artifacts]` `data-staging/preprocessing/`: sample_video-era staging outputs of the documented legacy pipeline; not part of the active collection -- detail: `{"entry_counts_by_status":{"legacy_unknown":2}}`
- `[foreign_artifacts]` `data-staging/transcripts/`: sample_video-era staging outputs of the documented legacy pipeline; not part of the active collection -- detail: `{"entry_counts_by_status":{"legacy_unknown":2}}`
### foreign_unowned

- `[duplicates]` `temp-extraction` (video `L21_V001`): same video id also has an artifact tree outside the active feature store (stale duplicate generation; not deleted by policy)
- `[duplicates]` `temp-extraction` (video `L21_V002`): same video id also has an artifact tree outside the active feature store (stale duplicate generation; not deleted by policy)
- `[duplicates]` `temp-extraction` (video `L21_V003`): same video id also has an artifact tree outside the active feature store (stale duplicate generation; not deleted by policy)
- `[duplicates]` `temp-extraction` (video `L21_V005`): same video id also has an artifact tree outside the active feature store (stale duplicate generation; not deleted by policy)
- `[duplicates]` `temp-extraction` (video `L21_V006`): same video id also has an artifact tree outside the active feature store (stale duplicate generation; not deleted by policy)
- `[foreign_artifacts]` `data-source/features/`: report/transcription artifact stored inside an analysis-output tree; no ownership reference discovered in code/docs/config/provenance; whisperx comparison artifacts inside the features tree; no ownership reference discovered in code/docs/config/provenance -- detail: `{"entry_counts_by_status":{"foreign_unowned":73}}`
- `[foreign_artifacts]` `data-source/metadata/`: report/transcription artifact stored inside an analysis-output tree; no ownership reference discovered in code/docs/config/provenance -- detail: `{"entry_counts_by_status":{"foreign_unowned":277}}`
- `[foreign_artifacts]` `temp-extraction/`: temporary extraction output duplicating active-collection video ids with a different artifact generation; unreferenced by code/docs -- detail: `{"entry_counts_by_status":{"foreign_unowned":16830}}`

## Provenance coverage

- `sources`: present=False, manifests=0
- `keyframes`: present=False, manifests=0
- `analysis`: present=False, manifests=0
- `evidence`: present=False, manifests=0
- `staging_p11_sample`: present=None, manifests=-

| feature | resolved | unavailable | mixed | absent |
|---|---|---|---|---|
| asr | 0 | 873 | 0 | 0 |
| asr_dense | 873 | 0 | 0 | 0 |
| image_clip_pe-l-14-336 | 0 | 873 | 0 | 0 |
| image_siglip_so400m-384 | 0 | 873 | 0 | 0 |
| ocr | 0 | 873 | 0 | 0 |
| ocr_dense | 873 | 0 | 0 | 0 |
| qwen_vl | 0 | 873 | 0 | 0 |

- Claim records embedded in registry: 1746
- Referenceability: unresolvable_locally: provenance/{sources,keyframes,analysis,evidence} absent at corpus root, so src_/rnd_/sel_/prv_ identifiers cannot be dereferenced within the audited corpus

## Duplicates

- `L21_V001` also present in: temp-extraction
- `L21_V002` also present in: temp-extraction
- `L21_V003` also present in: temp-extraction
- `L21_V005` also present in: temp-extraction
- `L21_V006` also present in: temp-extraction

## Incomplete-run markers

- markers found: 0

## Determinism notes

- All iteration is sorted; sampling uses evenly spaced indices over sorted IDs (no RNG).
- `report_content_sha256` covers the sorted flag list (paths/status/reasons/details) plus scope counts and registry hashes; wall-clock time is excluded.
- Registry hash: raw-file SHA-256 plus canonicalized-JSON SHA-256 (`registry_sha256_canonical`).
- Re-running with identical parameters on an unchanged corpus must reproduce `report_content_sha256` exactly.
