import numpy as np
import os
import json
import pandas as pd

class TranscriptSearchEngine:
    """
    A search engine for finding relevant sentences in video transcripts.
    """
    def __init__(self, input_dir="data-index"):
        """
        Initializes the search engine by loading the model and data.
        
        Args:
            input_dir (str): Directory containing embedding and metadata files.
        """
        print("Initializing TranscriptSearchEngine...")
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.embeddings, self.metadata = self._load_all_data(input_dir)
        if self.embeddings is not None:
            print("TranscriptSearchEngine initialized successfully.")

    def _find_keyframes_for_sentence(self, video_id: str, sentence_index: int):
        """
        Finds keyframes within the time interval of a specific sentence in a video.
        Args:
            video_id (str): The ID of the video.
            sentence_index (int): The index of the sentence.
        Returns:
            list: A list of dictionaries, each containing keyframe info.
        """
        try:
            # 1. Read audio chunk timestamps
            timestamps_path = f'data-staging/audio-chunk-timestamps/{video_id}.csv'
            if not os.path.exists(timestamps_path):
                # print(f"Warning: Timestamps file not found at {timestamps_path}")
                return []
            timestamps_df = pd.read_csv(timestamps_path)
            
            if sentence_index >= len(timestamps_df):
                # print(f"Warning: sentence_index {sentence_index} is out of bounds for {video_id}.csv")
                return []

            time_interval = timestamps_df.iloc[sentence_index]
            start_time = time_interval['start_time']
            end_time = time_interval['end_time']

            # 2. Read keyframe mapping
            keyframes_map_path = f'data-staging/map-keyframes/{video_id}.csv'
            if not os.path.exists(keyframes_map_path):
                # print(f"Warning: Keyframes map file not found at {keyframes_map_path}")
                return []
            keyframes_map_df = pd.read_csv(keyframes_map_path)

            # 3. Find keyframes within the time interval
            relevant_keyframes_df = keyframes_map_df[
                (keyframes_map_df['pts_time'] >= start_time) & 
                (keyframes_map_df['pts_time'] <= end_time)
            ]

            relevant_keyframes = []
            if not relevant_keyframes_df.empty:
                for _, row in relevant_keyframes_df.iterrows():
                    keyframe_info = {
                        "keyframe_filename": f"data-staging/keyframes/{video_id}/{int(row['n']):04}.jpg",
                        "timestamp": f"{row['pts_time']:.3f}s"
                    }
                    relevant_keyframes.append(keyframe_info)
            
            return relevant_keyframes

        except Exception as e:
            print(f"An unexpected error occurred while finding keyframes for {video_id}, sentence {sentence_index}: {e}")
            return []

    def _load_all_data(self, input_dir):
        """
        Loads the consolidated sentence embeddings and their metadata.

        Args:
            input_dir (str): The directory where the consolidated files are stored.

        Returns:
            tuple: A tuple containing the embeddings array and the metadata list.
                   Returns (None, None) if files are not found.
        """
        embeddings_path = os.path.join(input_dir, "transcript_embeddings.npy")
        metadata_path = os.path.join(input_dir, "transcript_metadata.json")

        if not os.path.exists(embeddings_path) or not os.path.exists(metadata_path):
            print("Error: Embeddings or metadata file not found.")
            print("Please run `transcript_embedding.py` first to generate the necessary files.")
            return None, None

        print("Loading transcript embedding data...")
        all_embeddings = np.load(embeddings_path)
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        print("Transcript data loaded successfully.")
        return all_embeddings, metadata

    def search(self, query, top_k=100):
        """
        Searches for the most relevant sentences across all loaded transcripts.

        Args:
            query (str): The search query.
            top_k (int): The number of top results to return.

        Returns:
            list: A list of dictionaries, each containing the video_id, sentence_index, 
                  sentence, and similarity_score.
                  Returns an empty list if embeddings are not loaded.
        """
        if self.embeddings is None or self.metadata is None:
            print("Embeddings not loaded. Cannot perform search.")
            return []

        # Generate embedding for the query
        from sklearn.metrics.pairwise import cosine_similarity

        query_embedding = self.model.encode([query])

        # Compute cosine similarity and flatten to a 1D array
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]

        # Find the indices of the top_k most similar sentences
        # `np.argsort` sorts in ascending order, so we take the last `top_k` elements and reverse them
        num_results = min(top_k, len(similarities))
        top_k_indices = np.argsort(similarities)[-num_results:][::-1]

        # Retrieve the corresponding metadata for each of the top results
        results = []
        for idx in top_k_indices:
            # Use .copy() to avoid modifying the original metadata list with the similarity score
            result = self.metadata[idx].copy()
            result['similarity_score'] = float(similarities[idx]) # Convert numpy float to python float for JSON
            
            video_id = result['video_id']
            sentence_index = result['sentence_index']

            # Find and add corresponding keyframes
            result['keyframes'] = self._find_keyframes_for_sentence(
                video_id, sentence_index
            )

            # Add the sentence text
            try:
                transcript_path = f'data-staging/transcripts/{video_id}.txt'
                if os.path.exists(transcript_path):
                    with open(transcript_path, 'r', encoding='utf-8') as f:
                        # Read the lines from the file
                        transcript_data = f.readlines()
                    
                    # Strip whitespace and filter out empty lines
                    sentences = [line.strip() for line in transcript_data if line.strip()]

                    if sentence_index < len(sentences):
                        result['sentence'] = sentences[sentence_index]
                    else:
                        result['sentence'] = "Sentence not found (index out of range)."
                else:
                    result['sentence'] = "Transcript file not found."
            except Exception as e:
                result['sentence'] = f"Error loading sentence: {e}"
            
            results.append(result)
        
        return results

# --- Singleton instance management ---
search_engine_instance = None

def get_search_engine():
    """
    Returns the singleton instance of the TranscriptSearchEngine.
    """
    global search_engine_instance
    if search_engine_instance is None:
        search_engine_instance = TranscriptSearchEngine()
    return search_engine_instance

def transcript_search(query, top_k=100):
    """
    A wrapper function to perform a search using the singleton engine instance.
    
    Args:
        query (str): The search query.
        top_k (int): The number of top results to return.

    Returns:
        list: A list of top search results.
    """
    # The engine is now initialized when the module is imported.
    return get_search_engine().search(query, top_k=top_k)


if __name__ == '__main__':
    # The engine is initialized automatically on module load.
    
    # Example Query 1
    sample_query_1 = "Football match"
    top_results_1 = transcript_search(sample_query_1, top_k=10)
    
    print(f"\nQuery: '{sample_query_1}'")
    if top_results_1:
        print(f"Top {len(top_results_1)} results:")
        print(json.dumps(top_results_1, indent=4, ensure_ascii=False))
    else:
        print("No results found.")
