import numpy as np
from sentence_transformers import SentenceTransformer
import os
import json
import torch

# Use CUDA if available
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

# Load a pre-trained model
model = SentenceTransformer('all-MiniLM-L6-v2', device=device)

def process_all_transcripts(transcript_dir, output_dir="data-index"):
    """
    Processes all transcript files in a directory, generates sentence embeddings,
    and saves them into consolidated files.

    Args:
        transcript_dir (str): The directory containing transcript .txt files.
        output_dir (str): The directory to save the consolidated embeddings and metadata.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    all_embeddings = []
    metadata = []  # List of dictionaries: {'video_id': str, 'sentence_index': int}

    print(f"Processing transcripts from: {transcript_dir}")
    transcript_files = [f for f in os.listdir(transcript_dir) if f.endswith(".txt")]

    if not transcript_files:
        print(f"No transcript files (.txt) found in '{transcript_dir}'.")
        return

    for filename in transcript_files:
        video_id = os.path.splitext(filename)[0]
        filepath = os.path.join(transcript_dir, filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            transcript = f.read()

        sentences = [s.strip() for s in transcript.split('\n') if s.strip()]
        if not sentences:
            continue

        print(f"  - Processing {video_id} ({len(sentences)} sentences)")
        sentence_embeddings = model.encode(sentences)
        all_embeddings.extend(sentence_embeddings)

        for i, sentence in enumerate(sentences):
            metadata.append({
                "video_id": video_id,
                "sentence_index": i,
            })

    embeddings_path = os.path.join(output_dir, "transcript_embeddings.npy")
    metadata_path = os.path.join(output_dir, "transcript_metadata.json")

    np.save(embeddings_path, np.array(all_embeddings))
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)

    print(f"\nSuccessfully processed {len(transcript_files)} transcripts.")
    print(f"Embeddings saved to: {embeddings_path}")
    print(f"Metadata saved to: {metadata_path}")

if __name__ == '__main__':
    # This script should be run to generate the embedding files.
    # Example: python transcript_embedding.py
    
    # Ensure the source directory exists before running
    transcript_directory = "./data-staging/transcripts"
    if not os.path.exists(transcript_directory):
        print(f"Error: Transcript directory not found at '{transcript_directory}'")
        print("Please create it and place your .txt transcript files inside.")
    else:
        process_all_transcripts(transcript_dir=transcript_directory)
