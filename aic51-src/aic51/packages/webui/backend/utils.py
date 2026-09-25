import concurrent.futures
import json
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import subprocess
import sys
import shutil
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import aic51.packages.constant as constant
from aic51.packages.logger import logger
from aic51.packages.search.traceability import (
    build_result_traceability,
    load_current_index_generation,
)


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
            Path.cwd() / "workspace_2",
            Path("testcol2"),
            Path("workspace2"),
            Path("workspace_2"),
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
            Path.cwd() / "workspace_2",
            Path("testcol2"),
            Path("workspace2"),
            Path("workspace_2"),
            Path.cwd(),
        ]
    return [
        Path.cwd(),
        Path.cwd() / "testcol1",
        Path.cwd() / "testcol2",
        Path.cwd() / "workspace",
        Path.cwd() / "workspace2",
        Path.cwd() / "workspace_2",
        Path("testcol1"),
        Path("testcol2"),
        Path("workspace"),
        Path("workspace2"),
        Path("workspace_2"),
    ]


def get_fps(video_id: str) -> float:
    for root in _get_candidate_roots(video_id):
        info_path = root / f"{constant.VIDEO_INFO_DIR}/{video_id}.json"
        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return float(data[constant.FPS_KEY])
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


MPC_CANDIDATE_PATHS = [
    r"E:\Apps\MPC-HC\mpc-hc64.exe",
    r"C:\Program Files\MPC-HC\mpc-hc64.exe",
    r"C:\Program Files (x86)\MPC-HC\mpc-hc.exe",
    r"C:\Program Files\K-Lite Codec Pack\MPC-HC64\mpc-hc64.exe",
    r"C:\Program Files (x86)\K-Lite Codec Pack\MPC-HC64\mpc-hc64.exe",
]


def find_mpc_executable() -> Path | None:
    for p_str in MPC_CANDIDATE_PATHS:
        p = Path(p_str)
        if p.exists() and p.is_file():
            return p
    which_mpc = shutil.which("mpc-hc64.exe") or shutil.which("mpc-hc.exe")
    if which_mpc:
        return Path(which_mpc)
    return None


def find_local_video_file(video_id: str) -> Path | None:
    for root in _get_candidate_roots(video_id):
        for sub in [
            constant.VIDEO_DIR,
            "data/videos",
            "videos",
            "workspace/data/videos",
            "data/compressed_videos",
            "workspace/data/compressed_videos",
        ]:
            p = root / sub / f"{video_id}{constant.VIDEO_EXTENSION}"
            if p.exists() and p.is_file():
                return p.resolve()
        direct = root / f"{video_id}{constant.VIDEO_EXTENSION}"
        if direct.exists() and direct.is_file():
            return direct.resolve()
    return None


def open_video_in_mpc(video_id: str, frame_id: str | int) -> dict:
    mpc_path = find_mpc_executable()
    if not mpc_path:
        return {"status": "error", "message": "Không tìm thấy phần mềm MPC-HC trên máy."}

    video_path = find_local_video_file(video_id)
    if not video_path:
        return {"status": "error", "message": f"Không tìm thấy file video {video_id} trên ổ đĩa."}

    try:
        frame_num = int(str(frame_id).strip())
    except (ValueError, TypeError):
        frame_num = 0

    # Ensure accurate FPS: all S01 videos are 30.0 FPS
    v_upper = str(video_id).upper()
    if v_upper.startswith("S01") or v_upper.startswith("S"):
        fps = 30.0
    else:
        fps = get_fps(video_id) or float(constant.DEFAULT_FPS)

    total_seconds = max(0.0, frame_num / fps)
    time_ms = int(total_seconds * 1000)

    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    startpos_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    creation_flags = 0
    if sys.platform.startswith("win"):
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        # Close any previous instance to avoid MPC-HC ignoring /startpos in single-instance mode
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "mpc-hc64.exe"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    try:
        subprocess.Popen(
            [str(mpc_path), "/fixedsize", "1600,900", "/startpos", startpos_str, str(video_path)],
            creationflags=creation_flags,
            close_fds=True,
        )
        return {
            "status": "ok",
            "video_id": video_id,
            "frame_id": frame_num,
            "fps": fps,
            "time_ms": time_ms,
            "startpos": startpos_str,
            "video_path": str(video_path),
            "mpc_path": str(mpc_path),
        }
    except Exception as e:
        logger.error(f"Failed to spawn MPC-HC: {e}")
        return {"status": "error", "message": str(e)}


