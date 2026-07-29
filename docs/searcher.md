# `packages/search/searcher.py`

## Purpose

Provides the core search engine (`Searcher`) for multi-modal video retrieval. It executes text-to-image similarity searches (via CLIP embeddings), keyword text matching (via OCR and ASR), image-to-image similarity search (via Milvus vector search), and multi-step temporal sequence search across video keyframes.

## Usage

```python
from aic51.packages.search.searcher import Searcher
import torch

# Initialize searcher with Milvus collection name and execution device
searcher = Searcher(collection_name="milvus", device=torch.device("cuda"))

# 1. Multimodal / Text query search
results = searcher.search_multimodal(
    q="a dog running on grass ocr:PET SHOP; a person holding leash",
    offset=0,
    limit=50,
    target_features=["image_clip_pe-l-14-336"],
    ocr_weight=0.3,
    asr_weight=0.1,
    max_interval=250,
    auto_translate=True,
)

# 2. Image-to-image similarity search
image_results = searcher.search_image(
    id="V001#000123",
    offset=0,
    limit=50,
    target_features=["image_clip_pe-l-14-336"],
)
```

## Query Syntax

Queries passed to `search_multimodal` are parsed by the `Query` helper class into three main query modes:

| Query Type | Syntax Example | Description |
|---|---|---|
| **Simple Video Lookup** | `video:V001,V002` | Retrieves all keyframes associated with the specified video ID(s). |
| **Single-Step Search** | `a blue car ocr:POLICE asr:siren` | Searches keyframes matching CLIP visual description, embedded OCR text, and/or ASR spoken text. |
| **Temporal Sequence Search** | `a person walking; a red car driving; a building` | Multi-step sequential search separated by `;`. Finds keyframe sequences occurring in chronological order within `max_interval` frames. |

> **Inline Tag Syntax:**
> - `ocr:text` or `[ocr:text]`: Extracts explicit OCR search target.
> - `asr:text` or `[asr:text]`: Extracts explicit ASR search target.
> - `video:id1,id2` or `[video:id1,id2]`: Filters results to specific video IDs.

## Search Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | `str` | *(required)* | Query string (supports plain text, `ocr:`, `asr:`, `video:`, and `;` temporal splits) |
| `offset` | `int` | `0` | Result pagination offset |
| `limit` | `int` | `50` | Maximum number of search results to return |
| `target_features` | `list[str]` | `[]` | List of target feature field names in Milvus database (e.g. `["image_clip_pe-l-14-336"]`) |
| `nprobe` | `int` | `8` | Milvus index search probe parameter for vector search accuracy/speed tradeoff |
| `temporal_k` | `int` | `10000` | Top candidates to retrieve per temporal segment before sequential matching |
| `ocr_weight` | `float` | `0.5` | Weight for OCR text matching score (range `[0.0, 1.0]`) |
| `asr_weight` | `float` | `0.0` | Weight for ASR spoken text matching score (range `[0.0, 1.0 - ocr_weight]`) |
| `max_interval` | `int` | `250` | Maximum allowed frame gap between consecutive steps in a temporal sequence |
| `selected` | `str \| None` | `None` | Optional target `frame_id` to automatically set page offset to include the selected item |
| `auto_translate` | `bool` | `False` | Automatically translates query text (e.g. EN $\rightarrow$ VI for OCR/ASR matching) |

## Response Structure

`search_multimodal` and `search_image` return a dictionary containing search results and metadata:

```json
{
  "results": [
    {
      "entity": {
        "frame_id": "V001#000123",
        "video_id": "V001",
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

## Class: `Searcher`

Stateful search engine class managing feature extractors and Milvus database interactions.

### Call graph

```
search_multimodal
├── Query(q)                       (Parses raw query into structured Query object)
├── _get_videos                    (Mode 1: Direct frame retrieval by video IDs)
├── _advance_search                (Mode 2: Single-step multimodal similarity search)
│   └── _similarity_search
│       ├── CLIP text search       (Cosine similarity via Milvus, weight = 1 - ocr_w - asr_w)
│       ├── OCR text search        (BM25 full-text search via Milvus, weight = ocr_w)
│       ├── ASR text search        (BM25 full-text search via Milvus, weight = asr_w)
│       └── _normalize_scores      (Min-max normalizes component scores to [0, 1])
└── _temporal_search               (Mode 3: Multi-step sequential search)
    ├── _similarity_search         (Executes similarity search per query segment)
    └── _combine_temporal_results  (DP sliding window alignment & per-frame score tracking)

search_image
├── get(id)                        (Fetch reference keyframe embedding from DB)
├── AnnSearchRequest               (Construct vector subrequests per target feature)
└── Milvus hybrid_search           (Execute multi-vector hybrid search with RRFRanker)
```

### Methods

#### `__init__`
Initializes `Searcher` instance.
- Creates `MilvusDatabase` connection for `collection_name`.
- Calls `_prepare_feature_extractors(device)` to initialize language models (e.g., CLIP text encoders).

#### `to`
Moves all loaded feature extractor models to the specified torch device (e.g., `"cuda"` or `"cpu"`).

#### `get`
Retrieves a single record payload from Milvus by `frame_id`.

#### `search_multimodal`
Main entry point for textual and multi-modal query execution.
- Accepts `auto_translate` flag to translate queries.
- Parses string `q` into a `Query` object.
- Branches to `_get_videos` if `query.simple` (video ID lookup only).
- Branches to `_advance_search` if `query.advance` with a single step.
- Branches to `_temporal_search` if `query.temporal` (multiple `;`-separated query steps).

#### `search_image`
Executes image-to-image similarity search based on an existing keyframe ID.
- Fetches target keyframe vector embedding from Milvus.
- Constructs `AnnSearchRequest` objects for each target feature field.
- Executes `hybrid_search` in Milvus using `RRFRanker` (Reciprocal Rank Fusion).

#### `_similarity_search`
Core multi-modal fusion scoring function for a single query step.
1. **CLIP Search:** Encodes text query via `get_text_features()` and executes vector search in Milvus (Cosine similarity). Assigned weight: `1.0 - ocr_weight - asr_weight`.
2. **OCR Search:** If enabled, executes BM25 search on the OCR text index (or translated text if `auto_translate` is enabled). Assigned weight: `ocr_weight`.
3. **ASR Search:** If enabled, executes BM25 search on the ASR text index (or translated text if `auto_translate` is enabled). Assigned weight: `asr_weight`.
4. **Score Normalization:** Normalizes raw scores per component to `[0, 1]` via `_normalize_scores`.
5. **Weighted Sum & Ranking:** Computes `final_score = clip_weight * clip_score + ocr_weight * ocr_score + asr_weight * asr_score`, sorts results descending, and returns entity list with score breakdown.

#### `_advance_search`
Handles single-step multimodal queries. Calls `_similarity_search` and applies pagination (`offset`, `limit`) and candidate pool constraints.

#### `_temporal_search`
Handles multi-step sequential queries (e.g., `"step1; step2"`).
- Computes SHA-256 hash of search parameters (including `video_ids`) to utilize `cache`.
- Executes `_similarity_search` for each query segment up to `temporal_k` candidates.
- Calls `_combine_temporal_results` to sequence candidates chronologically and compute per-frame scores.

#### `_combine_temporal_results`
Dynamic programming algorithm for sequence alignment across query steps.
- Processes query step results in reverse sequence order.
- Filters candidate pairs belonging to the same `video_id` where step $i+1$ frame index falls within `[frame_idx, frame_idx + max_interval]`.
- Calculates total combined distance score for ranking and tracks individual per-frame score breakdowns in `time_line_scores`.

#### `_get_videos`
Fetches all keyframes belonging to specified `video_ids` from Milvus. Caches results using SHA-256 query hashing. Automatically calculates pagination offset if `selected` keyframe is supplied.

#### `_normalize_scores` *(static method)*
Applies min-max normalization to a map of raw scores, scaling them into the range `[0, 1]`.

#### `_prepare_feature_extractors`
Reads model configurations from `GlobalConfig`.
- Checks OCR and ASR enable flags and field names.
- Instantiates text encoders (e.g., CLIP text extractors) via `FeatureExtractorFactory.get(model_name).from_pretrained(...)`.
- Maps target feature field names to corresponding language model extractors.

#### `_get_video_filter`
Generates a Milvus expression string filtering by video IDs (e.g. `'frame_id like "video1#%" || frame_id like "video2#%"'`).
