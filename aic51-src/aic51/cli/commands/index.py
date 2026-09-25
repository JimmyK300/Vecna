import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import numpy as np
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.index import MilvusDatabase
from aic51.packages.logger import logger
from aic51.packages.search.traceability import (
    artifact_provenance_claims,
    invalidate_current_index_generation,
    load_analysis_artifact_provenance,
    record_index_generation,
    summarize_provider_generations,
    summarize_video_lineage,
)

from .command import BaseCommand


class IndexCommand(BaseCommand):
    def __init__(self, *args, **kwargs):
        super(IndexCommand, self).__init__(*args, **kwargs)
        GlobalConfig.set_work_dir(self._work_dir)

    def add_args(self, subparser):
        parser = subparser.add_parser("index", help="Index features")

        parser.add_argument(
            "-c",
            "--collection",
            dest="collection_name",
            type=str,
            default=None,
            help="Name of collection to index",
        )
        parser.add_argument(
            "-o",
            "--overwrite",
            dest="do_overwrite",
            action="store_true",
            help="Overwrite existing collection",
        )
        parser.add_argument(
            "--no-update",
            dest="do_update",
            action="store_false",
            help="Do not update existing records",
        )

        parser.set_defaults(func=self)

    @staticmethod
    def _get_active_feature_fields() -> list[str]:
        feature_list = GlobalConfig.get("features") or {}
        feature_fields = []
        for feature_name, feat_cfg in feature_list.items():
            if not feat_cfg or (isinstance(feat_cfg, dict) and not feat_cfg.get("enable", True)):
                continue
            if isinstance(feat_cfg, dict) and not feat_cfg.get("index", {}).get("enable", True):
                continue
            feature_fields.append(feature_name)
        return feature_fields

    @classmethod
    def _get_metadata_feature_fields(cls) -> list[str]:
        feature_list = GlobalConfig.get("features") or {}
        fields = []
        for feature_name, feat_cfg in feature_list.items():
            if not feat_cfg or (isinstance(feat_cfg, dict) and not feat_cfg.get("enable", True)):
                continue
            mapping = GlobalConfig.get("features", feature_name, "index", "metadata_fields") or {}
            if mapping:
                fields.append(feature_name)
        return fields

    @classmethod
    def _get_metadata_target_fields(cls) -> list[str]:
        fields = []
        for feature_name in cls._get_metadata_feature_fields():
            mapping = GlobalConfig.get("features", feature_name, "index", "metadata_fields") or {}
            fields.extend(mapping.values())
        return sorted(set(fields))

    @staticmethod
    def _load_metadata_fields(frame_features_path: Path, feature_name: str) -> dict[str, list[str]]:
        """Load configured string-array fields from a feature JSON sidecar."""
        metadata_fields = GlobalConfig.get("features", feature_name, "index", "metadata_fields") or {}
        if not metadata_fields:
            return {}

        metadata_path = frame_features_path / f"{feature_name}.json"
        if not metadata_path.exists():
            logger.warning(f"Missing metadata sidecar: {metadata_path}")
            return {target_field: [] for target_field in metadata_fields.values()}

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        loaded = {}
        for source_key, target_field in metadata_fields.items():
            value = metadata.get(source_key, [])
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(
                    f'{metadata_path}: metadata key "{source_key}" must be an array of strings'
                )
            loaded[target_field] = value

        return loaded

    def __call__(self, collection_name: str | None, do_overwrite: bool, do_update: bool, verbose: bool, *args, **kwargs):
        GlobalConfig.set_work_dir(self._work_dir)
        if not collection_name:
            collection_name = (
                GlobalConfig.get("backends", "search", "collection")
                or GlobalConfig.get("milvus", "collection")
                or "milvus"
            )

        MilvusDatabase.start_server()

        # Invalidate attribution before any collection mutation. If indexing then
        # crashes, search remains truthful (`unavailable`) instead of silently
        # attaching the previous generation to a changed collection.
        invalidate_current_index_generation(self._work_dir, collection_name)
        database = MilvusDatabase(collection_name, do_overwrite)
        database.require_fields(self._get_metadata_target_fields())

        total_inserted = 0
        observed_provider_generations: dict[str, set[str]] = {}
        indexed_video_lineage: dict[str, dict[str, object]] = {}
        failed_videos: list[str] = []
        artifact_provenance = load_analysis_artifact_provenance(self._work_dir)

        max_workers_ratio = GlobalConfig.get("max_workers_ratio") or 0
        max_workers = max(1, round(os.cpu_count() or 0) * max_workers_ratio)
        with (
            Progress(
                TextColumn("{task.fields[name]}"),
                TextColumn(":"),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                disable=not verbose,
            ) as progress,
            ThreadPoolExecutor(max_workers) as executor,
        ):

            def update_progress(task_id):
                return lambda *args, **kwargs: progress.update(task_id, *args, **kwargs)

            def index_one_video(video_id):
                task_id = progress.add_task(description="Processing", name=video_id)
                try:
                    res = self._index_one_video(
                        database,
                        video_id,
                        do_update,
                        update_progress(task_id),
                        artifact_provenance,
                    )
                    progress.remove_task(task_id)
                except Exception as e:
                    res = (0, {}, {}, video_id)
                    logger.exception(e)
                    progress.update(task_id, description=f"Error: {str(e)}")

                return res

            futures = []
            video_paths = self._get_videos()

            for video_path in video_paths:
                video_id = video_path.stem
                futures.append(executor.submit(index_one_video, video_id))

            for future in futures:
                inserted, provider_generations, video_lineage, failed_video = future.result()
                total_inserted += inserted
                if failed_video:
                    failed_videos.append(failed_video)
                    continue
                indexed_video_lineage[video_lineage["video_id"]] = video_lineage["features"]
                for feature_name, generation_ids in provider_generations.items():
                    observed_provider_generations.setdefault(feature_name, set()).update(generation_ids)

        database.flush()

        feature_fields = self._get_active_feature_fields()
        provider_summary = summarize_provider_generations(feature_fields, observed_provider_generations)
        feature_configs = {name: GlobalConfig.get("features", name) for name in feature_fields}
        generation = record_index_generation(
            self._work_dir,
            collection_name=collection_name,
            feature_fields=feature_fields,
            feature_configs=feature_configs,
            provider_generations=provider_summary,
            video_lineage=indexed_video_lineage,
            inserted_entities=total_inserted,
            do_overwrite=do_overwrite,
            do_update=do_update,
            failed_videos=failed_videos,
        )

        logger.info(
            f"Inserted {total_inserted} entities; index_generation_id={generation['index_generation_id']}; "
            f"status={generation['status']}"
        )

    def _get_videos(self):
        features_dir = self._work_dir / constant.FEATURE_DIR

        video_paths = sorted(
            [d for d in features_dir.glob("*") if d.is_dir() and d.name != "features"],
            key=lambda path: path.stem,
        )
        return video_paths

    def _index_one_video(
        self,
        database: MilvusDatabase,
        video_id: str,
        do_update: bool,
        update_progress: Callable,
        artifact_provenance: dict[str, list[dict[str, str]]],
    ):
        video_features_dir = self._work_dir / constant.FEATURE_DIR / video_id

        data_list = []
        observed_provider_generations: dict[str, set[str]] = {}
        observed_lineage_claims: dict[str, list[dict[str, str]]] = {}
        feature_fields = self._get_active_feature_fields()
        metadata_feature_fields = self._get_metadata_feature_fields()

        frame_features_paths = [x for x in video_features_dir.glob("*") if x.is_dir()]

        update_progress(description="Indexing", completed=0, total=len(frame_features_paths))

        for frame_features_path in frame_features_paths:
            frame_id = frame_features_path.stem
            data = {
                "frame_id": f"{video_id}#{frame_id}",  # This is because Milvus does not allow composite primary key
            }
            frame_provider_generations: dict[str, set[str]] = {}
            frame_lineage_claims: dict[str, list[dict[str, str]]] = {}
            for feature_name in metadata_feature_fields:
                data.update(self._load_metadata_fields(frame_features_path, feature_name))

            for feature_name in feature_fields:
                # Analyse artifacts use a .npy file for the value indexed as the
                # feature itself. A same-stem .json file may contain scalar
                # metadata and must never be passed to np.load().
                feature_path = frame_features_path / f"{feature_name}.npy"
                if not feature_path.is_file():
                    continue

                feature = np.load(feature_path, allow_pickle=False)

                if feature.dtype.kind == "U":
                    feature = feature.tolist()
                elif feature.dtype.kind == "f":
                    feature = feature.astype(np.float32)

                data[feature_name] = feature
                claims = artifact_provenance_claims(
                    self._work_dir,
                    feature_path,
                    artifact_provenance,
                )
                provider_ids = {
                    claim["provider_generation_id"]
                    for claim in claims
                    if claim.get("provider_generation_id")
                }
                if provider_ids:
                    frame_provider_generations.setdefault(feature_name, set()).update(provider_ids)
                if claims:
                    frame_lineage_claims.setdefault(feature_name, []).extend(claims)

            # Fallback to configured default_value (e.g. "" for empty asr/ocr) if missing
            for f in feature_fields:
                if f not in data:
                    default_val = GlobalConfig.get("features", f, "index", "default_value")
                    if default_val is not None:
                        data[f] = default_val

            if all([f in data for f in feature_fields]):
                data_list.append({database.process_field_name(k): v for k, v in data.items()})
                for feature_name, provider_ids in frame_provider_generations.items():
                    observed_provider_generations.setdefault(feature_name, set()).update(provider_ids)
                for feature_name, claims in frame_lineage_claims.items():
                    observed_lineage_claims.setdefault(feature_name, []).extend(claims)
            else:
                missing_feats = [f for f in feature_fields if f not in data]
                logger.warning(f"Skipping {data['frame_id']}: Missing features {missing_feats}")

            update_progress(advance=1)

        database.insert(data_list, do_update)
        return (
            len(data_list),
            observed_provider_generations,
            {
                "video_id": video_id,
                "features": summarize_video_lineage(feature_fields, observed_lineage_claims),
            },
            None,
        )
