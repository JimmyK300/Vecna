# 🎬 float19 Video Search - Keyframe Edition

A state-of-the-art video retrieval system that uses keyframe-based semantic search for efficient video content discovery. The system extracts representative keyframes from videos and enables both text-based and image-based similarity search using CLIP embeddings.

## ✨ Features

- **🔤 Text Search**: Find keyframes using natural language descriptions
- **⚡ Fast Retrieval**: Optimized FAISS indexing for real-time search
- **📊 Smart Scoring**: Advanced similarity metrics for ranking results
- **📄 Export Support**: Download search results in CSV format
- **🎥 Video Playback**: Jump directly to specific moments in videos

## 🏗️ Architecture

The system consists of three main components:

1. **Keyframe Extraction**: Uses TransNetV2 to intelligently extract representative frames
2. **Embedding Generation**: CLIP model encodes keyframes into semantic vectors
3. **Search Engine**: FAISS index enables fast similarity search for queries

```
Videos → Keyframe Extraction → CLIP Encoding → FAISS Index → Search Results
```

## 📦 Installation

**Requirements**: Python 3.10+ (tested on Python 3.10)

### Option 1: Using Conda (Recommended)
```bash
conda create -n aic python=3.10
conda activate aic
pip install -r requirements.txt
```

### Option 2: Using Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```


## 📁 Data Structure

Your project structure should look like this:

```
float97_Video_Search/
├── data-source/           # Source videos (read-only)
│   └── videos/           # Place your .mp4 files here
├── data-staging/         # Processing artifacts
│   ├── keyframes/        # Extracted keyframe images
│   ├── preprocessing/    # TransNetV2 scene detection
│   ├── map-keyframes/    # Frame mapping metadata
│   └── clip-features/    # CLIP embeddings per video
├── data-index/           # Search index files
│   ├── keyframe_embedding.index   # FAISS index
│   └── keyframe_metadata.npy # Keyframe metadata
├── run-pipeline.sh       # Main processing pipeline
├── create-dir.sh       # Create directories
├── web_app.py           # Streamlit web interface
└── ...
```

### Setup Data Directories
```bash
# Create required directories
mkdir -p data-source/videos
mkdir -p data-staging/{keyframes,preprocessing,map-keyframes,clip-features,audios,audio-chunk-timestamps,transcripts}
mkdir -p data-index
mkdir -p submission
```
or run:
```bash
bash create-dir.sh
```

### Add Your Videos
Place your MP4 video files in `data-source/videos/`:
```bash
# Example
cp /path/to/your/videos/*.mp4 data-source/videos/
```

## 🚀 Quick Start

### 1. Process Videos (Indexing)
Run the complete pipeline to extract keyframes and generate embeddings:
```bash
bash run-pipeline.sh
```

This will:
- Extract keyframes from all videos in `data-source/videos/`
- Generate CLIP embeddings for each keyframe
- Build a FAISS search index

### 2. Start the Web Interface
Launch the Streamlit web application:
```bash
streamlit run web_app.py --server.headless true
```

### 3. Search Your Videos
- **Text Search**: Describe what you're looking for (e.g., "person walking")
- **Export Results**: Select keyframes and download as CSV

## 🔍 How It Works

1. **Video Processing**: TransNetV2 analyzes videos to detect scene boundaries
2. **Keyframe Selection**: Representative frames are extracted from each scene
3. **Feature Extraction**: CLIP model generates 512-dimensional embeddings for each keyframe
4. **Index Building**: FAISS creates an efficient search index from all embeddings
5. **Query Processing**: Text queries are encoded and matched against the index
6. **Result Ranking**: Results are ranked by cosine similarity and returned

## 🙏 Acknowledgments

- **OpenAI CLIP** for powerful vision-language embeddings
- **TransNetV2** for intelligent shot boundary detection  
- **FAISS** for efficient similarity search
- **Streamlit** for the intuitive web interface
    
## Managing dependencies

recommend using https://github.com/astral-sh/uv

```
# compile 
uv pip compile requirements.in --output-file requirements.txt
# sync
uv pip sync requirements.txt
```