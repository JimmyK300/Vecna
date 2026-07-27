import subprocess
from typing import Callable
 
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.storage import VideoStorage

class VideoCompressor:
    def __init__(self, store: VideoStorage, supported_ext: list[str]):
        self._store = store
        self._supported_ext = supported_ext
 
    def compress(self, video_id: str, update_progress: Callable) -> None:
        video_path = self._store.find_video(video_id, self._supported_ext)
        if video_path is None:
            logger.error(f"{video_id}: video file not found, skipping compression")
            return
 
        backup_path = video_path.with_name(f"_{video_path.name}")
        video_path.rename(backup_path)
 
        update_progress(description="Compressing video", completed=0, total=1)
 
        size_rate = GlobalConfig.get("add", "compress_size_rate") or 0.5
        base_size = GlobalConfig.get("add", "default_size") or [1280, 720]
        encoder = GlobalConfig.get("add", "video_encoder") or "h264_nvenc"
 
        # ffmpeg -i input.mp4 -vf scale="iw:ih" -c:v <encoder> -c:a aac -b:a 32k output.mp4 -y
        cmd = [
            "ffmpeg", "-v", "quiet", "-y",
            "-i", str(backup_path),
            "-vf", f"scale={base_size[0]}*{size_rate}:{base_size[1]}*{size_rate}",
            "-c:v", encoder,
            "-preset", "p4",
            "-cq", "28",
            "-c:a", "aac",
            "-b:a", "32k",
            str(video_path),
        ]
        result = subprocess.run(cmd)
 
        # Never lose the source video if ffmpeg fails or produced no output.
        if result.returncode != 0 or not video_path.exists():
            logger.error(f"{video_id}: compression failed, restoring original video")
            if backup_path.exists():
                backup_path.rename(video_path)
            update_progress(description="Compression failed")
            return
 
        backup_path.unlink()
        update_progress(advance=1)