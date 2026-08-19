from pathlib import Path
import re
import csv
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


def _find_image_file(folder_name: str, video_id: str, frame_id: str) -> Path | None:
    base_dir = Path.cwd() / folder_name
    p1 = base_dir / video_id / f"{frame_id}{constant.IMAGE_EXTENSION}"
    if p1.exists() and not p1.is_dir():
        return p1
    if str(frame_id).isdigit():
        val = int(frame_id)
        p2 = base_dir / video_id / f"{val:06d}{constant.IMAGE_EXTENSION}"
        if p2.exists() and not p2.is_dir():
            return p2
        p3 = base_dir / video_id / f"{val:05d}{constant.IMAGE_EXTENSION}"
        if p3.exists() and not p3.is_dir():
            return p3
    return None


@app.get(constant.FILE_ENDPOINT + "/{video_id}/{frame_id}")
async def get_file(request: Request, video_id: str, frame_id: str):
    file_path = _find_image_file(constant.THUMBNAIL_DIR, video_id, frame_id)
    if file_path:
        return FileResponse(file_path)
    else:
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "unavailable"}))


@app.get("/api/keyframes/{video_id}/{frame_id}")
async def get_keyframe(request: Request, video_id: str, frame_id: str):
    file_path = _find_image_file(constant.KEYFRAME_DIR, video_id, frame_id)
    if file_path:
        return FileResponse(file_path)
    else:
        file_path_thumb = _find_image_file(constant.THUMBNAIL_DIR, video_id, frame_id)
        if file_path_thumb:
            return FileResponse(file_path_thumb)
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "unavailable"}))


@app.get("/api/video/extract-frame/{video_id}/{frame_idx}")
async def extract_exact_frame(request: Request, video_id: str, frame_idx: int):
    """Trích xuất tức thì frame bất kỳ từ video gốc .mp4 phục vụ hiển thị exact frame."""
    file_path = _find_image_file(constant.KEYFRAME_DIR, video_id, str(frame_idx))
    if file_path:
        return FileResponse(file_path)

    video_path = Path.cwd() / f"{constant.VIDEO_DIR}/{video_id}{constant.VIDEO_EXTENSION}"
    if not video_path.exists():
        video_path = Path.cwd() / "data" / "videos" / f"{video_id}.mp4"

    if not video_path.exists():
        return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "video not found"}))

    try:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return Response(content=buffer.tobytes(), media_type="image/jpeg")
    except Exception as e:
        logger.error(f"Error extracting frame {frame_idx} from {video_id}: {e}")

    return JSONResponse(status_code=404, content=jsonable_encoder({constant.MESSAGE_KEY: "frame extraction failed"}))


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


def _get_existing_frame_indices(video_id: str) -> list[int]:
    indices = set()
    for dir_name in [constant.KEYFRAME_DIR, constant.THUMBNAIL_DIR, constant.FEATURE_DIR]:
        folder = Path.cwd() / dir_name / video_id
        if folder.exists() and folder.is_dir():
            for p in folder.iterdir():
                if p.is_file() and p.suffix.lower() == constant.IMAGE_EXTENSION:
                    stem = p.stem
                    if stem.isdigit():
                        indices.add(int(stem))
                elif p.is_dir() and p.name.isdigit():
                    indices.add(int(p.name))
    return sorted(list(indices))


@app.get("/api/video/keyframes/{video_id}")
async def get_video_keyframes(video_id: str):
    indices = _get_existing_frame_indices(video_id)
    if indices:
        return [f"{idx:06d}" for idx in indices]
    return []


def _get_map_keyframes_path(video_id: str) -> Path | None:
    candidates = [
        Path.cwd() / "workspace" / "map-keyframes" / f"{video_id}.csv",
        Path.cwd() / "map-keyframes" / f"{video_id}.csv",
        Path.cwd().parent / "workspace" / "map-keyframes" / f"{video_id}.csv",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def _load_map_keyframes_data(video_id: str):
    csv_path = _get_map_keyframes_path(video_id)
    if not csv_path:
        return None
    items = []
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    raw_val = int(row["frame_idx"])
                    items.append({
                        "n": int(row["n"]),
                        "pts_time": float(row["pts_time"]),
                        "fps": float(row["fps"]) if "fps" in row and row["fps"] else 25.0,
                        "frame_idx": f"{raw_val:06d}",
                        "raw_idx": raw_val
                    })
                except (ValueError, KeyError):
                    continue
        items.sort(key=lambda x: (x["pts_time"], x["raw_idx"]))
        return items
    except Exception as e:
        logger.error(f"Failed reading map-keyframes for {video_id}: {e}")
        return None


@app.get("/api/video/map-keyframes/{video_id}")
async def get_video_map_keyframes(video_id: str):
    items = _load_map_keyframes_data(video_id)
    if items is None:
        return JSONResponse(status_code=200, content=jsonable_encoder({"available": False, "keyframes": []}))
    return JSONResponse(status_code=200, content=jsonable_encoder({"available": True, "keyframes": items}))


@app.get("/api/video/max-frame/{video_id}")
async def get_video_max_frame(video_id: str):
    items = _load_map_keyframes_data(video_id)
    if items and len(items) > 0:
        max_idx = max(item["raw_idx"] for item in items)
        return {"video_id": video_id, "max_frame": max_idx}

    existing_indices = _get_existing_frame_indices(video_id)
    if existing_indices:
        return {"video_id": video_id, "max_frame": max(existing_indices)}

    return {"video_id": video_id, "max_frame": 999999}


def _get_closest_existing_image_frame(video_id: str, target_raw_idx: int) -> tuple[str, bool]:
    formatted_target = f"{target_raw_idx:06d}"
    if _find_image_file(constant.KEYFRAME_DIR, video_id, formatted_target) or \
       _find_image_file(constant.THUMBNAIL_DIR, video_id, formatted_target):
        return formatted_target, False

    existing_list = _get_existing_frame_indices(video_id)
    if not existing_list:
        return formatted_target, False

    closest_raw = min(existing_list, key=lambda x: abs(x - target_raw_idx))
    return f"{closest_raw:06d}", True


@app.get("/api/video/map-keyframes-around/{video_id}/{frame_id}")
async def get_video_map_keyframes_around(video_id: str, frame_id: str):
    items = _load_map_keyframes_data(video_id)
    if not items:
        return JSONResponse(status_code=200, content=jsonable_encoder({"available": False}))

    try:
        target_int = int(frame_id)
    except (ValueError, TypeError):
        target_int = -1

    items.sort(key=lambda x: x["raw_idx"])

    exact_match_item = next((item for item in items if item["raw_idx"] == target_int), None)

    if exact_match_item:
        is_exact_match = True
        curr_item = exact_match_item
        idx = items.index(exact_match_item)
        prev_item = items[max(0, idx - 1)]
        next_item = items[min(len(items) - 1, idx + 1)]
    else:
        is_exact_match = False
        idx = 0
        while idx < len(items) and items[idx]["raw_idx"] < target_int:
            idx += 1

        if idx == 0:
            prev_item = items[0]
            next_item = items[min(1, len(items) - 1)]
        elif idx >= len(items):
            prev_item = items[max(0, len(items) - 2)]
            next_item = items[-1]
        else:
            prev_item = items[idx - 1]
            next_item = items[idx]

        curr_item = prev_item

    def _enrich_item(item_dict):
        item_copy = dict(item_dict)
        disp_idx, is_fallback = _get_closest_existing_image_frame(video_id, item_copy["raw_idx"])
        item_copy["display_frame_idx"] = disp_idx
        item_copy["is_fallback_image"] = is_fallback
        return item_copy

    return JSONResponse(status_code=200, content=jsonable_encoder({
        "available": True,
        "target_frame_id": frame_id,
        "is_exact_match": is_exact_match,
        "prev": _enrich_item(prev_item),
        "curr": _enrich_item(curr_item),
        "next": _enrich_item(next_item),
    }))

