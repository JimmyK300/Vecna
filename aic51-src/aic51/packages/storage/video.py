import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
 
from rich.progress import Progress
 
import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.utils import get_executor, get_progress

class VideoStorage:
    def __init__(self, work_dir: Path):
        self._work_dir = work_dir
 
    def video_path(self, video_id: str, suffix: str) -> Path:
        return self._work_dir / constant.VIDEO_DIR / f"{video_id}{suffix}"
 
    def info_path(self, video_id: str) -> Path:
        return self._work_dir / constant.VIDEO_INFO_DIR / f"{video_id}.json"
 
    def find_video(self, video_id: str, supported_ext: list[str]) -> Optional[Path]:
        """Locate a stored video by id, regardless of its extension."""
        video_dir = self._work_dir / constant.VIDEO_DIR
        matches = [
            p for p in video_dir.glob(f"{video_id}.*")
            if p.suffix.lower() in supported_ext and not p.name.startswith("_")
        ]
        return matches[0] if matches else None
 
    def write_info(self, video_id: str, data: dict) -> None:
        path = self.info_path(video_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
