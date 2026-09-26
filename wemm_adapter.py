"""Native WeMM-Embedding-9B video processor and embedding wrapper."""

from __future__ import annotations

from pathlib import Path


def processor_inputs(processor, items, frames_per_window=64, frame_side=512):
    from qwen_vl_utils import process_vision_info

    conversations = []
    for item in items:
        frames = item["video"]
        assert len(frames) == frames_per_window
        conversations.append([{"role": "user", "content": [{"type": "video", "video": frames,
                            "total_pixels": frames_per_window * frame_side * frame_side}]}])
    prompts = [processor.apply_chat_template(c, tokenize=False, add_generation_prompt=False)
               for c in conversations]
    images, packed, kwargs = process_vision_info(
        conversations, image_patch_size=16, return_video_kwargs=True,
        return_video_metadata=True)
    assert packed is not None and len(packed) == len(items)
    videos, metadata = map(list, zip(*packed))
    assert all(video.shape[0] == frames_per_window for video in videos)
    kwargs["do_sample_frames"] = False
    result = processor(text=prompts, images=images, videos=videos,
                       video_metadata=metadata, padding=True, truncation=False,
                       do_resize=False, return_tensors="pt", **kwargs)
    assert processor.tokenizer.padding_side == "right"
    assert len(result["video_grid_thw"]) == len(items)
    assert all(int(grid[0]) == frames_per_window // 2 for grid in result["video_grid_thw"])
    return result


class Adapter:
    def __init__(self, model, processor, torch):
        self.model = model
        self.processor = processor
        self.torch = torch

    def process(self, items):
        assert 1 <= len(items) <= 4
        inputs = processor_inputs(self.processor, items).to("cuda")
        with self.torch.inference_mode():
            vectors = self.model.embedding(**inputs, use_cache=False)
        assert vectors.shape == (len(items), 4096)
        assert self.torch.isfinite(vectors).all()
        return vectors


def load_embedder(path: Path):
    import torch
    from transformers import AutoModel, AutoProcessor

    processor = AutoProcessor.from_pretrained(str(path), trust_remote_code=True,
                                               local_files_only=True)
    processor.tokenizer.padding_side = "right"
    model = AutoModel.from_pretrained(str(path), trust_remote_code=True,
                                      local_files_only=True, dtype=torch.bfloat16,
                                      attn_implementation="sdpa").cuda().eval()
    return Adapter(model, processor, torch), torch, "sdpa"
