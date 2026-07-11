import os
from tqdm import tqdm
import h5py
import numpy as np
from PIL import Image, UnidentifiedImageError
from typing import List, Tuple, Set, Dict
from pathlib import Path
import torch
import faiss
from glob import glob
from transformers import AutoImageProcessor, AutoModel

device = 'cuda' if torch.cuda.is_available() else 'cpu'
model_name = "facebook/dinov3-vitl16-pretrain-lvd1689m"
# Use HF Token for DinoV3 model
processor = AutoImageProcessor.from_pretrained(model_name)
model = AutoModel.from_pretrained(model_name).to(device).eval()

def extract(image_path: Path) -> np.ndarray:
    """Computes the embedding for a single image."""
    try:
        image = Image.open(image_path).convert("RGB")
    except (UnidentifiedImageError, FileNotFoundError):
        print(f"Warning: Could not open or identify image file: {image_path}")
        return None

    with torch.no_grad():
        inputs = processor(images=image, return_tensors="pt").to(device)
        outputs = model(**inputs)
        # DINOv3 embeddings are in last_hidden_state. Average pooling is a common way to get a single vector.
        embedding = outputs.last_hidden_state.mean(dim=1).squeeze().cpu().numpy()
        # Normalize the embedding for cosine similarity
        embedding = embedding / np.linalg.norm(embedding)
    return embedding

def build_index(image_folder, index_path, metadata_path, batch_size=256):
    """
    Scans a directory for images, extracts embeddings, and builds a FAISS index
    in a memory-efficient way by processing images in batches.
    """
    print(f"Scanning for images in {image_folder}...")
    image_paths = list(Path(image_folder).rglob('*.jpg'))
    if not image_paths:
        print(f"No JPG images found in {image_folder}")
        return

    print(f"Found {len(image_paths)} images to process...")

    index = None
    all_metadata = []
    batch_embeddings = []

    for img_path in tqdm(image_paths, desc="Extracting embeddings"):
        embedding = extract(img_path)
        if embedding is None:
            continue  # Skip images that couldn't be processed

        if index is None:
            # Initialize the index with the dimension of the first feature
            embedding_dim = embedding.shape[0]
            print(f"Embedding dimension: {embedding_dim}")
            # For normalized embeddings, IndexFlatIP (Inner Product) is better
            index = faiss.IndexFlatIP(embedding_dim)

        batch_embeddings.append(embedding)
        all_metadata.append(str(img_path))

        # If batch is full, add to index and clear the batch list
        if len(batch_embeddings) >= batch_size:
            embedding_array = np.vstack(batch_embeddings).astype('float32')
            index.add(embedding_array)
            batch_embeddings.clear()

    # Add any remaining embeddings from the last, partially-filled batch
    if batch_embeddings:
        embedding_array = np.vstack(batch_embeddings).astype('float32')
        index.add(embedding_array)

    if index is None or index.ntotal == 0:
        print("No features were extracted. Index not built.")
        return

    print(f"FAISS index built successfully with {index.ntotal} vectors.")
    
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(index_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Save the index and metadata
    metadata_array = np.array(all_metadata, dtype='object')
    faiss.write_index(index, index_path)
    np.save(metadata_path, metadata_array)
    
    print(f"FAISS index saved to: {index_path}")
    print(f"Metadata saved to: {metadata_path}")

if __name__ == "__main__":

    IMAGE_DIR = "data-staging/keyframes"
    INDEX_FILE = "data-index/dinov3.index"
    METADATA_FILE = "data-index/dinov3_metadata.npy"
    
    build_index(IMAGE_DIR, INDEX_FILE, METADATA_FILE)