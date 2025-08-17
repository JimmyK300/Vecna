#!/bin/bash
set -euxo pipefail

echo "=== Step 1: Extracting keyframes ==="
python keyframe_extractor.py

echo "=== Step 2: Generating keyframe embeddings ==="
python keyframe_embedding.py

echo "=== Complete keyframe indexing ==="

echo "=== Step 3: Processing OCR ==="
python ocr_processing.py

echo "=== Complete ocr processing ==="

echo "=== Step 4: Extracting transcript ==="
python transcript_extractor.py

echo "=== Step 5: Generating transcript embeddings ==="
python transcript_embedding.py