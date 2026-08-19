import concurrent.futures
import json
import logging
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin, urlparse

import cv2
import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import aic51.packages.constant as constant
from aic51.packages.logger import logger
from aic51.packages.search.traceability import (
    build_result_traceability,
    load_current_index_generation,
)

from .video_catalog import AmbiguousVideoError, resolve_video_path


def create_app(*args, **kwargs):
    app = FastAPI(*args, **kwargs)
    origins = [
        "*",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


@lru_cache(maxsize=1024)
def get_fps(video_id: str):
    """Return the FPS used to translate frame IDs into playback time.

    Older workspaces may not have ``data/video_info`` for externally mounted
    videos. In that case, read the FPS from the source media instead of using
    the historical 25 FPS fallback.
    """

    # The source media is authoritative. A sidecar can be stale, especially
    # for externally mounted videos whose metadata was never regenerated.
    try:
        video_path = resolve_video_path(video_id)
        if video_path is not None:
            capture = cv2.VideoCapture(str(video_path))
            try:
                fps = float(capture.get(cv2.CAP_PROP_FPS))
            finally:
                capture.release()
            if fps > 0:
                return fps
    except (AmbiguousVideoError, OSError, TypeError, ValueError):
        pass

    # Keep legacy workspaces usable when the source media is unavailable.
    try:
        with open(f"{constant.VIDEO_INFO_DIR}/{video_id}.json", "r") as f:
            fps = float(json.load(f)[constant.FPS_KEY])
        if fps > 0:
            return fps
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass

    return constant.DEFAULT_FPS


def get_fps_info(video_id: str) -> dict:
    try:
        with open(f"{constant.VIDEO_INFO_DIR}/{video_id}.json", "r") as f:
            data = json.load(f)
            return {
                constant.FPS_KEY: float(data.get(constant.FPS_KEY, constant.DEFAULT_FPS)),
                constant.FPS_FRACTION_KEY: data.get(constant.FPS_FRACTION_KEY),
                constant.R_FRAME_RATE_KEY: data.get(constant.R_FRAME_RATE_KEY),
                constant.AVG_FRAME_RATE_KEY: data.get(constant.AVG_FRAME_RATE_KEY),
            }
    except:
        return {
            constant.FPS_KEY: float(constant.DEFAULT_FPS),
            constant.FPS_FRACTION_KEY: f"{constant.DEFAULT_FPS}/1",
            constant.R_FRAME_RATE_KEY: f"{constant.DEFAULT_FPS}/1",
            constant.AVG_FRAME_RATE_KEY: f"{constant.DEFAULT_FPS}/1",
        }


def process_searcher_results(
    searcher_res: dict,
    *,
    include_traceability: bool = False,
    work_dir: Path | str | None = None,
    traceability_collection: str | None = None,
    traceability_features: list[str] | None = None,
):
    resolved_work_dir = Path(work_dir) if work_dir is not None else Path.cwd()
    index_generation = None
    if include_traceability and traceability_collection:
        index_generation = load_current_index_generation(
            resolved_work_dir,
            traceability_collection,
        )

    frames = []
    for record in searcher_res["results"]:
        data = record["entity"]
        record_id = data["frame_id"]  # <video_id>#<frame_id>
        video_id, frame_id = record_id.split("#")

        if "time_line" in record:
            time_line = record["time_line"]
        else:
            time_line = [frame_id]

        fps = get_fps(video_id)

        frame = {
            "id": record_id,
            "video_id": video_id,
            "frame_id": frame_id,
            "time_line": time_line,
            "time_line_scores": record.get("time_line_scores", [record.get("scores")]),
            "fps": fps,
            "scores": record.get("scores", None),
            "ocr": data.get("ocr", ""),
            "asr": data.get("asr", ""),
        }
        if include_traceability:
            frame["traceability"] = build_result_traceability(
                resolved_work_dir,
                video_id=video_id,
                frame_id=frame_id,
                fps=fps,
                collection_name=traceability_collection,
                feature_names=traceability_features,
                index_generation=index_generation,
            )
        frames.append(frame)

    return {
        constant.RESULT_TOTAL_KEY: searcher_res["total"],
        constant.RESULT_FRAMES_KEY: frames,
        constant.RESULT_OFFSET_KEY: searcher_res["offset"],
    }


def process_search_results(request, results):
    for id, frame in enumerate(results["frames"]):
        results["frames"][id] = process_frame_info(request, frame)
    return results


def process_frame_info(request, frame):
    domain = str(request.base_url)
    if frame.get("frame_uri"):
        frame_uri = urlparse(frame["frame_uri"])
        frame["frame_uri"] = urljoin(domain, frame_uri.path)
    if frame.get("video_uri"):
        video_uri = urlparse(frame["video_uri"])
        frame["video_uri"] = urljoin(domain, video_uri.path)
    return frame
