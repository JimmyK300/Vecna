import csv
import json
import os
import streamlit as st

ocr_results_file = './data-staging/ocr_results.csv'
vintern_results_file = './data-staging/vintern_results.json'
map_keyframes_folder = './data-staging/map-keyframes'

def load_csv_file(file_path):
    if not os.path.exists(file_path):
        st.error(f"Error: {file_path} does not exist.")
        return []
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        return [row for row in reader]

def load_vintern_data(file_path):
    """Load the vintern_results.json file"""
    if not os.path.exists(file_path):
        st.error(f"Error: {file_path} does not exist.")
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_match_in_ocr(input_text, ocr_data):
    results = []
    for row in ocr_data:
        if input_text.lower() in row['text'].lower():
            results.append(row)
    return results

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

def find_frame_idx(subfolder, file_name):
    map_keyframes_file = os.path.join(map_keyframes_folder, f"{subfolder}.csv")
    keyframes_data = load_csv_file(map_keyframes_file)

    if not keyframes_data:
        return None

    file_number = int(file_name.split('.')[0])
    file_number_adjusted = file_number + 1

    for row in keyframes_data:
        if int(row['n']) == file_number_adjusted:
            return row['frame_idx']
    return None

def display_search_results(input_text, kf, video):
    ocr_data = load_csv_file(ocr_results_file)
    if not kf:
        st.info("No frame index found.")
        return
    
    print(f"Searching for {kf}")
    kf_with_extension = f"{kf}.jpg"
    for row in ocr_data:
        if kf_with_extension in row['file_name'] and video in row['subfolder']:
            highlighted_text = row["text"].replace(input_text, f"<span style='color: yellow;'>{input_text}</span>")
            st.write(highlighted_text, unsafe_allow_html=True)
    
def search_by_ocr(input_text):
    """Search using the CSV OCR results (legacy)"""
    ocr_data = load_csv_file(ocr_results_file)
    if not ocr_data:
        st.error("No OCR data found.")
        return []

    matches = find_match_in_ocr(input_text, ocr_data)
    if not matches:
        reversed_text = input_text[::-1]
        matches = find_match_in_ocr(reversed_text, ocr_data)
        if not matches:
            st.info("No OCR matches found.")
            return []

    result_data = []
    for match in matches:
        subfolder = match['subfolder']
        file_name = match['file_name']
        frame_idx = find_frame_idx(subfolder, file_name)
        if frame_idx:
            result_data.append((subfolder, file_name, frame_idx, 0.0))  
    return result_data

def search_by_vintern(input_text, search_type='both'):
    """
    Search using vintern_results.json
    search_type: 'ocr', 'caption', or 'both' to search in OCR text, image captions, or both
    """
    vintern_data = load_vintern_data(vintern_results_file)
    if not vintern_data:
        st.error("No vintern data found.")
        return []

    matches = find_match_in_vintern(input_text, vintern_data, search_type)
    if not matches:
        st.info(f"No matches found for '{input_text}' in {search_type} field(s).")
        return []

    result_data = []
    for match in matches:
        video_id = match['video_id']
        keyframe_id = match['keyframe_id']
        
        # Convert video_id format (e.g., K01_V001 -> Videos_K01/K01_V001)
        # Assuming format: K##_V###
        parts = video_id.split('_')
        if len(parts) == 2:
            k_part = parts[0]  # K01
            subfolder = f"Videos_{k_part}"
            
            # Find frame index
            frame_idx = find_frame_idx_from_keyframe_id(subfolder, video_id, keyframe_id)
            if frame_idx:
                file_name = f"{keyframe_id}.jpg"
                result_data.append((subfolder, file_name, frame_idx, 0.0))
    
    return result_data

def find_frame_idx_from_keyframe_id(video_id, keyframe_id):
    """Find frame index from keyframe ID in the map-keyframes CSV"""
    map_keyframes_file = os.path.join(map_keyframes_folder, f"{video_id}.csv")
    
    if not os.path.exists(map_keyframes_file):
        return None
    
    keyframes_data = load_csv_file(map_keyframes_file)
    if not keyframes_data:
        return None

    # keyframe_id is like "0001", "0002", etc.
    keyframe_number = int(keyframe_id)
    
    for row in keyframes_data:
        if int(row['n']) == keyframe_number:
            return row['frame_idx']
    
    return None

def search_ocr_vintern(input_text):
    """
    Search by OCR text in vintern_results.json
    Returns: List of tuples (video_id, keyframe_id, ocr_text)
    """
    vintern_data = load_vintern_data(vintern_results_file)
    if not vintern_data:
        print("No vintern data found.")
        return []

    results = []
    input_lower = input_text.lower()
    
    for item in vintern_data:
        if 'ocr' in item and input_lower in item['ocr'].lower():
            video_id = item['video_id']
            keyframe_id = item['keyframe_id']
            ocr_text = item['ocr']
            results.append((video_id, keyframe_id, ocr_text))
    
    if not results:
        print(f"No OCR matches found for '{input_text}'")
    
    return results

if __name__ == "__main__":
    print("=" * 80)
    print("OCR Search Test")
    print("=" * 80)
    
    # Test 1: Search for "60 giây"
    print("\n[Test 1] Searching for '60 giây' in OCR...")
    results = search_ocr_vintern("60 giây")
    print(f"Found {len(results)} results:")
    for i, (video_id, keyframe_id, ocr_text) in enumerate(results[:5], 1):  # Show first 5
        print(f"  {i}. Video: {video_id}, Keyframe: {keyframe_id}")
        print(f"     OCR: {ocr_text}")
    
    # Test 2: Search for a common word
    print("\n[Test 2] Searching for 'tin chính' in OCR...")
    results2 = search_ocr_vintern("tin chính")
    print(f"Found {len(results2)} results:")
    for i, (video_id, keyframe_id, ocr_text) in enumerate(results2[:3], 1):  # Show first 3
        print(f"  {i}. Video: {video_id}, Keyframe: {keyframe_id}")
        print(f"     OCR: {ocr_text}")
    
    # Test 3: Search for something that might not exist
    print("\n[Test 3] Searching for 'xyz123' in OCR...")
    results3 = search_ocr_vintern("xyz123")
    print(f"Found {len(results3)} results")
    
    # Test 4: Search in both OCR and captions
    print("\n[Test 4] Searching for 'thành phố' in both OCR and captions...")
    results4 = search_by_vintern("thành phố", search_type='both')
    print(f"Found {len(results4)} results (subfolder, filename, frame_idx, score):")
    for i, result in enumerate(results4[:3], 1):  # Show first 3
        print(f"  {i}. {result}")
    
    print("\n" + "=" * 80)
    print("Test completed!")
    print("=" * 80)