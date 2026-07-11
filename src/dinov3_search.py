import os
from tqdm import tqdm
import numpy as np
from PIL import Image, UnidentifiedImageError
from typing import List, Tuple, Set, Dict
from pathlib import Path
import torch

class DinoV3SearchEngine:
    def __init__(self, index_path: str, metadata_path: str):
        """
        Initializes the search engine by loading the FAISS index and metadata.
        """
        import faiss
        from transformers import AutoImageProcessor, AutoModel

        self.index = faiss.read_index(index_path)
        self.metadata = np.load(metadata_path, allow_pickle=True)

        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model_name = "facebook/dinov3-vitl16-pretrain-lvd1689m"

        # Use HF Token for DinoV3 model
        self.processor = AutoImageProcessor.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name).to(self.device).eval()
        print("Dinov3 search engine ready.")

    def extract(self, image_path: Path) -> np.ndarray:
        """Computes the embedding for a single image."""
        try:
            image = Image.open(image_path).convert("RGB")
        except (UnidentifiedImageError, FileNotFoundError):
            print(f"Warning: Could not open or identify image file: {image_path}")
            return None

        with torch.no_grad():
            inputs = self.processor(images=image, return_tensors="pt").to(self.device)
            outputs = self.model(**inputs)
            # DINOv3 embeddings are in last_hidden_state. Average pooling is a common way to get a single vector.
            embedding = outputs.last_hidden_state.mean(dim=1).squeeze().cpu().numpy()
            # Normalize the embedding for cosine similarity
            embedding = embedding / np.linalg.norm(embedding)
        return embedding

    def search(self, query_image_path: Path, k: int = 5) -> List[Tuple[str, float]]:
        """
        Finds the top k most similar images to the query image.

        Args:
            query_image_path: Path to the query image.
            k: Number of similar images to retrieve.

        Returns:
            A list of tuples, where each tuple contains (image_path, similarity_score).
        """
        query_embedding = self.extract(query_image_path)
        if query_embedding is None:
            print(f"Could not generate embedding for {query_image_path}")
            return []

        # FAISS expects a 2D array of shape (n_queries, dim)
        query_embedding = query_embedding.reshape(1, -1).astype('float32')

        # Search the index
        distances, indices = self.index.search(query_embedding, k)

        results = []
        for i in range(k):
            idx = indices[0][i]
            dist = distances[0][i]
            # Metadata might be stored as bytes, decode if necessary
            meta_item = self.metadata[idx]
            if isinstance(meta_item, bytes):
                meta_item = meta_item.decode('utf-8')
            p = Path(meta_item.strip())
            video_id = p.parent.name
            keyframe_id = p.stem
            results.append((video_id, keyframe_id, dist))
            
        return results
    

# Initialize global search engine instance
search_engine = None
def get_search_engine() -> DinoV3SearchEngine:
    global search_engine
    if search_engine is None:
        INDEX_FILE = "data-index/dinov3.index"
        METADATA_FILE = "data-index/dinov3_metadata.npy"
        search_engine = DinoV3SearchEngine(INDEX_FILE, METADATA_FILE)
    return search_engine

def recommend(video_id, keyframe_id, limit=100):
    """
    Recommend similar keyframes based on a given video_id and keyframe_id.
    
    Args:
        video_id: ID of the video.
        keyframe_id: ID of the keyframe.
        limit: Number of recommendations to return.

    Returns:
        A list of recommended keyframes.
    """
    search_engine = get_search_engine()
    if not search_engine:
        print("Search engine is not initialized.")
        return []

    # Get the keyframe path
    path = f"data-staging/keyframes/{video_id}/{keyframe_id}.jpg"
    keyframe_path = Path(path)
    if not keyframe_path.exists():
        print(f"Keyframe not found: {keyframe_path}")
        return []

    # Search for similar keyframes
    similar_keyframes = search_engine.search(keyframe_path, k=limit)
    return similar_keyframes

if __name__ == "__main__":

    IMAGE_DIR = "data-staging/keyframes"
    INDEX_FILE = "data-index/dinov3.index"
    METADATA_FILE = "data-index/dinov3_metadata.npy"

    if os.path.exists(INDEX_FILE):
        search_engine = DinoV3SearchEngine(INDEX_FILE, METADATA_FILE)

        # Use an image from your dataset as a query
        # query_image = Path("image.png")
        query_image = Path("data-staging/keyframes/K19_V007/0257.jpg")
        top_k = 10
        
        print(f"\nSearching for top {top_k} images similar to {query_image}...")
        search_results = search_engine.search(query_image, k=top_k)
        
        if search_results:
            print("Search Results (video_id, keyframe_id, similarity_score):")
            for vid, kf, score in search_results:
                print(f"- {vid},{kf} (Score: {score:.4f})")
    else:
        print(f"Index file not found at {INDEX_FILE}")
