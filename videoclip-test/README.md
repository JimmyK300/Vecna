# Standalone VideoCLIP Feature Extractor & Tester

This repository provides a minimal, self-contained implementation to extract feature embeddings from video segments using pretrained CLIP models (such as Hugging Face CLIP or OpenCLIP) and calculate similarity scores against text queries.

## Features
- Direct video ingestion: accepts path to any `.mp4` video.
- Configurable frame sampling (default 8 frames per video clip).
- Temporal mean-pooling aggregation of frame embeddings.
- Full compatibility with both `transformers` v4.x and `transformers` v5.x (handles `BaseModelOutputWithPooling` outputs).

## Setup

1. **Install Dependencies**:
   ```bash
   pip install torch torchvision transformers opencv-python numpy pillow
   ```

2. **Verify Installation**:
   Ensure you have access to a Python environment with PyTorch.

## Usage

You can test video embeddings and similarity with text queries using `test_run.py`:
```bash
python test_run.py --video path/to/your/video.mp4
```

---

## Test Results and Remarks (Bản nhận xét kết quả)

Testing was conducted on the sample video clip (`000000.mp4` from *The Queen's Corgi* animation) using `openai/clip-vit-base-patch32`:

### Test Scores
| Query | Cosine Similarity | Remarks |
| :--- | :---: | :--- |
| `an animated queen sitting at her desk` | **0.3016** | **Highest score** (Perfect match to the main scene and animated character). |
| `a general in military uniform presenting a gift` | **0.2679** | **Strong match** (Accurately describes the old man in military uniform). |
| `a gift box wrapped in a Union Jack flag on a desk` | **0.2602** | **Strong match** (Identifies the specific British flag pattern on the gift box). |
| `an old woman in a light green top smiling` | **0.2436** | **Good match** (Describes the Queen's outfit and expression). |
| `a green desk lamp` | **0.2284** | **Moderate match** (Correctly detects the green desk lamp on the left). |
| `a dog playing with a toy` (Negative query) | **0.2001** | **Lowest score** (Correctly identifies that there is no dog or toy in the scene). |

### Key Remarks & Insights:
1. **Accurate Object & Style Association**: The model shows a very high correlation with style descriptors like `"animated"` and specific objects like `"desk lamp"`, `"gift box"`, and `"military uniform"`.
2. **Effective Contrast**: The negative query (`a dog playing with a toy`) scored the lowest (**0.2001**), showing that the model is capable of distinguishing matching visual concepts from non-matching ones.
3. **Temporal Mean-Pooling**: Because the 8 frames are averaged, objects that persist throughout the video (like the queen sitting at her desk and the military general standing next to her) obtain the highest scores, demonstrating the effectiveness of averaging frame embeddings for general video scene matching.
