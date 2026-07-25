import cv2
import torch
import numpy as np
from PIL import Image
from transformers import AutoModel, AutoProcessor

class VideoCLIPExtractor:
    def __init__(self, pretrained_model: str = "openai/clip-vit-base-patch32", device: str = "cpu"):
        self.device = torch.device(device)
        print(f"Loading processor for {pretrained_model}...")
        self.processor = AutoProcessor.from_pretrained(pretrained_model)
        print(f"Loading model for {pretrained_model}...")
        self.model = AutoModel.from_pretrained(pretrained_model).to(self.device)
        self.model.eval()
        self.num_frames = 8  # default sequence length

    def _read_video(self, video_path: str) -> list[Image.Image]:
        frames = []
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video file: {video_path}")
            
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            # Convert BGR (OpenCV) to RGB (PIL)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb_frame))
        cap.release()
        return frames

    def _preprocess_frames(self, frames: list[Image.Image]) -> dict:
        # Preprocess frames individually using AutoProcessor
        processed = self.processor(images=frames, return_tensors="pt")
        video_data = processed["pixel_values"]  # Shape: [num_extracted_frames, C, H, W]

        # Pad or truncate to self.num_frames (8)
        n = video_data.shape[0]
        if n < self.num_frames:
            offset = self.num_frames - n
            padding = torch.zeros(offset, *video_data.shape[1:])
            video_data = torch.cat([video_data, padding], dim=0)
        elif n > self.num_frames:
            # Sample self.num_frames frames evenly
            indices = np.linspace(0, n - 1, self.num_frames, dtype=int)
            video_data = video_data[indices]

        processed["pixel_values"] = video_data
        return processed

    def get_video_features(self, video_path: str) -> np.ndarray:
        # 1. Read frames
        frames = self._read_video(video_path)
        if len(frames) == 0:
            raise ValueError(f"No frames could be read from video: {video_path}")
            
        # 2. Preprocess
        inputs = self._preprocess_frames(frames)
        # Move inputs to device and add batch dimension [b=1, n=8, C, H, W]
        inputs = {k: v.to(self.device).unsqueeze(0) for k, v in inputs.items()}
        
        b, n, c, h, w = inputs["pixel_values"].shape
        # Reshape to [b*n, C, H, W] for the CLIP vision encoder forward pass
        inputs["pixel_values"] = inputs["pixel_values"].reshape(b * n, c, h, w)

        with torch.no_grad():
            batch_features = self.model.get_image_features(**inputs)
            
            # Compatibility layer for transformers v5.x (BaseModelOutputWithPooling)
            if not isinstance(batch_features, torch.Tensor):
                batch_features = batch_features.pooler_output
                
            # Reshape back to [b, n, feature_dim]
            batch_features = batch_features.reshape(b, n, -1)
            # Temporal Mean Pooling (average over frame embeddings)
            video_features = batch_features.mean(dim=1)
            # L2 Normalize
            video_features = video_features / video_features.norm(dim=-1, keepdim=True)
            
        return video_features.cpu().numpy()

    def get_text_features(self, queries: list[str]) -> np.ndarray:
        tokenized_input = self.processor(text=queries, return_tensors="pt", padding=True).to(self.device)
        
        with torch.no_grad():
            text_features = self.model.get_text_features(**tokenized_input)
            
            # Compatibility layer for transformers v5.x (BaseModelOutputWithPooling)
            if not isinstance(text_features, torch.Tensor):
                text_features = text_features.pooler_output
                
            # L2 Normalize
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            
        return text_features.cpu().numpy()

    def calculate_similarity(self, video_features: np.ndarray, text_features: np.ndarray) -> np.ndarray:
        # Cosine similarity is dot product since features are normalized
        return np.dot(video_features, text_features.T)[0]
