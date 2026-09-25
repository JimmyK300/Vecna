import time
from pathlib import Path
from queue import Queue
from threading import Thread

import numpy as np
import torch
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

import aic51.packages.constant as constant
from aic51.packages.analyse import FeatureExtractor, FeatureExtractorFactory
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.utils import get_device
from aic51.packages.utils.provenance import (
    ProvenanceStore,
    atomic_save_npy,
    atomic_write_json,
    preserve_artifact,
    stable_id,
)

from .command import BaseCommand


def _representative_doc(feature_name: str, video_id: str) -> str:
    """Human-readable corpus label for progress logs, e.g. L25_V048_ocr."""
    if "ocr" in feature_name:
        kind = "ocr"
    elif "asr" in feature_name:
        kind = "asr"
    else:
        kind = feature_name
    return f"{video_id}_{kind}"


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
            "--use-qwen-vl",
            dest="use_qwen_vl",
            action="store_true",
            help="Use Qwen VL embedding feature extractor (CUDA only)",
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
        parser.add_argument(
            "--use-text-embedding",
            dest="use_text_embedding",
            action="store_true",
            help="Use BGE-M3 text embedding extractors (ocr_dense / asr_dense)",
        )
        parser.add_argument(
            "--use-yolo",
            dest="use_yolo",
            action="store_true",
            help="Use YOLO11-seg traffic feature extractor",
        )
        parser.add_argument(
            "--use-yolo26x",
            "--use-yolo26x-seg",
            dest="use_yolo26x_seg",
            action="store_true",
            help="Use YOLO26x-seg traffic feature extractor for every keyframe",
        )
        parser.add_argument(
            "--keep-going",
            dest="keep_going",
            action="store_true",
            help="Record a video failure and continue instead of aborting the feature",
        )
        parser.add_argument(
            "--video",
            dest="video_ids_filter",
            action="append",
            default=None,
            help="Limit analysis to one or more video IDs (repeatable)",
        )
        parser.add_argument(
            "--input-folder",
            "--input-dir",
            dest="input_folder",
            default=None,
            help=(
                "Read YOLO26x frames from this folder instead of data/keyframes; "
                "accepts a flat image folder or <video_id>/<frame> subfolders"
            ),
        )
        parser.set_defaults(func=self)

    def __call__(
        self,
        do_gpu: bool,
        do_overwrite: bool,
        verbose: bool,
        use_image_clip: bool = False,
        use_qwen_vl: bool = False,
        use_image_siglip: bool = False,
        use_video_clip: bool = False,
        use_asr: bool = False,
        use_ocr: bool = False,
        use_text_embedding: bool = False,
        use_yolo: bool = False,
        use_yolo26x_seg: bool = False,
        keep_going: bool = False,
        video_ids_filter: list[str] | None = None,
        input_folder: str | None = None,
        *args,
        **kwargs,
    ):
        feature_infos = GlobalConfig.get("features")
        device = get_device(do_gpu)
        if feature_infos is None:
            raise RuntimeError("Features are not specified. Check your config file.")

        resolved_input_folder = None
        if input_folder:
            if not use_yolo26x_seg:
                raise ValueError("--input-folder/--input-dir requires --use-yolo26x-seg")
            resolved_input_folder = Path(input_folder).expanduser()
            if not resolved_input_folder.is_absolute():
                resolved_input_folder = self._work_dir / resolved_input_folder
            resolved_input_folder = resolved_input_folder.resolve()
            if not resolved_input_folder.is_dir():
                raise ValueError(f"YOLO26x input folder does not exist: {resolved_input_folder}")

        logger.info(f"Starting analyse process with (device={device}, allow_gpu={do_gpu})")

        any_use_flag = (
            use_image_clip
            or use_qwen_vl
            or use_image_siglip
            or use_video_clip
            or use_asr
            or use_ocr
            or use_text_embedding
            or use_yolo
            or use_yolo26x_seg
        )
        target_models = set()
        if use_image_clip:
            target_models.add("image_clip")
        if use_qwen_vl:
            target_models.add("qwen_vl_embedding")
        if use_image_siglip:
            target_models.add("image_siglip")
        if use_video_clip:
            target_models.add("video_clip")
        if use_asr:
            target_models.add("asr")
        if use_ocr:
            target_models.add("ocr")
        if use_text_embedding:
            target_models.add("text_embedding")
        if use_yolo:
            target_models.add("yolo_traffic")
        if use_yolo26x_seg:
            target_models.add("yolo26x_seg")

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
            if use_ocr and not use_text_embedding and model_name == "text_embedding":
                continue

            feature_extractor_cls = FeatureExtractorFactory.get(model_name)
            init_kwargs = {
                "source": source,
                "arch_name": arch_name,
                "pretrained_model": pretrained_model,
                "name": feature_name,
                "batch_size": batch_size,
                "device": device,
                "work_dir": self._work_dir,
            }
            if model_name == "text_embedding":
                init_kwargs["allow_gpu"] = do_gpu
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
                        init_kwargs[key] = value
            elif model_name in ("yolo_traffic", "yolo26x_seg"):
                for key in (
                    "conf",
                    "min_box_area",
                    "relation_conf",
                    "relation_horizontal",
                    "relation_vertical",
                    "relation_near",
                    "max_relation_objects",
                ):
                    value = GlobalConfig.get("features", feature_name, "analyse", key)
                    if value is None:
                        value = GlobalConfig.get("features", feature_name, key)
                    if value is not None:
                        init_kwargs[key] = value
                if model_name == "yolo26x_seg" and resolved_input_folder is not None:
                    init_kwargs["input_dir"] = resolved_input_folder

            if feature_extractor_cls:
                feature_extractor = feature_extractor_cls.from_pretrained(**init_kwargs)
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
            runtime_semantics = {}
            semantics_getter = getattr(feature_extractor, "runtime_semantics", None)
            if callable(semantics_getter):
                runtime_semantics.update(semantics_getter() or {})
            extractor_device = getattr(feature_extractor, "_device", None)
            if extractor_device is not None:
                runtime_semantics.setdefault("device", str(extractor_device))
            compute_type = getattr(feature_extractor, "_compute_type", None)
            if compute_type is not None:
                runtime_semantics.setdefault("compute_type", str(compute_type))
            if runtime_semantics:
                provider_generation["descriptor"]["runtime_semantics"] = runtime_semantics
                provider_generation["provider_generation_id"] = stable_id(
                    "prv",
                    provider_generation["descriptor"],
                )

            # Compatibility plumbing inside the legacy extractor path; this is
            # not a universal provider API.
            feature_extractor._vecna_provider_generation_id = provider_generation[
                "provider_generation_id"
            ]

            video_ids = self._get_video_ids(feature_extractor)
            if video_ids_filter:
                allowed = set(video_ids_filter)
                video_ids = [video_id for video_id in video_ids if video_id in allowed]
            compatible_generation_ids = self._provenance.compatible_provider_generation_ids(
                feature_name,
                runtime_semantics,
            )
            if compatible_generation_ids:
                logger.info(
                    f"{feature_name}: compatible generations={sorted(compatible_generation_ids)}"
                )
            logger.info(
                f"{feature_name}: {len(video_ids)} videos, "
                f"provider_generation={provider_generation['provider_generation_id']}"
            )
            pipeline = (
                (GlobalConfig.get("features", feature_name, "onnx_pipeline") or "auto")
                if model_name == "text_embedding"
                else "serial"
            )
            if (
                model_name == "text_embedding"
                and getattr(feature_extractor, "_backend", None) == "onnx"
                and str(pipeline).strip().lower() != "serial"
            ):
                adapt = str(
                    GlobalConfig.get("features", feature_name, "onnx_batch_adapt") or "auto"
                )
                raw_max_batch = GlobalConfig.get("features", feature_name, "onnx_max_batch")
                max_batch = int(raw_max_batch) if raw_max_batch is not None else 128
                self._analyse_onnx_preloaded(
                    feature_extractor,
                    model_name,
                    feature_name,
                    provider_generation,
                    video_ids,
                    do_overwrite,
                    keep_going,
                    batch_size,
                    compatible_generation_ids,
                    max_batch=max_batch,
                    adapt=adapt,
                )
                continue

            failures: list[dict] = []
            processed_frames = 0
            skipped_frames = 0
            started = time.perf_counter()
            with Progress(
                TextColumn("{task.fields[name]}"),
                TextColumn(":"),
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                disable=not verbose,
            ) as progress:
                for index, video_id in enumerate(video_ids, start=1):
                    try:
                        result = self._analyse_one_video(
                            feature_extractor,
                            model_name,
                            provider_generation,
                            video_id,
                            progress,
                            do_overwrite,
                            compatible_generation_ids,
                        )
                    except Exception as exc:
                        failures.append(
                            {
                                "video_id": video_id,
                                "feature_name": feature_name,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                        logger.exception(f"{feature_name} {video_id} failed")
                        if not keep_going:
                            raise
                        continue
                    processed_frames += result.get("processed", 0)
                    skipped_frames += result.get("skipped", 0)
                    elapsed = max(time.perf_counter() - started, 1e-9)
                    remaining = len(video_ids) - index
                    eta_s = (elapsed / index) * remaining if index else 0
                    docs_s = processed_frames / elapsed if processed_frames else 0.0
                    logger.info(
                        f"{feature_name} {video_id}: processed={result.get('processed', 0)} "
                        f"skipped={result.get('skipped', 0)} "
                        f"videos={index}/{len(video_ids)} "
                        f"{docs_s:.1f} docs/s elapsed={elapsed:.1f}s eta={eta_s:.0f}s"
                    )
            elapsed = max(time.perf_counter() - started, 1e-9)
            logger.info(
                f"{feature_name} done: processed={processed_frames} skipped={skipped_frames} "
                f"failures={len(failures)} {processed_frames / elapsed:.1f} docs/s "
                f"elapsed={elapsed:.1f}s"
            )
            if failures:
                fail_path = self._work_dir / "provenance" / "analysis" / f"{feature_name}.failures.json"
                atomic_write_json(
                    fail_path,
                    {
                        "feature_name": feature_name,
                        "provider_generation_id": provider_generation["provider_generation_id"],
                        "failures": failures,
                    },
                )
                logger.warning(f"{feature_name}: wrote {len(failures)} failures to {fail_path}")

    def _get_video_ids(self, feature_extractor: FeatureExtractor | None = None):
        discover = getattr(feature_extractor, "discover_video_ids", None) if feature_extractor else None
        if callable(discover):
            found = list(discover(self._work_dir) or [])
            if found or bool(getattr(feature_extractor, "custom_input_configured", False)):
                return found
        keyframes_dir = self._work_dir / constant.KEYFRAME_DIR
        if not keyframes_dir.is_dir():
            return []
        return sorted(
            [
                d.stem
                for d in keyframes_dir.glob("*")
                if d.is_dir() and d.stem[0] != "."
            ]
        )

    def _candidate_frame_ids(
        self,
        feature_extractor: FeatureExtractor,
        video_id: str,
    ) -> list[str]:
        discover = getattr(feature_extractor, "discover_frame_ids", None)
        if callable(discover):
            found = list(discover(self._work_dir, video_id) or [])
            if found or bool(getattr(feature_extractor, "custom_input_configured", False)):
                return found
        keyframes_dir = self._work_dir / constant.KEYFRAME_DIR / video_id
        if not keyframes_dir.is_dir():
            return []
        return sorted(
            keyframe.stem
            for keyframe in keyframes_dir.glob("*")
            if keyframe.is_file() and keyframe.stem[0] != "."
        )

    def _get_keyframes_list(
        self,
        feature_extractor: FeatureExtractor,
        video_id: str,
        do_overwrite: bool,
        provider_generation_id: str | None = None,
        compatible_generation_ids: set[str] | None = None,
    ):
        features_dir = self._work_dir / constant.FEATURE_DIR / video_id
        identity_aware = bool(getattr(feature_extractor, "identity_aware_outputs", False))
        recorded = {}
        claimed = {}
        if identity_aware:
            recorded = self._provenance.latest_frame_provider_generations(
                video_id,
                feature_extractor.name,
            )
            claimed = self._provenance.unfinished_frame_provider_generations(
                video_id,
                feature_extractor.name,
            )
        accepted = set(compatible_generation_ids or ())
        if provider_generation_id:
            accepted.add(provider_generation_id)

        pending = []
        skipped = 0
        preserved_count = 0
        for frame_id in self._candidate_frame_ids(feature_extractor, video_id):
            feature_path = features_dir / frame_id / f"{feature_extractor.name}.npy"
            if not feature_path.exists():
                pending.append(frame_id)
                continue
            if identity_aware:
                existing_generation = recorded.get(frame_id) or claimed.get(frame_id)
                if existing_generation in accepted and not do_overwrite:
                    skipped += 1
                    continue
                if existing_generation not in accepted:
                    reason = existing_generation or "unprovenanced"
                    preserve_artifact(feature_path, reason)
                    preserved_count += 1
                pending.append(frame_id)
                continue
            if do_overwrite:
                pending.append(frame_id)
            else:
                skipped += 1
        if preserved_count:
            logger.warning(
                f"{feature_extractor.name} {video_id}: "
                f"preserved {preserved_count} foreign artifacts"
            )
        return sorted(pending), skipped

    def _get_input_files(
        self,
        feature_extractor: FeatureExtractor,
        video_id: str,
        keyframes: list[str],
    ):
        input_paths = getattr(feature_extractor, "input_paths_for_frames", None)
        if callable(input_paths):
            return input_paths(self._work_dir, video_id, keyframes)

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

    def _collect_pending_text_jobs(
        self,
        feature_extractor,
        provider_generation: dict,
        video_ids: list[str],
        do_overwrite: bool,
        compatible_generation_ids: set[str] | None = None,
    ) -> tuple[list[dict], int]:
        skipped_frames = 0
        jobs: list[dict] = []
        for video_id in video_ids:
            pending, skipped = self._get_keyframes_list(
                feature_extractor,
                video_id,
                do_overwrite,
                provider_generation["provider_generation_id"],
                compatible_generation_ids,
            )
            skipped_frames += skipped
            if not pending:
                continue
            input_files = self._get_input_files(feature_extractor, video_id, pending)
            if not input_files:
                continue
            jobs.append(
                {
                    "video_id": video_id,
                    "frame_ids": [path.stem for path in input_files],
                }
            )
        return jobs, skipped_frames

    def _load_job_texts(self, feature_extractor, job: dict) -> list[str]:
        from aic51.packages.analyse.features.text_embedding import _load_frame_text

        text_source = getattr(feature_extractor, "_text_source", None)
        texts = []
        for frame_id in job["frame_ids"]:
            if not text_source:
                texts.append("")
                continue
            text_path = (
                self._work_dir
                / constant.FEATURE_DIR
                / job["video_id"]
                / frame_id
                / f"{text_source}.npy"
            )
            texts.append(_load_frame_text(text_path))
        return texts

    def _open_analysis_run(
        self,
        feature_extractor,
        provider_generation: dict,
        video_id: str,
        frame_ids: list[str],
    ) -> tuple[dict, dict]:
        source_record = self._provenance.ensure_source(video_id)
        keyframes_dir = self._work_dir / constant.KEYFRAME_DIR / video_id
        has_keyframes = keyframes_dir.is_dir() and any(
            path.is_file() and not path.name.startswith(".")
            for path in keyframes_dir.glob("*")
        )
        if has_keyframes:
            selection_generation = self._provenance.ensure_keyframe_generation(video_id)
        else:
            selection_generation = self._provenance.record_keyframe_generation(
                video_id,
                frame_ids,
                producer_configuration={
                    "origin": "observed_feature_frame_directories",
                    "feature_name": feature_extractor.name,
                },
                producer_identity="observed_existing_text_features",
                registration_origin="observed_at_analysis",
            )
        run = self._provenance.begin_analysis_run(
            video_id=video_id,
            feature_name=feature_extractor.name,
            provider_generation=provider_generation,
            requested_frame_ids=frame_ids,
        )
        run["current_source_rendition_id"] = source_record["current_rendition_id"]
        run["rendition_id"] = selection_generation["rendition_id"]
        atomic_write_json(
            self._provenance.analysis_path(
                video_id,
                feature_extractor.name,
                run["analysis_run_id"],
            ),
            run,
        )
        return run, self._provenance.frame_evidence_map(video_id)

    def _write_frame_vector(
        self,
        run: dict,
        model_name: str,
        video_id: str,
        frame_id: str,
        feature: np.ndarray,
        frame_evidence_map: dict,
    ) -> dict:
        feature_path = (
            self._work_dir
            / constant.FEATURE_DIR
            / video_id
            / frame_id
            / f"{run['feature_name']}.npy"
        )
        feature_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_npy(feature_path, np.asarray(feature))
        return self._provenance.output_record(
            run=run,
            frame_id=frame_id,
            feature_path=feature_path,
            feature=np.asarray(feature),
            model_name=model_name,
            frame_evidence_id=frame_evidence_map.get(frame_id),
        )

    def _analyse_onnx_preloaded(
        self,
        feature_extractor,
        model_name: str,
        feature_name: str,
        provider_generation: dict,
        video_ids: list[str],
        do_overwrite: bool,
        keep_going: bool,
        batch_size: int,
        compatible_generation_ids: set[str] | None = None,
        max_batch: int = 128,
        adapt: str = "auto",
    ) -> None:
        from aic51.packages.analyse.features.bge_onnx import build_ready_batches

        backend = getattr(feature_extractor, "_onnx_backend", None)
        if backend is None:
            raise RuntimeError("onnx preload pipeline requires BgeM3OnnxBackend")

        started = time.perf_counter()
        jobs, skipped_frames = self._collect_pending_text_jobs(
            feature_extractor,
            provider_generation,
            video_ids,
            do_overwrite,
            compatible_generation_ids,
        )
        pending_docs = sum(len(job["frame_ids"]) for job in jobs)
        logger.info(
            f"{feature_name}: overlapped pipeline pending={pending_docs} "
            f"skipped={skipped_frames} videos={len(jobs)}/{len(video_ids)} "
            f"batch_size={batch_size} max_batch={max_batch} adapt={adapt} "
            f"provider={backend.execution_provider}"
        )
        if pending_docs == 0:
            logger.info(
                f"{feature_name} done: processed=0 skipped={skipped_frames} "
                f"failures=0 0.0 docs/s elapsed={time.perf_counter() - started:.1f}s"
            )
            return

        failures: list[dict] = []
        infer_queue: Queue = Queue(maxsize=48)
        write_queue: Queue = Queue(maxsize=256)
        write_errors: list[Exception] = []
        producer_error: list[Exception] = []
        window_videos = 8

        def prepare_job(job: dict) -> bool:
            try:
                run, evidence_map = self._open_analysis_run(
                    feature_extractor,
                    provider_generation,
                    job["video_id"],
                    job["frame_ids"],
                )
            except Exception as exc:
                failures.append(
                    {
                        "video_id": job["video_id"],
                        "feature_name": feature_name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                logger.exception(f"{feature_name} {job['video_id']} failed to open run")
                if not keep_going:
                    raise
                return False
            job["run"] = run
            job["evidence_map"] = evidence_map
            job["outputs"] = []
            job["remaining"] = len(job["frame_ids"])
            job["texts"] = self._load_job_texts(feature_extractor, job)
            return True

        def producer() -> None:
            try:
                for start in range(0, len(jobs), window_videos):
                    window = []
                    texts: list[str] = []
                    owners: list[tuple[dict, int]] = []
                    for job in jobs[start : start + window_videos]:
                        if not prepare_job(job):
                            continue
                        window.append(job)
                        for local_index, text in enumerate(job["texts"]):
                            texts.append(text)
                            owners.append((job, local_index))
                    if not texts:
                        continue
                    token_lists = backend.tokenize_unpadded(texts)
                    ready = build_ready_batches(
                        token_lists,
                        batch_size=batch_size,
                        max_length=backend.max_length,
                        max_batch=max_batch,
                        adapt=adapt,
                    )
                    logger.info(
                        f"{feature_name}: queued {len(ready)} batches from "
                        f"{len(texts)} docs ({window[0]['video_id']}..{window[-1]['video_id']})"
                    )
                    for batch in ready:
                        mapped = tuple(owners[index] for index in batch.indices)
                        infer_queue.put((batch, mapped))
            except Exception as exc:
                producer_error.append(exc)
                logger.exception(f"{feature_name} tokenize producer failed")
            infer_queue.put(None)

        def writer() -> None:
            while True:
                item = write_queue.get()
                if item is None:
                    return
                job, local_index, vector = item
                try:
                    output = self._write_frame_vector(
                        job["run"],
                        model_name,
                        job["video_id"],
                        job["frame_ids"][local_index],
                        vector,
                        job["evidence_map"],
                    )
                    job["outputs"].append(output)
                    job["remaining"] -= 1
                    if job["remaining"] == 0:
                        self._provenance.finish_analysis_run(
                            job["run"],
                            status="success",
                            outputs=job["outputs"],
                            evidence_manifest=None,
                        )
                except Exception as exc:
                    write_errors.append(exc)
                    logger.exception(f"{feature_name} {job['video_id']} write failed")

        producer_thread = Thread(target=producer, name=f"{feature_name}-tokenize", daemon=True)
        writer_thread = Thread(target=writer, name=f"{feature_name}-writer", daemon=True)
        producer_thread.start()
        writer_thread.start()

        inferred = 0
        batch_index = 0
        infer_started = time.perf_counter()
        try:
            while True:
                item = infer_queue.get()
                if item is None:
                    break
                batch, mapped = item
                vectors = backend.embed_encoded(batch.encoded)
                for row, (job, local_index) in enumerate(mapped):
                    write_queue.put((job, local_index, vectors[row]))
                inferred += len(mapped)
                batch_index += 1
                if batch_index == 1 or batch_index % 25 == 0:
                    elapsed = max(time.perf_counter() - infer_started, 1e-9)
                    sample_job, _sample_index = mapped[0]
                    sample = _representative_doc(feature_name, sample_job["video_id"])
                    logger.info(
                        f"{feature_name} infer: batch={batch_index}/{sample} "
                        f"n={len(mapped)} pad={batch.pad_width} "
                        f"inferred={inferred}/{pending_docs} {inferred / elapsed:.1f} docs/s "
                        f"infer_q={infer_queue.qsize()} write_q={write_queue.qsize()}"
                    )
        except Exception as exc:
            for job in jobs:
                if job.get("run") is not None and job.get("remaining", 0) > 0:
                    self._provenance.finish_analysis_run(
                        job["run"],
                        status="failed",
                        outputs=job.get("outputs") or [],
                        evidence_manifest=None,
                        error=exc,
                    )
                    failures.append(
                        {
                            "video_id": job["video_id"],
                            "feature_name": feature_name,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
            if not keep_going:
                write_queue.put(None)
                writer_thread.join(timeout=30)
                producer_thread.join(timeout=5)
                raise
        write_queue.put(None)
        writer_thread.join()
        producer_thread.join()
        if producer_error and not keep_going:
            raise producer_error[0]
        if write_errors and not keep_going:
            raise write_errors[0]

        elapsed = max(time.perf_counter() - started, 1e-9)
        logger.info(
            f"{feature_name} done: processed={inferred} skipped={skipped_frames} "
            f"failures={len(failures)} {inferred / elapsed:.1f} docs/s "
            f"elapsed={elapsed:.1f}s"
        )
        if failures:
            fail_path = self._work_dir / "provenance" / "analysis" / f"{feature_name}.failures.json"
            atomic_write_json(
                fail_path,
                {
                    "feature_name": feature_name,
                    "provider_generation_id": provider_generation["provider_generation_id"],
                    "failures": failures,
                },
            )
            logger.warning(f"{feature_name}: wrote {len(failures)} failures to {fail_path}")

    def _analyse_one_video(
        self,
        feature_extractor: FeatureExtractor,
        model_name: str,
        provider_generation: dict,
        video_id: str,
        progress: Progress,
        do_overwrite: bool,
        compatible_generation_ids: set[str] | None = None,
    ):
        task_id = progress.add_task(description="Analysing", name=video_id)
        run = None
        outputs = []
        evidence_manifest = None
        try:
            progress.update(task_id, description="Extracting features")

            keyframes, skipped = self._get_keyframes_list(
                feature_extractor,
                video_id,
                do_overwrite,
                provider_generation["provider_generation_id"],
                compatible_generation_ids,
            )
            if not keyframes:
                progress.remove_task(task_id)
                return {"processed": 0, "skipped": skipped}

            input_files = self._get_input_files(
                feature_extractor,
                video_id,
                keyframes,
            )
            if not input_files:
                progress.remove_task(task_id)
                return {"processed": 0, "skipped": skipped}

            input_frame_ids = [path.stem for path in input_files]
            source_record = self._provenance.ensure_source(video_id)
            keyframes_dir = self._work_dir / constant.KEYFRAME_DIR / video_id
            has_keyframes = keyframes_dir.is_dir() and any(
                path.is_file() and not path.name.startswith(".")
                for path in keyframes_dir.glob("*")
            )
            if has_keyframes:
                selection_generation = self._provenance.ensure_keyframe_generation(video_id)
            else:
                selection_generation = self._provenance.record_keyframe_generation(
                    video_id,
                    input_frame_ids,
                    producer_configuration={
                        "origin": "observed_feature_frame_directories",
                        "feature_name": feature_extractor.name,
                    },
                    producer_identity="observed_existing_text_features",
                    registration_origin="observed_at_analysis",
                )
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
            atomic_write_json(
                self._provenance.analysis_path(
                    video_id,
                    feature_extractor.name,
                    run["analysis_run_id"],
                ),
                run,
            )

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
                atomic_save_npy(feature_path, feature)
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
            return {"processed": len(input_files), "skipped": skipped}
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
