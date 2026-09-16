# Analysis provenance v1

This is the first compatibility-sidecar implementation of the ratified Vecna Slices 2–5. It is intentionally additive: existing `features/<video>/<frame>/<feature>.npy` files remain the compatibility outputs consumed by current indexing/search code.

## Why this exists

The legacy pipeline discarded information that cannot be reconstructed later:

- source/rendition and keyframe-selection lineage;
- OCR boxes, provider-native confidence, raw language-specific observations, and crop provenance;
- WhisperX native segment intervals/language before ASR was projected onto keyframes;
- provider/model/config/runtime/code identity for each analysis run;
- the distinction between native Evidence and frame compatibility projections.

New `add` and `analyse` runs preserve those facts under `provenance/` without requiring current consumers to read them.

## Layout

```text
provenance/
  sources/<video_id>.json
  keyframes/<video_id>.json
  analysis/<video_id>/<feature_name>/<analysis_run_id>.json
  evidence/<video_id>/<feature_name>/<analysis_run_id>.json
```

### `sources/`

`aic51-cli add` registers the exact stored bytes and refreshes the source registry after an optional re-encode/compression. The first v1 source identity is a legacy-migration identity scoped to the provenance workspace; it does **not** claim that historical logical-content identity was recovered. Each observable stored rendition has an exact asset SHA-256, and later re-encodes are retained as separate rendition records.

If a video predates this implementation, historical import/rendition provenance is explicitly `unknown`; the code does not backfill current assumptions as history.

### `keyframes/`

New keyframe extraction records the actual generated frame IDs plus the current selection implementation fingerprint and material selection/extraction config. Multiple observed/generated selection generations can coexist in the registry.

For pre-existing keyframes whose original selector/configuration was discarded, the current files are registered as observed and historical producer/configuration stays `unknown` rather than being inferred from today's settings.

If a video is later re-encoded after frame extraction, those Frame Evidence objects remain bound to the rendition from which they were actually selected. The newer stored rendition is tracked separately instead of retroactively changing Evidence identity.

### `analysis/`

One manifest per provider/video execution records:

- provider generation identity and available material config;
- implementation source SHA-256;
- material runtime semantics when observable, such as device/compute type;
- source/rendition/selection generation;
- current stored rendition separately when it differs from the Evidence rendition;
- requested frames;
- success/failure state;
- existing `.npy` output paths;
- representation/artifact identities, shape, dtype, and exact output SHA-256 fixity;
- link to a typed evidence manifest when the provider emits one.

### OCR evidence

OCR records retain:

- normalized legacy frame text;
- language-pass text assembled from provider observations;
- token observations;
- Tesseract provider-native confidence values;
- pixel boxes and Tesseract block/paragraph/line/word locators;
- exact input keyframe-image SHA-256;
- image size and the existing top-8/9 crop preprocessing window;
- parent Frame Evidence relation.

OCR Evidence identity is content-sensitive: materially different observations produce a different Evidence ID even under the same provider/input generation.

Confidence values are provider-native diagnostics, not calibrated correctness probabilities.

### ASR evidence

ASR records retain:

- exact audio-input SHA-256;
- WhisperX native transcript segments and their start/end intervals;
- raw and normalized text;
- language when returned by the provider;
- words when returned by the provider;
- the explicit legacy frame projection used by current Vecna;
- whether a frame was inside a native interval or used the existing nearest-segment-within-2s fallback;
- reconstructed frame time based on the existing rounded-FPS compatibility rule.

ASR Evidence identity includes the material native segment content/timing and exact audio input, so materially different retained output does not silently reuse the same Evidence identity.

## Compatibility guarantees for v1

- Existing `.npy` paths are unchanged.
- OCR/ASR still produce one normalized text value per keyframe for current indexing/search.
- Visual features still produce the same frame-level `.npy` arrays.
- Provenance lives outside `features/`, so current glob-based index code does not need to understand it.
- Missing historical information stays `unknown`.
- This v1 does not change search, fusion, temporal logic, index backends, SearchResult JSON, frontend layout, or submission payloads.

## Before processing more corpus data

For **new corpus data**, use a build containing this change starting at `aic51-cli add`, not only at `analyse`, so source/rendition and keyframe-generation provenance are captured when they are created.

If a video/keyframe set predates this change, the sidecar can register what is observable but cannot reconstruct its discarded producer configuration. If OCR/ASR was already generated before this change, rerunning the relevant analysis with `--overwrite` is required to obtain boxes/native ASR segments that were previously discarded.

Before a bulk batch, run the PR's one-video smoke gate: ingest one representative video, inspect source/keyframe sidecars, run OCR and ASR, verify the legacy `.npy` outputs still index/search, and inspect the rich Evidence JSON.

This v1 sidecar is the capture layer. Traceable SearchResult v2 and frontend Candidate Details consume these fields in later bounded changes.
