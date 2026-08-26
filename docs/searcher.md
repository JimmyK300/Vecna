# `packages/search/searcher.py`

## Purpose

Provides the core search engine (`Searcher`) for multi-modal video retrieval. It executes text-to-image similarity searches (via CLIP embeddings), keyword text matching (via OCR and ASR), image-to-image similarity search (via Milvus vector search), include/exclude video filtering, and multi-step temporal sequence search across video keyframes.

## Usage

```python
from aic51.packages.search.searcher import Searcher
import torch

# Initialize searcher with Milvus collection name and execution device
searcher = Searcher(collection_name="milvus", device=torch.device("cuda"))

# 1. Multimodal / Text query search with include & exclude video filtering
results = searcher.search_multimodal(
    q="a dog running on grass ocr:PET SHOP [!video: L18_V005]",
    offset=0,
    limit=50,
    target_features=["image_clip_pe-l-14-336"],
    ocr_weight=0.3,
    asr_weight=0.1,
    temporal_k=2000,
    max_interval=1000,
    auto_translate=True,
    include_videos="L18_V001, L18_V002",
    exclude_videos="L18_V005",
)

# 2. Image-to-image similarity search
image_results = searcher.search_image(
    id="L18_V001#000123",
    offset=0,
    limit=50,
    target_features=["image_clip_pe-l-14-336"],
)
```

## Query Syntax

Queries passed to `search_multimodal` are parsed by the `Query` helper class into three main query modes:

| Query Type | Syntax Example | Description |
|---|---|---|
| **Simple Video Lookup** | `video:L18_V001,L18_V002` or `[video:L18_V001]` | Retrieves all keyframes associated with the specified target video ID(s). |
| **Exclude Video Filter** | `!video:L18_V005` or `[exclude_video:L18_V005]` | Excludes all keyframes from specified video ID(s) from search results. |
| **Single-Step Search** | `a blue car ocr:POLICE asr:siren` | Searches keyframes matching CLIP visual description, embedded OCR text, and/or ASR spoken text. |
| **Temporal Sequence Search** | `a person walking / a red car driving / a building` | Multi-step sequential search separated by `/`, `\`, or `;`. Finds keyframe sequences occurring in chronological order within `max_interval` frames. |

> **Inline Tag Syntax Details:**
> - `ocr:text` or `[ocr:text]`: Extracts explicit OCR search target string.
> - `asr:text` or `[asr:text]`: Extracts explicit ASR search target string.
> - `video:id1,id2` or `[video:id1,id2]`: Filters search results to include only specified video IDs.
> - `!video:id1,id2` or `[exclude_video:id1,id2]` or `[!video:id1,id2]`: Filters search results to exclude specified video IDs.
> - **Temporal Separators:** Steps can be separated using `;`, `/`, or `\`.

## Search Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | `str` | *(required)* | Query string (supports plain text, `ocr:`, `asr:`, `video:`, `!video:`, and `/` or `;` temporal splits) |
| `offset` | `int` | `0` | Result pagination offset |
| `limit` | `int` | `50` | Maximum number of search results to return |
| `target_features` | `list[str]` | `[]` | List of target feature field names in Milvus database (e.g. `["image_clip_pe-l-14-336"]`) |
| `nprobe` | `int` | `8` | Milvus index search probe parameter for vector search accuracy/speed tradeoff |
| `temporal_k` | `int` | `200` | Top candidates to retrieve per temporal segment before sequential matching |
| `ocr_weight` | `float` | `0.0` | Weight for OCR text matching score (range `[0.0, 1.0]`) |
| `asr_weight` | `float` | `0.0` | Weight for ASR spoken text matching score (range `[0.0, 1.0 - ocr_weight]`) |
| `max_interval` | `int` | `1000` | Maximum allowed frame gap between consecutive steps in a temporal sequence |
| `selected` | `str \| None` | `None` | Optional target `frame_id` to automatically set page offset to include the selected item |
| `auto_translate` | `bool` | `False` | Automatically translates query text (e.g. EN $\rightarrow$ VI for OCR/ASR matching) |
| `en_to_vi_translate` | `bool` | `False` | Forces EN $\rightarrow$ VI translation for OCR/ASR text matching |
| `include_videos` | `str` | `""` | Optional comma/space separated list of video IDs to restrict search to |
| `exclude_videos` | `str` | `""` | Optional comma/space separated list of video IDs to exclude from search |

## Response Structure

`search_multimodal` and `search_image` return a dictionary containing search results and metadata:

```json
{
  "results": [
    {
      "entity": {
        "frame_id": "L18_V001#000123",
        "video_id": "L18_V001",
        "frame_idx": 123
      },
      "distance": 1.8739,
      "scores": {
        "final": 1.8739,
        "clip": 1.8739,
        "ocr": 0.0,
        "asr": 0.0,
        "clip_raw": 0.624,
        "ocr_raw": 0.0,
        "asr_raw": 0.0
      },
      "time_line": ["000123", "000185"],
      "time_line_scores": [
        { "final": 0.9800, "clip": 0.9800, "ocr": 0.0, "asr": 0.0 },
        { "final": 0.8939, "clip": 0.8939, "ocr": 0.0, "asr": 0.0 }
      ]
    }
  ],
  "total": 1250,
  "offset": 0
}
```

| Field | Description |
|---|---|
| `results` | List of matching entities ordered by score descending |
| `results[].entity` | Milvus entity payload (e.g., `frame_id`, video metadata) |
| `results[].distance` | Combined search score across all temporal steps (higher is better) |
| `results[].scores` | Overall accumulated score breakdown (`final`, `clip`, `ocr`, `asr`) |
| `results[].time_line` | Keyframe IDs forming the temporal sequence |
| `results[].time_line_scores` | List of individual score breakdowns for each keyframe in `time_line` |
| `total` | Total matching results or database size |
| `offset` | Pagination start offset |

## Class: `Searcher` & `Query`

Stateful search engine class managing feature extractors, query parsing, video filtering, and Milvus database interactions.

### Call Graph

```
search_multimodal
├── Query(q, include_videos, exclude_videos) (Parses query text, inline tags, & video filters)
├── _get_videos                              (Mode 1: Direct frame retrieval filtered by include/exclude)
├── _advance_search                          (Mode 2: Single-step multimodal search)
│   ├── Dynamic replenishment loop           (Automatically scales candidate_limit when exclude_video is set)
│   └── _similarity_search
│       ├── CLIP text search                 (Cosine similarity via Milvus, weight = 1 - ocr_w - asr_w)
│       ├── OCR text search                  (BM25 full-text search via Milvus, weight = ocr_w)
│       ├── ASR text search                  (BM25 full-text search via Milvus, weight = asr_w)
│       └── _normalize_scores                (Min-max normalizes component scores to [0, 1])
└── _temporal_search                         (Mode 3: Multi-step sequential search)
    ├── _similarity_search                   (Executes similarity search per query segment)
    ├── _combine_temporal_results            (DP sliding window alignment & per-frame score tracking)
    └── _filter_exclude_videos               (Filters out temporal results from excluded video IDs)

search_image
├── get(id)                                  (Fetch reference keyframe embedding from DB)
├── AnnSearchRequest                         (Construct vector subrequests per target feature)
└── Milvus hybrid_search                     (Execute multi-vector hybrid search with RRFRanker)
```

### Methods & Features

#### `Query` (Helper Class in `utils.py`)
- Extracts `include_video_ids` and `exclude_video_ids` from query string tags (`[video:...]`, `[!video:...]`, `[exclude_video:...]`) and explicit parameters.
- Parses multi-step temporal queries using regex supporting `/`, `\`, and `;` as step delimiters.
- Exposes `include_video_ids` and `exclude_video_ids` properties.

#### `search_multimodal`
Main entry point for textual and multi-modal query execution.
- Accepts `auto_translate`, `en_to_vi_translate`, `include_videos`, and `exclude_videos` flags.
- Parses string `q` into a `Query` object.
- Branches to `_get_videos` if `query.simple` (video ID lookup only).
- Branches to `_advance_search` if `query.advance` with a single step.
- Branches to `_temporal_search` if `query.temporal` (multiple step query).

#### `_advance_search`
Handles single-step multimodal queries with dynamic replenishment:
- When `exclude_video_ids` is present, executes a dynamic candidate expansion loop (starting at `max(300, (offset + limit) * 3)` and doubling candidates) until at least `offset + limit` clean items are retrieved, ensuring pages do not become empty or truncated.

#### `_temporal_search`
Handles multi-step sequential queries (e.g., `"step1 / step2"`).
- Computes SHA-256 hash of search parameters (including `include_video_ids` and `exclude_video_ids`) to utilize `cache`.
- Executes `_similarity_search` per step up to `temporal_k` candidates (default: `200`).
- Combines sequence alignment within `max_interval` frames (default: `1000`).
- Applies `_filter_exclude_videos` to exclude restricted video IDs.

#### `_get_videos`
Fetches keyframes belonging to specified `include_video_ids` while excluding `exclude_video_ids`. Caches results using SHA-256 query hashing.

#### `_filter_exclude_videos` *(static method)*
Filters search result lists to remove any item whose `video_id` matches any ID in `exclude_video_ids`.

