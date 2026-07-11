import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import os
import json
import glob

class CaptionSearchEngine:
    """
    A search engine for finding relevant keyframes based on image captions.
    """
    def __init__(self, input_dir="data-index"):
        """
        Initializes the search engine by loading the model and data.
        
        Args:
            input_dir (str): Directory containing embedding and metadata files.
        """
        print("Initializing CaptionSearchEngine...")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.embeddings, self.metadata = self._load_all_data(input_dir)
        self._load_caption_data()
        if self.embeddings is not None:
            print("CaptionSearchEngine initialized successfully.")

    def _load_all_data(self, input_dir):
        """
        Loads the consolidated caption embeddings and their metadata.

        Args:
            input_dir (str): The directory where the consolidated files are stored.

        Returns:
            tuple: A tuple containing the embeddings array and the metadata list.
                   Returns (None, None) if files are not found.
        """
        embeddings_path = os.path.join(input_dir, "caption_embedding.npy")
        metadata_path = os.path.join(input_dir, "caption_metadata.json")

        if not os.path.exists(embeddings_path) or not os.path.exists(metadata_path):
            print("Error: Caption embeddings or metadata file not found.")
            print("Please run `caption_embedding.py` first to generate the necessary files.")
            return None, None

        print("Loading caption embedding data...")
        all_embeddings = np.load(embeddings_path)
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        print("Caption data loaded successfully.")
        return all_embeddings, metadata

    def _load_caption_data(self, caption_dir="data-staging"):
        """Loads all caption text from the source JSON files into memory."""
        self.captions_data = {}
        caption_files = glob.glob(os.path.join(caption_dir, "vintern_results_*.json"))
        for file_path in caption_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    video_id = item.get("video_id")
                    keyframe_id = item.get("keyframe_id")
                    caption = item.get("image-captioning")
                    if video_id and keyframe_id and caption:
                        if video_id not in self.captions_data:
                            self.captions_data[video_id] = {}
                        self.captions_data[video_id][keyframe_id] = caption

    def search(self, query, top_k=100):
        """
        Searches for the most relevant keyframes based on caption similarity.

        Args:
            query (str): The search query.
            top_k (int): The number of top results to return.

        Returns:
            list: A list of dictionaries, each containing result info.
        """
        if self.embeddings is None or self.metadata is None:
            print("Embeddings not loaded. Cannot perform search.")
            return []

        query_embedding = self.model.encode([query])
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]

        num_results = min(top_k, len(similarities))
        top_k_indices = np.argsort(similarities)[-num_results:][::-1]

        results = []
        for idx in top_k_indices:
            result = self.metadata[idx].copy()
            result['similarity_score'] = float(similarities[idx])
            
            video_id = result.get('video_id')
            keyframe_id = result.get('keyframe_id')

            if video_id and keyframe_id:
                result['caption'] = self.captions_data.get(video_id, {}).get(keyframe_id, "Caption not found.")
                result['keyframe_filename'] = f"data-staging/keyframes/{video_id}/{keyframe_id}.jpg"
            
            results.append(result)
        
        return results

# --- Singleton instance management ---
search_engine_instance = CaptionSearchEngine()

def get_search_engine():
    """
    Returns the singleton instance of the CaptionSearchEngine.
    """
    return search_engine_instance

def caption_search(query, top_k=100):
    """
    A wrapper function to perform a search using the singleton engine instance.
    """
    return search_engine_instance.search(query, top_k=top_k)


if __name__ == '__main__':
    # Example Query
    sample_query = "A city skyline at dusk"
    top_results = caption_search(sample_query, top_k=5)
    
    print(f"\nQuery: '{sample_query}'")
    if top_results:
        print(f"Top {len(top_results)} results:")
        print(json.dumps(top_results, indent=4, ensure_ascii=False))
    else:
        print("No results found or engine not initialized.")
