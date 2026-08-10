# Analysis provenance v1

This is the first compatibility sidecar implementation of the ratified Vecna Slices 2–5.
It is intentionally additive: existing `features/<video>/<frame>/<feature>.npy` files remain the compatibility outputs consumed by current indexing/search code.

## Why this exists

The legacy pipeline discarded information that cannot be reconstructed later:

- OCR boxes, provider-native confidence, raw language-specific tokens, and crop provenance;
- WhisperX native segment intervals/language before ASR was projected onto keyframes;
- provider/model/config/code identity for each analysis run;
- explicit source/rendition/frame-evidence identities and the distinction between native evidence and frame compatibility projections.

New analysis runs preserve those facts under `provenance/` without requiring current consumers to read them.

## Layout

```text
provenance/
  sources/<video_id>.json
  keyframes/<video_id>.json
  analysis/<video_id>/<feature_name>/<analysis_run_id>.json
  evidence/<video_id>/<feature_name>/<analysis_run_id>.json
```

### `sources/`

Registers a stable logical source ID and the currently observable rendition. If the video predates this implementation, historical import/rendition provenance is explicitly `unknown`; the code does not backfill current assumptions as history.

### `keyframes/`

Registers the exact observed keyframe membership and stable frame Evidence IDs. For pre-existing keyframes the historical selector/configuration is `unknown` rather than inferred from today's config.

### `analysis/`

One manifest per provider/video execution. It records:

- provider generation identity and material config currently available to the runtime;
- source/rendition/selection generation;
- requested frames;
- success/failure state;
- existing `.npy` output paths;
- representation/artifact identities, shape and dtype;
- link to a typed evidence manifest when the provider emits one.

### OCR evidence

OCR records retain:

- normalized legacy frame text;
- raw text separated by language pass;
- token observations;
- Tesseract provider-native confidence values;
- pixel boxes and Tesseract block/line/word locators;
- image size and the existing bottom-crop preprocessing window;
- parent frame Evidence relation.

Confidence values are provider-native diagnostics, not calibrated correctness probabilities.

### ASR evidence

ASR records retain:

- WhisperX native transcript segments and their start/end intervals;
- raw and normalized text;
- language when returned by the provider;
- words when returned by the provider;
- the explicit legacy frame projection used by current Vecna;
- whether a frame was inside a native interval or used the existing nearest-segment-within-2s fallback;
- reconstructed frame time based on the existing rounded-FPS compatibility rule.

## Compatibility guarantees for v1

- Existing `.npy` paths are unchanged.
- OCR/ASR still produce one normalized text value per keyframe for current indexing/search.
- Visual features still produce the same frame-level `.npy` arrays.
- Provenance lives outside `features/`, so current glob-based index code does not need to understand it.
- Missing historical information stays `unknown`.

## Before processing more corpus data

Use a build containing this change for new `aic51-cli analyse` runs. If a video was analyzed before this change, rerunning with `--overwrite` is required to obtain OCR/ASR evidence that was previously discarded; provenance code cannot reconstruct missing boxes or native ASR segments from old normalized `.npy` strings.

This v1 sidecar is the capture layer. SearchResult v2 and frontend Candidate Details will consume these fields in later bounded changes.
