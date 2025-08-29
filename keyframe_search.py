import csv
from typing import Tuple, List
import faiss
import numpy as np
import open_clip
import torch
from sklearn.preprocessing import normalize
from PIL import Image

from helpers import get_logger
from load_all_video_keyframes_info import load_all_video_keyframes_info

all_video, video_keyframe_dict = load_all_video_keyframes_info()
logger = get_logger()


class KeyframeSearchEngine:
    def __init__(self):
        """Initialize the keyframe search engine with CLIP model and FAISS index."""
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")
        
        # Load CLIP model
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-SO400M-14-SigLIP-384",
            pretrained="webli",
            device=self.device,
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer("ViT-SO400M-14-SigLIP-384")
        
        # Load the keyframe embedding from the FAISS index
        cpu_index = faiss.read_index("./data-index/keyframe_embedding.index")
        self.embedding_info = np.load("./data-index/keyframe_metadata.npy")
        
        # Try to move FAISS index to GPU if available
        if faiss.get_num_gpus() > 0:
            res = faiss.StandardGpuResources()
            self.keyframe_index = faiss.index_cpu_to_gpu(res, 0, cpu_index)
            logger.info("FAISS index moved to GPU.")
        else:
            self.keyframe_index = cpu_index
            logger.info("FAISS index running on CPU.")

        logger.info(f"Loaded {self.keyframe_index.ntotal} keyframes")

    def search_by_text(self, query: str, limit: int = 100) -> List[Tuple[str, str, float]]:
        """
        Search keyframes using text query.
        
        Args:
            query: Text query to search for
            limit: Maximum number of results to return
            
        Returns:
            List of tuples (video_id, keyframe_id, similarity_score)
        """
        logger.debug(f"Searching for: {query}")
        
        # Encode the text query
        tokenized = self.tokenizer(query)
        if hasattr(tokenized, 'to'):
            tokenized = tokenized.to(self.device)
        query_feature = self.model.encode_text(tokenized)
        query_embedding = query_feature.detach().cpu().numpy().reshape(1, -1).astype("float32")
        query_embedding = normalize(query_embedding, axis=1)
        
        # Search in FAISS index
        distances, indices = self.keyframe_index.search(query_embedding, min(limit, self.keyframe_index.ntotal))
        
        # Convert distances to similarity scores (higher is better)
        similarity_scores = 1 / (distances + 1e-8)
        
        # Prepare results
        results = []
        for idx, score in zip(indices[0], similarity_scores[0]):
            video_id = self.embedding_info[idx][0]
            keyframe_id = self.embedding_info[idx][1]
            results.append((video_id, keyframe_id, float(score)))
        
        return results

    def search_by_image(self, image_path: str, limit: int = 100) -> List[Tuple[str, str, float]]:
        """
        Search keyframes using an image query.
        
        Args:
            image_path: Path to the query image
            limit: Maximum number of results to return
            
        Returns:
            List of tuples (video_id, keyframe_id, similarity_score)
        """
        logger.debug(f"Searching by image: {image_path}")
        
        # Load and preprocess the image
        image = Image.open(image_path).convert("RGB")
        image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)
        
        # Encode the image
        with torch.no_grad():
            image_feature = self.model.encode_image(image_tensor)
            image_feature /= image_feature.norm(dim=-1, keepdim=True)
        
        query_embedding = image_feature.detach().cpu().numpy().astype("float32")
        query_embedding = normalize(query_embedding, axis=1)
        
        # Search in FAISS index
        distances, indices = self.keyframe_index.search(query_embedding, min(limit, self.keyframe_index.ntotal))
        
        # Convert distances to similarity scores
        similarity_scores = 1 / (distances + 1e-8)
        
        # Prepare results
        results = []
        for idx, score in zip(indices[0], similarity_scores[0]):
            video_id = self.embedding_info[idx][0]
            keyframe_id = self.embedding_info[idx][1]
            results.append((video_id, keyframe_id, float(score)))
        
        return results


# Initialize global search engine instance
search_engine = KeyframeSearchEngine()


def get_search_engine():
    """Get or create the global search engine instance."""
    return search_engine


def keyframe_search(query: str, limit: int = 100) -> List[Tuple[str, str, float]]:
    """
    Search keyframes using text query (backward compatibility function).
    
    Args:
        query: Text query to search for
        limit: Maximum number of results to return
        
    Returns:
        List of tuples (video_id, keyframe_id, similarity_score)
    """
    engine = get_search_engine()
    return engine.search_by_text(query, limit)


def image_search(image_path: str, limit: int = 100) -> List[Tuple[str, str, float]]:
    """
    Search keyframes using image query.
    
    Args:
        image_path: Path to the query image
        limit: Maximum number of results to return
        
    Returns:
        List of tuples (video_id, keyframe_id, similarity_score)
    """
    engine = get_search_engine()
    return engine.search_by_image(image_path, limit)


if __name__ == "__main__":
    # Test the search functionality
    test_query = "person walking"
    logger.info(f"Testing search with query: {test_query}")
    
    results = keyframe_search(test_query, 10)
    
    logger.info(f"Found {len(results)} results:")
    for video, keyframe, score in results:
        logger.info(f"Video: {video}, Keyframe: {keyframe}, Score: {score:.4f}")
        
        # Optionally display the image
        file_path = f"./data-staging/keyframes/{video}/{keyframe}.jpg"
        try:
            image = Image.open(file_path)
            print(f"Image path: {file_path}")
        except FileNotFoundError:
            logger.warning(f"Image not found: {file_path}")
