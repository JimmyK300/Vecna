"""
TransNetV2 scene-cut detection helper.

Requires the official TransNetV2 repo's `inference/` directory to be on
PYTHONPATH (it provides the `transnetv2` module imported below), plus
its pretrained weights directory:

    git clone https://github.com/soCzech/TransNetV2.git
    # (requires git-lfs: `git lfs install && git lfs pull` inside the repo,
    #  otherwise the weights are just corrupt pointer files)

Config expected (via GlobalConfig):
    add.transnetv2_weights_dir  -> path to TransNetV2/inference/transnetv2-weights/
    add.transnetv2_use_gpu      -> bool, default True
"""

from __future__ import annotations

import logging
from pathlib import Path


def configure_gpu(memory_growth: bool = True, gpu_index: int | None = None) -> bool:
    """Configure TensorFlow to use an available GPU. Returns True if one was found."""
    import tensorflow as tf

    gpus = tf.config.list_physical_devices("GPU")
    if not gpus:
        logging.warning(
            "[TransNetV2] No GPU detected by TensorFlow — falling back to CPU."
        )
        return False

    try:
        if gpu_index is not None:
            tf.config.set_visible_devices(gpus[gpu_index], "GPU")
            gpus = [gpus[gpu_index]]
        if memory_growth:
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
        logging.info(f"[TransNetV2] Using GPU(s): {[g.name for g in gpus]}")
        return True
    except RuntimeError as e:
        logging.warning(f"[TransNetV2] Could not configure GPU: {e}")
        return False

import sys
def load_transnetv2_model(weights_dir: str, use_gpu: bool = True, gpu_index: int | None = None):
    """Load a TransNetV2 model instance once, to be reused across videos."""
    # raise RuntimeError("I ENTERED load_transnetv2_model")
    # print("DEBUG TransNetV2 symbol:", TransNetV2, file=sys.stderr, flush=True)
    
    if use_gpu:
        configure_gpu(gpu_index=gpu_index)
    else:
        import tensorflow as tf
        tf.config.set_visible_devices([], "GPU")

    try:
        from aic51.resources import TransNetV2
    except ImportError as e:
        raise ImportError(
            "Could not import TransNetV2. Clone https://github.com/soCzech/TransNetV2 "
            "and add its `inference/` directory to PYTHONPATH."
        ) from e

    model = TransNetV2(model_dir=weights_dir)

    # print("DEBUG created model:", model, file=sys.stderr, flush=True)
    # print("DEBUG created type:", type(model), file=sys.stderr, flush=True)

    return model


def get_scene_cuts(
    video_path: str | Path,
    weights_dir: str | None = None,
    threshold: float = 0.5,
    use_gpu: bool = True,
    gpu_index: int | None = None,
    _model=None,
):
    """
    Run TransNetV2 on a video and return scene boundaries.

    Args:
        video_path: Path to the video file.
        weights_dir: Path to TransNetV2 pretrained weights. Required unless
                     `_model` is passed directly.
        threshold: Transition probability threshold (default 0.5).
        use_gpu / gpu_index: GPU configuration, ignored if `_model` is passed.
        _model: A pre-loaded TransNetV2 instance (from load_transnetv2_model),
                to avoid reloading weights for every video.

    Returns:
        List of (start_frame, end_frame) tuples covering the whole video.
    """
    # raise RuntimeError("I ENTERED load_transnetv2_model")


    # if _model is None:
    #     if not weights_dir:
    #         raise ValueError("weights_dir is required when _model is not provided")
    _model = load_transnetv2_model(weights_dir, use_gpu=use_gpu, gpu_index=gpu_index)

    _video_frames, single_frame_predictions, _all_frame_predictions = (
        _model.predict_video(str(video_path))
    )
    scenes = _model.predictions_to_scenes(single_frame_predictions, threshold=threshold)
    return [(int(start), int(end)) for start, end in scenes]