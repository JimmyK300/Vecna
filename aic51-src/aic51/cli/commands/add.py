import json
import os
import shutil
import subprocess
import sys
import wave
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.utils.provenance import ProvenanceStore, implementation_fingerprint

from .command import BaseCommand


class AddCommand(BaseCommand):
    SUPPORTED_EXT = [
        ".mp4",
    ]

    def __init__(self, *args, **kwargs):
        super(AddCommand, self).__init__(*args, **kwargs)
        self._provenance = ProvenanceStore(self._work_dir)

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
            "--clip-length",
            dest="clip_length",
            type=float,
            default=None,
            help="Length of each video clip in seconds (default: 5.0s or from config)",
        )
        parser.add_argument(
            "--min-clip-gap",
            dest="min_clip_gap",
            type=float,
            default=None,
            help="Minimum temporal gap (seconds) between consecutive video clips (default: 4.0s or from config)",
        )
        parser.add_argument(
            "-g",
            "--gpu",
            dest="use_gpu",
            action="store_true",
            help="Use GPU hardware acceleration (NVENC) for fast video clip generation",
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
        clip_length: float | None = None,
        min_clip_gap: float | None = None,
        use_gpu: bool = False,
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
            clip_length=clip_length,
            min_clip_gap=min_clip_gap,
            use_gpu=use_gpu,
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
        clip_length: float | None = None,
        min_clip_gap: float | None = None,
        use_gpu: bool = False,
    ):
        max_workers_ratio = GlobalConfig.get("max_workers_ratio") or 0
        max_workers = max(
            1,
            min(int(max_workers_ratio * (os.cpu_count() or 0)), 8),
        )
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
                    description="Processing...",
                    name=video_path.name,
                )
                try:
                    status_ok, output_path, video_id = self._load_video(
                        video_path,
                        do_move,
                        do_overwrite,
                        show_progress(task_id),
                    )
                    # Register the exact stored bytes before any optional re-encode.
                    self._provenance.ensure_source(video_id, refresh=True)

                    if do_move:
                        video_path = output_path

                    if status_ok and do_compress and do_compress_first:
                        self._compress_video(video_id, show_progress(task_id))
                        self._extract_video_info(output_path)
                        self._provenance.ensure_source(video_id, refresh=True)

                    if do_audio:
                        self._extract_audio(video_path, do_overwrite, show_progress(task_id))

                    if do_keyframe or do_clip:
                        self._extract_keyframes(
                            output_path,
                            video_path,
                            do_overwrite,
                            do_audio,
                            do_clip,
                            show_progress(task_id),
                            clip_length=clip_length,
                            min_clip_gap=min_clip_gap,
                            use_gpu=use_gpu,
                        )

                    if status_ok and do_compress and not do_compress_first:
                        self._compress_video(video_id, show_progress(task_id))
                        self._extract_video_info(output_path)
                        self._provenance.ensure_source(video_id, refresh=True)
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

            futures = [executor.submit(add_one_video, path) for path in video_paths]
            for future in futures:
                future.result()

    def _load_video(
        self,
        video_path: Path,
        do_move: bool,
        do_overwrite: bool,
        update_progress: Callable,
    ):
        update_progress(description="Saving video", completed=0, total=1)

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

    def _record_keyframe_provenance(
        self,
        video_id: str,
        keyframe_dir: Path,
        *,
        video_fps: float | int,
        max_scene_length_seconds: float,
        keyframe_ratio: float,
        thumbnail_ratio: float,
        default_size: list[int],
        do_clip: bool,
    ):
        frame_ids = sorted(
            p.stem
            for p in keyframe_dir.glob("*")
            if p.is_file() and not p.stem.startswith(".")
        )
        self._provenance.record_keyframe_generation(
            video_id,
            frame_ids,
            producer_identity={
                "name": "aic51.add.keyframe_selection",
                "implementation": implementation_fingerprint(self),
            },
            producer_configuration={
                "selection_rule": "ffprobe_packet_keyframes_plus_max_scene_gap",
                "frame_rate_used": video_fps,
                "max_scene_length_seconds": max_scene_length_seconds,
                "keyframe_resize_ratio": keyframe_ratio,
                "thumbnail_resize_ratio": thumbnail_ratio,
                "default_size": default_size,
                "clip_path_enabled": do_clip,
                "jpeg_quality": 50,
            },
        )

    def _extract_clips_from_existing_keyframes(
        self,
        video_path: Path,
        keyframe_dir: Path,
        video_clips_dir: Path,
        clip_length: float,
        min_clip_gap: float,
        use_gpu: bool,
        update_progress: Callable,
    ):
        video_clips_dir.mkdir(parents=True, exist_ok=True)
        video_fps = self._get_fps(video_path)
        min_clip_gap_frames = int(round(min_clip_gap * video_fps))

        keyframe_files = sorted(
            [
                p
                for p in keyframe_dir.glob("*")
                if p.is_file() and p.suffix.lower() in [".jpg", ".png", ".jpeg"]
            ],
            key=lambda p: p.stem,
        )
        if not keyframe_files:
            return

        frame_indices = []
        for kf in keyframe_files:
            try:
                frame_indices.append(int(kf.stem))
            except ValueError:
                pass
        frame_indices.sort()

        selected_frames = []
        if frame_indices:
            selected_frames.append(frame_indices[0])
            last_f = frame_indices[0]
            for f in frame_indices[1:]:
                if f - last_f >= min_clip_gap_frames:
                    selected_frames.append(f)
                    last_f = f

        update_progress(
            description="Clipping with GPU" if use_gpu else "Clipping",
            completed=0,
            total=len(selected_frames),
        )

        half_len_sec = clip_length / 2.0
        tasks = []
        for f_idx in selected_frames:
            out_clip = video_clips_dir / f"{f_idx:06d}.mp4"
            if out_clip.exists() and out_clip.stat().st_size > 1024:
                update_progress(advance=1)
                continue
            center_sec = f_idx / video_fps
            start_sec = max(0.0, center_sec - half_len_sec)
            tasks.append((out_clip, start_sec))

        if not tasks:
            return

        def _cut(out_clip: Path, start_sec: float):
            if use_gpu:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-hwaccel",
                    "cuda",
                    "-ss",
                    f"{start_sec:.3f}",
                    "-t",
                    f"{clip_length:.3f}",
                    "-i",
                    str(video_path),
                    "-c:v",
                    "h264_nvenc",
                    "-preset",
                    "p1",
                    "-b:v",
                    "3M",
                    "-maxrate",
                    "4M",
                    "-bufsize",
                    "8M",
                    "-an",
                    str(out_clip),
                ]
                res = subprocess.run(cmd, capture_output=True)
                if res.returncode == 0 and out_clip.exists() and out_clip.stat().st_size > 1024:
                    return True

            cmd_cpu = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start_sec:.3f}",
                "-t",
                f"{clip_length:.3f}",
                "-i",
                str(video_path),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-an",
                str(out_clip),
            ]
            res_cpu = subprocess.run(cmd_cpu, capture_output=True)
            return res_cpu.returncode == 0 and out_clip.exists() and out_clip.stat().st_size > 1024

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_cut, out_clip, s_sec) for out_clip, s_sec in tasks]
            for fut in futures:
                fut.result()
                update_progress(advance=1)

    def _extract_keyframes(
        self,
        video_path: Path,
        raw_video_path: Path,
        do_overwrite: bool,
        do_audio: bool,
        do_clip: bool,
        update_progress: Callable,
        clip_length: float | None = None,
        min_clip_gap: float | None = None,
        use_gpu: bool = False,
    ):
        audio_path = self._work_dir / constant.AUDIO_DIR / f"{video_path.stem}.wav"
        keyframe_dir = self._work_dir / constant.KEYFRAME_DIR / video_path.stem
        thumbnail_dir = self._work_dir / constant.THUMBNAIL_DIR / video_path.stem
        video_clips_dir = self._work_dir / constant.VIDEO_CLIP_DIR / video_path.stem
        audio_clips_dir = self._work_dir / constant.AUDIO_CLIP_DIR / video_path.stem

        if keyframe_dir.exists() and (
            not do_clip
            or (video_clips_dir.exists() and any(video_clips_dir.glob("*.mp4")))
        ):
            if do_overwrite:
                shutil.rmtree(keyframe_dir)
                if thumbnail_dir.exists():
                    shutil.rmtree(thumbnail_dir)
                if video_clips_dir.exists():
                    shutil.rmtree(video_clips_dir)
            else:
                # Existing pre-v1 frames are registered truthfully as observed;
                # their historical producer/configuration remains unknown.
                self._provenance.ensure_keyframe_generation(video_path.stem)
                return
        elif do_overwrite:
            if keyframe_dir.exists():
                shutil.rmtree(keyframe_dir)
            if thumbnail_dir.exists():
                shutil.rmtree(thumbnail_dir)
            if video_clips_dir.exists():
                shutil.rmtree(video_clips_dir)

        if keyframe_dir.exists() and not do_overwrite and do_clip:
            actual_clip_length = (
                clip_length
                if clip_length is not None
                else (GlobalConfig.get("add", "clip_length") or 5.0)
            )
            actual_min_clip_gap = (
                min_clip_gap
                if min_clip_gap is not None
                else (GlobalConfig.get("add", "min_clip_gap") or 4.0)
            )
            self._extract_clips_from_existing_keyframes(
                video_path=video_path,
                keyframe_dir=keyframe_dir,
                video_clips_dir=video_clips_dir,
                clip_length=float(actual_clip_length),
                min_clip_gap=float(actual_min_clip_gap),
                use_gpu=use_gpu,
                update_progress=update_progress,
            )
            self._provenance.ensure_keyframe_generation(video_path.stem)
            return

        keyframe_dir.mkdir(parents=True, exist_ok=True)
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        if do_clip:
            video_clips_dir.mkdir(parents=True, exist_ok=True)
            if do_audio:
                audio_clips_dir.mkdir(parents=True, exist_ok=True)

        update_progress(description="Finding keyframes", completed=0, total=1)
        keyframes_list = self._get_keyframes_list(raw_video_path)
        keyframes_set = set(keyframes_list)
        update_progress(advance=1)
        video_fps = self._get_fps(video_path)

        max_scene_length_seconds = GlobalConfig.get("add", "max_scene_length") or 1
        max_scene_length = int(round(max_scene_length_seconds * video_fps))
        keyframe_ratio = GlobalConfig.get("add", "keyframe_resize_ratio") or 0.5
        thumbnail_ratio = GlobalConfig.get("add", "thumbnail_resize_ratio") or 0.25

        actual_clip_length = (
            clip_length
            if clip_length is not None
            else (GlobalConfig.get("add", "clip_length") or 5.0)
        )
        actual_min_clip_gap = (
            min_clip_gap
            if min_clip_gap is not None
            else (GlobalConfig.get("add", "min_clip_gap") or 4.0)
        )
        clip_length = float(actual_clip_length)
        min_clip_gap_seconds = float(actual_min_clip_gap)

        video_length = int(round(clip_length * video_fps))
        min_clip_gap_frames = int(round(min_clip_gap_seconds * video_fps))
        video_clip_fps = video_fps

        if do_audio:
            with wave.open(str(audio_path), "rb") as f:
                wave_params = f.getparams()
                audio_fps = f.getframerate()
                audio_frames = f.readframes(f.getnframes())
                audio_frame_size = f.getsampwidth() * f.getnchannels()

            audio_length = clip_length * audio_fps
            audio_clip_interval = audio_length // 7
        else:
            wave_params = audio_fps = audio_frames = audio_frame_size = audio_length = (
                audio_clip_interval
            ) = None

        update_progress(
            description="Extracting keyframes",
            completed=0,
            total=len(keyframes_list),
        )

        default_size = GlobalConfig.get("add", "default_size") or [1280, 720]
        target_w, target_h = default_size[0], default_size[1]
        cap = cv2.VideoCapture(str(video_path))

        if not do_clip:
            frame_counter = 0
            scene_length = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if scene_length >= max_scene_length or frame_counter in keyframes_set:
                    if frame.shape[1] == target_w and frame.shape[0] == target_h:
                        current_frame = frame
                    else:
                        current_frame = cv2.resize(frame, (target_w, target_h))

                    if keyframe_ratio == 1.0 or abs(keyframe_ratio - 1.0) < 1e-5:
                        keyframe_frame = current_frame
                    else:
                        keyframe_frame = cv2.resize(
                            current_frame,
                            None,
                            fx=keyframe_ratio,
                            fy=keyframe_ratio,
                        )

                    cv2.imwrite(
                        str(keyframe_dir / f"{frame_counter:06d}.jpg"),
                        keyframe_frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 50],
                    )

                    thumbnail = cv2.resize(
                        current_frame,
                        None,
                        fx=thumbnail_ratio,
                        fy=thumbnail_ratio,
                    )
                    cv2.imwrite(
                        str(thumbnail_dir / f"{frame_counter:06d}.jpg"),
                        thumbnail,
                        [cv2.IMWRITE_JPEG_QUALITY, 50],
                    )
                    scene_length = 0

                scene_length += 1
                frame_counter += 1

            update_progress(completed=len(keyframes_list))
            cap.release()
            self._record_keyframe_provenance(
                video_path.stem,
                keyframe_dir,
                video_fps=video_fps,
                max_scene_length_seconds=max_scene_length_seconds,
                keyframe_ratio=keyframe_ratio,
                thumbnail_ratio=thumbnail_ratio,
                default_size=default_size,
                do_clip=do_clip,
            )
            return

        video_frames = []
        frame_counter = 0
        scene_length = 0
        last_clip_frame = -min_clip_gap_frames

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

            video_frame_counter = frame_counter - video_length + 1

            if video_frame_counter in keyframes_set:
                update_progress(advance=1)

            if scene_length >= max_scene_length or video_frame_counter in keyframes_set:
                current_frame = video_frames[-video_length]

                if keyframe_ratio == 1.0 or abs(keyframe_ratio - 1.0) < 1e-5:
                    keyframe_frame = current_frame
                else:
                    keyframe_frame = cv2.resize(
                        current_frame,
                        None,
                        fx=keyframe_ratio,
                        fy=keyframe_ratio,
                    )

                cv2.imwrite(
                    str(keyframe_dir / f"{video_frame_counter:06d}.jpg"),
                    keyframe_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 50],
                )

                thumbnail = cv2.resize(
                    current_frame,
                    None,
                    fx=thumbnail_ratio,
                    fy=thumbnail_ratio,
                )
                cv2.imwrite(
                    str(thumbnail_dir / f"{video_frame_counter:06d}.jpg"),
                    thumbnail,
                    [cv2.IMWRITE_JPEG_QUALITY, 50],
                )

                if do_clip and not use_gpu and (video_frame_counter - last_clip_frame >= min_clip_gap_frames):
                    last_clip_frame = video_frame_counter
                    video_frame_center = len(video_frames) - video_length
                    half_len = video_length // 2
                    start_idx = max(0, video_frame_center - half_len)
                    end_idx = min(len(video_frames) - 1, video_frame_center + half_len)

                    clip_path = video_clips_dir / f"{video_frame_counter:06d}.mp4"
                    video_writer = cv2.VideoWriter(
                        str(clip_path),
                        cv2.VideoWriter_fourcc(*"mp4v"),
                        video_clip_fps,
                        (target_w, target_h),
                    )
                    for i in range(start_idx, end_idx + 1):
                        video_writer.write(video_frames[i])
                    video_writer.release()

                    if do_audio and audio_frames is not None and audio_frame_size:
                        audio_frame_counter = round(video_frame_counter / video_fps * audio_fps)
                        half_audio_len = int(round((clip_length / 2) * audio_fps))
                        audio_start = max(0, audio_frame_counter - half_audio_len)
                        audio_end = min(
                            len(audio_frames) // audio_frame_size,
                            audio_start + int(round(clip_length * audio_fps)),
                        )
                        audio_clip_path = audio_clips_dir / f"{video_frame_counter:06d}.wav"
                        with wave.open(str(audio_clip_path), "wb") as f_out:
                            f_out.setparams(wave_params)
                            f_out.writeframes(
                                audio_frames[
                                    audio_start * audio_frame_size : audio_end * audio_frame_size
                                ]
                            )

                scene_length = 0

            if video_frame_counter >= 0:
                scene_length += 1
            frame_counter += 1

        cap.release()

        if do_clip and use_gpu:
            self._extract_clips_from_existing_keyframes(
                video_path=video_path,
                keyframe_dir=keyframe_dir,
                video_clips_dir=video_clips_dir,
                clip_length=clip_length,
                min_clip_gap=min_clip_gap_seconds,
                use_gpu=True,
                update_progress=update_progress,
            )
        self._record_keyframe_provenance(
            video_path.stem,
            keyframe_dir,
            video_fps=video_fps,
            max_scene_length_seconds=max_scene_length_seconds,
            keyframe_ratio=keyframe_ratio,
            thumbnail_ratio=thumbnail_ratio,
            default_size=default_size,
            do_clip=do_clip,
        )

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
        return [i for i, line in enumerate(lines) if "K" in line]

    def _get_fps_info(self, video_path: Path) -> dict:
        ffprobe_cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-of",
            "compact=p=0",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate,avg_frame_rate",
            str(video_path),
        ]
        res = subprocess.run(ffprobe_cmd, capture_output=True, text=True)

        if not res.stdout.strip():
            ffprobe_cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-of",
                "compact=p=0",
                "-select_streams",
                "0",
                "-show_entries",
                "stream=r_frame_rate,avg_frame_rate",
                str(video_path),
            ]
            res = subprocess.run(ffprobe_cmd, capture_output=True, text=True)

        entry_dict = {}
        for item in res.stdout.strip().replace("stream|", "").split("|"):
            if "=" in item:
                k, v = item.split("=", 1)
                entry_dict[k] = v

        r_fps_str = entry_dict.get("r_frame_rate", "25/1")
        avg_fps_str = entry_dict.get("avg_frame_rate", r_fps_str)

        fps_fraction = None
        for cand in [r_fps_str, avg_fps_str]:
            if cand and cand != "0/0":
                try:
                    frac = Fraction(cand)
                    if frac > 0:
                        fps_fraction = frac
                        break
                except (ValueError, ZeroDivisionError):
                    continue

        if fps_fraction is None:
            fps_fraction = Fraction(constant.DEFAULT_FPS, 1)

        fps_float = float(fps_fraction)

        return {
            constant.FPS_KEY: fps_float,
            constant.FPS_FRACTION_KEY: str(fps_fraction),
            constant.R_FRAME_RATE_KEY: r_fps_str,
            constant.AVG_FRAME_RATE_KEY: avg_fps_str,
        }

    def _get_fps(self, video_path: Path) -> float:
        info = self._get_fps_info(video_path)
        return info[constant.FPS_KEY]

    def _extract_video_info(self, video_path: Path):
        info_file = self._work_dir / constant.VIDEO_INFO_DIR / f"{video_path.stem}.json"
        info_file.parent.mkdir(parents=True, exist_ok=True)

        data = self._get_fps_info(video_path)
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _extract_audio(
        self,
        video_path: Path,
        do_overwrite: bool,
        update_progress: Callable,
    ):
        audio_path = self._work_dir / constant.AUDIO_DIR / f"{video_path.stem}.wav"

        if audio_path.exists() and not do_overwrite:
            return

        audio_path.parent.mkdir(parents=True, exist_ok=True)

        update_progress(description="Extracting audio", completed=0, total=1)
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
