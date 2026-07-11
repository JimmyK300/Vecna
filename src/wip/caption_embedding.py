import numpy as np
from sentence_transformers import SentenceTransformer
import os
import json
import torch
import glob

# Use CUDA if available
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

# Load a pre-trained model
model = SentenceTransformer('all-MiniLM-L6-v2', device=device)

def process_all_captions(caption_dir, output_dir="data-index"):
    """
    Processes all caption JSON files in a directory, generates sentence embeddings,
    and saves them into consolidated files.

    Args:
        caption_dir (str): The directory containing caption .json files.
        output_dir (str): The directory to save the consolidated embeddings and metadata.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    all_embeddings = []
    metadata = []  # List of dictionaries: {'video_id': str, 'keyframe_id': str}
    captions_to_embed = []

    print(f"Processing captions from: {caption_dir}")
    caption_files = glob.glob(os.path.join(caption_dir, "vintern_results_*.json"))

    if not caption_files:
        print(f"No caption files (vintern_results_*.json) found in '{caption_dir}'.")
        return

    for filepath in caption_files:
        print(f"  - Loading {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for item in data:
            if 'image-captioning' in item and item['image-captioning']:
                captions_to_embed.append(item['image-captioning'])
                metadata.append({
                    "video_id": item.get("video_id"),
                    "keyframe_id": item.get("keyframe_id"),
                })

    if not captions_to_embed:
        print("No captions found to process.")
        return

    print(f"Embedding {len(captions_to_embed)} captions...")
    all_embeddings = model.encode(captions_to_embed, show_progress_bar=True)

    embeddings_path = os.path.join(output_dir, "caption_embedding.npy")
    metadata_path = os.path.join(output_dir, "caption_metadata.json")

    np.save(embeddings_path, np.array(all_embeddings))
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)

    print(f"\nSuccessfully processed {len(caption_files)} caption files.")
    print(f"Embeddings saved to: {embeddings_path}")
    print(f"Metadata saved to: {metadata_path}")

if __name__ == '__main__':
    # This script should be run to generate the embedding files.
    # Example: python caption_embedding.py
    
    # Ensure the source directory exists before running
    caption_directory = "./data-staging"
    if not os.path.exists(caption_directory):
        print(f"Error: Caption directory not found at '{caption_directory}'")
        print("Please create it and place your vintern_results_*.json files inside.")
    else:
        process_all_captions(caption_dir=caption_directory)
