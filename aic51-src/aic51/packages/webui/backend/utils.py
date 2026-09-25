import concurrent.futures
import csv
import json
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import aic51.packages.constant as constant
from aic51.packages.logger import logger


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


def _get_candidate_roots(video_id: str = ""):
    v_upper = str(video_id).upper()
    if v_upper.startswith("N"):
        return [
            Path.cwd() / "testcol2",
            Path.cwd() / "workspace2",
            Path("testcol2"),
            Path("workspace2"),
            Path.cwd() / "testcol1",
            Path.cwd() / "workspace",
            Path("testcol1"),
            Path("workspace"),
            Path.cwd(),
        ]
    elif any(v_upper.startswith(p) for p in ("S", "L", "M")):
        return [
            Path.cwd() / "testcol1",
            Path.cwd() / "workspace",
            Path("testcol1"),
            Path("workspace"),
            Path.cwd() / "testcol2",
            Path.cwd() / "workspace2",
            Path("testcol2"),
            Path("workspace2"),
            Path.cwd(),
        ]
    return [
        Path.cwd(),
        Path.cwd() / "testcol1",
        Path.cwd() / "testcol2",
        Path.cwd() / "workspace",
        Path.cwd() / "workspace2",
        Path("testcol1"),
        Path("testcol2"),
        Path("workspace"),
        Path("workspace2"),
    ]


def get_fps(video_id: str) -> float:
    for root in _get_candidate_roots(video_id):
        info_path = root / f"{constant.VIDEO_INFO_DIR}/{video_id}.json"
        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    val = float(data[constant.FPS_KEY])
                    if val > 0:
                        return val
            except Exception:
                pass

        # Also check map-keyframes CSV for true FPS
        for sub in ["map-keyframes", "data/map-keyframes", "workspace/map-keyframes"]:
            csv_path = root / sub / f"{video_id}.csv"
            if csv_path.exists():
                try:
                    with open(csv_path, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        first_row = next(reader, None)
                        if first_row and "fps" in first_row and first_row["fps"]:
                            val = float(first_row["fps"])
                            if val > 0:
                                return val
                except Exception:
                    pass

    return float(constant.DEFAULT_FPS)


def get_fps_info(video_id: str) -> dict:
    for root in _get_candidate_roots(video_id):
        info_path = root / f"{constant.VIDEO_INFO_DIR}/{video_id}.json"
        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {
                        constant.FPS_KEY: float(data.get(constant.FPS_KEY, constant.DEFAULT_FPS)),
                        constant.FPS_FRACTION_KEY: data.get(constant.FPS_FRACTION_KEY),
                        constant.R_FRAME_RATE_KEY: data.get(constant.R_FRAME_RATE_KEY),
                        constant.AVG_FRAME_RATE_KEY: data.get(constant.AVG_FRAME_RATE_KEY),
                    }
            except Exception:
                pass

        # Also check map-keyframes CSV
        for sub in ["map-keyframes", "data/map-keyframes", "workspace/map-keyframes"]:
            csv_path = root / sub / f"{video_id}.csv"
            if csv_path.exists():
                try:
                    with open(csv_path, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        first_row = next(reader, None)
                        if first_row and "fps" in first_row and first_row["fps"]:
                            val = float(first_row["fps"])
                            if val > 0:
                                return {
                                    constant.FPS_KEY: val,
                                    constant.FPS_FRACTION_KEY: f"{int(val)}/1",
                                    constant.R_FRAME_RATE_KEY: f"{int(val)}/1",
                                    constant.AVG_FRAME_RATE_KEY: f"{int(val)}/1",
                                }
                except Exception:
                    pass

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
    if include_traceability:
        from aic51.packages.search.traceability import (
            build_result_traceability,
            load_current_index_generation,
        )
        if traceability_collection:
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
            "collection": record.get("collection", ""),
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
