from pathlib import Path
from typing import Any, Callable, Literal, Optional

import numpy as np
import open_clip
import torch
from PIL import Image
from torch.utils.data import DataLoader

import aic51.packages.constant as constant
from aic51.packages.analyse.datasets import ImageDataset
from aic51.packages.config import GlobalConfig

from .feature_extractor import FeatureExtractor, FeatureExtractorFactory


class OpenCLIPPreprocessWrapper:
    def __init__(self, preprocess):
        self._preprocess = preprocess

    def __call__(self, image):
        return self._preprocess(image)


@FeatureExtractorFactory.register("image_siglip")
class ImageSigLIP(FeatureExtractor):
    @staticmethod
    def require_input() -> Any:
        return constant.KEYFRAME_DIR

    @staticmethod
    def from_pretrained(
        arch_name: str = "ViT-SO400M-14-SigLIP-384",
        pretrained_model: str = "webli",
        source: str = "open_clip",
        *args,
        **kwargs,
    ) -> "ImageSigLIP":
        return ImageSigLIP(arch_name=arch_name, pretrained_model=pretrained_model, *args, **kwargs)

    def __init__(
        self,
        arch_name: str = "ViT-SO400M-14-SigLIP-384",
        pretrained_model: str = "webli",
        name: str = "image_siglip",
        batch_size: int = 1,
        device: torch.device = torch.device("cpu"),
        *args,
        **kwargs,
    ):
        if not arch_name:
            arch_name = "ViT-SO400M-14-SigLIP-384"
        if not pretrained_model or pretrained_model == "meta":
            pretrained_model = "webli"

        model, _, preprocess = open_clip.create_model_and_transforms(arch_name, pretrained_model)
        tokenizer = open_clip.get_tokenizer(arch_name)

        self._model = model
        self._preprocess = preprocess
        self._tokenizer = tokenizer

        self._model.eval()

        super().__init__(name, batch_size, device)

    def get_features(
        self,
        images: list[Path | str] | np.ndarray | torch.Tensor | list[Image.Image],
        callback: Optional[Callable] = None,
    ) -> np.ndarray:

        dataset = ImageDataset(images, OpenCLIPPreprocessWrapper(self._preprocess))

        dataloader = DataLoader(
            dataset=dataset,
            batch_size=self._batch_size,
            shuffle=False,
            drop_last=False,
            num_workers=GlobalConfig.get("analyse", "num_workers") or 0,
            pin_memory=(True if GlobalConfig.get("analyse", "pin_memory") else False),
        )

        features_list = []
        num_batches = len(dataloader)
        step = max(1, num_batches // 50)
        use_autocast = self._device.type == "cuda"

        with torch.no_grad():
            if callback:
                callback(self, 0, num_batches, [])

            with torch.cuda.amp.autocast(enabled=use_autocast):
                for i, data in enumerate(dataloader):
                    data = data.to(self._device)
                    batch_features = self._model.encode_image(data)
                    features_list.append(batch_features)

                    if callback and ((i + 1) % step == 0 or (i + 1) == num_batches):
                        callback(self, i + 1, num_batches, features_list)

            if len(features_list) == 0:
                return np.array([])

            image_features = torch.cat(features_list, dim=0)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        return image_features.cpu().numpy()

    def get_text_features(self, texts: list[str] | str | np.ndarray, callback: Optional[Callable] = None) -> Any:
        if isinstance(texts, np.ndarray):
            texts = list(texts.tolist())
        if isinstance(texts, str):
            texts = [texts]

        tokenized_input = self._tokenizer(texts).to(self._device)
        use_autocast = self._device.type == "cuda"
        with torch.no_grad():
            with torch.cuda.amp.autocast(enabled=use_autocast):
                text_features = self._model.encode_text(tokenized_input)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        return text_features.cpu().numpy()

    def to(self, device: str | torch.device):
        self._device = torch.device(device)
        self._model.to(self._device)
