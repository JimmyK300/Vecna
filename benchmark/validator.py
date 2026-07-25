import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from aic51.packages.logger import logger
from .schema import QuerySample, CategoryEnum, ExpectedModalityEnum


class QueryValidator:
    """
    Implements the Query Validation Process:
    1. Verify correct_video_id and timestamps.
    2. Check schema completeness and constraints.
    3. Ensure expected_modalities are valid (image_clip, ocr, asr only; NO video_clip).
    4. Provide dry-run top-K evaluation to assist human validation.
    """

    def __init__(self, work_dir: Optional[Path] = None):
        self.work_dir = work_dir or Path.cwd()

    def validate_query_sample(self, sample: QuerySample) -> Tuple[bool, List[str]]:
        errors = sample.validate_schema()

        if self.work_dir and sample.correct_video_id:
            vid = sample.correct_video_id
            possible_paths = [
                self.work_dir / "data" / "videos" / f"{vid}.mp4",
                self.work_dir / "data" / "video_info" / f"{vid}.json",
                self.work_dir / "dataset" / f"{vid}.mp4",
                self.work_dir.parent / "dataset" / f"{vid}.mp4",
            ]
            if not any(p.exists() for p in possible_paths):
                errors.append(f"Warning: Neither video file nor info file for ({vid}) found in workspace/dataset paths.")

        is_valid = len(errors) == 0
        return is_valid, errors

    def validate_dataset(self, queries: List[QuerySample]) -> Dict[str, Any]:
        results = {
            "total": len(queries),
            "valid_count": 0,
            "invalid_count": 0,
            "validated_flag_count": sum(1 for q in queries if q.validated),
            "errors_by_query": {}
        }

        for q in queries:
            is_valid, errors = self.validate_query_sample(q)
            if is_valid:
                results["valid_count"] += 1
            else:
                results["invalid_count"] += 1
                results["errors_by_query"][q.query_id] = errors

        return results

    def inspect_query_candidates(
        self,
        query: QuerySample,
        searcher: Any,
        top_k: int = 20,
        fps: float = 25.0
    ) -> Dict[str, Any]:
        import time
        st = time.time()

        target_features = []
        ocr_weight = 0.0
        asr_weight = 0.0

        for mod in query.expected_modalities:
            if mod == ExpectedModalityEnum.IMAGE_CLIP.value:
                target_features.append("image_clip_pe-l-14-336")
            elif mod == ExpectedModalityEnum.OCR.value:
                ocr_weight = 0.5
            elif mod == ExpectedModalityEnum.ASR.value:
                asr_weight = 0.5

        if not target_features:
            target_features = ["image_clip_pe-l-14-336"]

        search_res = searcher.search_multimodal(
            query.query,
            0,
            top_k,
            target_features,
            nprobe=8,
            ocr_weight=ocr_weight,
            asr_weight=asr_weight,
        )

        latency_ms = (time.time() - st) * 1000.0
        raw_results = search_res.get("results", [])

        hit_rank = None
        candidates = []

        for idx, rec in enumerate(raw_results, start=1):
            entity = rec.get("entity", {})
            record_id = entity.get("frame_id", "")
            if "#" in record_id:
                vid, fid_str = record_id.split("#")
                fid = int(fid_str)
            else:
                vid, fid = record_id, 0

            time_sec = fid / fps
            score = rec.get("distance", rec.get("score", 0.0))

            is_match = (
                vid.lower() == query.correct_video_id.lower() and
                (query.correct_start_time <= time_sec <= query.correct_end_time or
                 abs(time_sec - query.correct_start_time) <= 5.0)
            )

            if is_match and hit_rank is None:
                hit_rank = idx

            candidates.append({
                "rank": idx,
                "video_id": vid,
                "frame_id": fid,
                "timestamp_sec": round(time_sec, 2),
                "score": round(float(score), 4),
                "is_ground_truth": is_match
            })

        return {
            "query_id": query.query_id,
            "query": query.query,
            "correct_video_id": query.correct_video_id,
            "correct_time_range": [query.correct_start_time, query.correct_end_time],
            "hit_rank": hit_rank,
            "latency_ms": round(latency_ms, 2),
            "candidates": candidates
        }
