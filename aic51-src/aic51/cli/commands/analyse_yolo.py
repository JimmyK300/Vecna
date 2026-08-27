from __future__ import annotations

from typing import Any

import torch
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from aic51.packages.analyse import FeatureExtractorFactory
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.utils import get_device
from aic51.packages.utils.provenance import stable_id

from .analyse import AnalyseCommand


class AnalyseYoloCommand(AnalyseCommand):
    """Run YOLO semantic extraction and its BGE-M3 projection in one command."""

    def add_args(self, subparser):
        parser = subparser.add_parser(
            "analyse-yolo",
            help="Extract YOLO object semantics and build the YOLO semantic vector index",
        )
        parser.add_argument("--no-gpu", dest="do_gpu", action="store_false")
        parser.add_argument("-o", "--overwrite", dest="do_overwrite", action="store_true")
        parser.add_argument(
            "--video",
            dest="video_ids_filter",
            action="append",
            default=None,
            help="Limit analysis to one or more video IDs (repeatable)",
        )
        parser.add_argument(
            "--raw-only",
            dest="raw_only",
            action="store_true",
            help="Write YOLO detector text but skip the BGE-M3 yolo_semantic projection",
        )
        parser.add_argument(
            "--yolo-backend",
            choices=("auto", "ultralytics", "onnx"),
            default=None,
            help="Override features.yolo.backend for this run",
        )
        parser.add_argument(
            "--yolo-onnx-provider",
            choices=("auto", "dml", "cpu"),
            default=None,
            help="Override features.yolo.onnx_provider for this run",
        )
        parser.add_argument(
            "--yolo-onnx-model",
            default=None,
            help="Path to the baked-vocabulary YOLOE ONNX artifact",
        )
        parser.add_argument(
            "--yolo-class-names",
            default=None,
            help="Optional JSON/TXT class-name map if the ONNX metadata has no names",
        )
        parser.set_defaults(func=self)

    @staticmethod
    def _feature_kwargs(
        feature_name: str,
        device: torch.device,
        work_dir,
        *,
        allow_gpu: bool,
        overrides: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        model_name = GlobalConfig.get("features", feature_name, "model")
        if model_name is None:
            raise RuntimeError(f"features.{feature_name} is missing from config")

        source = GlobalConfig.get("features", feature_name, "source")
        arch_name = GlobalConfig.get("features", feature_name, "arch_name")
        pretrained_model = GlobalConfig.get("features", feature_name, "pretrained_model")
        batch_size = GlobalConfig.get("features", feature_name, "analyse", "batch_size") or 1

        kwargs: dict[str, Any] = {
            "source": source,
            "arch_name": arch_name,
            "pretrained_model": pretrained_model,
            "name": feature_name,
            "batch_size": batch_size,
            "device": device,
            "work_dir": work_dir,
        }

        if model_name == "yolo":
            kwargs["allow_gpu"] = bool(allow_gpu)
            for key in (
                "confidence",
                "imgsz",
                "max_det",
                "iou",
                "max_details",
                "vocabulary",
                "backend",
                "onnx_provider",
                "onnx_model_path",
                "onnx_class_names_path",
                "onnx_device_id",
            ):
                value = GlobalConfig.get("features", feature_name, key)
                if value is not None:
                    kwargs[key] = value
            for key, value in (overrides or {}).items():
                if value is not None:
                    kwargs[key] = value

        if model_name == "text_embedding":
            # This is intentionally based on the user's GPU permission, not on
            # torch.device.  On Windows AMD, get_device() is CPU while the BGE
            # ONNX backend may still legitimately use DirectML.
            kwargs["allow_gpu"] = bool(allow_gpu)
            for key in (
                "backend",
                "onnx_provider",
                "onnx_model_path",
                "onnx_tokenizer_path",
                "onnx_max_length",
                "max_length",
                "text_source",
            ):
                value = GlobalConfig.get("features", feature_name, key)
                if value is not None:
                    kwargs[key] = value

        return model_name, kwargs

    def _run_feature(
        self,
        feature_name: str,
        device: torch.device,
        do_overwrite: bool,
        verbose: bool,
        video_ids_filter: list[str] | None,
        *,
        allow_gpu: bool,
        overrides: dict[str, Any] | None = None,
    ) -> None:
        model_name, init_kwargs = self._feature_kwargs(
            feature_name,
            device,
            self._work_dir,
            allow_gpu=allow_gpu,
            overrides=overrides,
        )
        extractor_cls = FeatureExtractorFactory.get(model_name)
        if extractor_cls is None:
            if model_name == "yolo":
                hint = (
                    "Install `aic51-src[yolo]` for the Ultralytics/CUDA path or "
                    "`aic51-src[yolo-directml]` for the ONNX DirectML runtime path."
                )
            else:
                hint = f"Feature extractor {model_name!r} failed to register."
            raise RuntimeError(hint)

        extractor = extractor_cls.from_pretrained(**init_kwargs)
        source = GlobalConfig.get("features", feature_name, "source")
        arch_name = GlobalConfig.get("features", feature_name, "arch_name")
        pretrained_model = GlobalConfig.get("features", feature_name, "pretrained_model")
        batch_size = GlobalConfig.get("features", feature_name, "analyse", "batch_size") or 1

        provider_generation = self._provenance.provider_generation(
            feature_name=feature_name,
            model_name=model_name,
            source=source,
            arch_name=arch_name,
            pretrained_model=pretrained_model,
            batch_size=batch_size,
            extractor=extractor,
        )
        runtime_semantics = {}
        semantics_getter = getattr(extractor, "runtime_semantics", None)
        if callable(semantics_getter):
            runtime_semantics.update(semantics_getter() or {})
        extractor_device = getattr(extractor, "_device", None)
        if extractor_device is not None:
            runtime_semantics.setdefault("device", str(extractor_device))
        if runtime_semantics:
            provider_generation["descriptor"]["runtime_semantics"] = runtime_semantics
            provider_generation["provider_generation_id"] = stable_id(
                "prv", provider_generation["descriptor"]
            )
        extractor._vecna_provider_generation_id = provider_generation["provider_generation_id"]

        compatible = self._provenance.compatible_provider_generation_ids(
            feature_name, runtime_semantics
        )
        video_ids = self._get_video_ids(extractor)
        if video_ids_filter:
            allowed = set(video_ids_filter)
            video_ids = [video_id for video_id in video_ids if video_id in allowed]

        logger.info(
            "%s: %d videos, provider_generation=%s semantics=%s",
            feature_name,
            len(video_ids),
            provider_generation["provider_generation_id"],
            runtime_semantics,
        )

        processed = 0
        skipped = 0
        with Progress(
            TextColumn("{task.fields[name]}"),
            TextColumn(":"),
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TimeElapsedColumn(),
            disable=not verbose,
        ) as progress:
            for video_id in video_ids:
                result = self._analyse_one_video(
                    extractor,
                    model_name,
                    provider_generation,
                    video_id,
                    progress,
                    do_overwrite,
                    compatible,
                )
                processed += result.get("processed", 0)
                skipped += result.get("skipped", 0)

        logger.info("%s done: processed=%d skipped=%d", feature_name, processed, skipped)

    def __call__(
        self,
        do_gpu: bool,
        do_overwrite: bool,
        verbose: bool,
        raw_only: bool = False,
        video_ids_filter: list[str] | None = None,
        yolo_backend: str | None = None,
        yolo_onnx_provider: str | None = None,
        yolo_onnx_model: str | None = None,
        yolo_class_names: str | None = None,
        *args,
        **kwargs,
    ):
        device = get_device(do_gpu)
        yolo_overrides = {
            "backend": yolo_backend,
            "onnx_provider": yolo_onnx_provider,
            "onnx_model_path": yolo_onnx_model,
            "onnx_class_names_path": yolo_class_names,
        }
        self._run_feature(
            "yolo",
            device,
            do_overwrite,
            verbose,
            video_ids_filter,
            allow_gpu=do_gpu,
            overrides=yolo_overrides,
        )
        if not raw_only:
            self._run_feature(
                "yolo_semantic",
                device,
                do_overwrite,
                verbose,
                video_ids_filter,
                allow_gpu=do_gpu,
            )
