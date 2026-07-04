# Baseline Decision

**Chosen backend baseline:** SigLIP (ViT-B/16) Feature Extraction + FAISS Vector Indexing

**Reason:** It provides the strongest out-of-the-box performance for multilingual text-to-image/video retrieval while maintaining high processing speed and low implementation complexity for v0.

**Evidence:** Multiple recent VBS (2023/2024) and LSC systems utilize contrastive language-image pretraining as their primary search mechanism. SigLIP is chosen over standard OpenAI CLIP because recent benchmarks (e.g., WebLI dataset papers) show SigLIP handles zero-shot retrieval better and supports multilingual queries natively, which is crucial if our users search in Vietnamese.

**Implementation steps:**
1. **Video Processing:** Write a script (using FFmpeg/OpenCV) to extract keyframes from videos at 1 FPS.
2. **Feature Extraction:** Pass keyframes through the pre-trained SigLIP model to generate dense vectors (embeddings).
3. **Indexing:** Build a FAISS `IndexFlatIP` (Inner Product) index to store these vectors.
4. **Querying:** Convert the user's text query to a vector using the same SigLIP text encoder and perform a nearest-neighbor search in FAISS.

**Expected weaknesses:**
* **Temporal Blindness:** The system evaluates frames independently. It cannot understand actions that happen over time (e.g., "a man *putting down* a cup" vs "a man *picking up* a cup").
* **Missed Context:** Ignores spoken dialogue (ASR) and visible text (OCR).

**Next improvements:**
* Integrate an OCR pipeline (e.g., EasyOCR) and index the extracted text into Elasticsearch or Meilisearch.
* Implement a late-fusion mechanism to combine FAISS vector search scores with Elasticsearch keyword search scores.