import os
import pandas as pd
import easyocr
from PIL import Image, ImageFilter
import cv2
from tqdm import tqdm
from load_all_video_keyframes_info import load_all_video_keyframes_info

all_video, video_keyframe_dict = load_all_video_keyframes_info()
reader = easyocr.Reader(["vi", "en"], gpu=True)

media_info_df = pd.read_csv("./data-source/media-info.csv")
videos_need_to_preprocess = media_info_df[media_info_df["author"] == "60 Giây Official"]["source_file"].tolist()
videos_need_to_preprocess = [os.path.splitext(v)[0] for v in videos_need_to_preprocess]

def preprocess(file_path):
    image = cv2.imread(file_path)
    # Define the region to black out
    x, y, w, h = 0,650, 1280, 50
    # Black out the defined region
    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 0), -1)

    x , y, w, h = 1045, 50, 150,65
    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 0), -1)
    return image

def process_file(file_path, image_folder):
    print(f"Processing file: {file_path}")
    video_name = os.path.basename(os.path.dirname(file_path))
    if video_name in videos_need_to_preprocess:
        img = preprocess(file_path)
    else:
        img = file_path
    text = reader.readtext(img, detail=0, paragraph=True)
    subfolder = os.path.relpath(os.path.dirname(file_path), image_folder)
    return {
        "file_name": os.path.basename(file_path),
        "subfolder": subfolder,
        "text": " ".join(text),
    }

def perform_ocr_on_images(image_folder, output_csv):
    print("Starting OCR process...")
    
    # Check if output file exists to determine if we need to write headers
    write_headers = not os.path.exists(output_csv)
    
    for v in tqdm(all_video, desc="Processing videos"):
        for kf in tqdm(video_keyframe_dict[v], desc=f"Processing {v}", leave=False):
            file_path = f"./data-staging/keyframes/{v}/{kf}.jpg"
            result = process_file(file_path, image_folder)
            
            # Create DataFrame for this single result
            df = pd.DataFrame([result])
            
            # Write to CSV with proper header handling
            if write_headers:
                df.to_csv(output_csv, mode='w', header=True, index=False)
                write_headers = False  # Only write header once
            else:
                df.to_csv(output_csv, mode='a', header=False, index=False)

    print(f"OCR process completed. Results saved to {output_csv}.")


if __name__ == "__main__":
    image_folder = "./data-staging/keyframes"
    output_csv = "./data-staging/ocr_results.csv"
    perform_ocr_on_images(image_folder, output_csv)

    # This part is to test the ocr in a single picture
    # file_path = './image.png'
    # result = reader.readtext(file_path, detail=0, paragraph=True)
    # for line in result:
    #     print(line)
