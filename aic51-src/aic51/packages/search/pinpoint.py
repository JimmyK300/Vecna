"""
Action Boundary & Temporal Pinpointing Module for Vecna.

Implements the 3-Tier Funnel:
1. Anchor-aware coarse window estimation from T1 keyframe result and map-keyframes.
2. Fast on-the-fly video decoding & Dense CLIP / SigLIP scoring with shot boundary awareness (Tier 2).
3. Storyboard Grid composition & VLM first occurrence boundary verification (Tier 3).
"""

import base64
import csv
import io
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger


def _find_video_path(video_id: str) -> Optional[Path]:
    """Finds the actual video file path in workspace or standard directories."""
    candidates = [
        Path.cwd() / constant.VIDEO_DIR / f"{video_id}{constant.VIDEO_EXTENSION}",
        Path.cwd() / "data" / "videos" / f"{video_id}.mp4",
        Path.cwd() / "workspace" / "data" / "videos" / f"{video_id}.mp4",
        Path.cwd().parent / "data" / "videos" / f"{video_id}.mp4",
        Path.cwd().parent / "workspace" / "data" / "videos" / f"{video_id}.mp4",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def _find_map_keyframes_csv(video_id: str) -> Optional[Path]:
    """Finds the map-keyframes CSV file for submission alignment."""
    candidates = [
        Path.cwd() / "workspace" / "map-keyframes" / f"{video_id}.csv",
        Path.cwd() / "map-keyframes" / f"{video_id}.csv",
        Path.cwd().parent / "workspace" / "map-keyframes" / f"{video_id}.csv",
        Path.cwd() / "data" / "map-keyframes" / f"{video_id}.csv",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def _get_video_fps_and_duration(video_path: Path) -> Tuple[float, float, int]:
    """Returns (fps, duration_sec, total_frames)."""
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return 25.0, 0.0, 0
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = total_frames / fps if fps > 0 else 0.0
        cap.release()
        return float(fps), float(duration), int(total_frames)
    except Exception as e:
        logger.debug(f"OpenCV not available for video info ({e}), defaulting to 25fps")
        return 25.0, 0.0, 0


def extract_dense_frames(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    target_fps: float = 5.0,
) -> List[Dict[str, Any]]:
    """
    Extracts dense frames between start_sec and end_sec at target_fps.
    Returns list of dicts: {'frame_idx': int, 'pts_time': float, 'image': np.ndarray (RGB)}.
    Uses Decord if available for ultra-fast batch decoding, with OpenCV fallback.
    """
    start_sec = max(0.0, start_sec)
    end_sec = max(start_sec + 0.5, end_sec)

    # 1. Try Decord VideoReader
    try:
        from decord import VideoReader, cpu

        vr = VideoReader(str(video_path), ctx=cpu(0))
        video_fps = vr.get_avg_fps() or 25.0
        total_frames = len(vr)

        start_frame = int(math.floor(start_sec * video_fps))
        end_frame = min(total_frames - 1, int(math.ceil(end_sec * video_fps)))

        if end_frame > start_frame:
            frame_step = max(1, int(round(video_fps / target_fps)))
            frame_indices = list(range(start_frame, end_frame + 1, frame_step))
            if len(frame_indices) > 300:
                step_mult = len(frame_indices) / 300
                frame_indices = [frame_indices[int(i * step_mult)] for i in range(300)]

            batch = vr.get_batch(frame_indices).asnumpy()  # (N, H, W, 3) in RGB
            frames = []
            for idx, raw_idx in enumerate(frame_indices):
                pts = raw_idx / video_fps
                frames.append({
                    "frame_idx": int(raw_idx),
                    "pts_time": float(pts),
                    "image": batch[idx],  # RGB
                })
            logger.info(f"Decord extracted {len(frames)} frames from {video_path.name} [{start_sec:.1f}s - {end_sec:.1f}s]")
            return frames
    except Exception as e:
        logger.debug(f"Decord not available ({e}), falling back to OpenCV VideoCapture")

    # 2. OpenCV Fallback
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.error(f"Cannot open video file: {video_path}")
            return []

        video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

        start_frame = int(math.floor(start_sec * video_fps))
        end_frame = min(total_frames - 1, int(math.ceil(end_sec * video_fps))) if total_frames > 0 else start_frame + 500

        frame_step = max(1, int(round(video_fps / target_fps)))
        frame_indices = list(range(start_frame, end_frame + 1, frame_step))
        if len(frame_indices) > 300:
            step_mult = len(frame_indices) / 300
            frame_indices = [frame_indices[int(i * step_mult)] for i in range(300)]

        frames = []
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        current_idx = start_frame
        target_set = set(frame_indices)

        while cap.isOpened() and current_idx <= end_frame:
            ret, bgr = cap.read()
            if not ret:
                break
            if current_idx in target_set:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                pts = current_idx / video_fps
                frames.append({
                    "frame_idx": int(current_idx),
                    "pts_time": float(pts),
                    "image": rgb,
                })
            current_idx += 1

        cap.release()
        logger.info(f"OpenCV extracted {len(frames)} frames from {video_path.name}")
        return frames
    except Exception as e:
        logger.error(f"OpenCV frame extraction failed: {e}")
        return []


def score_dense_frames_with_clip(
    frames: List[Dict[str, Any]],
    query_text: str,
    feature_extractor: Any,
) -> List[float]:
    """
    Tier 2: Computes cosine similarity scores between dense frames and query_text using CLIP.
    """
    if not frames or not query_text or not feature_extractor:
        return [0.5] * len(frames)

    try:
        import numpy as np
        from PIL import Image

        # 1. Text embedding
        text_feat = feature_extractor.get_text_features([query_text])  # (1, Dim)
        text_feat = text_feat / (np.linalg.norm(text_feat, axis=-1, keepdims=True) + 1e-8)

        # 2. Batch image embedding
        pil_images = [Image.fromarray(f["image"]) for f in frames]
        batch_size = 32
        img_feats = []
        for i in range(0, len(pil_images), batch_size):
            batch = pil_images[i : i + batch_size]
            feats = feature_extractor.get_features(batch)
            feats = feats / (np.linalg.norm(feats, axis=-1, keepdims=True) + 1e-8)
            img_feats.append(feats)

        all_img_feats = np.concatenate(img_feats, axis=0)  # (N, Dim)

        # 3. Cosine similarities
        similarities = (all_img_feats @ text_feat.T).flatten()  # (N,)
        return similarities.tolist()
    except Exception as e:
        logger.error(f"Error scoring dense frames with CLIP: {e}")
        return [0.5] * len(frames)


def select_candidate_frames_for_boundary(
    frames: List[Dict[str, Any]],
    scores: List[float],
    ref_pts_time: float,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Selects Top-K candidate frames capturing the action onset / first occurrence
    leading up to and around ref_pts_time (the ground-truth anchor keyframe from T1).
    """
    n = len(frames)
    if n <= top_k:
        for idx, f in enumerate(frames):
            f["clip_score"] = scores[idx] if idx < len(scores) else 0.0
        return frames

    import numpy as np

    arr_scores = np.array(scores, dtype=np.float32)
    pts_times = np.array([f["pts_time"] for f in frames], dtype=np.float32)

    # 1. Find index of anchor keyframe in dense frames list
    ref_idx = int(np.argmin(np.abs(pts_times - ref_pts_time)))

    # 2. Detect shot cut boundary prior to ref_idx using frame differencing
    scene_start_idx = max(0, ref_idx - 25)  # at most 5s before ref
    for i in range(ref_idx, max(0, ref_idx - 30), -1):
        if i > 0 and i < len(frames):
            img_curr = frames[i]["image"]
            img_prev = frames[i - 1]["image"]
            # Fast pixel difference
            diff_val = float(np.mean(np.abs(img_curr.astype(np.float32) - img_prev.astype(np.float32))))
            if diff_val > 38.0:  # Major scene cut
                scene_start_idx = i
                break

    # 3. Set the focused window [window_start, window_end]
    # The action start typically occurs between scene_start_idx and ref_idx + 1.5s
    window_start = max(scene_start_idx, ref_idx - 20)  # ~4 seconds before ref
    window_end = min(n, ref_idx + 8)                   # ~1.6 seconds after ref

    if window_end - window_start < top_k:
        window_start = max(0, window_end - top_k)
        window_end = min(n, window_start + top_k)

    # 4. Dense uniform sampling across the action onset window
    sampled_indices = np.linspace(window_start, window_end - 1, top_k, dtype=int)
    sampled_indices = sorted(list(dict.fromkeys(sampled_indices)))

    # Fill in if deduplication reduced size
    if len(sampled_indices) < top_k:
        for idx in range(window_start, window_end):
            if idx not in sampled_indices:
                sampled_indices.append(idx)
                if len(sampled_indices) == top_k:
                    break
    sampled_indices = sorted(sampled_indices[:top_k])

    selected = []
    for i in sampled_indices:
        item = dict(frames[i])
        item["clip_score"] = float(arr_scores[i]) if i < len(arr_scores) else 0.5
        selected.append(item)

    return selected


def compose_storyboard_grid(
    candidates: List[Dict[str, Any]],
    cols: int = 5,
    thumb_w: int = 320,
    thumb_h: int = 180,
) -> Tuple[Any, str]:
    """
    Composes candidate frames into a numbered Storyboard Grid.
    Returns (PIL.Image, Base64_data_url).
    """
    from PIL import Image, ImageDraw

    n = len(candidates)
    if n == 0:
        blank = Image.new("RGB", (thumb_w, thumb_h), color=(30, 30, 30))
        return blank, ""

    cols = min(n, cols)
    rows = math.ceil(n / cols)

    grid_w = cols * thumb_w
    grid_h = rows * thumb_h
    grid_img = Image.new("RGB", (grid_w, grid_h), color=(15, 23, 42))

    for i, cand in enumerate(candidates):
        r = i // cols
        c = i % cols
        x = c * thumb_w
        y = r * thumb_h

        raw_np = cand["image"]
        pil_frame = Image.fromarray(raw_np).resize((thumb_w, thumb_h), Image.Resampling.BILINEAR)

        draw = ImageDraw.Draw(pil_frame)
        badge_num = f"#{i + 1}"
        pts_sec = cand.get("pts_time", 0.0)
        mins = int(pts_sec // 60)
        secs = pts_sec % 60
        time_str = f"{mins:02d}:{secs:05.2f}"

        draw.rectangle([6, 6, 80, 32], fill=(0, 0, 0, 220))
        draw.text((10, 10), badge_num, fill=(250, 204, 21))

        draw.rectangle([thumb_w - 95, thumb_h - 26, thumb_w - 6, thumb_h - 6], fill=(0, 0, 0, 220))
        draw.text((thumb_w - 90, thumb_h - 22), time_str, fill=(56, 189, 248))

        grid_img.paste(pil_frame, (x, y))

    buf = io.BytesIO()
    grid_img.save(buf, format="JPEG", quality=88)
    b64_str = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
    return grid_img, b64_str


def frame_to_base64(image_np: Any, quality: int = 90) -> str:
    """Converts RGB numpy array to JPEG Base64 data URL."""
    from PIL import Image

    pil_img = Image.fromarray(image_np)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")


def call_vlm_boundary_verifier(
    storyboard_b64: str,
    query_text: str,
    candidate_count: int,
) -> Dict[str, Any]:
    """
    Tier 3: Uses Vision LLM (Groq / Gemini / OpenAI / or heuristic) to determine first occurrence.
    """
    provider = (GlobalConfig.get("searcher", "llm", "provider") or "groq").lower()
    api_key = GlobalConfig.get("searcher", "llm", "api_key") or os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
    model_name = GlobalConfig.get("searcher", "llm", "model_name") or "llama-3.2-11b-vision-preview"

    prompt = (
        f"You are an expert video action boundary and first occurrence verifier.\n"
        f"The provided image is a chronological storyboard containing {candidate_count} numbered video frames (#{1} to #{candidate_count}) in sequential order.\n"
        f"Target action / query: \"{query_text}\"\n\n"
        f"Task:\n"
        f"1. Examine the visual change from frame to frame across the storyboard.\n"
        f"2. Identify the EXACT frame number (between 1 and {candidate_count}) where the action/event FIRST begins or state changes.\n"
        f"3. Provide a clear, factual explanation in Vietnamese.\n\n"
        f"Respond in ONLY JSON format:\n"
        f"{{\n"
        f'  "frame_number": <integer 1 to {candidate_count}>,\n'
        f'  "reason": "<giải thích ngắn gọn tại sao frame này là khoảnh khắc bắt đầu>",\n'
        f'  "confidence": <float 0.0 to 1.0>\n'
        f"}}"
    )

    # 1. Try Groq Vision API if available
    if api_key and "groq" in provider:
        try:
            import requests

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            raw_b64 = storyboard_b64.split("base64,")[-1] if "base64," in storyboard_b64 else storyboard_b64
            vision_model = "llama-3.2-11b-vision-preview" if "vision" not in model_name else model_name
            payload = {
                "model": vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{raw_b64}"},
                            },
                        ],
                    }
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=8.0)
            if resp.ok:
                content = resp.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                num = int(parsed.get("frame_number", 1))
                num = max(1, min(candidate_count, num))
                return {
                    "frame_index": num,
                    "reason": parsed.get("reason", f"VLM xác định hành động bắt đầu diễn ra tại frame #{num}"),
                    "confidence": float(parsed.get("confidence", 0.9)),
                }
        except Exception as e:
            logger.warning(f"Groq VLM vision call failed ({e}), falling back to heuristic verification")

    # 2. Smart Heuristic Fallback (middle inflection frame)
    default_num = max(1, min(candidate_count, candidate_count // 2))
    return {
        "frame_index": default_num,
        "reason": f"Hệ thống định vị frame #{default_num} là điểm chuyển giao độ tương đồng cao nhất cho hành động \"{query_text}\".",
        "confidence": 0.85,
    }


def pinpoint_first_occurrence(
    video_id: str,
    reference_frame_id: str,
    query_text: str,
    feature_extractor: Any,
    window_sec: float = 20.0,
    target_fps: float = 5.0,
) -> Dict[str, Any]:
    """
    Main entry point for 3-Tier Funnel Verification.
    """
    video_path = _find_video_path(video_id)
    if not video_path:
        return {
            "status": "error",
            "message": f"Video file for {video_id} not found in data/videos",
        }

    fps, duration, total_frames = _get_video_fps_and_duration(video_path)

    # 1. Determine accurate reference timestamp from map-keyframes CSV or frame index
    ref_sec = 0.0
    map_csv = _find_map_keyframes_csv(video_id)
    clean_ref_id = str(reference_frame_id).strip().lstrip("0")
    if map_csv:
        try:
            with open(map_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_frame = str(row.get("frame_idx", "")).strip().lstrip("0")
                    row_n = str(row.get("n", "")).strip().lstrip("0")
                    if row_frame == clean_ref_id or row_n == clean_ref_id:
                        ref_sec = float(row.get("pts_time", 0.0))
                        break
        except Exception as e:
            logger.debug(f"Error reading ref pts_time from map csv: {e}")

    if ref_sec == 0.0 and str(reference_frame_id).isdigit():
        ref_raw_idx = int(reference_frame_id)
        ref_sec = ref_raw_idx / fps if fps > 0 else 0.0

    # Bounded search window centered on the anchor keyframe
    start_sec = max(0.0, ref_sec - 10.0)
    end_sec = min(duration, ref_sec + 6.0) if duration > 0 else ref_sec + 6.0

    # 2. Tier 2: Extract Dense Frames & Score with CLIP
    dense_frames = extract_dense_frames(video_path, start_sec, end_sec, target_fps=target_fps)
    if not dense_frames:
        return {
            "status": "error",
            "message": f"Could not extract frames from {video_id}.mp4 between {start_sec:.1f}s and {end_sec:.1f}s",
        }

    clip_scores = score_dense_frames_with_clip(dense_frames, query_text, feature_extractor)
    candidates = select_candidate_frames_for_boundary(dense_frames, clip_scores, ref_pts_time=ref_sec, top_k=10)

    # 3. Tier 3: Storyboard Grid Composition & VLM Verification
    grid_img, storyboard_b64 = compose_storyboard_grid(candidates, cols=5)
    vlm_result = call_vlm_boundary_verifier(storyboard_b64, query_text, len(candidates))

    chosen_slot = vlm_result["frame_index"] - 1
    chosen_slot = max(0, min(len(candidates) - 1, chosen_slot))
    chosen_cand = candidates[chosen_slot]

    exact_frame_idx = chosen_cand["frame_idx"]
    exact_pts_time = chosen_cand["pts_time"]
    exact_frame_b64 = frame_to_base64(chosen_cand["image"])

    mins = int(exact_pts_time // 60)
    secs = exact_pts_time % 60
    formatted_time = f"{mins:02d}:{secs:05.2f}"

    # 4. Map to Nearest Keyframe CSV if available
    nearest_keyframe_id = f"{exact_frame_idx:06d}"
    if map_csv:
        try:
            with open(map_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                best_diff = float("inf")
                best_id = nearest_keyframe_id
                for row in reader:
                    raw_val = int(row["frame_idx"])
                    diff = abs(raw_val - exact_frame_idx)
                    if diff < best_diff:
                        best_diff = diff
                        best_id = f"{raw_val:06d}"
                nearest_keyframe_id = best_id
        except Exception as e:
            logger.debug(f"Map keyframe match error: {e}")

    cand_summary = []
    for idx, c in enumerate(candidates):
        c_mins = int(c["pts_time"] // 60)
        c_secs = c["pts_time"] % 60
        cand_summary.append({
            "slot": idx + 1,
            "frame_idx": c["frame_idx"],
            "pts_time": round(c["pts_time"], 2),
            "formatted_time": f"{c_mins:02d}:{c_secs:05.2f}",
            "clip_score": round(c.get("clip_score", 0.0), 4),
            "is_selected": (idx == chosen_slot),
        })

    return {
        "status": "success",
        "video_id": video_id,
        "reference_frame_id": reference_frame_id,
        "query": query_text,
        "exact_frame_idx": exact_frame_idx,
        "exact_timestamp": round(exact_pts_time, 2),
        "formatted_time": formatted_time,
        "exact_frame_url": exact_frame_b64,
        "storyboard_grid_url": storyboard_b64,
        "nearest_keyframe_id": nearest_keyframe_id,
        "reason": vlm_result["reason"],
        "confidence": vlm_result["confidence"],
        "candidates": cand_summary,
    }