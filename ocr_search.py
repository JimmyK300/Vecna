"""
OCR and Caption Search Module using Vintern Results
This module provides search functionality for OCR text and image captions
extracted using the Vintern-1B-v3_5 model.
"""

import csv
import json
import os
import streamlit as st

# Configuration
VINTERN_RESULTS_FILE = './data-staging/vintern_results.json'
MAP_KEYFRAMES_FOLDER = './data-staging/map-keyframes'


def load_csv_file(file_path):
    """Load CSV file and return list of dictionaries"""
    if not os.path.exists(file_path):
        st.error(f"Error: {file_path} does not exist.")
        return []
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        return [row for row in reader]


def load_vintern_data(file_path=VINTERN_RESULTS_FILE):
    """Load the vintern_results.json file"""
    if not os.path.exists(file_path):
        st.error(f"Error: {file_path} does not exist.")
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        st.error(f"Error parsing JSON file: {e}")
        return []


def find_match_in_vintern(input_text, vintern_data, search_type='both'):
    """
    Search in vintern_results.json
    search_type: 'ocr', 'caption', or 'both'
    """
    results = []
    input_lower = input_text.lower()
    
    for item in vintern_data:
        match = False
        
        if search_type in ['ocr', 'both']:
            if 'ocr' in item and input_lower in item['ocr'].lower():
                match = True
        
        if search_type in ['caption', 'both']:
            if 'image-captioning' in item and input_lower in item['image-captioning'].lower():
                match = True
        
        if match:
            results.append(item)
    
    return results

def find_frame_idx_from_keyframe_id(video_id, keyframe_id):
    """
    Find frame index from keyframe ID in the map-keyframes CSV
    
    Args:
        video_id: Video ID (e.g., 'K01_V001')
        keyframe_id: Keyframe ID (e.g., '0001', '0002')
    
    Returns:
        Frame index as string, or None if not found
    """
    map_keyframes_file = os.path.join(MAP_KEYFRAMES_FOLDER, f"{video_id}.csv")
    
    if not os.path.exists(map_keyframes_file):
        return None
    
    keyframes_data = load_csv_file(map_keyframes_file)
    if not keyframes_data:
        return None

    # keyframe_id is like "0001", "0002", etc.
    try:
        keyframe_number = int(keyframe_id)
    except ValueError:
        return None
    
    for row in keyframes_data:
        if int(row['n']) == keyframe_number:
            return row['frame_idx']
    
    return None


def display_search_results(input_text, kf, video):
    """
    Display OCR search results with highlighted text from Vintern data
    
    Args:
        input_text: Search query text
        kf: Keyframe ID
        video: Video ID
    """
    vintern_data = load_vintern_data()
    if not kf:
        st.info("No frame index found.")
        return
    
    print(f"Searching for keyframe {kf} in video {video}")
    
    # Find matching entry in Vintern data
    for item in vintern_data:
        if item.get('video_id') == video and item.get('keyframe_id') == kf:
            ocr_text = item.get('ocr', '')
            if input_text.lower() in ocr_text.lower():
                # Highlight the search term
                highlighted_text = ocr_text.replace(
                    input_text, 
                    f"<span style='background-color: yellow; color: black;'>{input_text}</span>"
                )
                st.write(highlighted_text, unsafe_allow_html=True)
                return
    
    st.info("No OCR text found for this keyframe.")


def search_by_vintern(input_text, search_type='both'):
    """
    Search using vintern_results.json
    
    Args:
        input_text: Search query text
        search_type: 'ocr', 'caption', or 'both' to search in OCR text, image captions, or both
    
    Returns:
        List of tuples (subfolder, filename, frame_idx, score)
    """
    vintern_data = load_vintern_data()
    if not vintern_data:
        st.error("No Vintern data found.")
        return []

    matches = find_match_in_vintern(input_text, vintern_data, search_type)
    if not matches:
        st.info(f"No matches found for '{input_text}' in {search_type} field(s).")
        return []

    result_data = []
    for match in matches:
        video_id = match['video_id']
        keyframe_id = match['keyframe_id']
        
        # Find frame index
        frame_idx = find_frame_idx_from_keyframe_id(video_id, keyframe_id)
        if frame_idx:
            # Convert video_id format for subfolder (e.g., K01_V001 -> Videos_K01)
            parts = video_id.split('_')
            if len(parts) == 2:
                k_part = parts[0]  # K01
                subfolder = f"Videos_{k_part}"
                file_name = f"{keyframe_id}.jpg"
                result_data.append((subfolder, file_name, frame_idx, 0.0))
    
    return result_data


def search_ocr_vintern(input_text):
    """
    Search by OCR text in vintern_results.json
    
    Args:
        input_text: Search query text
    
    Returns:
        List of tuples (video_id, keyframe_id, ocr_text)
    """
    vintern_data = load_vintern_data()
    if not vintern_data:
        print("No Vintern data found.")
        return []

    results = []
    input_lower = input_text.lower()
    
    for item in vintern_data:
        if 'ocr' in item and input_lower in item['ocr'].lower():
            video_id = item.get('video_id', '')
            keyframe_id = item.get('keyframe_id', '')
            ocr_text = item.get('ocr', '')
            results.append((video_id, keyframe_id, ocr_text))
    
    if not results:
        print(f"No OCR matches found for '{input_text}'")
    
    return results


def search_caption_vintern(input_text):
    """
    Search by image caption in vintern_results.json
    
    Args:
        input_text: Search query text
    
    Returns:
        List of tuples (video_id, keyframe_id, caption_text)
    """
    vintern_data = load_vintern_data()
    if not vintern_data:
        print("No Vintern data found.")
        return []

    results = []
    input_lower = input_text.lower()
    
    for item in vintern_data:
        if 'image-captioning' in item and input_lower in item['image-captioning'].lower():
            video_id = item.get('video_id', '')
            keyframe_id = item.get('keyframe_id', '')
            caption_text = item.get('image-captioning', '')
            results.append((video_id, keyframe_id, caption_text))
    
    if not results:
        print(f"No caption matches found for '{input_text}'")
    
    return results

if __name__ == "__main__":
    print("=" * 80)
    print("Vintern OCR & Caption Search Test")
    print("=" * 80)
    
    # Test 1: Search for text in OCR
    print("\n[Test 1] Searching for '60 giây' in OCR...")
    results = search_ocr_vintern("60 giây")
    print(f"Found {len(results)} results:")
    for i, (video_id, keyframe_id, ocr_text) in enumerate(results[:5], 1):  # Show first 5
        print(f"  {i}. Video: {video_id}, Keyframe: {keyframe_id}")
        print(f"     OCR: {ocr_text[:100]}...")  # Truncate long text
    
    # Test 2: Search for text in captions
    print("\n[Test 2] Searching for 'người đàn ông' in captions...")
    results2 = search_caption_vintern("người đàn ông")
    print(f"Found {len(results2)} results:")
    for i, (video_id, keyframe_id, caption_text) in enumerate(results2[:3], 1):  # Show first 3
        print(f"  {i}. Video: {video_id}, Keyframe: {keyframe_id}")
        print(f"     Caption: {caption_text[:100]}...")
    
    # Test 3: Search in both OCR and captions
    print("\n[Test 3] Searching for 'thành phố' in both OCR and captions...")
    results3 = search_by_vintern("thành phố", search_type='both')
    print(f"Found {len(results3)} results (subfolder, filename, frame_idx, score):")
    for i, result in enumerate(results3[:5], 1):  # Show first 5
        subfolder, filename, frame_idx, score = result
        print(f"  {i}. {subfolder}/{filename} - Frame: {frame_idx}")
    
    # Test 4: Search only in OCR
    print("\n[Test 4] Searching for 'tin tức' in OCR only...")
    results4 = search_by_vintern("tin tức", search_type='ocr')
    print(f"Found {len(results4)} results")
    
    # Test 5: Search only in captions
    print("\n[Test 5] Searching for 'cảnh đẹp' in captions only...")
    results5 = search_by_vintern("cảnh đẹp", search_type='caption')
    print(f"Found {len(results5)} results")
    
    print("\n" + "=" * 80)
    print("Test completed!")
    print("=" * 80)