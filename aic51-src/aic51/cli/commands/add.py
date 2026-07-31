import json
import os
import shutil
import subprocess
import sys
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from .command import BaseCommand

class AddCommand(BaseCommand):
    SUPPORTED_EXT = [
        ".mp4",
    ]

    def __init__(self, *args, **kwargs):
        super(AddCommand, self).__init__(*args, **kwargs)

    def add_args(self, subparser):
        parser = subparser.add_parser("add", help="Add video(s) to the work directory")
        parser.add_argument(
            "video_path",
            type=str,
            help="Path to video(s)",
        )
        parser.add_argument(
            "-d",
            "--directory",
            dest="do_multi",
            action="store_true",
            help="Treat video_path as directory",
        )
        parser.add_argument(
            "-m",
            "--move",
            dest="do_move",
            action="store_true",
            help="Move video(s) (only valid if video(s) are on this machine)",
        )
        parser.add_argument(
            "-o",
            "--overwrite",
            dest="do_overwrite",
            action="store_true",
            help="Overwrite existing files",
        )
        parser.add_argument(
            "-k",
            "--keyframe",
            dest="do_keyframe",
            action="store_true",
            help="Extract keyframes",
        )
        parser.add_argument(
            "-a",
            "--audio",
            dest="do_audio",
            action="store_true",
            help="Extract audio",
        )
        parser.add_argument(
            "-c",
            "--clip",
            dest="do_clip",
            action="store_true",
            help="Extract to clips",
        )
        parser.add_argument(
            "-C",
            "--compress",
            dest="do_compress",
            action="store_true",
            help="Compress videos",
        )
        parser.add_argument(
            "--compress-first",
            dest="do_compress_first",
            action="store_true",
            help="Compress the video right after loading",
        )

        parser.set_defaults(func=self)

    def __call__(
        self,
        video_path: str | Path,
        do_multi: bool,
        do_move: bool,
        do_overwrite: bool,
        do_keyframe: bool,
        do_audio: bool,
        do_clip: bool,
        do_compress: bool,
        do_compress_first: bool,
        verbose: bool,
        *args,
        **kwargs,
    ):
        video_path = Path(video_path)

        if not video_path.exists():
            logger.error(f"{video_path}: No such file or directory")
            sys.exit(1)

        if do_multi:
            video_paths = [
                v
                for v in video_path.glob("*")
                if v.suffix.lower() in self.SUPPORTED_EXT and not v.is_dir()
            ]
        else:
            if video_path.is_dir():
                self._logger.error(f"{video_path}: Not a file")
                sys.exit(1)

            video_paths = [video_path]

        video_paths = sorted(video_paths, key=lambda path: path.stem)
        self._add_videos(
            video_paths,
            do_move,
            do_overwrite,
            do_keyframe,
            do_audio,
            do_clip,
            do_compress,
            do_compress_first,
            verbose,
        )

    def _add_videos(
        self,
        video_paths: list[Path],
        do_move: bool,
        do_overwrite: bool,
        do_keyframe: bool,
        do_audio: bool,
        do_clip: bool,
        do_compress: bool,
        do_compress_first: bool,
        verbose: bool,
    ):
        max_workers_ratio = GlobalConfig.get("max_workers_ratio") or 0
        max_workers = max(1, min(int(max_workers_ratio * (os.cpu_count() or 0)), 8))  # Scale to 8 workers for 60-80% GPU utilization
        with (
            Progress(
                TextColumn("{task.fields[name]}"),
                TextColumn(":"),
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                disable=not verbose,
                transient=True,
            ) as progress,
            ThreadPoolExecutor(max_workers) as executor,
        ):

            def show_progress(task_id):
                return lambda **kwargs: progress.update(task_id, **kwargs)

            def add_one_video(video_path: Path):
                task_id = progress.add_task(
                    description=f"Processing...",
                    name=video_path.name,
                )
                try:
                    status_ok, output_path, video_id = self._load_video(
                        video_path,
                        do_move,
                        do_overwrite,
                        show_progress(task_id),
                    )

                    if do_move:
                        video_path = output_path

                    if status_ok and do_compress and do_compress_first:
                        self._compress_video(video_id, show_progress(task_id))

                    if do_audio:
                        self._extract_audio(video_path, do_overwrite, show_progress(task_id))

                    if do_keyframe:
                        self._extract_keyframes(
                            output_path,
                            video_path,
                            do_overwrite,
                            do_audio,
                            do_clip,
                            show_progress(task_id),
                        )

                    if status_ok and do_compress and not do_compress_first:
                        self._compress_video(video_id, show_progress(task_id))
                except Exception as e:
                    logger.exception(e)
                    progress.update(
                        task_id,
                        description=f"Error: {str(e)}",
                    )
                finally:
                    try:
                        progress.remove_task(task_id)
                    except Exception:
                        pass

            futures = []
            for path in video_paths:
                futures.append(executor.submit(add_one_video, path))
            for f in futures:
                f.result()

    def _load_video(
        self, video_path: Path, do_move: bool, do_overwrite: bool, update_progress: Callable
    ):
        update_progress(description=f"Saving video", completed=0, total=1)

        video_id = video_path.stem
        output_path = self._work_dir / constant.VIDEO_DIR / f"{video_id}{video_path.suffix}"

        if output_path.exists() and not do_overwrite:
            return 0, output_path, video_id

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if do_move:
            shutil.move(video_path, output_path)
        else:
            shutil.copy(video_path, output_path)

        self._extract_video_info(output_path)

        update_progress(advance=1)

        return 1, output_path, video_id

    def _extract_keyframes(
        self,
        video_path: Path,
        raw_video_path: Path,
        do_overwrite: bool,
        do_audio: bool,
        do_clip: bool,
        update_progress: Callable,
    ):
        audio_path = self._work_dir / constant.AUDIO_DIR / f"{video_path.stem}.wav"
        keyframe_dir = self._work_dir / constant.KEYFRAME_DIR / f"{video_path.stem}"
        thumbnail_dir = self._work_dir / constant.THUMBNAIL_DIR / f"{video_path.stem}"
        video_clips_dir = self._work_dir / constant.VIDEO_CLIP_DIR / f"{video_path.stem}"
        audio_clips_dir = self._work_dir / constant.AUDIO_CLIP_DIR / f"{video_path.stem}"

        if keyframe_dir.exists():
            if do_overwrite:
                shutil.rmtree(keyframe_dir)
                if thumbnail_dir.exists():
                    shutil.rmtree(thumbnail_dir)
                if video_clips_dir.exists():
                    shutil.rmtree(video_clips_dir)
            else:
                return

        keyframe_dir.mkdir(parents=True, exist_ok=True)
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        if do_clip:
            video_clips_dir.mkdir(parents=True, exist_ok=True)
            if do_audio:
                audio_clips_dir.mkdir(parents=True, exist_ok=True)

        update_progress(description=f"Finding keyframes", completed=0, total=1)
        keyframes_list = self._get_keyframes_list(raw_video_path)
        keyframes_set = set(keyframes_list)
        update_progress(advance=1)
        video_fps = self._get_fps(video_path)

        max_scene_length = GlobalConfig.get("add", "max_scene_length") or 1  # in seconds
        max_scene_length = max_scene_length * video_fps  # in frames
        keyframe_ratio = GlobalConfig.get("add", "keyframe_resize_ratio") or 0.5
        thumbnail_ratio = GlobalConfig.get("add", "thumbnail_resize_ratio") or 0.25
        clip_length = GlobalConfig.get("add", "clip_length") or 7  # in seconds

        video_length = clip_length * video_fps  # in frames
        video_clip_fps = max(1, int(1 / (video_length / video_fps)))
        video_clip_interval = video_length // 7

        if do_audio:
            with wave.open(str(audio_path), "rb") as f:
                wave_params = f.getparams()
                audio_fps = f.getframerate()
                audio_frames = f.readframes(f.getnframes())
                audio_frame_size = f.getsampwidth() * f.getnchannels()

            audio_length = clip_length * audio_fps  # in frames
            audio_clip_interval = audio_length // 7
        else:
            wave_params = audio_fps = audio_frames = audio_frame_size = audio_length = (
                audio_clip_interval
            ) = None

        update_progress(description=f"Extracting keyframes", completed=0, total=len(keyframes_list))

        default_size = GlobalConfig.get("add", "default_size") or [1280, 720]
        target_w, target_h = default_size[0], default_size[1]
        cap = cv2.VideoCapture(str(video_path))

        # Fast path when video clips are not required (e.g. add -d -ka)
        if not do_clip:
            _frame_counter = 0
            scene_length = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if scene_length >= max_scene_length or _frame_counter in keyframes_set:
                    if frame.shape[1] == target_w and frame.shape[0] == target_h:
                        current_frame = frame
                    else:
                        current_frame = cv2.resize(frame, (target_w, target_h))

                    if keyframe_ratio == 1.0 or abs(keyframe_ratio - 1.0) < 1e-5:
                        keyframe_frame = current_frame
                    else:
                        keyframe_frame = cv2.resize(
                            current_frame, None, fx=keyframe_ratio, fy=keyframe_ratio
                        )

                    cv2.imwrite(
                        str(keyframe_dir / f"{_frame_counter:06d}.jpg"),
                        keyframe_frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 50],
                    )

                    thumbnail = cv2.resize(current_frame, None, fx=thumbnail_ratio, fy=thumbnail_ratio)
                    cv2.imwrite(
                        str(thumbnail_dir / f"{_frame_counter:06d}.jpg"),
                        thumbnail,
                        [cv2.IMWRITE_JPEG_QUALITY, 50],
                    )
                    scene_length = 0

                scene_length += 1
                _frame_counter += 1

            update_progress(completed=len(keyframes_list))
            cap.release()
            return

        # Full sequential path with sliding window buffer when do_clip is True
        video_frames = []
        _frame_counter = 0
        scene_length = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame.shape[1] == target_w and frame.shape[0] == target_h:
                default_size_frame = frame
            else:
                default_size_frame = cv2.resize(frame, (target_w, target_h))

            video_frames.append(default_size_frame)

            if len(video_frames) >= 2 * video_length:
                video_frames.pop(0)

            video_frame_counter = _frame_counter - video_length + 1

            if video_frame_counter in keyframes_set:
                update_progress(advance=1)

            if scene_length >= max_scene_length or video_frame_counter in keyframes_set:
                current_frame = video_frames[-video_length]

                if keyframe_ratio == 1.0 or abs(keyframe_ratio - 1.0) < 1e-5:
                    keyframe_frame = current_frame
                else:
                    keyframe_frame = cv2.resize(
                        current_frame, None, fx=keyframe_ratio, fy=keyframe_ratio
                    )

                cv2.imwrite(
                    str(keyframe_dir / f"{video_frame_counter:06d}.jpg"),
                    keyframe_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 50],
                )

                thumbnail = cv2.resize(current_frame, None, fx=thumbnail_ratio, fy=thumbnail_ratio)
                cv2.imwrite(
                    str(thumbnail_dir / f"{video_frame_counter:06d}.jpg"),
                    thumbnail,
                    [cv2.IMWRITE_JPEG_QUALITY, 50],
                )

                scene_length = 0

            if video_frame_counter >= 0:
                scene_length += 1
            _frame_counter += 1

        cap.release()

    def _get_keyframes_list(self, video_path: Path):
        ffprobe_cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-select_streams",
            "v:0",
            "-show_entries",
            "packet=flags",
            "-of",
            "csv",
            str(video_path),
        ]
        res = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        lines = [x for x in res.stdout.strip().split("\n") if x.startswith("packet")]
        keyframes_list = [i for i, line in enumerate(lines) if "K" in line]
        return keyframes_list

    def _extract_video_info(self, video_path: Path):
        info_file = self._work_dir / constant.VIDEO_INFO_DIR / f"{video_path.stem}.json"
        info_file.parent.mkdir(parents=True, exist_ok=True)

        data = {constant.FPS_KEY: self._get_fps(video_path)}
        with open(info_file, "w") as f:
            json.dump(data, f)

    def _get_fps(self, video_path: Path):
        ffprobe_cmd = ["ffprobe", "-v", "quiet", "-of", "compact=p=0"] + [
            "-select_streams",
            "0",
            "-show_entries",
            "stream=r_frame_rate",
            str(video_path),
        ]
        res = subprocess.run(ffprobe_cmd, capture_output=True, text=True)

        fraction = str(res.stdout).split("=")[1].split("/")
        fps = round(int(fraction[0]) / int(fraction[1]))

        return fps

    def _extract_audio(self, video_path: Path, do_overwrite: bool, update_progress: Callable):
        audio_path = self._work_dir / constant.AUDIO_DIR / f"{video_path.stem}.wav"

        if audio_path.exists() and not do_overwrite:
            return

        audio_path.parent.mkdir(parents=True, exist_ok=True)

        update_progress(description="Extracting audio", completed=0, total=1)
        # ffmpeg -i test.mp4 -ab 160k -ac 2 -ar 44100 -vn audio.wa
        ffmpeg_cmd = (
            ["ffmpeg", "-v", "quiet", "-y"]
            + ["-i", str(video_path)]
            + ["-ab", "160k", "-ac", "1", "-ar", "11000", "-vn", str(audio_path)]
        )
        subprocess.run(ffmpeg_cmd)

        update_progress(advance=1)

    def _compress_video(self, video_id: str, update_progress: Callable):
        video_path = self._work_dir / constant.VIDEO_DIR / f"{video_id}.mp4"
        video_path = video_path.rename(video_path.parent / f"_{video_path.stem}.mp4")

        output_path = self._work_dir / constant.VIDEO_DIR / f"{video_id}.mp4"
        compress_size_rate = GlobalConfig.get("add", "compress_size_rate") or 0.5

        update_progress(description="Compress video", completed=0, total=1)
        # ffmpeg -i input.mp4 -vf scale="iw:ih" -c:v libx264 -tune zerolatency -preset ultrafast -crf 40 -c:a aac -b:a 32k  output.mp4 -y
        default_size = GlobalConfig.get("add", "default_size") or [1280, 720]
        ffmpeg_cmd = (
            ["ffmpeg", "-hwaccel", "cuda", "-v", "quiet", "-y"]
            + ["-i", str(video_path)]
            + [
                "-vf",
                f"scale={default_size[0]}*{compress_size_rate}:{default_size[1]}*{compress_size_rate}",
            ]
            + [
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p4",
                "-cq",
                "28",
                "-c:a",
                "aac",
                "-b:a",
                "32k",
                str(output_path),
            ]
        )
        subprocess.run(ffmpeg_cmd)

        os.remove(video_path)

        update_progress(advance=1)
