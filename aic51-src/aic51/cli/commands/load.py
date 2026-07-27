import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable
from dataclasses import dataclass

from rich.progress import Progress

from aic51.packages.utils import get_executor, get_progress
import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.load import MetadataExtractor, VideoCompressor
from aic51.packages.storage import VideoStorage
from .command import BaseCommand

@dataclass
class AddOptions:
    do_move: bool = False
    do_overwrite: bool = False
    do_compress: bool = False

@dataclass
class AddResult:
    added: bool  # False if the video already existed and wasn't overwritten
    video_id: str
    output_path: Path

class VideoIngestor:
    def __init__(self, store: VideoStorage, compressor: VideoCompressor):
        self._store = store
        self._compressor = compressor
 
    def ingest(self, video_path: Path, options: AddOptions, update_progress: Callable) -> AddResult:
        video_id = video_path.stem
        output_path = self._store.video_path(video_id, video_path.suffix)
 
        if output_path.exists() and not options.do_overwrite:
            update_progress(description="Already exists, skipped", completed=1, total=1)
            return AddResult(added=False, video_id=video_id, output_path=output_path)
 
        update_progress(description="Saving video", completed=0, total=1)
        output_path.parent.mkdir(parents=True, exist_ok=True)
 
        if options.do_move:
            shutil.move(video_path, output_path)
        else:
            shutil.copy(video_path, output_path)
 
        metadata = MetadataExtractor.probe(output_path)
        self._store.write_info(video_id, metadata)
        update_progress(advance=1)
 
        if options.do_compress:
            self._compressor.compress(video_id, update_progress)
 
        return AddResult(added=True, video_id=video_id, output_path=output_path)

class LoadCommand(BaseCommand):
    SUPPORTED_EXT = [".mp4"]
 
    def __init__(self, work_dir: Path, *args, **kwargs):
        super().__init__(work_dir, *args, **kwargs)
        store = VideoStorage(work_dir)
        compressor = VideoCompressor(store, self.SUPPORTED_EXT)
        self._ingestor = VideoIngestor(store, compressor)
 
    def add_args(self, subparser):
        parser = subparser.add_parser("load", help="Load video(s) into the work directory")
        parser.add_argument("video_path", type=str, help="Path to a video file or directory")
        parser.add_argument(
            "-d", "--directory", dest="do_multi", action="store_true",
            help="Treat video_path as a directory",
        )
        parser.add_argument(
            "-m", "--move", dest="do_move", action="store_true",
            help="Move instead of copy (source must be on this machine)",
        )
        parser.add_argument(
            "-o", "--overwrite", dest="do_overwrite", action="store_true",
            help="Overwrite existing files",
        )
        parser.add_argument(
            "-C", "--compress", dest="do_compress", action="store_true",
            help="Compress videos after loading",
        )
        parser.set_defaults(func=self)
 
    def __call__(
        self,
        video_path: str | Path,
        do_multi: bool,
        do_move: bool,
        do_overwrite: bool,
        do_compress: bool,
        verbose: bool,
        *args,
        **kwargs,
    ):
        video_paths = self._resolve_video_paths(Path(video_path), do_multi)
        options = AddOptions(do_move=do_move, do_overwrite=do_overwrite, do_compress=do_compress)
        self._add_videos(video_paths, options, verbose)
 
    def _resolve_video_paths(self, video_path: Path, do_multi: bool) -> list[Path]:
        if not video_path.exists():
            logger.error(f"{video_path}: No such file or directory")
            sys.exit(1)
 
        if do_multi:
            if not video_path.is_dir():
                logger.error(f"{video_path}: Not a directory")
                sys.exit(1)
            paths = [
                p for p in video_path.glob("*")
                if p.is_file() and p.suffix.lower() in self.SUPPORTED_EXT
            ]
        else:
            if video_path.is_dir():
                logger.error(f"{video_path}: Not a file")
                sys.exit(1)
            if video_path.suffix.lower() not in self.SUPPORTED_EXT:
                logger.error(f"{video_path}: Unsupported file type")
                sys.exit(1)
            paths = [video_path]
 
        return sorted(paths, key=lambda p: p.stem)
 
    def _add_videos(self, video_paths: list[Path], options: AddOptions, verbose: bool) -> None:
        with (
            get_progress(disable=not verbose) as progress,
            get_executor() as executor,
        ):
            futures = [
                executor.submit(self._add_one_video, path, options, progress)
                for path in video_paths
            ]
            for f in futures:
                f.result()
 
    def _add_one_video(self, video_path: Path, options: AddOptions, progress: Progress) -> None:
        task_id = progress.add_task(description="Processing...", name=video_path.name)
        update_progress = lambda **kwargs: progress.update(task_id, **kwargs)
 
        try:
            self._ingestor.ingest(video_path, options, update_progress)
            progress.remove_task(task_id)
        except Exception as e:
            logger.exception(e)
            progress.update(task_id, description=f"Error: {e}")