from .feature_extractor import FeatureExtractor, FeatureExtractorFactory
from .text_embedding import TextEmbedding

# Optional extractors register themselves on import. Missing extra
# dependencies must not block the BGE-M3 ONNX backend.
for _module in (
    "image_clip",
    "image_siglip",
    "video_clip",
    "ocr",
    "asr",
    "qwen_vl",
    "yolo",
):
    try:
        __import__(f"{__name__}.{_module}", fromlist=["*"])
    except ImportError:
        pass
