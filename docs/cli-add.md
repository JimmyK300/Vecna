# `cli/commands/add.py`

## Purpose

Loads video(s) into the workspace and preprocess all loaded data. Preprocessing includes extracting keyframes, cutting audio, and generating short video clips centered on each keyframe.

## Usage

```bash
aic25-cli add ../data/videos -d -kc
```

## CLI Arguments

| Flag | Name | Description |
|---|---|---|
| `path` | — | Path to a video file or a directory of videos |
| `-d` | `--directory` | Treat `path` as a directory rather than a single video |
| `-k` | `--keyframe` | Extract keyframes (`.jpg`) |
| `-a` | `--audio` | Extract audio (`.wav`) *(unused in current pipeline)* |
| `-c` | `--clip` | Extract video clips (`.mp4`) *(unused in current pipeline)* |
| `-C` | `--compress` | Compress the video to a lower resolution *(unused in current pipeline)* |
| `--compress-first` | — | Compress the video before running other preprocessing steps *(unused in current pipeline)* |
| `-o` | `--overwrite` | Overwrite existing files |

> **Known issue:** the progress bar for `-C` does not currently display correctly.

## Output

The command creates the following directory structure inside the workspace:

```
data/
├── videos/
│   └── <video_id>.mp4
├── video_info/
│   └── <video_id>.json
├── keyframes/
│   └── <video_id>/
        └── <frame_id>.jpg
├── thumbnails/
│   └── <video_id>/
        └── <frame_id>.jpg
├── video_clip/
│   └── <video_id>/
        └── <frame_id>.mp4
├── audio/
│   └── <video_id>.wav
└── audio_clip/
    └── <video_id>/
        └── <frame_id>.wav
```

| Path | Description | Requires |
|---|---|---|
| `data/videos/` | Imported videos | — |
| `data/video_info/` | Metadata for each video (currently FPS only) | — |
| `data/keyframes/<video_id>/` | Extracted keyframes | `-k` |
| `data/thumbnails/<video_id>/` | Thumbnail images | `-k` |
| `data/video_clip/<video_id>/` | Video clips centered on keyframes | `-k -c` |
| `data/audio/<video_id>.wav` | Extracted audio | `-a` |
| `data/audio_clip/<video_id>/` | Audio corresponding to each video clip | `-k -c -a` |

## Class: `AddCommand`

Callable class that implements this command.

### Call graph

```
__call__
└── _add_videos
    └── _load_video
        ├── _compress_video        (optional, if --compress-first)
        ├── _extract_audio         (optional, -a)
        ├── _extract_keyframes     (optional, -k)
        │   └── clip extraction    (optional, -c, runs inside _extract_keyframes)
        └── _compress_video        (optional, if not --compress-first)
```

### Methods

#### `__init__`
Initializes the command via inheritance from `BaseCommand`.

#### `__call__`
Entry point of the command.
- Determines whether the input is a single video or a directory.
- Collects all videos to process.
- Calls `_add_videos()`.

#### `_add_videos`
Orchestrates processing of the full video list in parallel.

For each video, runs the following sequence:
1. `_load_video`
2. `_compress_video` — optional, only if `--compress-first`
3. `_extract_audio` — optional, `-a`
4. `_extract_keyframes` — optional, `-k` (also handles clip extraction internally)
5. `_compress_video` — optional, only if **not** `--compress-first`

#### `_load_video`
Copies or moves the source video into `data/videos/`. Skips if the target already exists, unless `-o`/overwrite is set. Calls `_extract_video_info` to save metadata.

Returns a status flag, the output path, and the video ID (the filename stem). This `video_id` is used consistently as the identifier across `keyframes/`, `thumbnails/`, `video_clip/`, and later in `AnalyseCommand` / Milvus indexing.

#### `_extract_keyframes`
The core preprocessing step. Performs three tasks in a single pass over the video:

1. **Finds keyframes** via `_get_keyframes_list`, and enforces a maximum gap (`max_scene_length` seconds) between keyframes.
2. **Saves a keyframe + thumbnail JPEG** for each selected frame, resized per the `keyframe_resize_ratio` / `thumbnail_resize_ratio` config values.
3. **If `-c`/`do_clip` is set:** writes a short `.mp4` clip (and, if `-a` is also set, a corresponding `.wav` clip) centered on each keyframe, sampling every `video_clip_interval`-th frame across a `clip_length`-second window. *(Unused in current pipeline.)*

#### `_get_keyframes_list`
Runs `ffprobe` to inspect every frame’s picture type (I, P, or B) and returns only the indices of I-frames.
Video codecs such as those used in MP4 files compress video using different frame types. I-frames are self-contained frames that can be decoded without referring to surrounding frames, while P-frames and B-frames store predictions based on other frames.
Because I-frames are independently decodable and are often inserted at scene changes or regular keyframe intervals, they can serve as fast and reliable keyframe candidates.
Learn more about I-frames [here](https://en.wikipedia.org/wiki/Video_compression_picture_types).

#### `_extract_video_info`
Runs `_get_fps_info` and writes exact rational FPS metadata (`frame_rate`, `frame_rate_fraction`, `r_frame_rate`, `avg_frame_rate`) as JSON to `data/video_info/<video_id>.json`.

#### `_get_fps`
Parses `ffprobe` output via `Fraction` to return the exact float FPS of the video.

#### `_extract_audio`
Runs `ffmpeg` to extract audio to `data/audio/<video_id>.wav`. *(Unused in current pipeline.)*

#### `_compress_video`
Re-encodes the video via `ffmpeg` using NVENC hardware encoding (`h264_nvenc`) at a reduced resolution. Cannot be run on AMD due to not supporting NVENC. *(Unused in current pipeline.)*
