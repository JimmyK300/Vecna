# `cli/commands/analyse.py`

## Purpose

Analyzes keyframes and other media extracted from videos using various feature extractors (e.g., Image CLIP, Video CLIP, OCR, ASR) to generate embedding vectors or text metadata, which are then saved as NumPy `.npy` files in the workspace.

## Usage

```bash
aic51-cli analyse [options]
```

## CLI Arguments

| Flag | Name | Description |
|---|---|---|
| `--no-gpu` | — | Disable GPU usage and fallback to CPU (or MPS if available) |
| `-o` | `--overwrite` | Overwrite existing feature files instead of skipping already processed keyframes |
| `--use-image-clip` | — | Run ONLY the Image CLIP feature extractor (if configured) |
| `--use-image-siglip` | — | Run ONLY the Image SigLIP feature extractor (if configured) |
| `--use-qwen-vl` | — | Run ONLY the Qwen VL embedding feature extractor (CUDA only) |
| `--use-video-clip` | — | Run ONLY the Video CLIP feature extractor (if configured) |
| `--use-asr` | — | Run ONLY the ASR (WhisperX) feature extractor (if configured) |
| `--use-ocr` | — | Run ONLY the OCR feature extractor (if configured) |
| `--use-text-embedding` | — | Run ONLY BGE-M3 text embedding (`ocr_dense` / `asr_dense`) |
| `--use-yolo` | — | Run ONLY the YOLO11-seg Traffic feature extractor (if configured) |
| `--keep-going` | — | Record a video failure and continue the remaining videos |
| `--video ID` | — | Limit analysis to one or more video IDs (repeatable) |

ONNX text-embedding progress lines include a representative document and the
live batch width, e.g. `ocr_dense infer: batch=2500/L25_V048_ocr n=64 pad=32`.

> **Behavior of `--use-*` flags:**
> - If **none** of the `--use-*` flags are specified, all feature extractors defined in `config.yaml` are executed by default.
> - If **one or more** of these flags are specified, only the selected extractor(s) will be executed.
>
> **Note on Testing Individual Modules:**
> If you wish to test/run a specific module individually, you should either:
> 1. Use the corresponding CLI flag (e.g., `--use-asr`), OR
> 2. Comment out the unused extractors under the `features:` block in `config.yaml` if running `aic51-cli analyse` without selection flags.

## Output

The command creates/saves features inside the `features/` directory in the root of the workspace:

```
features/
└── <video_name>/
    └── <keyframe_id>/
        └── <feature_extractor_name>.npy
```

| Path | Description | Required Input |
|---|---|---|
| `features/<video_name>/<keyframe>/image_clip_pe-l-14-336.npy` | Image CLIP embedding (NumPy array) | `data/keyframes/<video_name>/` (images) |
| `features/<video_name>/<keyframe>/video_clip_pe-l-14-336.npy` | Video CLIP embedding (NumPy array) | `data/video_clips/<video_name>/` (video clips) |
| `features/<video_name>/<keyframe>/ocr.npy` | Extracted text from keyframe via OCR | `data/keyframes/<video_name>/` (images) |
| `features/<video_name>/<keyframe>/asr.npy` | Extracted spoken audio text near keyframe timestamp via ASR | `data/keyframes/<video_name>/` (for mapping), `data/audio/<video_name>.wav` (audio) |

## Class: `AnalyseCommand`

Callable class that implements the feature analysis command.

### Call graph

```
__call__
└── For each feature in config:
    └── For each video:
        └── _analyse_one_video
            ├── _get_keyframes_list   (filtered by overwrite flag)
            ├── _get_input_files      (based on require_input)
            ├── get_features          (FeatureExtractor model inference)
            └── Save features         (saves as <feature_extractor_name>.npy)
```

### Methods

#### `__init__`
Initializes the command via inheritance from `BaseCommand`.

#### `add_args`
Registers CLI arguments (GPU control, overwrite option, and feature-specific selection flags) to the command's subparser.

#### `__call__`
Entry point of the command.
- Loads features list from the global config (`config.yaml`).
- Configures the execution device (GPU/CPU) via `_get_device()`.
- Gathers video IDs to process via `_get_video_ids()`.
- Determines target models based on the specified `--use-*` flags. If any use flag is set, filters the active feature list accordingly.
- Loops over configured feature extractors, instantiating them via `FeatureExtractorFactory`, and runs `_analyse_one_video` for each video with a rich progress bar.

#### `_get_device`
Configures the device mapping. Selects `cuda` (if CUDA is available), `mps` (if Apple Silicon GPU is available), or falls back to `cpu`.

#### `_get_video_ids`
Retrieves sorted stems of all directories in `data/keyframes/` to identify the videos that have been preprocessed and are ready for feature extraction.

#### `_get_keyframes_list`
Returns a sorted list of keyframe stems for a video that need to be processed.
- If `--overwrite` is NOT set, it checks if the feature file already exists in `features/<video_id>/<keyframe>/<feature_extractor_name>.npy` and skips it.
- Otherwise, lists all keyframes under `data/keyframes/<video_id>/` that are to be processed.

#### `_get_input_files`
Locates the required input media path (e.g. `data/keyframes/` or `data/video_clips/`) for the feature extractor and filters them down to the list of keyframes needing analysis.

#### `_analyse_one_video`
Orchestrates feature extraction for a single video and feature extractor.
1. Calls `_get_keyframes_list` to find keyframes requiring analysis.
2. Calls `_get_input_files` to collect the input paths.
3. Invokes `feature_extractor.get_features` on the inputs to extract embeddings/text.
4. Iterates through the outputs, creates target directories, and saves the features as `.npy` files inside `features/<video_id>/<keyframe>/<feature_extractor_name>.npy`.
