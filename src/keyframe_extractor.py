import csv
import os
import sys
from pathlib import Path
import subprocess
import cv2
import numpy as np
import concurrent.futures
import threading
from queue import Queue
import time

from src.helpers import get_logger
from src.load_all_video_keyframes_info import load_all_video_keyframes_info

logger = get_logger()
all_video, video_keyframe_dict = load_all_video_keyframes_info()

def detect_video_codec(video_path):
    """Detect video codec using ffprobe"""
    try:
        cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0", 
               "-show_entries", "stream=codec_name", "-of", "csv=p=0", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"ffprobe failed for {video_path}: {e}")
    return "unknown"

def get_video_fps(video_path):
    """Get video FPS using ffprobe"""
    try:
        cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0", 
               "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            fps_str = result.stdout.strip()
            if '/' in fps_str:
                num, den = fps_str.split('/')
                fps = float(num) / float(den) if float(den) != 0 else 25
            else:
                fps = float(fps_str) if fps_str else 25
            return fps
    except Exception as e:
        logger.warning(f"Failed to get FPS for {video_path}: {e}")
        return 25  # default fps
    
def keyframe_extractor(v):
    # in
    video_path = f"./data-source/videos/{v}.mp4"
    file_path = f"./data-staging/preprocessing/{v}_scenes.txt"
    # out
    kf_path = f"./data-staging/keyframes/{v}"
    map_path = f"./data-staging/map-keyframes/{v}.csv"

    if Path(kf_path).is_dir():
        logger.info(f"{kf_path} exist, ignore...")
        return

    os.makedirs(kf_path)

    # Check codec
    codec = detect_video_codec(video_path)
    logger.info(f"Video {v} codec: {codec}")
    
    use_ffmpeg = codec != "h264"
    if use_ffmpeg:
        logger.info(f"Using ffmpeg extraction for non-h264 codec: {codec}")
        fps = get_video_fps(video_path)
    else:
        logger.info(f"Using OpenCV extraction for h264 codec")

    cap = None
    if not use_ffmpeg:
        cap = cv2.VideoCapture(video_path)

    with open(map_path, "w", newline="") as mapping_file, open(file_path, "r") as file:
        mapping = csv.writer(mapping_file)
        mapping.writerow(["n", "pts_time", "fps", "frame_idx"])
        lines = file.readlines()
        
        if use_ffmpeg:
            # Extract ALL frames in ONE ffmpeg call
            # This avoids the GPU context degradation issue entirely
            logger.info(f"Using single-call batch extraction for {codec} codec")
            
            start_time = time.time()
            
            # Prepare all frame numbers and output paths
            frame_numbers = []
            output_paths = []
            for i, line in enumerate(lines):
                left, right = line.split(" ")
                mid = (int(left) + int(right)) // 2
                frame_numbers.append(mid)
                output_paths.append(f"./data-staging/keyframes/{v}/{i+1:04}.jpg")
            
            # Create a single filter that extracts all frames at once
            frame_selects = "+".join([f"eq(n\\,{fn})" for fn in frame_numbers])
            
            # Build the ultimate ffmpeg command
            if codec == "av1":
                cmd = [
                    "ffmpeg",
                    "-c:v", "av1_cuvid",
                    "-i", video_path,
                    "-vf", f"select='{frame_selects}'",
                    "-vsync", "0",
                    "-y", "-loglevel", "quiet"
                ]
            elif codec == "h264":
                cmd = [
                    "ffmpeg", 
                    "-c:v", "h264_cuvid",
                    "-i", video_path,
                    "-vf", f"select='{frame_selects}'",
                    "-vsync", "0",
                    "-y", "-loglevel", "quiet"
                ]
            elif codec == "hevc":
                cmd = [
                    "ffmpeg",
                    "-c:v", "hevc_cuvid", 
                    "-i", video_path,
                    "-vf", f"select='{frame_selects}'",
                    "-vsync", "0",
                    "-y", "-loglevel", "quiet"
                ]
            else:
                cmd = [
                    "ffmpeg",
                    "-hwaccel", "cuda",
                    "-i", video_path,
                    "-vf", f"select='{frame_selects}'", 
                    "-vsync", "0",
                    "-y", "-loglevel", "quiet"
                ]
            
            # Use a temporary directory for batch output
            temp_dir = f"/tmp/batch_extract_{v}"
            os.makedirs(temp_dir, exist_ok=True)
            cmd.append(f"{temp_dir}/frame_%04d.jpg")
            
            logger.info(f"Extracting {len(frame_numbers)} frames in single GPU call...")
            
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=300)  # 5 min timeout
                
                all_results = []
                if result.returncode == 0:
                    # Move files to correct locations
                    for i, (frame_num, output_path) in enumerate(zip(frame_numbers, output_paths)):
                        temp_file = f"{temp_dir}/frame_{i+1:04d}.jpg"
                        if os.path.exists(temp_file):
                            try:
                                os.rename(temp_file, output_path)
                                all_results.append((i + 1, frame_num, True, output_path))
                            except Exception as e:
                                logger.warning(f"Failed to move {temp_file}: {e}")
                                all_results.append((i + 1, frame_num, False, output_path))
                        else:
                            all_results.append((i + 1, frame_num, False, output_path))
                else:
                    # Fallback to sequential CPU extraction
                    logger.error(f"Batch GPU extraction failed, falling back to CPU")
                    all_results = []
                    for i, (frame_num, output_path) in enumerate(zip(frame_numbers, output_paths)):
                        cpu_cmd = [
                            "ffmpeg", "-i", video_path, 
                            "-vf", f"select=eq(n\\,{frame_num})", 
                            "-vframes", "1", "-y", output_path
                        ]
                        cpu_result = subprocess.run(cpu_cmd, capture_output=True)
                        success = cpu_result.returncode == 0 and os.path.exists(output_path)
                        all_results.append((i + 1, frame_num, success, output_path))
                
                # Cleanup temp directory
                import shutil
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    
            except subprocess.TimeoutExpired:
                logger.error("Batch extraction timed out")
                all_results = [(i + 1, fn, False, op) for i, (fn, op) in enumerate(zip(frame_numbers, output_paths))]
            
            total_time = time.time() - start_time
            successful_frames = sum(1 for r in all_results if r[2])
            
            # Write results to mapping file in order
            for idx, frame_num, success, keyframe_path in all_results:
                if success:
                    mapping.writerow([idx, frame_num / fps, fps, frame_num])
                    print(f"Saved keyframe {frame_num} of video {v} using single-call ffmpeg (GPU-accelerated for {codec})")
                else:
                    print(f"Failed to extract frame {frame_num} from video {v} using ffmpeg.", file=sys.stderr)
            
            logger.info(f"{successful_frames}/{len(lines)} frames in {total_time:.2f}s ({successful_frames/total_time:.1f} fps)")
            
        else:
            # Use OpenCV for h264 codec (sequential processing)
            for i, line in enumerate(lines):
                left, right = line.split(" ")
                mid = (int(left) + int(right)) // 2
                keyframe_path = f"./data-staging/keyframes/{v}/{i+1:04}.jpg"
                
                cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
                ret, frame = cap.read()
                if ret:
                    cv2.imwrite(keyframe_path, frame)
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    mapping.writerow([i + 1, mid / fps, fps, mid])
                    print(f"Saved keyframe {mid} of video {v} using OpenCV")
                else:
                    print(f"Failed to extract frame {mid} from video {v} using OpenCV.", file=sys.stderr)

    if cap is not None:
        cap.release()


if __name__ == "__main__":
    os.makedirs("./data-staging/map-keyframes", exist_ok=True)

    logger.info("keyframe_extractor")
    for v in all_video:
        start = time.time()
        keyframe_extractor(v)
        end = time.time()
        logger.info(f"Processed video {v} in {end - start:.2f} seconds")
