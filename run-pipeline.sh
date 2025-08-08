#!/bin/bash
set -euxo pipefail

echo "Starting keyframe-only video search pipeline..."

# 1. Extract keyframes from videos using TransNetV2
echo "=== Step 1: Extracting keyframes ==="
python keyframe_extractor.py

# 2. Generate CLIP embeddings for keyframes
echo "=== Step 2: Generating keyframe embeddings ==="
python keyframe_embedding.py

echo "=== Pipeline completed successfully! ==="
echo "Your video search system is ready for keyframe-based queries."

