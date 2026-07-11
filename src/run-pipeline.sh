#!/bin/bash
set -euxo pipefail

echo "=== Step 1: Extracting keyframes ==="
transnetv2_pytorch ./data-source/videos/
./preprocessing.sh
python keyframe_extractor.py

echo "=== Step 2: Generating keyframe embeddings ==="
python keyframe_embedding.py

echo "=== Complete keyframe indexing ==="

echo "=== Step 3: Extracting transcript ==="
python transcript_extractor.py

echo "=== Step 4: Generating transcript embeddings ==="
python transcript_embedding.py

echo "=== Step 5: Processing OCR ==="
python json_to_csv.py
python ocr_processing.py

echo "=== Complete ocr processing ==="