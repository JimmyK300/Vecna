"""Run TransNetV2 scene detection on CPU for one or more local videos.

This is the Windows-friendly first stage of the extraction pipeline. It uses
the TransNetV2 weights checked into this repository and writes scene files in
the format expected by keyframe_extractor.py.
"""

import argparse
import os
from pathlib import Path

# Set this before importing TensorFlow so this stage is explicitly CPU-only.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

import numpy as np

from src.transnetv2 import TransNetV2


def process_video(model: TransNetV2, video_path: Path, output_dir: Path) -> Path:
    print(f"Processing {video_path} on CPU...")
    _, single_frame_predictions, _ = model.predict_video(str(video_path))
    scenes = model.predictions_to_scenes(single_frame_predictions)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_path.stem}_scenes.txt"
    np.savetxt(output_path, scenes, fmt="%d")

    print(f"Wrote {len(scenes)} scenes to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "videos",
        nargs="*",
        type=Path,
        help="Video files to process. Defaults to data-source/videos/*.mp4.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data-staging/preprocessing"),
        help="Directory for generated *_scenes.txt files.",
    )
    args = parser.parse_args()

    videos = args.videos or sorted(Path("data-source/videos").glob("*.mp4"))
    if not videos:
        raise SystemExit("No .mp4 files found in data-source/videos.")

    model = TransNetV2()
    for video_path in videos:
        if not video_path.is_file():
            raise SystemExit(f"Video not found: {video_path}")
        process_video(model, video_path, args.output_dir)


if __name__ == "__main__":
    main()
