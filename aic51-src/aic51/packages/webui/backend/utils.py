import concurrent.futures
import json
import logging
from urllib.parse import urljoin, urlparse

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import aic51.packages.constant as constant
from aic51.packages.logger import logger
from aic51.packages.provenance import runtime_provenance


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


def get_fps(video_id: str):
    try:
        with open(f"{constant.VIDEO_INFO_DIR}/{video_id}.json", "r") as f:
            fps = float(json.load(f)[constant.FPS_KEY])
    except:
        fps = constant.DEFAULT_FPS

    return fps


def _frame_time_bounds(frame_ids: list[str], fps: float) -> tuple[int | None, int | None]:
    numeric_ids = []
    for frame_id in frame_ids:
        try:
            numeric_ids.append(int(frame_id))
        except (TypeError, ValueError):
            continue
    if not numeric_ids or not fps:
        return None, None
    return round(min(numeric_ids) * 1000 / fps), round(max(numeric_ids) * 1000 / fps)


def process_searcher_results(searcher_res: dict):
    provenance = runtime_provenance(collection_name=searcher_res.get("collection_name"))
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
        scores = record.get("scores") or {}
        component_scores = {
            key: value for key, value in scores.items() if key in {"clip", "ocr", "asr"}
        }
        matched_modalities = [key for key, value in component_scores.items() if value > 0]
        start_ms, end_ms = _frame_time_bounds([str(item) for item in time_line], fps)

        frames.append(
            {
                "id": record_id,
                "video_id": video_id,
                "frame_id": frame_id,
                "time_line": time_line,
                "time_line_scores": record.get("time_line_scores", [record.get("scores")]),
                "fps": fps,
                "scores": record.get("scores", None),
                "result_schema_version": "2",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "evidence_type": "interval_projection" if len(time_line) > 1 else "frame_projection",
                "matched_modalities": matched_modalities,
                "matched_text": {
                    key: data.get(key)
                    for key in ("ocr", "asr")
                    if isinstance(data.get(key), str) and data.get(key)
                },
                "component_scores": component_scores,
                "fusion_method": record.get("fusion_method") or searcher_res.get("fusion_method"),
                "source_artifact_ids": [record_id],
                **provenance,
            }
        )

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
