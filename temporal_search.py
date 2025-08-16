import itertools
from typing import List, Tuple
from PIL import Image
import torch
from sklearn.preprocessing import normalize
import numpy as np

from keyframe_search import KeyframeSearchEngine
from helpers import get_logger

logger = get_logger()


def search_by_temporal(queries: str, limit: int = 100, sequence_gap: int = 1) -> List[Tuple[str, List[str], float]]:
    """
    Search for a temporal sequence of events by finding the first event,
    and then looking for subsequent events in the following keyframes.
    Returns a list of (video_id, [keyframe_ids], average_similarity).
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
        for i, text_feature in enumerate(text_features[1:]):
            last_found_kf_id = current_sequence[-1][0]

            # Define a search window for the next keyframe
            start_window = last_found_kf_id + 1
            end_window = start_window + sequence_gap

            best_match_in_window = None  # (keyframe_id, score)

            # Iterate through the keyframes in the window
            for kf_to_check in range(start_window, end_window):
                
                # Find the embedding for this keyframe
                try:
                    if kf_to_check >= len(embedding_list):
                        # Avoid index out of bounds if the window extends beyond the number of keyframes
                        break
                    
                    image_feature = embedding_list[kf_to_check]

                    # Calculate similarity
                    similarity = np.dot(text_feature, image_feature)

                    if (
                        best_match_in_window is None
                        or similarity > best_match_in_window[1]
                    ):
                        best_match_in_window = (kf_to_check, similarity)

                except Exception as e:
                    # Could be an out of bounds error or other issue.
                    # logger.debug(f"Could not check keyframe {kf_to_check_id} for video {video_id}: {e}")
                    pass

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
            all_sequences.append((video_id, keyframe_ids, avg_score))

    # Sort sequences by average score
    all_sequences.sort(key=lambda x: x[2], reverse=True)
    
    logger.info(f"Found {len(all_sequences)} temporal sequences.")
    return all_sequences[:limit]


if __name__ == "__main__":
    # Test the search functionality
    test_query = "A person in a red and white suit underwater. He is wearing a snorkel or diving mask and appears to be swimming in a body of water. The water is a bright, clear blue, and there are some small, yellow fish visible in the background.\nA crowd of people gathered inside a curved, glass-walled underwater tunnel. People are looking out at the marine life, and some are taking photos."
    logger.info(f"Testing search with query: {test_query}")
    
    results = search_by_temporal(test_query, 50)

    logger.info(f"Found {len(results)} results:")
    for video, keyframe, score in results:
        logger.info(f"Video: {video}, Keyframe: {keyframe}, Score: {score:.4f}")
        
        # Optionally display the image
        # file_path = f"./data-staging/keyframes/{video}/{keyframe}.jpg"
        # try:
        #     image = Image.open(file_path)
        #     print(f"Image path: {file_path}")
        # except FileNotFoundError:
        #     logger.warning(f"Image not found: {file_path}")
