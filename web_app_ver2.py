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

WIDTH = 350

# Initialize session state
if "cached" not in st.session_state:
    st.session_state["cached"] = {}

if "search_results" not in st.session_state:
    st.session_state["search_results"] = []

if "ocr_results" not in st.session_state:
    st.session_state["ocr_results"] = []

if "selected_keyframes" not in st.session_state:
    st.session_state["selected_keyframes"] = {}

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
    search_option = st.radio("Search by:", ("keyframe", "ocr"))
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
        st.session_state["selected_keyframes"] = {}
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

    os.makedirs("submission", exist_ok=True)
    outpath = f"submission/{query_id}.csv"
    is_qa = "qa" in query_id

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

    if export_button:
        handle_export(search_option, query_id, download_placeholder)
