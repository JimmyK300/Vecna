import csv
import os
from itertools import islice
from typing import Tuple
import subprocess
import tempfile
import io
import shutil

import numpy as np
import streamlit as st
from PIL import Image

from keyframe_search import keyframe_search
from helpers import get_logger
from ocr_search import display_search_results, search_by_ocr
from temporal_search import search_by_temporal
from transcript_search import transcript_search
from dinov3_search import recommend

WIDTH = 350

# Initialize session state

if "search_results" not in st.session_state:
    st.session_state["search_results"] = []

if "ocr_results" not in st.session_state:
    st.session_state["ocr_results"] = []

if "temporal_results" not in st.session_state:
    st.session_state["temporal_results"] = []

if "transcript_results" not in st.session_state:
    st.session_state["transcript_results"] = []

if "selected_keyframes" not in st.session_state:
    st.session_state["selected_keyframes"] = {}

if "selected_sequences" not in st.session_state:
    st.session_state["selected_sequences"] = {}

# Pagination state
if "current_page" not in st.session_state:
    st.session_state["current_page"] = 0

if "results_per_page" not in st.session_state:
    st.session_state["results_per_page"] = 20

# Cache for loaded images
if "image_cache" not in st.session_state:
    st.session_state["image_cache"] = {}

# Frame viewer session state
if "frame_viewer_video" not in st.session_state:
    st.session_state["frame_viewer_video"] = None

if "frame_number" not in st.session_state:
    st.session_state["frame_number"] = 0

if "show_frame_dialog" not in st.session_state:
    st.session_state["show_frame_dialog"] = False

if "last_search_term" not in st.session_state:
    st.session_state["last_search_term"] = ""

logger = get_logger()


@st.cache_data
def get_video_info(video_path):
    """Get video information using ffprobe."""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'quiet',
            '-count_frames',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=nb_frames',
            '-of', 'csv=p=0',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        total_frames = int(result.stdout.strip())
        return total_frames
    except (subprocess.CalledProcessError, ValueError):
        # Fallback method to estimate frames
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'stream=duration,r_frame_rate',
                '-select_streams', 'v:0',
                '-of', 'csv=p=0',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration, frame_rate = result.stdout.strip().split(',')
            
            # Parse frame rate (could be like "30/1" or "29.97")
            if '/' in frame_rate:
                num, den = map(float, frame_rate.split('/'))
                fps = num / den
            else:
                fps = float(frame_rate)
            
            total_frames = int(float(duration) * fps)
            return total_frames
        except:
            return 1000  # Default fallback


def extract_frames_batch(video_path, temp_dir, total_frames, frame_interval=10):
    """Extract frames at specified intervals using ffmpeg."""
    try:
        # Extract every nth frame with low quality
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vf', f'select=not(mod(n\\,{frame_interval}))',
            '-vsync', 'vfr',
            '-q:v', '10',  # Low quality (1-31, higher = lower quality)
            '-s', '640x360',  # Reduce resolution for speed
            os.path.join(temp_dir, 'frame_%06d.jpg')
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            return True
        else:
            st.error(f"FFmpeg error: {result.stderr}")
            return False
            
    except Exception as e:
        st.error(f"Error extracting frames: {str(e)}")
        return False


def get_frame_from_folder(temp_dir, frame_number, frame_interval=10):
    """Get frame from pre-extracted folder."""
    try:
        # Calculate which extracted frame to use
        extracted_frame_index = frame_number // frame_interval
        frame_filename = f'frame_{extracted_frame_index + 1:06d}.jpg'
        frame_path = os.path.join(temp_dir, frame_filename)
        
        if os.path.exists(frame_path):
            with Image.open(frame_path) as img:
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='JPEG')
                return img_bytes.getvalue()
        else:
            # Find closest available frame
            available_frames = [f for f in os.listdir(temp_dir) if f.startswith('frame_') and f.endswith('.jpg')]
            if available_frames:
                # Get the closest frame
                frame_numbers = [int(f.split('_')[1].split('.')[0]) for f in available_frames]
                closest_frame_num = min(frame_numbers, key=lambda x: abs(x - (extracted_frame_index + 1)))
                closest_frame_file = f'frame_{closest_frame_num:06d}.jpg'
                closest_frame_path = os.path.join(temp_dir, closest_frame_file)
                
                with Image.open(closest_frame_path) as img:
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format='JPEG')
                    return img_bytes.getvalue()
            
        return None
        
    except Exception as e:
        st.error(f"Error loading frame: {str(e)}")
        return None


@st.dialog("Video Frame Viewer")
def frame_viewer_dialog():
    video_id = st.session_state["frame_viewer_video"]
    video_path = f"./data-source/videos/{video_id}.mp4"
    
    # Get total frames once (cached)
    total_frames = get_video_info(video_path)
    
    # Initialize temp directory in session state if not exists for this video
    temp_dir_key = f'temp_dir_{video_id}'
    frames_extracted_key = f'frames_extracted_{video_id}'
    
    if temp_dir_key not in st.session_state or not os.path.exists(st.session_state[temp_dir_key]):
        st.session_state[temp_dir_key] = tempfile.mkdtemp(prefix=f'video_frames_{video_id}_')
        st.session_state[frames_extracted_key] = False
    
    # Extract frames if not done yet
    if not st.session_state[frames_extracted_key]:
        with st.spinner('Extracting frames... This may take a moment.'):
            success = extract_frames_batch(video_path, st.session_state[temp_dir_key], total_frames, frame_interval=10)
            if success:
                st.session_state[frames_extracted_key] = True
                st.rerun()
            else:
                st.error("Failed to extract frames")
                return
    
    # Get the current frame bytes
    frame_bytes = get_frame_from_folder(st.session_state[temp_dir_key], st.session_state["frame_number"], frame_interval=10)

    if frame_bytes is not None:
        st.image(frame_bytes, use_column_width=True)
        st.write(f"Video: {video_id} | Frame: {st.session_state['frame_number'] + 1} of {total_frames}")
        st.caption("Note: Showing nearest extracted frame (every 10th frame)")
        st.caption("⚠️ Please use the 'Close' button below to properly exit and clean up temporary files.")
    else:
        st.error("Error: Could not read frame.")

    # Add a slider to navigate frames
    new_frame_number = st.slider("Frame", 0, total_frames - 1, st.session_state["frame_number"])
    if new_frame_number != st.session_state["frame_number"]:
        st.session_state["frame_number"] = new_frame_number
        st.rerun()

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if st.button("⬅️ Previous"):
            if st.session_state["frame_number"] > 0:
                st.session_state["frame_number"] -= 10
                st.rerun()

    with col2:
        if st.button("Next ➡️"):
            if st.session_state["frame_number"] < total_frames - 1:
                st.session_state["frame_number"] += 10
                st.rerun()
    
    with col3:
        if st.button("🔒 Close"):
            # Clean up temporary directory when closing
            if temp_dir_key in st.session_state and os.path.exists(st.session_state[temp_dir_key]):
                shutil.rmtree(st.session_state[temp_dir_key])
                del st.session_state[temp_dir_key]
                if frames_extracted_key in st.session_state:
                    del st.session_state[frames_extracted_key]
            st.session_state["show_frame_dialog"] = False
            st.rerun()


@st.dialog("Playing source video")
def play_dialog(video, kf):
    map_path = f"./data-staging/map-keyframes/{video}.csv"
    time_path = f"./data-staging/preprocessing/{video}_scenes.txt"
    with open(map_path) as map_file, open(time_path) as time_file:
        map_file = csv.reader(map_file)
        time_file = csv.reader(time_file, delimiter=" ")
        k = int(kf)
        n, pts_time, fps, frame_idx = list(islice(map_file, k + 1))[k]
        start, end = list(islice(time_file, k))[k - 1]
    st.write(f"{video},{frame_idx}")
    st.write(f"FPS: {fps}")
    start_time = int(start) / float(fps)
    end_time = int(end) / float(fps)
    if int(start_time) == int(end_time):
        end_time = end_time + 1
    st.video(
        f"./data-source/videos/{video}.mp4",
        autoplay=True,
        start_time=start_time,
        end_time=end_time,
    )

def handle_recommend(video_id, kf_id):
    with st.spinner("Finding similar images..."):
        results = recommend(video_id, kf_id)
        st.session_state["search_results"] = results
        st.session_state["ocr_results"] = []
        st.session_state["temporal_results"] = []
        st.session_state["transcript_results"] = []
        st.session_state["current_page"] = 0
        st.session_state["last_search_option"] = "keyframe"
        st.rerun()

@st.dialog("Similar Images")
def recommend_dialog(video_id, kf_id):
    st.image(f"./data-staging/keyframes/{video_id}/{kf_id}.jpg", caption="Source Image", use_column_width=True)
    st.write("Top 100 similar images:")
    
    with st.spinner("Finding similar images..."):
        results = recommend(video_id, kf_id) # Returns list of (image_path, score)

    if not results:
        st.warning("No similar images found.")
        return

    # Display results in a grid
    num_columns = 4
    cols = st.columns(num_columns)
    
    for i, (video_id, keyframe_id, score) in enumerate(results):
        path = f"data-staging/keyframes/{video_id}/{keyframe_id}.jpg"
        with cols[i % num_columns]:
            if os.path.exists(path):
                st.image(path, caption=f"Score: {score:.4f}", width=WIDTH)
            else:
                st.warning(f"Not found: {path}")

@st.dialog("Zoom keyframe")
def zoom_image(file_path, video, kf, option = "keyframe"):
    map_path = f"./data-staging/map-keyframes/{video}.csv"
    time_path = f"./data-staging/preprocessing/{video}_scenes.txt"
    with open(map_path) as map_file, open(time_path) as time_file:
        map_file = csv.reader(map_file)
        time_file = csv.reader(time_file, delimiter=" ")
        k = int(kf)
        n, pts_time, fps, frame_idx = list(islice(map_file, k + 1))[k]
        start, end = list(islice(time_file, k))[k - 1]
    
    if option == "ocr":
        # Get search term from session state if available for OCR results
        search_term = st.session_state.get("last_search_term", "")
        if search_term:
            display_search_results(search_term, kf, video)

    st.image(file_path, caption=f"{video} | frame: {frame_idx}", use_column_width=True)


def setup_page():
    st.set_page_config(layout="wide")
    hide_img_fs = """
    <style>
    button[title="View fullscreen"]{
        visibility: hidden;
    }
    </style>
    """
    st.markdown(hide_img_fs, unsafe_allow_html=True)
    st.header("float19™ Video Search")
    st.write(
        "Welcome to float19 Video Search. You can blah blah blah here. And blah blah blah there also."
    )


def render_search_ui():
    col1, col2, _, _ = st.columns(4)
    with col1:
        search_option = st.radio("Search by:", ("keyframe", "ocr", "temporal", "transcript"))
    with col2:
        id_to_watch = st.text_input("Watch a video given its ID?")
        col21, col22 = st.columns(2)
        with col21:
            watch_vid_button = st.button("view")
            if watch_vid_button:
                play_dialog(id_to_watch,"0001")
        with col22:
            frame_vid_button = st.button("frame")
            if frame_vid_button:
                st.session_state["frame_viewer_video"] = id_to_watch
                st.session_state["frame_number"] = 0
                st.session_state["show_frame_dialog"] = True
                st.rerun()
    search_term = st.text_area("Ask a question here:", height=100)
    excluded_video = st.text_input("Excluded video IDs (comma-separated), used for temporal search only", "")
    
    # Results per page setting
    st.session_state["results_per_page"] = st.selectbox(
        "Results per page", 
        [10, 20, 50, 100], 
        index=[10, 20, 50, 100].index(st.session_state["results_per_page"])
    )
    
    col1, col2 = st.columns(2)
    with col1:
        query_id = st.text_input(
            "Unique query id (used for export filename)", value="query-0-kis"
        )
    with col2:
        qa_answer = st.text_input(
            "QA query answer"
        )
    col1, col2 = st.columns(2)
    with col1:
        search_button = st.button("SEARCH", type="primary")
    with col2:
        export_button = st.button("Export Selected Keyframes")
    
    download_placeholder = st.empty()
    
    return search_option, id_to_watch, watch_vid_button, frame_vid_button, search_term, excluded_video, query_id, qa_answer, search_button, export_button, download_placeholder


def handle_search(search_option, search_term, query_id, excluded_video):
    excluded_video = excluded_video.split(",") if excluded_video else []
    with st.spinner("Fetching Answer..."):
        st.session_state["ocr_results"] = []
        st.session_state["search_results"] = []
        st.session_state["temporal_results"] = []
        st.session_state["transcript_results"] = []
        st.session_state["selected_keyframes"] = {}
        st.session_state["selected_sequences"] = {}
        st.session_state["current_page"] = 0  # Reset to first page
        search_term = search_term.strip()
        st.session_state["last_search_term"] = search_term  # Store for later use
        logger.info("searching...", search_term)

        if search_option == "keyframe":
            st.session_state["search_results"] = keyframe_search(search_term, limit=1000)
        elif search_option == "ocr":
            st.session_state["ocr_results"] = search_by_ocr(search_term)
        elif search_option == "temporal":
            st.session_state["temporal_results"] = search_by_temporal(search_term, limit=200, excluded_video=excluded_video)
        elif search_option == "transcript":
            st.session_state["transcript_results"] = transcript_search(search_term, top_k=100)


def render_pagination_controls(total_results, position="top"):
    """Render pagination controls"""
    if total_results == 0:
        return
    
    results_per_page = st.session_state["results_per_page"]
    total_pages = (total_results - 1) // results_per_page + 1
    current_page = st.session_state["current_page"]
    
    col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
    
    with col1:
        if st.button("⏮️ First", disabled=(current_page == 0), key=f"first_{position}"):
            st.session_state["current_page"] = 0
            st.rerun()
    
    with col2:
        if st.button("⬅️ Prev", disabled=(current_page == 0), key=f"prev_{position}"):
            st.session_state["current_page"] = max(0, current_page - 1)
            st.rerun()
    
    with col3:
        st.write(f"Page {current_page + 1} of {total_pages} ({total_results} results)")
    
    with col4:
        if st.button("Next ➡️", disabled=(current_page >= total_pages - 1), key=f"next_{position}"):
            st.session_state["current_page"] = min(total_pages - 1, current_page + 1)
            st.rerun()
    
    with col5:
        if st.button("Last ⏭️", disabled=(current_page >= total_pages - 1), key=f"last_{position}"):
            st.session_state["current_page"] = total_pages - 1
            st.rerun()


def display_transcript_results():
    results = st.session_state.get("transcript_results", [])
    if not results:
        return

    total_results = len(results)
    results_per_page = st.session_state["results_per_page"]
    current_page = st.session_state["current_page"]
    
    # Calculate pagination
    start_idx = current_page * results_per_page
    end_idx = min(start_idx + results_per_page, total_results)
    current_results = results[start_idx:end_idx]

    st.write(f"Found {total_results} relevant transcript sentences.")
    
    # Render pagination controls at the top
    render_pagination_controls(total_results, "transcript_top")
    
    st.markdown("---")

    for i, result in enumerate(current_results):
        actual_idx = start_idx + i  # Actual index in the full results list
        st.markdown("---")
        video_id = result['video_id']
        sentence = result['sentence']
        score = result['similarity_score']
        keyframes = result.get('keyframes', [])

        st.subheader(f"Result {actual_idx + 1}: Video `{video_id}` | Similarity: `{score:.4f}`")
        st.markdown(f"> {sentence}")

        if not keyframes:
            st.warning("No keyframes found for this sentence's time interval.")
            continue

        # Create a selection box for the entire result group
        group_key = f"transcript_group_{actual_idx}"
        if group_key not in st.session_state["selected_keyframes"]:
            st.session_state["selected_keyframes"][group_key] = False
        
        st.session_state["selected_keyframes"][group_key] = st.checkbox(
            "Select all keyframes in this group", key=f"checkbox_{group_key}"
        )

        # Display keyframes in a grid with a fixed number of columns.
        # This avoids overlapping issues and provides a clean, scrollable layout.
        num_columns = 4 
        cols = st.columns(num_columns)
        
        for j, kf_info in enumerate(keyframes):
            with cols[j % num_columns]:
                file_path = kf_info['keyframe_filename']
                kf_name = os.path.basename(file_path)
                kf_id = kf_name.split('.')[0]
                
                if os.path.exists(file_path):
                    # Get frame_idx from mapping for caption
                    try:
                        map_path = f"./data-staging/map-keyframes/{video_id}.csv"
                        with open(map_path) as map_file:
                            mapping = list(csv.reader(map_file))
                            k = int(kf_id)
                            if k < len(mapping):
                                _, _, _, frame_idx = mapping[k]
                                st.image(file_path, caption=f"{video_id} | frame: {frame_idx} | score: {score:.4f}", width=WIDTH)
                            else:
                                st.image(file_path, caption=f"{video_id} | kf: {kf_id} | score: {score:.4f}", width=WIDTH)
                    except (FileNotFoundError, IndexError, ValueError):
                        st.image(file_path, caption=f"{video_id} | kf: {kf_id} | score: {score:.4f}", width=WIDTH)
                else:
                    st.warning(f"Not found:\n{file_path}")

                key = f"{video_id}/{kf_id}"
                # Use three columns for the buttons to place them side-by-side
                button_col1, button_col2, button_col3 = st.columns([1, 1, 1])
                with button_col1:
                    if st.button(f"view", key=f"view_transcript_{actual_idx}_{j}"):
                        play_dialog(video_id, kf_id)
                with button_col2:
                    if st.button(f"similar", key=f"similar_transcript_{actual_idx}_{j}"):
                        handle_recommend(video_id, kf_id)
                with button_col3:
                    if st.button(f"frame", key=f"frame_transcript_{actual_idx}_{j}"):
                        st.session_state["frame_viewer_video"] = video_id
                        st.session_state["frame_number"] = 0
                        st.session_state["show_frame_dialog"] = True
                        st.rerun()
    
    # Render pagination controls at the bottom
    st.markdown("---")
    render_pagination_controls(total_results, "transcript_bottom")


def display_temporal_results():
    results = st.session_state.get("temporal_results", [])
    if not results:
        return

    total_results = len(results)
    results_per_page = st.session_state["results_per_page"]
    current_page = st.session_state["current_page"]
    
    # Calculate pagination
    start_idx = current_page * results_per_page
    end_idx = min(start_idx + results_per_page, total_results)
    current_results = results[start_idx:end_idx]

    st.write(f"Found {total_results} temporal sequences.")
    
    # Render pagination controls at the top
    render_pagination_controls(total_results, "temporal_top")
    
    st.markdown("---")

    for i, (video_id, kf_ids, scores, avg_similarity) in enumerate(current_results):
        actual_idx = start_idx + i  # Actual index in the full results list
        st.markdown("---")
        
        col1, col2 = st.columns([0.9, 0.1])
        with col1:
            st.subheader(f"Sequence {actual_idx + 1}: Video `{video_id}` | Avg. Similarity: `{avg_similarity:.4f}`")
        with col2:
            if actual_idx not in st.session_state["selected_sequences"]:
                st.session_state["selected_sequences"][actual_idx] = False
            st.session_state["selected_sequences"][actual_idx] = st.checkbox(
                "Select", key=f"select_seq_{actual_idx}"
            )

        num_columns = 4 
        cols = st.columns(num_columns)

        for j, kf_id in enumerate(kf_ids):
            with cols[j % num_columns]:
                score = scores[j]
                kf_id_str = str(kf_id).zfill(4)
                file_path = f"./data-staging/keyframes/{video_id}/{kf_id_str}.jpg"
                if os.path.exists(file_path):
                    # Get frame_idx from mapping for caption
                    try:
                        map_path = f"./data-staging/map-keyframes/{video_id}.csv"
                        with open(map_path) as map_file:
                            mapping = list(csv.reader(map_file))
                            k = int(kf_id)
                            if k < len(mapping):
                                _, _, _, frame_idx = mapping[k]
                                st.image(file_path, caption=f"{video_id} | frame: {frame_idx} | score: {score:.4f}", width=WIDTH)
                            else:
                                st.image(file_path, caption=f"{video_id} | kf: {kf_id_str} | score: {score:.4f}", width=WIDTH)
                    except (FileNotFoundError, IndexError, ValueError):
                        st.image(file_path, caption=f"{video_id} | kf: {kf_id_str} | score: {score:.4f}", width=WIDTH)
                else:
                    st.warning(f"Not found:\n{file_path}")

                key = f"{video_id}/{kf_id}"
                button_col1, button_col2, button_col3 = st.columns([1, 1, 1])
                with button_col1:
                    if st.button(f"view", key=f"view_temporal_{actual_idx}_{j}"):
                        play_dialog(video_id, kf_id)
                with button_col2:
                    if st.button(f"similar", key=f"similar_temporal_{actual_idx}_{j}"):
                        handle_recommend(video_id, str(kf_id).zfill(4))
                with button_col3:
                    if st.button(f"frame", key=f"frame_temporal_{actual_idx}_{j}"):
                        st.session_state["frame_viewer_video"] = video_id
                        st.session_state["frame_number"] = 0
                        st.session_state["show_frame_dialog"] = True
                        st.rerun()
    
    # Render pagination controls at the bottom
    st.markdown("---")
    render_pagination_controls(total_results, "temporal_bottom")


def display_results(search_option):
    results = st.session_state["search_results"] or st.session_state["ocr_results"]
    if not results:
        return
    
    total_results = len(results)
    results_per_page = st.session_state["results_per_page"]
    current_page = st.session_state["current_page"]
    
    # Calculate pagination
    start_idx = current_page * results_per_page
    end_idx = min(start_idx + results_per_page, total_results)
    current_results = results[start_idx:end_idx]

    st.write(f"Found {total_results} results.")
    
    # Render pagination controls at the top
    render_pagination_controls(total_results, "results_top")
    
    st.markdown("---")
    
    # Display results in a 4-column grid
    col1, col2, col3, col4 = st.columns(4)
    
    for i, result in enumerate(current_results):
        actual_idx = start_idx + i  # Actual index in the full results list
        
        if search_option == "keyframe":
            video, kf, similarity = result
            file_path = f"./data-staging/keyframes/{video}/{kf}.jpg"
            key = f"{video}/{kf}"
        else:  # For ocr_results
            subfolder, file_name, frame_idx, similarity = result
            file_path = f"./data-staging/keyframes/{subfolder}/{file_name}"
            key = f"{subfolder}/{file_name.split('.')[0]}"

        similarity = round(float(similarity), 5) if isinstance(similarity, (int, float)) else similarity
        column = [col1, col2, col3, col4][i % 4]

        with column:
            if os.path.exists(file_path):
                if search_option == "keyframe":
                    # Get frame_idx from mapping for keyframe results
                    try:
                        map_path = f"./data-staging/map-keyframes/{video}.csv"
                        with open(map_path) as map_file:
                            mapping = list(csv.reader(map_file))
                            k = int(kf)
                            if k < len(mapping):
                                _, _, _, frame_idx = mapping[k]
                                st.image(file_path, caption=f"{video} | frame: {frame_idx} | score: {similarity:.4f}", width=WIDTH)
                            else:
                                st.image(file_path, caption=f"{video} | kf: {kf} | score: {similarity:.4f}", width=WIDTH)
                    except (FileNotFoundError, IndexError, ValueError):
                        st.image(file_path, caption=f"{video} | kf: {kf} | score: {similarity:.4f}", width=WIDTH)
                else:  # For ocr_results, frame_idx is already available
                    st.image(file_path, caption=f"{subfolder} | frame: {frame_idx} | score: {similarity:.4f}", width=WIDTH)
            else:
                st.warning(f"Image not found:\n{file_path}")

            if key not in st.session_state["selected_keyframes"]:
                st.session_state["selected_keyframes"][key] = False
            st.session_state["selected_keyframes"][key] = st.checkbox(
                f"Select", key=f"checkbox_{actual_idx}_{key}"
            )

            button_col1, button_col2, button_col3 = st.columns([1, 1, 1])
            with button_col1:
                if st.button(f"view", key=f"view_{actual_idx}_{key}"):
                    play_dialog(
                        video if search_option == "keyframe" else subfolder,
                        kf if search_option == "keyframe" else file_name.split(".")[0],
                    )
            with button_col2:
                if st.button(f"similar", key=f"similar_{actual_idx}_{key}"):
                    video_id = video if search_option == "keyframe" else subfolder
                    kf_id = kf if search_option == "keyframe" else file_name.split(".")[0]
                    handle_recommend(video_id, kf_id)
            with button_col3:
                if st.button(f"frame", key=f"frame_{actual_idx}_{key}"):
                    st.session_state["frame_viewer_video"] = video if search_option == "keyframe" else subfolder
                    st.session_state["frame_number"] = 0
                    st.session_state["show_frame_dialog"] = True
                    st.rerun()
    
    # Render pagination controls at the bottom
    st.markdown("---")
    render_pagination_controls(total_results, "results_bottom")


def handle_export(search_option, query_id, qa_answer, download_placeholder):
    os.makedirs("submission", exist_ok=True)
    outpath = f"submission/{query_id}.csv"
    is_qa = "qa" in query_id

    if search_option == "transcript":
        results = st.session_state.get("transcript_results", [])
        selected_keyframes = []
        unselected_keyframes = []

        for i, result in enumerate(results):
            group_key = f"transcript_group_{i}"
            is_selected = st.session_state.get("selected_keyframes", {}).get(group_key, False)
            
            for kf_info in result.get('keyframes', []):
                video_id = result['video_id']
                kf_name = os.path.basename(kf_info['keyframe_filename'])
                kf_id = kf_name.split('.')[0]
                
                if is_selected:
                    selected_keyframes.append((video_id, kf_id))
                else:
                    unselected_keyframes.append((video_id, kf_id))

        with open(outpath, "w", newline="") as f:
            writer = csv.writer(f)
            def write_keyframes_to_csv(keyframes_list):
                for video_id, kf_id in keyframes_list:
                    map_path = f"./data-staging/map-keyframes/{video_id}.csv"
                    try:
                        with open(map_path) as map_file:
                            mapping = list(csv.reader(map_file))
                            k = int(kf_id)
                            if k < len(mapping):
                                _, _, _, frame_idx = mapping[k]
                                if is_qa:
                                    writer.writerow([video_id, frame_idx, qa_answer])
                                else:
                                    writer.writerow([video_id, frame_idx])
                    except (FileNotFoundError, IndexError, ValueError) as e:
                        logger.warning(f"Could not process keyframe {video_id}/{kf_id}: {e}")
                        continue
            
            write_keyframes_to_csv(selected_keyframes)
            write_keyframes_to_csv(unselected_keyframes)

        logger.info(f"Exported {len(selected_keyframes)} selected keyframes to the top of {outpath}")

    elif search_option == "temporal":
        results = st.session_state.get("temporal_results", [])
        
        selected_sequences = []
        unselected_sequences = []

        for i, result in enumerate(results):
            if st.session_state.get("selected_sequences", {}).get(i, False):
                selected_sequences.append(result)
            else:
                unselected_sequences.append(result)
        
        with open(outpath, "w", newline="") as f:
            writer = csv.writer(f)
            
            def write_sequences_to_csv(sequences):
                for video_id, kf_ids, _, _ in sequences:
                    map_path = f"./data-staging/map-keyframes/{video_id}.csv"
                    try:
                        with open(map_path) as map_file:
                            mapping = list(csv.reader(map_file))
                            for kf_id in kf_ids:
                                k = int(kf_id)
                                if k < len(mapping):
                                    _, _, _, frame_idx = mapping[k]
                                    if is_qa:
                                        writer.writerow([video_id, frame_idx, qa_answer])
                                    else:
                                        writer.writerow([video_id, frame_idx])
                    except FileNotFoundError:
                        logger.warning(f"Map file not found for video: {video_id}")
                        continue
            
            write_sequences_to_csv(selected_sequences)
            write_sequences_to_csv(unselected_sequences)

        logger.info(f"Exported {len(results)} temporal sequences to {outpath}")

    else:
        results = st.session_state["search_results"] or st.session_state["ocr_results"]
        selected_results = [
            result
            for result in results
            if (
                search_option == "keyframe"
                and st.session_state["selected_keyframes"].get(f"{result[0]}/{result[1]}", False)
            )
            or (
                search_option == "ocr"
                and st.session_state["selected_keyframes"].get(f"{result[0]}/{result[1].split('.')[0]}", False)
            )
        ]

        unselected_results = [
            result
            for result in results
            if not (
                (
                    search_option == "keyframe"
                    and st.session_state["selected_keyframes"].get(f"{result[0]}/{result[1]}", False)
                )
                or (
                    search_option == "ocr"
                    and st.session_state["selected_keyframes"].get(f"{result[0]}/{result[1].split('.')[0]}", False)
                )
            )
        ]

        with open(outpath, "w") as f:
            for result in selected_results + unselected_results:
                if search_option == "keyframe":
                    vid, kf, _ = result
                    map_path = f"./data-staging/map-keyframes/{vid}.csv"
                    k = int(kf)
                    with open(map_path) as map_file:
                        map_file = csv.reader(map_file)
                        _, _, _, frame_idx = list(islice(map_file, k + 1))[k]
                    if is_qa:
                        f.write(f"{vid},{frame_idx},\"{qa_answer}\"\n")
                    else:
                        f.write(f"{vid},{frame_idx}\n")
                else:  # For ocr_results
                    subfolder, file_name, frame_idx, _ = result
                    if is_qa:
                        f.write(f"{subfolder},{frame_idx},\"{qa_answer}\"\n")
                    else:
                        f.write(f"{subfolder},{frame_idx}\n")
        logger.info(f"Exported {len(selected_results)} selected keyframes to the top of {outpath}")

    with download_placeholder:
        st.download_button(
            f"Download submission file",
            data=open(outpath),
            file_name=f"{query_id}.csv",
            key="download_export",
        )


if __name__ == "__main__":
    setup_page()
    search_option, vid_to_watch, watch_vid_button, frame_vid_button, search_term, excluded_video, query_id, qa_answer, search_button, export_button, download_placeholder = render_search_ui()

    if "last_search_option" not in st.session_state:
        st.session_state["last_search_option"] = "keyframe"

    if search_button:
        st.session_state["last_search_option"] = search_option
        handle_search(search_option, search_term, query_id, excluded_video)
    
    display_option = st.session_state["last_search_option"]
    if st.session_state.get("search_results") or st.session_state.get("ocr_results"):
        display_results(display_option)
    elif st.session_state.get("temporal_results"):
        display_temporal_results()
    elif st.session_state.get("transcript_results"):
        display_transcript_results()

    if export_button:
        handle_export(search_option, query_id, qa_answer, download_placeholder)
    
    # Show frame viewer dialog if requested
    if st.session_state.get("show_frame_dialog", False):
        frame_viewer_dialog()
