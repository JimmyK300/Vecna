import json
from load_all_video_keyframes_info import load_all_video_keyframes_info

def check_missing_keyframes(json_file):
    """
    Checks for missing video_id and keyframe_id combinations in the results JSON file.
    """
    all_video, video_keyframe_dict = load_all_video_keyframes_info()

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Error: Could not read or parse {json_file}")
        data = []

    existing_entries = set((item.get('video_id'), str(item.get('keyframe_id'))) for item in data)
    
    missing_count = 0
    for video_id in all_video:
        for keyframe_id in video_keyframe_dict.get(video_id, []):
            if (video_id, str(keyframe_id)) not in existing_entries:
                print(f"Missing entry: video_id={video_id}, keyframe_id={keyframe_id}")
                missing_count += 1
    
    if missing_count == 0:
        print("No missing keyframes found.")
    else:
        print(f"\nTotal missing entries: {missing_count}")

if __name__ == "__main__":
    results_file = 'data-staging/vintern_ocr_results.csv'
    check_missing_keyframes(results_file)
