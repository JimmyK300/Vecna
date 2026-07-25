import sys
import argparse
from pathlib import Path
from video_clip_extractor import VideoCLIPExtractor

# Configure stdout to use UTF-8 for Vietnamese printing
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description="Test VideoCLIP Feature Extractor")
    parser.add_argument(
        "--video", 
        type=str, 
        default=None, 
        help="Path to the video file to test"
    )
    parser.add_argument(
        "--model", 
        type=str, 
        default="openai/clip-vit-base-patch32", 
        help="Pretrained CLIP model name on Hugging Face"
    )
    parser.add_argument(
        "--device", 
        type=str, 
        default=None, 
        help="Device to run on (cuda or cpu)"
    )
    args = parser.parse_args()

    # Determine default device dynamically
    import torch
    device = args.device
    if not device:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    # Find a default video path if not provided
    video_path = args.video
    if not video_path:
        # Check if there is a sample video in the workspace
        workspace_video = Path(__file__).resolve().parent.parent / "workspace" / "data" / "video_clips" / "sample_video" / "000000.mp4"
        if workspace_video.exists():
            video_path = str(workspace_video)
        else:
            print("Error: Please provide a video path using --video option.")
            sys.exit(1)

    print(f"Initializing VideoCLIPExtractor on {device}...")
    extractor = VideoCLIPExtractor(pretrained_model=args.model, device=device)

    print(f"\nRunning extraction on: {video_path}")
    try:
        video_features = extractor.get_video_features(video_path)
        print(f"Successfully extracted video embedding. Shape: {video_features.shape}")
        
        # Test queries specific to the video content (The Queen's Corgi scene)
        queries = [
            "an animated queen sitting at her desk",
            "a gift box wrapped in a Union Jack flag on a desk",
            "a general in military uniform presenting a gift",
            "an old woman in a light green top smiling",
            "a green desk lamp",
            "a dog playing with a toy"  # negative query
        ]
        
        print("\nExtracting text features...")
        text_features = extractor.get_text_features(queries)
        print(f"Successfully extracted text embeddings. Shape: {text_features.shape}")
        
        similarities = extractor.calculate_similarity(video_features, text_features)
        
        print("\nSimilarity Scores:")
        print("-" * 50)
        for query, score in zip(queries, similarities):
            print(f"Query: '{query}' -> Cosine Similarity: {score:.4f}")
        print("-" * 50)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
