import numpy as np
import torch
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

import aic51.packages.constant as constant
from aic51.packages.analyse import FeatureExtractor, FeatureExtractorFactory
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger

from .command import BaseCommand


class AnalyseCommand(BaseCommand):
    def __init__(self, *args, **kwargs):
        super(AnalyseCommand, self).__init__(*args, **kwargs)

    def add_args(self, subparser):
        parser = subparser.add_parser("analyse", help="Analyse extracted keyframes")

        parser.add_argument(
            "--no-gpu",
            dest="do_gpu",
            action="store_false",
            help="Do not use gpu",
        )
        parser.add_argument(
            "-o",
            "--overwrite",
            dest="do_overwrite",
            action="store_true",
            help="Skip overlapping videos",
        )
        parser.add_argument(
            "--use-image-clip",
            dest="use_image_clip",
            action="store_true",
            help="Use image clip feature extractor",
        )
        parser.add_argument(
            "--use-video-clip",
            dest="use_video_clip",
            action="store_true",
            help="Use video clip feature extractor",
        )
        parser.add_argument(
            "--use-asr",
            dest="use_asr",
            action="store_true",
            help="Use ASR feature extractor",
        )
        parser.add_argument(
            "--use-ocr",
            dest="use_ocr",
            action="store_true",
            help="Use OCR feature extractor",
        )
        parser.add_argument(
            "--use-yolo",
            dest="use_yolo",
            action="store_true",
            help="Use YOLO feature extractor",
        )

        parser.set_defaults(func=self)

    def __call__(
        self,
        do_gpu: bool,
        do_overwrite: bool,
        verbose: bool,
        use_image_clip: bool = False,
        use_video_clip: bool = False,
        use_asr: bool = False,
        use_ocr: bool = False,
        use_yolo: bool = False,
        *args,
        **kwargs,
    ):
        feature_infos = GlobalConfig.get("features")
        device = self._get_device(do_gpu)

        if feature_infos is None:
            raise RuntimeError(f"Features are not specified. Check your config file.")

        video_ids = self._get_video_ids()

        logger.info(f"Starting analyse process with (device={device})")

        any_use_flag = use_image_clip or use_video_clip or use_asr or use_ocr or use_yolo
        target_models = set()
        if use_image_clip:
            target_models.add("image_clip")
        if use_video_clip:
            target_models.add("video_clip")
        if use_asr:
            target_models.add("asr")
        if use_ocr:
            target_models.add("ocr")
        if use_yolo:
            target_models.add("yolo")

        for feature_name in feature_infos.keys():
            source = GlobalConfig.get("features", feature_name, "source")
            model_name = GlobalConfig.get("features", feature_name, "model")
            arch_name = GlobalConfig.get("features", feature_name, "arch_name")
            pretrained_model = GlobalConfig.get("features", feature_name, "pretrained_model")
            batch_size = GlobalConfig.get("features", feature_name, "analyse", "batch_size") or 1

            assert model_name is not None

            if any_use_flag and (model_name not in target_models and feature_name not in target_models):
                continue

            feature_extractor_cls = FeatureExtractorFactory.get(model_name)
            if feature_extractor_cls:
                feature_extractor = feature_extractor_cls.from_pretrained(
                    source=source,
                    arch_name=arch_name,
                    pretrained_model=pretrained_model,
                    name=feature_name,
                    batch_size=batch_size,
                    device=device,
                )
            else:
                feature_extractor = None

            polite_name = f"{model_name}" + (f' from "{pretrained_model}"' if pretrained_model else "")
            if feature_extractor:
                logger.info(f"Extracting features using {polite_name}")
            else:
                logger.error(f"{polite_name}: invalid feature extractor")
                continue

            with (
                Progress(
                    TextColumn("{task.fields[name]}"),
                    TextColumn(":"),
                    SpinnerColumn(),
                    *Progress.get_default_columns(),
                    TimeElapsedColumn(),
                    disable=not verbose,
                ) as progress,
            ):
                for video_id in video_ids:
                    self._analyse_one_video(feature_extractor, video_id, progress, do_overwrite)

    def _get_device(self, do_gpu: bool):
        device = torch.device("cpu")
        if do_gpu:
            if torch.cuda.is_available():
                device = torch.device("cuda")
            elif torch.backends.mps.is_available():
                device = torch.device("mps")
            else:
                logger.warning("GPU is not available, fallbacked to CPU")

        return device

    def _get_video_ids(self):
        keyframes_dir = self._work_dir / constant.KEYFRAME_DIR
        video_ids = sorted([d.stem for d in keyframes_dir.glob("*") if d.is_dir() and d.stem[0] != "."])
        return video_ids

    def _get_keyframes_list(self, feature_extractor: FeatureExtractor, video_id: str, do_overwrite: bool):
        keyframes_dir = self._work_dir / constant.KEYFRAME_DIR / video_id
        features_dir = self._work_dir / constant.FEATURE_DIR / video_id

        has_features = set()
        if features_dir.exists() and not do_overwrite:
            for feature_path in features_dir.glob("*/*.npy"):
                if feature_path.is_dir():
                    continue

                if feature_path.stem == feature_extractor.name:
                    has_features.add(feature_path.parent.stem)

        keyframes = []
        for keyframe in keyframes_dir.glob("*"):
            if keyframe.is_dir() or keyframe.stem[0] == "." or keyframe.stem in has_features:
                continue
            keyframes.append(keyframe.stem)

        keyframes = sorted(keyframes)

        return keyframes

    def _get_input_files(self, feature_extractor: FeatureExtractor, video_id: str, keyframes: list[str]):
        inputs_dir = self._work_dir / feature_extractor.require_input() / video_id
        if not inputs_dir.exists():
            raise RuntimeError(
                f'video_id={video_id} does not have "{feature_extractor.require_input()}" for {feature_extractor.name}'
            )

        keyframes_set = set(keyframes)

        return sorted([f for f in inputs_dir.glob("*") if f.stem in keyframes_set], key=lambda x: x.stem)

    def _analyse_one_video(
        self, feature_extractor: FeatureExtractor, video_id: str, progress: Progress, do_overwrite: bool
    ):
        task_id = progress.add_task(
            description="Analysing",
            name=video_id,
        )
        try:
            progress.update(
                task_id,
                description="Extracting features",
            )

            keyframes = self._get_keyframes_list(feature_extractor, video_id, do_overwrite)
            input_files = self._get_input_files(feature_extractor, video_id, keyframes)

            def update_progress(feature_extractor, completed, total, res):
                progress.update(task_id, completed=completed, total=total)

            features = feature_extractor.get_features(input_files, update_progress)

            progress.update(
                task_id,
                description="Saving features",
                name=video_id,
                total=len(keyframes),
            )

            video_save_dir = self._work_dir / constant.FEATURE_DIR / video_id
            for i, keyframe in enumerate(keyframes):
                keyframe_save_dir = video_save_dir / keyframe
                keyframe_save_dir.mkdir(parents=True, exist_ok=True)
                feature = np.array(features[i])

                assert isinstance(feature, np.ndarray)

                np.save(keyframe_save_dir / f"{feature_extractor.name}.npy", feature)
                progress.update(task_id, advance=1)

            progress.remove_task(task_id)
        except Exception as e:
            raise e
            progress.update(task_id, description=f"Error: {str(e)}")
