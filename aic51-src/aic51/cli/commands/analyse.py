from pathlib import Path

import numpy as np
import torch
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

import aic51.packages.constant as constant
from aic51.packages.analyse import FeatureExtractor, FeatureExtractorFactory
from aic51.packages.analyse.provenance import (
    EVIDENCE_SCHEMA_VERSION,
    SCHEMA_VERSION,
    build_artifact_record,
    implementation_source_sha256,
    merge_artifact_records,
    provider_generation_id,
    read_json,
    relative_path,
    resolve_code_revision,
    utc_now,
    write_json,
)
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.utils import get_device

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

            if any_use_flag and not any(tm in model_name or tm in feature_name for tm in target_models):
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

            polite_name = f"{model_name}" + (f' from "{pretrained_model}"' if pretrained_model else "")
            if feature_extractor:
                logger.info(f"Extracting features using {polite_name}")
            else:
                logger.error(f"{polite_name}: invalid feature extractor")
                continue

            provider_descriptor = self._provider_descriptor(
                feature_extractor=feature_extractor,
                feature_name=feature_name,
                source=source,
                model_name=model_name,
                arch_name=arch_name,
                pretrained_model=pretrained_model,
            )
            analysis_runtime = {
                "batch_size": batch_size,
                "device": str(device),
            }

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
                    self._analyse_one_video(
                        feature_extractor,
                        video_id,
                        progress,
                        do_overwrite,
                        provider_descriptor,
                        analysis_runtime,
                    )

    def _provider_descriptor(
        self,
        feature_extractor: FeatureExtractor,
        feature_name: str,
        source,
        model_name: str,
        arch_name,
        pretrained_model,
    ):
        return {
            "provider_family": model_name,
            "feature_name": feature_name,
            "implementation": f"{feature_extractor.__class__.__module__}.{feature_extractor.__class__.__qualname__}",
            "implementation_sha256": implementation_source_sha256(feature_extractor),
            "source": source,
            "model": model_name,
            "arch_name": arch_name,
            "pretrained_model": pretrained_model,
            "input_kind": str(feature_extractor.require_input()),
        }

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

        return sorted(keyframes)

    def _get_input_files(self, feature_extractor: FeatureExtractor, video_id: str, keyframes: list[str]):
        inputs_dir = self._work_dir / feature_extractor.require_input() / video_id
        if not inputs_dir.exists():
            raise RuntimeError(
                f'video_id={video_id} does not have "{feature_extractor.require_input()}" for {feature_extractor.name}'
            )

        keyframes_set = set(keyframes)

        return sorted([f for f in inputs_dir.glob("*") if f.stem in keyframes_set], key=lambda x: x.stem)

    def _write_native_evidence(
        self,
        feature_extractor: FeatureExtractor,
        video_id: str,
        video_save_dir: Path,
        provider_id: str,
    ) -> dict:
        evidence_getter = getattr(feature_extractor, "get_native_evidence", None)
        if not callable(evidence_getter):
            return {}

        bundle = evidence_getter()
        if not bundle:
            return {}

        scope = bundle.get("scope")
        items = bundle.get("items", [])
        created_at = utc_now()

        if scope == "frame":
            paths = {}
            for item in items:
                frame_id = str(item["frame_id"])
                evidence_path = video_save_dir / frame_id / f"{feature_extractor.name}.evidence.json"
                payload = {
                    "schema_version": EVIDENCE_SCHEMA_VERSION,
                    "provider_generation_id": provider_id,
                    "video_id": video_id,
                    "feature_name": feature_extractor.name,
                    "created_at": created_at,
                    "evidence": item,
                }
                write_json(evidence_path, payload)
                paths[frame_id] = relative_path(evidence_path, self._work_dir)
            return {"scope": "frame", "paths": paths}

        if scope == "video":
            evidence_path = (
                video_save_dir
                / "_provenance"
                / f"{feature_extractor.name}.{provider_id[-16:]}.native-evidence.json"
            )
            payload = {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "provider_generation_id": provider_id,
                "video_id": video_id,
                "feature_name": feature_extractor.name,
                "created_at": created_at,
                "status": bundle.get("status", "unknown"),
                "kind": bundle.get("kind"),
                "language": bundle.get("language"),
                "items": items,
            }
            write_json(evidence_path, payload)
            return {"scope": "video", "path": relative_path(evidence_path, self._work_dir)}

        logger.warning(f"Ignoring unsupported native evidence scope={scope!r} for {feature_extractor.name}")
        return {}

    def _write_manifest(
        self,
        video_id: str,
        feature_extractor: FeatureExtractor,
        provider_descriptor: dict,
        provider_id: str,
        analysis_runtime: dict,
        artifact_records: list[dict],
        native_evidence: dict,
        attempt_status: str = "success",
        error: Exception | None = None,
    ):
        video_save_dir = self._work_dir / constant.FEATURE_DIR / video_id
        manifest_path = (
            video_save_dir
            / "_provenance"
            / f"{feature_extractor.name}.{provider_id[-16:]}.manifest.json"
        )
        existing = read_json(manifest_path) or {}
        existing_records = existing.get("artifacts", [])
        merged_records = merge_artifact_records(existing_records, artifact_records)
        now = utc_now()

        if attempt_status == "success":
            overall_status = "success"
        elif merged_records:
            overall_status = "partial"
        else:
            overall_status = "failed"

        last_attempt = {
            "status": attempt_status,
            "at": now,
        }
        if error is not None:
            last_attempt["error"] = {
                "type": error.__class__.__name__,
                "message": str(error),
            }

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "video_id": video_id,
            "feature_name": feature_extractor.name,
            "status": overall_status,
            "provider_generation": {
                "id": provider_id,
                "descriptor": provider_descriptor,
            },
            "analysis_runtime": analysis_runtime,
            "analysis_code_revision": resolve_code_revision(),
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "last_attempt": last_attempt,
            "artifacts": merged_records,
        }
        if native_evidence:
            manifest["native_evidence"] = native_evidence
        elif existing.get("native_evidence"):
            manifest["native_evidence"] = existing["native_evidence"]

        write_json(manifest_path, manifest)

    def _analyse_one_video(
        self,
        feature_extractor: FeatureExtractor,
        video_id: str,
        progress: Progress,
        do_overwrite: bool,
        provider_descriptor: dict,
        analysis_runtime: dict,
    ):
        task_id = progress.add_task(
            description="Analysing",
            name=video_id,
        )
        provider_id = provider_generation_id(provider_descriptor)
        artifact_records = []
        native_evidence = {}

        try:
            progress.update(
                task_id,
                description="Extracting features",
            )

            keyframes = self._get_keyframes_list(feature_extractor, video_id, do_overwrite)
            if not keyframes:
                progress.remove_task(task_id)
                return

            input_files = self._get_input_files(feature_extractor, video_id, keyframes)
            if not input_files:
                progress.remove_task(task_id)
                return

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
            native_evidence = self._write_native_evidence(
                feature_extractor=feature_extractor,
                video_id=video_id,
                video_save_dir=video_save_dir,
                provider_id=provider_id,
            )
            frame_evidence_paths = native_evidence.get("paths", {}) if native_evidence.get("scope") == "frame" else {}

            for i, keyframe in enumerate(keyframes):
                keyframe_save_dir = video_save_dir / keyframe
                keyframe_save_dir.mkdir(parents=True, exist_ok=True)
                feature = np.array(features[i])

                assert isinstance(feature, np.ndarray)

                artifact_path = keyframe_save_dir / f"{feature_extractor.name}.npy"
                np.save(artifact_path, feature)
                artifact_records.append(
                    build_artifact_record(
                        artifact_path=artifact_path,
                        root=self._work_dir,
                        video_id=video_id,
                        frame_id=str(keyframe),
                        feature=feature,
                        native_evidence_path=frame_evidence_paths.get(str(keyframe)),
                    )
                )
                progress.update(task_id, advance=1)

            self._write_manifest(
                video_id=video_id,
                feature_extractor=feature_extractor,
                provider_descriptor=provider_descriptor,
                provider_id=provider_id,
                analysis_runtime=analysis_runtime,
                artifact_records=artifact_records,
                native_evidence=native_evidence,
                attempt_status="success",
            )

            progress.remove_task(task_id)
        except Exception as error:
            try:
                self._write_manifest(
                    video_id=video_id,
                    feature_extractor=feature_extractor,
                    provider_descriptor=provider_descriptor,
                    provider_id=provider_id,
                    analysis_runtime=analysis_runtime,
                    artifact_records=artifact_records,
                    native_evidence=native_evidence,
                    attempt_status="failed",
                    error=error,
                )
            except Exception as manifest_error:
                logger.error(
                    f"Failed to persist analysis failure provenance for video_id={video_id}, "
                    f"feature={feature_extractor.name}: {manifest_error}"
                )
            progress.remove_task(task_id)
            raise
