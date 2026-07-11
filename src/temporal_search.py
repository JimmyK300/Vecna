import itertools
from typing import List, Tuple
import torch

from src.keyframe_search import keyframe_search
from src.helpers import get_logger

logger = get_logger()


def search_by_temporal(queries: str, limit: int = 100, sequence_gap: int = 30, excluded_video: List[str] = None) -> List[Tuple[str, List[str], List[float], float]]:
    """
    Search for a temporal sequence of events by finding the first event,
    and then looking for subsequent events in the following keyframes.
    Returns a list of (video_id, [keyframe_ids], [scores], average_similarity).
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Temporal search for: {queries}")

    queries = queries.split('\n') if isinstance(queries, str) else queries

    # Get search results for each query part.
    results_by_query = [keyframe_search(q, limit=1000) for q in queries]

    # Organize results by video ID for easier lookup.
    video_results = {}
    for i, results in enumerate(results_by_query):
        for video_id, kf_id, score in results:
            if video_id not in video_results:
                video_results[video_id] = [[] for _ in range(len(queries))]
            video_results[video_id][i].append((int(kf_id), score))

    all_sequences = []
    if excluded_video is None:
        excluded_video = []
    for video_id, query_results in video_results.items():
        if video_id in excluded_video:
            continue
        # Sort keyframes by ID for each query part to ensure chronological order.
        for qr in query_results:
            qr.sort()

        # Find all valid sequences in this video.
        sequences = find_sequences_in_video(query_results, sequence_gap)
        for seq in sequences:
            keyframe_ids = [str(item[0]) for item in seq]
            scores = [item[1] for item in seq]
            avg_score = sum(scores) / len(scores)
            all_sequences.append((video_id, keyframe_ids, scores, avg_score))

    # Sort all found sequences by their average score.
    all_sequences.sort(key=lambda x: x[3], reverse=True)

    logger.info(f"Found {len(all_sequences)} temporal sequences.")
    return all_sequences[:limit]


def find_sequences_in_video(query_results, gap):
    if not query_results or not query_results[0]:
        return []

    # Start with sequences of length 1 from the first query's results.
    sequences = [[item] for item in query_results[0]]

    # Iteratively build longer sequences.
    for i in range(1, len(query_results)):
        new_sequences = []
        for seq in sequences:
            last_kf_id, _ = seq[-1]
            # Find all valid next keyframes in the sequence from the next query's results.
            for kf_id, score in query_results[i]:
                if last_kf_id < kf_id <= last_kf_id + gap:
                    new_seq = seq + [(kf_id, score)]
                    new_sequences.append(new_seq)
        sequences = new_sequences

    return sequences


if __name__ == "__main__":
    # Test the search functionality
    # test_query = "A pair of red sneakers shoes\nMultiple sneakers are being displ[ayed on the shelves\nA tennis ball being placed in front of a white shoes"
    test_query = "A flycam shot of a bridge in Ho Chi Minh City\na shot of Bitexco Tower\nHoan Kiem Lake in Hanoi"
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
