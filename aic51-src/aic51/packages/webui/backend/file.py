from pathlib import Path
import re
import numpy as np

from fastapi import Header, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse

import aic51.packages.constant as constant
from aic51.packages.logger import logger

from .utils import create_app, get_fps

app = create_app()


@app.get(constant.HEALTH_ENDPOINT + "/{video_id}/{frame_id}")
async def frame_health(request: Request, video_id: str, frame_id: str):
    file_path = Path.cwd() / f"{constant.THUMBNAIL_DIR}/{video_id}/{frame_id}{constant.IMAGE_EXTENSION}"
    if file_path.exists() and not file_path.is_dir():
        return JSONResponse(status_code=200, content=jsonable_encoder({constant.MESSAGE_KEY: "available"}))
    else:
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "unavailable"}))


@app.get(constant.HEALTH_ENDPOINT + "/{video_id}")
async def video_health(request: Request, video_id: str):
    file_path = Path.cwd() / f"{constant.VIDEO_DIR}/{video_id}{constant.VIDEO_EXTENSION}"
    if file_path.exists() and not file_path.is_dir():
        return JSONResponse(status_code=200, content=jsonable_encoder({constant.MESSAGE_KEY: "available"}))
    else:
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "unavailable"}))


@app.get(constant.HEALTH_ENDPOINT)
async def health(request: Request):
    return JSONResponse(status_code=200, content=jsonable_encoder({constant.MESSAGE_KEY: "alive"}))


@app.get(constant.FILE_INFO_ENDPOINT + "/{video_id}/{frame_id}")
async def frame_info(request: Request, video_id: str, frame_id: str):
    id = f"{video_id}#{frame_id}"
    fps = get_fps(video_id)
    
    # Construct video URI based on request base URL
    domain = str(request.base_url).rstrip('/')
    video_uri = f"{domain}{constant.FILE_ENDPOINT}/{video_id}"

    return dict(
        id=id,
        video_id=video_id,
        frame_id=frame_id,
        fps=fps,
        video_uri=video_uri,
    )


@app.get("/api/frame/ocr/{video_id}/{frame_id}")
async def get_frame_ocr(video_id: str, frame_id: str):
    ocr_file = Path.cwd() / constant.FEATURE_DIR / video_id / str(frame_id) / "ocr.npy"
    if ocr_file.exists():
        try:
            text = str(np.load(ocr_file, allow_pickle=True))
            return {"video_id": video_id, "frame_id": frame_id, "ocr": text}
        except Exception as e:
            logger.error(f"Error reading OCR for {video_id} {frame_id}: {e}")
    return {"video_id": video_id, "frame_id": frame_id, "ocr": ""}


@app.get(constant.FILE_ENDPOINT + "/{video_id}/{frame_id}")
async def get_file(request: Request, video_id: str, frame_id: str):
    file_path = Path.cwd() / f"{constant.THUMBNAIL_DIR}/{video_id}/{frame_id}{constant.IMAGE_EXTENSION}"
    if file_path.exists() and not file_path.is_dir():
        return FileResponse(file_path)
    else:
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "unavailable"}))


@app.get("/api/keyframes/{video_id}/{frame_id}")
async def get_keyframe(request: Request, video_id: str, frame_id: str):
    file_path = Path.cwd() / f"{constant.KEYFRAME_DIR}/{video_id}/{frame_id}{constant.IMAGE_EXTENSION}"
    if file_path.exists() and not file_path.is_dir():
        return FileResponse(file_path)
    else:
        file_path_thumb = Path.cwd() / f"{constant.THUMBNAIL_DIR}/{video_id}/{frame_id}{constant.IMAGE_EXTENSION}"
        if file_path_thumb.exists() and not file_path_thumb.is_dir():
            return FileResponse(file_path_thumb)
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "unavailable"}))


CHUNK_SIZE = 1024 * 1024


@app.get(constant.FILE_ENDPOINT + "/{video_id}")
async def get_video(request: Request, video_id: str, range: str = Header(None)):
    file_path = Path.cwd() / f"{constant.VIDEO_DIR}/{video_id}{constant.VIDEO_EXTENSION}"
    if not file_path.exists() or file_path.is_dir():
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "unavailable"}))

    start, end = range.replace("bytes=", "").split("-")
    start = int(start)
    end = int(end) if end else start + CHUNK_SIZE

    with open(file_path, "rb") as video:
        video.seek(start)
        data = video.read(end - start)
        filesize = file_path.stat().st_size
        headers = {
            "Content-Range": f"bytes {str(start)}-{str(min(end, filesize-1))}/{str(filesize)}",
            "Accept-Ranges": "bytes",
        }
    return Response(data, status_code=206, headers=headers, media_type=constant.VIDEO_MEDIA_TYPE)


@app.get("/api/videos")
async def get_video_inventory():
    """Return video IDs that actually exist in the analyzed feature store."""
    feature_root = Path.cwd() / constant.FEATURE_DIR
    if not feature_root.exists():
        return {"videos": []}

    videos = sorted(item.name for item in feature_root.iterdir() if item.is_dir())
    return {"videos": videos}


def split_into_sentences(segment):
    text = segment["text"]
    # Split by standard sentence punctuation (dot, question mark, exclamation mark)
    # keeping the punctuation with the sentence
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) <= 1:
        return [segment]
        
    total_len = sum(len(s) for s in sentences)
    if total_len == 0:
        return [segment]
        
    start_time = segment["start_time"]
    end_time = segment["end_time"]
    duration = end_time - start_time
    
    start_frame = segment["start_frame"]
    end_frame = segment["end_frame"]
    frame_diff = end_frame - start_frame
    
    sub_segments = []
    current_time = start_time
    current_frame = start_frame
    
    for i, s in enumerate(sentences):
        s_len = len(s)
        ratio = s_len / total_len
        s_duration = duration * ratio
        s_frames = frame_diff * ratio
        
        s_end_time = current_time + s_duration
        s_end_frame = int(round(current_frame + s_frames))
        
        # Ensure we don't overshoot
        if i == len(sentences) - 1:
            s_end_time = end_time
            s_end_frame = end_frame
            
        sub_segments.append({
            "start_frame": int(round(current_frame)),
            "start_time": current_time,
            "end_frame": s_end_frame,
            "end_time": s_end_time,
            "text": s
        })
        
        current_time = s_end_time
        current_frame = s_end_frame
        
    return sub_segments


@app.get("/api/video/transcript/{video_id}")
async def get_video_transcript(video_id: str):
    fps = get_fps(video_id)
    features_path = Path.cwd() / constant.FEATURE_DIR / video_id
    if not features_path.exists():
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "unavailable"}))
    
    transcript = []
    # Find all frame directories
    frame_dirs = sorted(features_path.glob("*"))
    for d in frame_dirs:
        if d.is_dir() and d.name.isdigit():
            asr_file = d / "asr.npy"
            if asr_file.exists():
                try:
                    # load whisper text
                    text = str(np.load(asr_file, allow_pickle=True))
                    frame_id = int(d.name)
                    # compute timestamp
                    timestamp = frame_id / fps if fps else 0.0
                    transcript.append({
                        "frame_id": frame_id,
                        "timestamp": timestamp,
                        "text": text
                    })
                except Exception as e:
                    logger.error(f"Error reading ASR for {video_id} {d.name}: {e}")
    
    # Group consecutive identical texts to produce clean transcript segments
    grouped_transcript = []
    current_segment = None
    for entry in transcript:
        text = entry["text"].strip()
        if not text:
            continue
        if current_segment is None:
            current_segment = {
                "start_frame": entry["frame_id"],
                "start_time": entry["timestamp"],
                "end_frame": entry["frame_id"],
                "end_time": entry["timestamp"],
                "text": text
            }
        elif current_segment["text"] == text:
            current_segment["end_frame"] = entry["frame_id"]
            current_segment["end_time"] = entry["timestamp"]
        else:
            grouped_transcript.append(current_segment)
            current_segment = {
                "start_frame": entry["frame_id"],
                "start_time": entry["timestamp"],
                "end_frame": entry["frame_id"],
                "end_time": entry["timestamp"],
                "text": text
            }
    if current_segment is not None:
        grouped_transcript.append(current_segment)
        
    # Split large aggregated segments into sentence-level segments
    final_transcript = []
    for segment in grouped_transcript:
        final_transcript.extend(split_into_sentences(segment))
        
    return final_transcript


@app.get("/api/video/keyframes/{video_id}")
async def get_video_keyframes(video_id: str):
    features_path = Path.cwd() / constant.FEATURE_DIR / video_id
    if not features_path.exists():
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "unavailable"}))
    
    keyframes = []
    # Find all frame directories
    frame_dirs = sorted(features_path.glob("*"))
    for d in frame_dirs:
        if d.is_dir() and d.name.isdigit():
            keyframes.append(d.name)
            
    return keyframes