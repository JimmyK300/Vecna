import json
import subprocess
from pathlib import Path
 
import aic51.packages.constant as constant
from aic51.packages.logger import logger

class MetadataExtractor:
    @staticmethod
    def probe(video_path: Path) -> dict:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate,width,height,duration",
                "-of", "json", str(video_path),
            ],
            capture_output=True,
            text=True,
        )
 
        if result.returncode != 0:
            logger.warning(f"{video_path.name}: ffprobe failed, metadata will be incomplete")
            return {}
 
        streams = json.loads(result.stdout).get("streams") or [{}]
        stream = streams[0]
 
        fps = 0.0
        if "r_frame_rate" in stream:
            num, _, den = stream["r_frame_rate"].partition("/")
            den = den or "1"
            fps = float(num) / float(den) if float(den) else 0.0
 
        return {
            constant.FPS_KEY: fps,
            "width": stream.get("width"),
            "height": stream.get("height"),
            "duration": float(stream["duration"]) if stream.get("duration") else None,
        }
