import itertools
from typing import List, Tuple
from PIL import Image
import torch
from sklearn.preprocessing import normalize
import numpy as np

from keyframe_search import KeyframeSearchEngine
from helpers import get_logger

logger = get_logger()


def search_by_temporal(queries: str, limit: int = 100, sequence_gap: int = 1) -> List[Tuple[str, List[str], List[float], float]]:
    """
    Search for a temporal sequence of events by finding the first event,
    and then looking for subsequent events in the following keyframes.
    Returns a list of (video_id, [keyframe_ids], [scores], average_similarity).
    """
    logger.info(f"Temporal search for: {queries}")
    search_engine = KeyframeSearchEngine()

    queries = queries.split('\n') if isinstance(queries, str) else queries

    # Encode all text queries first
    text_features = [
        search_engine.model.encode_text(search_engine.tokenizer(q)) for q in queries
    ]
    text_features = [
        normalize(feature.detach().cpu().numpy()).squeeze() for feature in text_features
    ]

    # Start search with the first query
    initial_results = search_engine.search_by_text(queries[0], limit=200)

    all_sequences = []

    for video_id, start_kf_id, score1 in initial_results:
        # This list will hold the sequence of keyframe IDs found for this video, starting with the result from the first query.
        # Each element will be a tuple: (keyframe_id, score)
        current_sequence = [(int(start_kf_id), score1)]

        try:
            embedding_list = np.load(f"./data-staging/clip-features/{video_id}.npy")
        except FileNotFoundError:
            # If the embedding file for this video doesn't exist, skip it.
            logger.warning(f"Embedding file not found for video: {video_id}")
            continue

        # Now, look for the rest of the queries in sequence
        for i, text_query in enumerate(queries[1:]):
            last_found_kf_id = current_sequence[-1][0]

            # Define a search window for the next keyframe
            start_window = last_found_kf_id + 1
            end_window = start_window + sequence_gap

            # Use the keyframe_search to find potential candidates for the next step
            # We search with a high limit to increase the chance of finding a match in the desired window
            candidate_results = search_engine.search_by_text(text_query, limit=500)

            best_match_in_window = None

            # Filter the candidates to find the best one within the same video and the correct time window
            for cand_video_id, cand_kf_id, cand_score in candidate_results:
                if cand_video_id == video_id:
                    kf_index = int(cand_kf_id)
                    if start_window <= kf_index < end_window:
                        # This is the best possible match in the window since results are sorted by score
                        best_match_in_window = (kf_index, cand_score)
                        break  # Found the best match

            if best_match_in_window:
                current_sequence.append(best_match_in_window)
            else:
                # If we can't find the next item in the sequence, this sequence is broken.
                current_sequence = []  # Clear the sequence
                break  # Stop searching for this initial result.

        if current_sequence and len(current_sequence) == len(queries):
            # We found a full sequence
            keyframe_ids = [str(item[0]) for item in current_sequence]
            scores = [item[1] for item in current_sequence]
            avg_score = sum(scores) / len(scores)
            all_sequences.append((video_id, keyframe_ids, scores, avg_score))
            if video_id == 'L01_V005':
                print(video_id, keyframe_ids, scores)
    # Sort sequences by average score
    all_sequences.sort(key=lambda x: x[3], reverse=True)
    
    logger.info(f"Found {len(all_sequences)} temporal sequences.")
    return all_sequences[:limit]


if __name__ == "__main__":
    # Test the search functionality
    test_query = "A pair of red sneakers shoes\nMultiple sneakers are being displayed on the shelves\nA tennis ball being placed in front of a white shoes"
    logger.info(f"Testing search with query: {test_query}")
    
    results = search_by_temporal(test_query, 10)

    logger.info(f"Found {len(results)} results:")
    for video, keyframes, scores, avg_score in results:
        logger.info(f"Video: {video}, Keyframes: {keyframes}, Scores: {scores}, Avg Score: {avg_score:.4f}")
        
        # Optionally display the image
        # file_path = f"./data-staging/keyframes/{video}/{keyframe}.jpg"
        # try:
        #     image = Image.open(file_path)
        #     print(f"Image path: {file_path}")
        # except FileNotFoundError:
        #     logger.warning(f"Image not found: {file_path}")
