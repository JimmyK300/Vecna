# This is the previous repo's README.md

## Ho Chi Minh City AI Challenge 2025

This repository contains the implementation of the float97's video retrieval system, developed for the HCMC AI Challenge 2025. The system is designed to perform complex event retrieval on large, untrimmed video collections, covering domains such as news, sports, tourism, and cooking.

The solution addresses three primary competition tasks: 
1. **Textual Known Item Search (KIS):** Identifying specific video segments based on natural language descriptions.
2. **Visual Question Answering (Q&A):** Extracting contextual information from visual and auditory cues.
3. **Temporal Retrieval and Alignment of Key Events (TRAKE):** Precise frame-level alignment through the decomposition of sequential event queries.

## Intended Pipeline

![AIC Pipeline](AIC_pipeline.png)

> **⚠️ Work In Progress**: The components related to the **Vintern-1B-v3_5** model for OCR extraction and image captioning are currently under development. The related code has been moved to the `wip/` folder. The current system focuses on keyframe extraction, embedding generation, and multimodal search using SigLIP, DINOv3, and WhisperX.

## System Architecture

The architecture is divided into an **Offline Processing Pipeline** for indexing and an **Online Retrieval Phase** for user interaction.

### 1. Offline Indexing

- **Keyframe Extraction:** Uses **TransNetv2** (PyTorch implementation by [YangTuanAnh](https://github.com/YangTuanAnh/transnetv2_pytorch)) to segment videos based on scene changes, reducing redundancy.
- **Semantic Embeddings:** **ViT-gopt-16-SigLIP2-384** encodes keyframes into rich semantic vectors.
- **Audio Transcription:** **WhisperX** ("turbo" model) generates time-stamped Vietnamese transcripts.
- **Visual Similarity:** **DINOv3** features are leveraged for recommendation systems and visual similarity searching.
- **OCR & Captioning (WIP):** Integration of **Vintern-1B-v3_5** for extracting on-screen text and generating descriptive captions.

### 2. Online Retrieval

- **Multimodal Routing:** Queries are dispatched to specific indices (Visual, ASR, or OCR) based on user intent.
- **Vector Search**: **FAISS** provides similarity searches, enabling sub-second retrieval across datasets.
- **User Interface:** A streamlined **Streamlit** dashboard for real-time interaction, result visualization, and submission formatting.

## Project Structure

Your project structure should look like this:

```
float97_Video_Search/
│
├── 📂 data-source/                      # Source videos (read-only)
│   └── videos/                          # Place your .mp4 files here
│
├── 📂 data-staging/                     # Intermediate processing artifacts
│   ├── keyframes/                       # Extracted keyframe images (JPG)
│   ├── preprocessing/                   # TransNetV2 scene detection results
│   ├── map-keyframes/                   # CSV files mapping keyframes to frame indices
│   ├── audios/                          # Extracted audio files (WAV)
│   ├── audio-chunk-timestamps/          # Audio chunk timing metadata
│   ├── transcripts/                     # WhisperX transcription results (JSON)
│   └── vintern_results.json             # Vintern OCR & caption results (WIP)
│
├── 📂 data-index/                       # Search indices for fast retrieval
│   ├── siglip_keyframe_embedding.index  # FAISS index for visual search
│   ├── siglip_keyframe_metadata.npy     # Metadata for visual search results
│   ├── transcript_embeddings.npy        # Embeddings for transcript search
│   ├── transcript_metadata.json         # Metadata for transcript search
│   └── keyframe_metadata.npy            # General keyframe metadata
│
├── 📂 wip/                              # Work in Progress - Experimental features
│   ├── ocr_object.py                    # Vintern OCR extraction
│   ├── ocr_processing.py                # Vintern processing pipeline
│   ├── ocr_cleaning.py                  # Vintern results cleaning
│   ├── vintern_cleaning.py              # Additional Vintern utilities
│   ├── caption_search.py                # Caption-based search (experimental)
│   ├── caption_embedding.py             # Caption embeddings (experimental)
│   └── check_vintern_processing.py      # Vintern processing verification
│
├── 📂 transnetv2-weights/               # Pre-trained TransNetV2 model weights
│
├── 🎯 Core Processing Scripts
│   ├── transnetv2.py                    # Scene boundary detection
│   ├── keyframe_extractor.py            # Extract keyframes from videos
│   ├── dinov3_embedding.py              # Generate DINOv3 embeddings for similarity
│   ├── transcript_extractor.py          # Extract audio and generate transcripts
│   ├── transcript_embedding.py          # Generate transcript embeddings
│   └── keyframe_embedding.py            # Generate SigLIP visual embeddings
│
├── 🔍 Search Modules
│   ├── keyframe_search.py               # Visual keyframe search
│   ├── siglip_search.py                 # SigLIP-based visual search
│   ├── dinov3_search.py                 # DINOv3-based similarity search
│   ├── transcript_search.py             # Audio transcript search
│   ├── ocr_search.py                    # OCR text search (Vintern-based)
│   ├── temporal_search.py               # Temporal event search
│   └── attention_search.py              # Attention-based search
│
├── 🌐 Web Application
│   ├── web_app.py                       # Main Streamlit web interface
│   └── frame_playback.py                # Video frame playback utilities
│
├── 🛠️ Utilities
│   ├── helpers.py                       # Common helper functions
│   ├── http_requests.py                 # HTTP request utilities for submission
│   ├── json_to_csv.py                   # JSON to CSV converter
│   ├── load_all_video_keyframes_info.py # Load all keyframe information
│   └── old_temp_search.py               # Legacy search implementation
│
├── 📜 Scripts
│   ├── run-pipeline.sh                  # Main processing pipeline executor
│   ├── preprocessing.sh                 # Preprocessing script
│   ├── create_dir.sh                    # Create required directories
│   └── format-code.sh                   # Code formatting utility
│
├── 📋 Configuration
│   ├── requirements.txt                 # Python dependencies
│   ├── README.md                        # This file
│   └── AIC_pipeline.png                 # Architecture diagram
│
└── 📊 Query & Submission
    ├── _query/                          # Test queries for development
    ├── pack1-groupA/                    # Competition query pack 1
    ├── pack3-groupA/                    # Competition query pack 3
    └── submission/                      # Generated submission files
```

## Deployment and Execution

### Prerequisites

* Python 3.10+
* NVIDIA GPU with CUDA support

### Installation

```bash
# Environment Setup
conda create -n aic python=3.10 -y
conda activate aic
pip install -r requirements.txt

# Directory Initialization
bash create-dir.sh

```

### Pipeline Execution

To process raw video data and generate the searchable index:

```bash
bash run-pipeline.sh

```

### Launching the Web

```bash
# Set library path for GPU optimization
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Execute web application
streamlit run web_app.py --server.port 8501

# On the remote server, you might want to run this instead
streamlit run web_app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true

```

---

## Retrieval Methodology

1. **Video Processing**: TransNetV2 analyzes videos to detect scene boundaries
2. **Keyframe Selection**: Representative frames are extracted from each scene
3. **Feature Extraction**: CLIP model generates 512-dimensional embeddings for each keyframe
4. **Index Building**: FAISS creates an efficient search index from all embeddings
5. **Query Processing**: Text queries are encoded and matched against the index
6. **Result Ranking**: Results are ranked by cosine similarity and returned
