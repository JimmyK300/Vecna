import os
import pandas as pd
from PIL import Image, ImageFilter
import cv2
from tqdm import tqdm
from load_all_video_keyframes_info import load_all_video_keyframes_info
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
import threading

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
    # Model and tokenizer are now initialized per-process via the executor's initializer
    model, tokenizer = get_model_and_tokenizer()
    print(f"Processing file: {file_path} in process {os.getpid()}")

    img_path_to_load = file_path
    temp_file_handle = None

    try:
        video_name = os.path.basename(os.path.dirname(file_path))
        if video_name in videos_need_to_preprocess:
            processed_image = preprocess(file_path)
            
            # Create a temporary file to save the preprocessed image
            temp_file_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            cv2.imwrite(temp_file_handle.name, processed_image)
            img_path_to_load = temp_file_handle.name
            temp_file_handle.close() # Close the file handle so load_image can open it

        pixel_values = load_image(img_path_to_load, max_num=6).to(torch.bfloat16).cuda()
        generation_config = dict(max_new_tokens= 1024, do_sample=False, num_beams = 3, repetition_penalty=2.5)

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
    finally:
        if temp_file_handle:
            os.unlink(temp_file_handle.name)

def perform_ocr_on_images(output_json, max_workers):
    print("Starting OCR process with multiprocessing...")
    
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

    existing_entries = set((item.get('video_id'), str(item.get('keyframe_id'))) for item in data)

    tasks_to_process = []
    for v in all_video:
        for kf in video_keyframe_dict[v]:
            if (v, str(kf)) not in existing_entries:
                file_path = f"./data-staging/keyframes/{v}/{kf}.jpg"
                if os.path.exists(file_path):
                    tasks_to_process.append((file_path, v, kf))

    # Using ProcessPoolExecutor for true parallelism
    with ProcessPoolExecutor(max_workers=max_workers, initializer=init_model_and_tokenizer) as executor:
        future_to_task = {executor.submit(process_file, *task): task for task in tasks_to_process}
        
        for future in tqdm(as_completed(future_to_task), total=len(tasks_to_process), desc="Processing keyframes"):
            try:
                result = future.result()
                if result:
                    data.append(result)
                    
                    # Write periodically to save progress
                    with open(output_json, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as exc:
                task = future_to_task[future]
                print(f'Task {task} generated an exception: {exc}')

    print(f"OCR process completed. Results saved to {output_json}.")


if __name__ == "__main__":
    output_json = "./data-staging/vintern_results.json"
    # Set number of workers, e.g., number of CPU cores or GPUs
    # perform_ocr_on_images(output_json, max_workers=os.cpu_count() or 1) #CRASHES ON MY PC
    perform_ocr_on_images(output_json, max_workers=4)

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
