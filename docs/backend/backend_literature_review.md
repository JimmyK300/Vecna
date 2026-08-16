# Backend Literature Review

### 1. What do most strong systems have in common?

* **Multi-stage Retrieval:** Most top systems (e.g., in Video Browser Showdown) do not rely on a single model. They use a fast, coarse retrieval stage (usually Visual-Language embeddings like CLIP) followed by a re-ranking stage using metadata or temporal context.
* **Vector Databases:** Almost all systems utilize robust vector search engines like FAISS, Milvus, or Qdrant for fast similarity search on millions of frames.
* **Keyframe Abstraction:** Instead of processing entire videos, strong baselines sample keyframes (e.g., 1 frame per second or scene-change detection) to reduce compute overhead.

### 2. What is the simplest runnable baseline?

The simplest runnable baseline is a **Zero-shot Keyframe Retrieval Pipeline using SigLIP + FAISS**.

* **Why:** It requires no model training, only feature extraction. We sample videos at 1 fps, extract embeddings using a pre-trained SigLIP model, store them in a FAISS index, and query using text embeddings.

### 3. Which modalities matter most?

* **Visual (Keyframes):** This is the core modality. Without visual embeddings, text-to-video search is impossible.
* **Text (OCR/ASR):** These are secondary but highly impactful for specific queries (e.g., searching for a news broadcast or a specific street sign). They should be added *after* the 	visual baseline is stable.
* **Object Detection**: For highly specific query
* **Facial Recognition/Sound Event detection**: for specialized query like, "happy face"/"cat meowing"

### 4. Which systems are too heavy for us?

* Systems utilizing dense video captioning (e.g., generating a descriptive paragraph for every second of video using BLIP-2/LLaVA) are too computationally expensive for our initial index building.
* Systems using complex 3D-CNNs for spatio-temporal feature extraction are difficult to set up and slow to infer.

### 5. Which systems are realistic for our team?

* **Dual-Encoder Models (CLIP/SigLIP):** Highly realistic. Pre-trained weights are easily available via HuggingFace, and feature extraction can be batched efficiently on moderate GPUs.
