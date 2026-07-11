from glob import glob
from pathlib import Path
from typing import Tuple


def load_all_video_keyframes_info() -> Tuple[list[str], dict[str, list]]:
    """
    Create a list of video and list of keyframe
    """
    print("loading all videos and keyframes information")
    all_keyframe = glob("./data-staging/keyframes/*/*.jpg")
    video_keyframe_dict = {}
    all_video = sorted(
        path.stem
        for path in Path("data-source/videos").glob("*.mp4")
        if path.is_file()
    )

    print(f"loaded {len(all_keyframe)} keyframes")
    print(f"loaded {len(all_video)} videos")

    for kf in all_keyframe:
        keyframe_path = Path(kf)
        vid = keyframe_path.parent.name
        kf = keyframe_path.stem
        if vid not in video_keyframe_dict.keys():
            video_keyframe_dict[vid] = [kf]
        else:
            video_keyframe_dict[vid].append(kf)

    for k, v in video_keyframe_dict.items():
        video_keyframe_dict[k] = sorted(v)

    return all_video, video_keyframe_dict
