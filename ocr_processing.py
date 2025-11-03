import os
import pandas as pd
import easyocr
from PIL import Image, ImageFilter
import cv2
from tqdm import tqdm
from load_all_video_keyframes_info import load_all_video_keyframes_info

all_video, video_keyframe_dict = load_all_video_keyframes_info()

from ocr_object import *
import os
from pathlib import Path

media_info_df = pd.read_csv("./data-source/media-info.csv")
videos_need_to_preprocess = media_info_df[media_info_df["author"] == "60 Giây Official"]["source_file"].tolist()
videos_need_to_preprocess = [os.path.splitext(v)[0] for v in videos_need_to_preprocess]

def preprocess(file_path):
    image = cv2.imread(file_path)
    height, width = image.shape[:2]
    if height == 720 and width == 1280:
        # Define the region to black out
        x, y, w, h = 0,650, 1280, 50
        # Black out the defined region
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 0), -1)

        x , y, w, h = 1045, 50, 150,65
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 0), -1)
    elif height == 1080 and width == 1920:
        # Define the region to black out
        x, y, w, h = 0,975, 1920, 75
        # Black out the defined region
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 0), -1)

        x , y, w, h = 1565, 75, 225,100
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 0), -1)
    return image

def process_file(file_path, video_id, keyframe_id):
    print(f"Processing file: {file_path}")
    temp_path = f"./data-staging/{video_id}_{keyframe_id}.jpg"
    img_pre = preprocess(file_path)  # Preprocess the image
    cv2.imwrite(str(temp_path), img_pre)
    img = file_path
    pixel_values = load_image(temp_path, max_num=6).to(torch.bfloat16).cuda()
    generation_config = dict(max_new_tokens= 1024, do_sample=False, num_beams = 3, repetition_penalty=2.5)
    
    if os.path.exists(temp_path): # Remove temp file
        os.remove(temp_path)
    
    prompt = '<image>\nĐối với hình ảnh được cung cấp, hãy thực hiện hai tác vụ sau và trả về kết quả dưới dạng một đối tượng JSON duy nhất:\n' \
    '1.  **image-captioning**: Cung cấp mô tả chi tiết về nội dung của hình ảnh.\n' \
    '2.  **ocr**: Trích xuất toàn bộ văn bản (chữ) có thể nhận diện được từ hình ảnh. Nếu không có văn bản nào được nhận diện, hãy trả về "".\n' \
    'Đảm bảo rằng văn bản được trích xuất giữ nguyên định dạng và cấu trúc ban đầu.\n' \
    'Định dạng phản hồi phải là một đối tượng JSON với hai trường: "image-captioning" và "ocr".\n'

    response, history = model.chat(tokenizer, pixel_values, prompt, generation_config, history=None, return_history=True)

    try:
        cleaned_response = re.sub(r'```json\s*|\s*```', '', response).strip()
        response_obj = json.loads(cleaned_response)
    except json.JSONDecodeError:
        response_obj = {"text": re.sub(r'\s+', ' ', response).strip()}

    if isinstance(response_obj, dict):
        entry = {
            "video_id": video_id,
            "keyframe_id": keyframe_id,
            **response_obj
        }
    else:
        entry = {
            "video_id": video_id,
            "keyframe_id": keyframe_id,
            "response": response_obj
        }
    return entry

def perform_ocr_on_images(output_json):
    print("Starting OCR process...")
    
    if os.path.exists(output_json):
        try:
            with open(output_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
        except (json.JSONDecodeError, IOError):
            data = []
    else:
        data = []

    existing_entries = set((item.get('video_id'), item.get('keyframe_id')) for item in data)

    for v in tqdm(all_video, desc="Processing videos"):
        for kf in tqdm(video_keyframe_dict[v], desc=f"Processing {v}", leave=False):
            if (v, kf) in existing_entries:
                continue

            file_path = f"./data-staging/keyframes/{v}/{kf}.jpg"
            if not os.path.exists(file_path):
                continue
            
            result = process_file(file_path, v, kf)
            data.append(result)
            
            with open(output_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"OCR process completed. Results saved to {output_json}.")


if __name__ == "__main__":
    output_json = "./data-staging/vintern_results.json"
    perform_ocr_on_images(output_json)

    # # demo: run and save a before/after of preprocess on a sample keyframe

    # # choose a demo video/keyframe
    # if videos_need_to_preprocess:
    #     demo_video = videos_need_to_preprocess[0]
    # elif all_video:
    #     demo_video = all_video[0]
    # else:
    #     demo_video = None

    # if demo_video is None:
    #     print("No videos available for demo.")
    # else:
    #     kf_list = video_keyframe_dict.get(demo_video, [])
    #     if not kf_list:
    #         print(f"No keyframes found for video {demo_video}.")
    #     else:
    #         demo_kf = kf_list[20]
    #         src_path = f"./data-staging/keyframes/{demo_video}/{demo_kf}.jpg"
    #         if not os.path.exists(src_path):
    #             print(f"Demo keyframe not found: {src_path}")
    #         else:
    #             out_dir = Path("./data-staging/demo")
    #             out_dir.mkdir(parents=True, exist_ok=True)

    #             # save original copy
    #             orig_out = out_dir / f"{demo_video}_{demo_kf}_orig.jpg"
    #             pre_out = out_dir / f"{demo_video}_{demo_kf}_preprocessed.jpg"

    #             img_orig = cv2.imread(src_path)
    #             cv2.imwrite(str(orig_out), img_orig)

    #             img_pre = preprocess(src_path)  
    #             cv2.imwrite(str(pre_out), img_pre)

    #             print(f"Demo saved:\n - original: {orig_out}\n - preprocessed: {pre_out}")
