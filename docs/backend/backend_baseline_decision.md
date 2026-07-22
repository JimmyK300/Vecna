# Baseline Decision

**Chosen backend baseline:** SigLIP2 (google/siglip2-giant-opt-patch16-384) Feature Extraction + FAISS Vector Indexing

**Reason:** Strongest out-of-the-box model in the CLIP/SigLIP family, since this is offline embedding, we dont care abt speed. FAISS is the default Vector DB here because it is optimized for vector search, but later on if we want to implement metadata search, we should use another DB or use 2 separate DB.

**Evidence:** Multiple recent VBS (2023/2024) and LSC systems utilize contrastive language-image pretraining as their primary search mechanism. SigLIP is chosen over standard OpenAI CLIP because recent benchmarks (e.g., WebLI dataset papers) show SigLIP handles zero-shot retrieval better and supports multilingual queries natively, which is crucial if our users search in Vietnamese.

**Implementation steps:**

1. **Video Processing:** Write a script (using FFmpeg/OpenCV) to extract keyframes from videos every 12 frames.
2. **Feature Extraction:** Pass keyframes through the pre-trained SigLIP model to generate dense vectors (embeddings).
3. **Indexing:** Build a FAISS `IndexFlatIP` (Inner Product) index to store these vectors.
4. **Querying:** Convert the user's text query to a vector using the same SigLIP text encoder and perform a nearest-neighbor search in FAISS.

**Expected weaknesses:**

* **Temporal Blindness:** The system evaluates frames independently. It cannot understand actions that happen over time (e.g., "a man *putting down* a cup" vs "a man *picking up* a cup").
* **Missed Context:** Ignores spoken dialogue (ASR) and visible text (OCR).
* **Irrelevant Keyframs:** Many keyframes near eachother could be similar leading to poor search.
* **Missed Details:** Cant discern details like "2 birds on the sky"" very accurately.

**Next improvements:**

High Priority

* **OCR/ASR** (e.g., EasyOCR) and index the extracted text into keyword search like Elasticsearch or Meilisearch.
* **Late-fusion mechanism** (added the scores with corresponding weights) to combine FAISS vector search scores with Elasticsearch keyword search scores.
* **Scene Detection**, more sophisticated keyframe extraction than every 12 frames
* **Reranking,** after finding top 1000 or somthing, reranking by using a slower stronger model on those limited candidates.

Medium Priority

* **Object detection**
* **Facial Recognition**
* **Sound Event detection**

Low Priority

* **Supervised learning** to adjust the weights of late-fusion.
* **ChatBot** to help with math problems/query expansion or to yap ;3
