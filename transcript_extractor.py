import os
import subprocess
import whisperx
import asyncio
from googletrans import Translator

import helpers
from helpers import get_logger
from load_all_video_keyframes_info import load_all_video_keyframes_info

logger = get_logger()

batch_size = 1  # reduce if low on GPU mem
# whisperx_model = whisperx.load_model(
#     "large-v2", "cuda", compute_type="float16", language="vi"
# )
whisperx_model = whisperx.load_model(
    # "large-v2", "cpu", compute_type="int8", language="vi"
    "turbo", "cuda", compute_type="int8", language="vi"
)

translator = Translator()


async def translate_text(text, src='vi', dest='en'):
    """Translates a single string of text."""
    try:
        translated = await translator.translate(text, src=src, dest=dest)
        return translated.text
    except Exception as e:
        logger.error(f"Could not translate sentence: '{text}'. Error: {e}")
        return f"[TRANSLATION_ERROR] {text}"

def video_to_audio(video_path, audio_path):
    """
    Extracts audio from a video file using ffmpeg, silent, GPU-accelerated mode
    """
    logger.debug(f"converting video {video_path} to {audio_path}")
    # command = f"ffmpeg -hide_banner -loglevel error -hwaccel cuda -y -i {video_path} -acodec pcm_s16le -ac 1 -ar 16000 -vn {audio_path}"
    command = f"ffmpeg -hide_banner -loglevel error -y -i {video_path} -acodec pcm_s16le -ac 1 -ar 16000 -vn {audio_path}"
    subprocess.call(command, shell=True)

async def whisperx_speech_to_text(audio_path, video_path, transcript_path):
    audio = whisperx.load_audio(audio_path)
    result = whisperx_model.transcribe(
        audio, batch_size=batch_size, print_progress=True
    )
    # print(result["segments"])  # before alignment

    text = ""
    vid_name = os.path.basename(video_path)[:-4]
    with open(f"./data-staging/audio-chunk-timestamps/{vid_name}.csv", "w") as ts_file:
        ts_file.write("start_time,end_time\n")
        for v in result["segments"]:
            original_text = v["text"].strip()
            translated_text = await translate_text(original_text)
            text += translated_text
            text += "\n"
            ts_file.write(f"""{v["start"]},{v["end"]}\n""")
    # print(text)

    # 2. Align whisper output
    # model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
    # result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
    # print(result["segments"])  # after alignment

    with open(transcript_path, "w") as f:
        f.write(text)
    
async def main_async():
    all_video, video_keyframe_dict = load_all_video_keyframes_info()
    for v in all_video:
        video_path = f"./data-source/videos/{v}.mp4"
        audio_path = os.path.basename(video_path)
        audio_path = f"./data-staging/audios/{audio_path[:-4]}.wav"
        transcript_path = f"./data-staging/transcripts/{v}.txt"

        if helpers.is_exits(transcript_path):
            logger.debug(f"ignore {transcript_path}")
            continue

        if not helpers.is_exits(audio_path):
            video_to_audio(video_path, audio_path)

        logger.info(f"running speech to text from {audio_path} to {transcript_path} ...")
        await whisperx_speech_to_text(audio_path, video_path, transcript_path)

if __name__ == "__main__":
    asyncio.run(main_async())