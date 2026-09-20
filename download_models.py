import os
import sys
import torch
import nltk
from pathlib import Path

def log(msg):
    print(f"\n{'='*50}\n{msg}\n{'='*50}", flush=True)

def download_nltk():
    log("[1/7] Downloading NLTK resources...")
    for res in ["punkt", "punkt_tab", "averaged_perceptron_tagger"]:
        try:
            nltk.download(res, quiet=False)
        except Exception as e:
            print(f"Warning: could not download NLTK {res}: {e}")

def download_yolo():
    log("[2/7] Downloading YOLOv8x weights...")
    try:
        from ultralytics import YOLO
        model = YOLO("yolov8x.pt")
        print("YOLOv8x downloaded successfully.")
    except Exception as e:
        print(f"Error downloading YOLOv8x: {e}")

def download_open_clip_models():
    log("[3/7] Downloading OpenCLIP models (PE-Core-L-14-336 & SigLIP)...")
    import open_clip

    print("--> 3a. Downloading PE-Core-L-14-336 (pretrained='meta')...")
    try:
        open_clip.create_model_and_transforms("PE-Core-L-14-336", pretrained="meta")
        open_clip.get_tokenizer("PE-Core-L-14-336")
        print("PE-Core-L-14-336 downloaded successfully.")
    except Exception as e:
        print(f"Error downloading PE-Core-L-14-336: {e}")

    print("--> 3b. Downloading ViT-SO400M-14-SigLIP-384 (pretrained='webli')...")
    try:
        open_clip.create_model_and_transforms("ViT-SO400M-14-SigLIP-384", pretrained="webli")
        open_clip.get_tokenizer("ViT-SO400M-14-SigLIP-384")
        print("ViT-SO400M-14-SigLIP-384 downloaded successfully.")
    except Exception as e:
        print(f"Error downloading ViT-SO400M-14-SigLIP-384: {e}")

def download_bge_models():
    log("[4/7] Downloading BGE-M3 & Reranker...")
    from transformers import AutoModel, AutoTokenizer
    from sentence_transformers import CrossEncoder

    print("--> 4a. Downloading BAAI/bge-m3...")
    try:
        AutoTokenizer.from_pretrained("BAAI/bge-m3")
        AutoModel.from_pretrained("BAAI/bge-m3")
        print("BAAI/bge-m3 downloaded successfully.")
    except Exception as e:
        print(f"Error downloading BAAI/bge-m3: {e}")

    print("--> 4b. Downloading BAAI/bge-reranker-v2-m3...")
    try:
        CrossEncoder("BAAI/bge-reranker-v2-m3")
        print("BAAI/bge-reranker-v2-m3 downloaded successfully.")
    except Exception as e:
        print(f"Error downloading BAAI/bge-reranker-v2-m3: {e}")

def download_qwen_vl():
    log("[5/7] Downloading Qwen/Qwen3-VL-Embedding-2B...")
    try:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer("Qwen/Qwen3-VL-Embedding-2B")
        print("Qwen/Qwen3-VL-Embedding-2B downloaded successfully.")
    except Exception as e:
        print(f"Error downloading Qwen/Qwen3-VL-Embedding-2B: {e}")

def download_qwen_vl_reranker():
    log("[5b/7] Downloading Qwen/Qwen3-VL-Reranker-2B...")
    try:
        from sentence_transformers import CrossEncoder
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if (device == "cuda" and torch.cuda.is_bf16_supported()) else (torch.float16 if device == "cuda" else torch.float32)
        CrossEncoder("Qwen/Qwen3-VL-Reranker-2B", device=device, trust_remote_code=True, model_kwargs={"torch_dtype": dtype})
        print("Qwen/Qwen3-VL-Reranker-2B downloaded successfully.")
    except Exception as e:
        print(f"Error downloading Qwen/Qwen3-VL-Reranker-2B: {e}")

def download_whisper():
    log("[6/7] Downloading WhisperX / Faster-Whisper large-v3-turbo...")
    try:
        import whisperx
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        print(f"Loading whisperx large-v3-turbo on device={device}, compute_type={compute_type}...")
        whisperx.load_model("large-v3-turbo", device=device, compute_type=compute_type)
        print("WhisperX large-v3-turbo downloaded successfully.")
    except Exception as e:
        print(f"Error downloading WhisperX large-v3-turbo: {e}")

def main():
    print(f"Python: {sys.executable}")
    print(f"CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    download_nltk()
    download_yolo()
    download_open_clip_models()
    download_bge_models()
    download_qwen_vl()
    download_qwen_vl_reranker()
    download_whisper()
    log("[7/7] All downloads completed!")

if __name__ == "__main__":
    main()
