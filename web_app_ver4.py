import csv
import os
from itertools import islice
from typing import Tuple

import numpy as np
import streamlit as st
from PIL import Image

from keyframe_search import keyframe_search
from helpers import get_logger
from ocr_search import display_search_results, search_by_ocr
from temporal_search import search_by_temporal
from transcript_search import transcript_search

WIDTH = 350

# Initialize session state
if "cached" not in st.session_state:
    st.session_state["cached"] = {}

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

logger = get_logger()


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
    st.video(
        f"./data-source/videos/{video}.mp4",
        autoplay=True,
        start_time=int(start) / int(fps[:-2]),
        end_time=int(end) / int(fps[:-2]),
    )

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
        display_search_results(search_term, kf, video)

    st.image(file_path, caption=f"{video},{frame_idx}", use_column_width=True)


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
    search_option = st.radio("Search by:", ("keyframe", "ocr", "temporal", "transcript"))
    search_term = st.text_area("Ask a question here:", height=100)
    query_id = st.text_input(
        "Unique query id (used for export filename)", value="query-0-kis"
    )
    col1, col2 = st.columns(2)
    with col1:
        search_button = st.button("SEARCH", type="primary")
    with col2:
        export_button = st.button("Export Selected Keyframes")
    
    download_placeholder = st.empty()
    
    return search_option, search_term, query_id, search_button, export_button, download_placeholder


def handle_search(search_option, search_term, query_id):
    with st.spinner("Fetching Answer..."):
        st.session_state["ocr_results"] = []
        st.session_state["search_results"] = []
        st.session_state["temporal_results"] = []
        st.session_state["transcript_results"] = []
        st.session_state["selected_keyframes"] = {}
        st.session_state["selected_sequences"] = {}
        search_term = search_term.strip()
        logger.info("searching...", search_term)

        if search_option == "keyframe":
            if st.session_state["cached"].get(search_term):
                logger.info("fetch from cache")
                st.session_state["search_results"] = st.session_state["cached"].get(search_term)
            else:
                logger.info("fetch from source")
                st.session_state["search_results"] = keyframe_search(
                    search_term, limit=300
                )
                st.session_state["cached"][search_term] = st.session_state["search_results"]
        elif search_option == "ocr":
            st.session_state["ocr_results"] = search_by_ocr(search_term)
        elif search_option == "temporal":
            st.session_state["temporal_results"] = search_by_temporal(search_term, limit=50)
        elif search_option == "transcript":
            st.session_state["transcript_results"] = transcript_search(search_term, top_k=50)


def display_transcript_results():
    results = st.session_state.get("transcript_results", [])
    if not results:
        return

    st.write(f"Found {len(results)} relevant transcript sentences.")

    for i, result in enumerate(results):
        st.markdown("---")
        video_id = result['video_id']
        sentence = result['sentence']
        score = result['similarity_score']
        keyframes = result.get('keyframes', [])

        st.subheader(f"Result {i+1}: Video `{video_id}` | Similarity: `{score:.4f}`")
        st.markdown(f"> {sentence}")

        if not keyframes:
            st.warning("No keyframes found for this sentence's time interval.")
            continue

        # Create a selection box for the entire result group
        group_key = f"transcript_group_{i}"
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
                    st.image(file_path, caption=f"kf: {kf_id} @ {kf_info['timestamp']}", width=WIDTH)
                else:
                    st.warning(f"Not found:\n{file_path}")

                key = f"{video_id}/{kf_id}"
                # Use two columns for the buttons to place them side-by-side
                button_col1, button_col2 = st.columns([1, 1])
                with button_col1:
                    if st.button(f"view {key}", key=f"view_transcript_{i}_{j}"):
                        play_dialog(video_id, kf_id)
                with button_col2:
                    if st.button(f"zoom {key}", key=f"zoom_transcript_{i}_{j}"):
                        zoom_image(file_path, video_id, kf_id, option="keyframe")


def display_temporal_results():
    results = st.session_state.get("temporal_results", [])
    if not results:
        return

    st.write(f"Found {len(results)} temporal sequences.")

    for i, (video_id, kf_ids, scores, avg_similarity) in enumerate(results):
        st.markdown("---")
        
        col1, col2 = st.columns([0.9, 0.1])
        with col1:
            st.subheader(f"Sequence {i+1}: Video `{video_id}` | Avg. Similarity: `{avg_similarity:.4f}`")
        with col2:
            if i not in st.session_state["selected_sequences"]:
                st.session_state["selected_sequences"][i] = False
            st.session_state["selected_sequences"][i] = st.checkbox(
                "Select", key=f"select_seq_{i}"
            )

        num_columns = 4 
        cols = st.columns(num_columns)

        for j, kf_id in enumerate(kf_ids):
            with cols[j % num_columns]:
                score = scores[j]
                kf_id_str = str(kf_id).zfill(4)
                file_path = f"./data-staging/keyframes/{video_id}/{kf_id_str}.jpg"
                if os.path.exists(file_path):
                    st.image(file_path, caption=f"kf: {kf_id_str} | score: {score:.4f}", width=WIDTH)
                else:
                    st.warning(f"Not found:\n{file_path}")

                key = f"{video_id}/{kf_id}"
                button_col1, button_col2 = st.columns([1, 1])
                with button_col1:
                    if st.button(f"view {key}", key=f"view_temporal_{i}_{j}"):
                        play_dialog(video_id, kf_id)
                with button_col2:
                    if st.button(f"zoom {key}", key=f"zoom_temporal_{i}_{j}"):
                        zoom_image(file_path, video_id, kf_id, option="temporal")


def display_results(search_option):
    col1, col2, col3, col4 = st.columns(4)
    results = st.session_state["search_results"] or st.session_state["ocr_results"]

    for i, result in enumerate(results):
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
            st.image(file_path, caption=similarity, width=WIDTH)

            if key not in st.session_state["selected_keyframes"]:
                st.session_state["selected_keyframes"][key] = False
            st.session_state["selected_keyframes"][key] = st.checkbox(
                f"Select {key}", key=f"checkbox_{key}"
            )

            button_col1, button_col2 = st.columns([1, 1])
            with button_col1:
                if st.button(f"view {key}", key=f"view_{key}"):
                    play_dialog(
                        video if search_option == "keyframe" else subfolder,
                        kf if search_option == "keyframe" else file_name.split(".")[0],
                    )
            with button_col2:
                if st.button(f"zoom {key}", key=f"zoom_{key}"):
                    zoom_image(
                        file_path,
                        video if search_option == "keyframe" else subfolder,
                        kf if search_option == "keyframe" else file_name.split(".")[0],
                        search_option,
                    )


def handle_export(search_option, query_id, download_placeholder):
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
                                    writer.writerow([video_id, frame_idx, ""])
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
                                        writer.writerow([video_id, frame_idx, ""])
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
                        f.write(f"{vid},{frame_idx},\n")
                    else:
                        f.write(f"{vid},{frame_idx}\n")
                else:  # For ocr_results
                    subfolder, file_name, frame_idx, _ = result
                    if is_qa:
                        f.write(f"{subfolder},{frame_idx},\n")
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
    search_option, search_term, query_id, search_button, export_button, download_placeholder = render_search_ui()

    if search_button:
        handle_search(search_option, search_term, query_id)

    if st.session_state["search_results"] or st.session_state["ocr_results"]:
        display_results(search_option)
    elif st.session_state["temporal_results"]:
        display_temporal_results()
    elif st.session_state["transcript_results"]:
        display_transcript_results()

    if export_button:
        handle_export(search_option, query_id, download_placeholder)
