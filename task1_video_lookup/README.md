# Video Keyframe Lookup Prototype

### 1. What the prototype does
This prototype is a minimum video keyframe lookup system. It automatically processes an input video by extracting frames at a specific interval (every 12 frames) and saving them locally with metadata (frame index, timestamp, and file path). It then uses OpenAI's CLIP model to generate vector embeddings for each extracted frame and indexes them using FAISS. Finally, it takes a text query, embeds it using CLIP, and performs a similarity search in the FAISS index to return and rank the top 10 frames that best match the textual description.

### 2. How to run it
1. Ensure your working directory has the following structure:
   - `sample_video.mp4` (your input video)
   - `task1.ipynb`
   - `frames/` (empty folder for extracted images)
2. Install the required Python libraries using the terminal:
   `pip install opencv-python torch torchvision transformers faiss-cpu Pillow`
3. Open `task1.ipynb` in your editor (e.g., VS Code) and ensure your Python kernel matches the environment where you installed the libraries.
4. Select **"Run All"** to execute the cells sequentially. The code will extract frames, generate embeddings, and print the top 10 search results.

### 3. What query was tested
The system was tested with the following text query: 
`"a corgi puppy in a gift box"`

### 4. What the top result looked like
The system successfully identified the exact moment the corgi appeared from the box. The top result printed in the console looked like this:
`1. frame=12 time=0.50s score=0.315 path=frames/frame_000012.jpg`

### 5. What part was confusing or difficult
The most challenging part of this task was handling environment setups and library updates:
* **Transformers Library Update:** When implementing CLIP, calling `model.get_image_features()` and `model.get_text_features()` returned a `BaseModelOutputWithPooling` object instead of a direct PyTorch Tensor in newer versions of the `transformers` library. This caused an `AttributeError` when trying to call `.cpu().numpy()`. I had to figure out how to extract the tensor (using `.pooler_output` or indexing) before normalizing it for FAISS.