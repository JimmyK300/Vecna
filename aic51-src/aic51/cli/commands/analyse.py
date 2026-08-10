import numpy as np
import torch
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

import aic51.packages.constant as constant
from aic51.packages.analyse import FeatureExtractor, FeatureExtractorFactory
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.utils import get_device
from aic51.packages.utils.provenance import ProvenanceStore

from .command import BaseCommand


class AnalyseCommand(BaseCommand):
    def __init__(self, *args, **kwargs):
        super(AnalyseCommand, self).__init__(*args, **kwargs)
        self._provenance = ProvenanceStore(self._work_dir)

    def add_args(self, subparser):
        parser = subparser.add_parser("analyse", help="Analyse extracted keyframes")
        parser.add_argument("--no-gpu", dest="do_gpu", action="store_false", help="Do not use gpu")
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
            "--use-image-siglip",
            dest="use_image_siglip",
            action="store_true",
            help="Use image siglip feature extractor",
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
        parser.set_defaults(func=self)

    def __call__(
        self,
        do_gpu: bool,
        do_overwrite: bool,
        verbose: bool,
        use_image_clip: bool = False,
        use_image_siglip: bool = False,
        use_video_clip: bool = False,
        use_asr: bool = False,
        use_ocr: bool = False,
        *args,
        **kwargs,
    ):
        feature_infos = GlobalConfig.get("features")
        device = get_device(do_gpu)
        if feature_infos is None:
            raise RuntimeError("Features are not specified. Check your config file.")

        video_ids = self._get_video_ids()
        logger.info(f"Starting analyse process with (device={device})")

        any_use_flag = use_image_clip or use_image_siglip or use_video_clip or use_asr or use_ocr
        target_models = set()
        if use_image_clip:
            target_models.add("image_clip")
        if use_image_siglip:
            target_models.add("image_siglip")
        if use_video_clip:
            target_models.add("video_clip")
        if use_asr:
            target_models.add("asr")
        if use_ocr:
            target_models.add("ocr")

        for feature_name in feature_infos.keys():
            source = GlobalConfig.get("features", feature_name, "source")
            model_name = GlobalConfig.get("features", feature_name, "model")
            arch_name = GlobalConfig.get("features", feature_name, "arch_name")
            pretrained_model = GlobalConfig.get("features", feature_name, "pretrained_model")
            batch_size = GlobalConfig.get("features", feature_name, "analyse", "batch_size") or 1

            assert model_name is not None
            if any_use_flag and not any(
                tm in model_name or tm in feature_name for tm in target_models
            ):
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
                    work_dir=self._work_dir,
                )
            else:
                feature_extractor = None

            polite_name = f"{model_name}" + (
                f' from "{pretrained_model}"' if pretrained_model else ""
            )
            if feature_extractor:
                logger.info(f"Extracting features using {polite_name}")
            else:
                logger.error(f"{polite_name}: invalid feature extractor")
                continue

            provider_generation = self._provenance.provider_generation(
                feature_name=feature_name,
                model_name=model_name,
                source=source,
                arch_name=arch_name,
                pretrained_model=pretrained_model,
                batch_size=batch_size,
                extractor=feature_extractor,
            )
            # Compatibility plumbing inside the legacy extractor path; this is
            # not a universal provider API.
            feature_extractor._vecna_provider_generation_id = provider_generation[
                "provider_generation_id"
            ]

            with Progress(
                TextColumn("{task.fields[name]}"),
                TextColumn(":"),
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                disable=not verbose,
            ) as progress:
                for video_id in video_ids:
                    self._analyse_one_video(
                        feature_extractor,
                        model_name,
                        provider_generation,
                        video_id,
                        progress,
                        do_overwrite,
                    )

    def _get_video_ids(self):
        keyframes_dir = self._work_dir / constant.KEYFRAME_DIR
        return sorted(
            [
                d.stem
                for d in keyframes_dir.glob("*")
                if d.is_dir() and d.stem[0] != "."
            ]
        )

    def _get_keyframes_list(
        self,
        feature_extractor: FeatureExtractor,
        video_id: str,
        do_overwrite: bool,
    ):
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
            if (
                keyframe.is_dir()
                or keyframe.stem[0] == "."
                or keyframe.stem in has_features
            ):
                continue
            keyframes.append(keyframe.stem)
        return sorted(keyframes)

    def _get_input_files(
        self,
        feature_extractor: FeatureExtractor,
        video_id: str,
        keyframes: list[str],
    ):
        inputs_dir = self._work_dir / feature_extractor.require_input() / video_id
        if not inputs_dir.exists():
            raise RuntimeError(
                f'video_id={video_id} does not have "{feature_extractor.require_input()}" '
                f"for {feature_extractor.name}"
            )

        keyframes_set = set(keyframes)
        return sorted(
            [f for f in inputs_dir.glob("*") if f.stem in keyframes_set],
            key=lambda x: x.stem,
        )

    def _analyse_one_video(
        self,
        feature_extractor: FeatureExtractor,
        model_name: str,
        provider_generation: dict,
        video_id: str,
        progress: Progress,
        do_overwrite: bool,
    ):
        task_id = progress.add_task(description="Analysing", name=video_id)
        run = None
        outputs = []
        evidence_manifest = None
        try:
            progress.update(task_id, description="Extracting features")

            keyframes = self._get_keyframes_list(
                feature_extractor,
                video_id,
                do_overwrite,
            )
            if not keyframes:
                progress.remove_task(task_id)
                return

            input_files = self._get_input_files(
                feature_extractor,
                video_id,
                keyframes,
            )
            if not input_files:
                progress.remove_task(task_id)
                return

            input_frame_ids = [path.stem for path in input_files]
            source_record = self._provenance.ensure_source(video_id)
            selection_generation = self._provenance.ensure_keyframe_generation(video_id)
            run = self._provenance.begin_analysis_run(
                video_id=video_id,
                feature_name=feature_extractor.name,
                provider_generation=provider_generation,
                requested_frame_ids=input_frame_ids,
            )
            # Evidence belongs to the rendition used by the selected frames. A
            # later compression/re-encode may be the current stored rendition
            # without retroactively changing the frame Evidence identity.
            run["current_source_rendition_id"] = source_record["current_rendition_id"]
            run["rendition_id"] = selection_generation["rendition_id"]

            frame_evidence_map = self._provenance.frame_evidence_map(video_id)
            feature_extractor._vecna_source_context = {
                "source_id": run["source_id"],
                "rendition_id": run["rendition_id"],
                "selection_generation_id": run["selection_generation_id"],
                "frame_evidence_map": frame_evidence_map,
            }
            feature_extractor._vecna_analysis_run_id = run["analysis_run_id"]

            def update_progress(feature_extractor, completed, total, res):
                progress.update(task_id, completed=completed, total=total)

            features = feature_extractor.get_features(input_files, update_progress)
            if len(features) != len(input_files):
                raise RuntimeError(
                    f"{feature_extractor.name}: returned {len(features)} outputs for "
                    f"{len(input_files)} inputs"
                )

            evidence_getter = getattr(
                feature_extractor,
                "get_last_evidence_payload",
                None,
            )
            if callable(evidence_getter):
                evidence_payload = evidence_getter()
                if evidence_payload is not None:
                    evidence_manifest = self._provenance.write_evidence(
                        video_id=video_id,
                        feature_name=feature_extractor.name,
                        run_id=run["analysis_run_id"],
                        payload=evidence_payload,
                    )

            progress.update(
                task_id,
                description="Saving features",
                name=video_id,
                total=len(input_files),
            )

            video_save_dir = self._work_dir / constant.FEATURE_DIR / video_id
            for i, input_file in enumerate(input_files):
                frame_id = input_file.stem
                keyframe_save_dir = video_save_dir / frame_id
                keyframe_save_dir.mkdir(parents=True, exist_ok=True)
                feature = np.array(features[i])
                assert isinstance(feature, np.ndarray)

                feature_path = keyframe_save_dir / f"{feature_extractor.name}.npy"
                np.save(feature_path, feature)
                outputs.append(
                    self._provenance.output_record(
                        run=run,
                        frame_id=frame_id,
                        feature_path=feature_path,
                        feature=feature,
                        model_name=model_name,
                        frame_evidence_id=frame_evidence_map.get(frame_id),
                    )
                )
                progress.update(task_id, advance=1)

            self._provenance.finish_analysis_run(
                run,
                status="success",
                outputs=outputs,
                evidence_manifest=evidence_manifest,
            )
            progress.remove_task(task_id)
        except Exception as e:
            if run is not None:
                self._provenance.finish_analysis_run(
                    run,
                    status="failed",
                    outputs=outputs,
                    evidence_manifest=evidence_manifest,
                    error=e,
                )
            try:
                progress.update(task_id, description=f"Error: {str(e)}")
            except Exception:
                pass
            raise
