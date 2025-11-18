import os
import json

def check_missing_videos():
    """
    Checks for videos that exist in the source directory but have not been processed by vintern.
    """
    videos_dir = 'data-source/videos'
    vintern_results_path = 'data-staging/vintern_results.json'

    # 1. Get all video filenames from the videos directory
    try:
        all_videos = [f.split('.')[0] for f in os.listdir(videos_dir) if f.endswith('.mp4')]
    except FileNotFoundError:
        print(f"Error: Directory not found at {videos_dir}")
        return

    # 2. Get all processed video_ids from the vintern results
    try:
        with open(vintern_results_path, 'r', encoding='utf-8') as f:
            vintern_data = json.load(f)
        
        processed_videos = sorted(list(set(item['video_id'] for item in vintern_data)))
    except FileNotFoundError:
        print(f"Error: File not found at {vintern_results_path}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {vintern_results_path}")
        return

    # 3. Find the difference
    unprocessed_videos = sorted(list(set(all_videos) - set(processed_videos)))

    if unprocessed_videos:
        print("Found unprocessed videos:")
        for video_id in unprocessed_videos:
            print(video_id)
    else:
        print("All videos have been processed by vintern.")

def check_missing_keyframes():
    """
    Checks for videos that have keyframes but are not in the vintern results.
    """
    keyframes_dir = 'data-staging/keyframes'
    vintern_results_path = 'data-staging/vintern.json'

    # 1. Get all video directories from the keyframes directory
    try:
        all_keyframes_videos = [d for d in os.listdir(keyframes_dir) if os.path.isdir(os.path.join(keyframes_dir, d))]
    except FileNotFoundError:
        print(f"Error: Directory not found at {keyframes_dir}")
        return

    # 2. Get all processed video_ids from the vintern results
    try:
        with open(vintern_results_path, 'r', encoding='utf-8') as f:
            vintern_data = json.load(f)
        
        processed_videos = sorted(list(set(item['video_id'] for item in vintern_data)))
    except FileNotFoundError:
        print(f"Error: File not found at {vintern_results_path}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {vintern_results_path}")
        return

    # 3. Find the difference
    missing_keyframes_videos = sorted(list(set(all_keyframes_videos) - set(processed_videos)))

    if missing_keyframes_videos:
        print("\nFound videos with keyframes but missing from vintern results:")
        for video_id in missing_keyframes_videos:
            print(video_id)
    else:
        print("\nAll videos with keyframes have been processed by vintern.")

if __name__ == '__main__':
    check_missing_videos()
    check_missing_keyframes()
