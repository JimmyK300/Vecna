"""Default-off Searcher adapter for Vecna Issue #64.

The production ``Searcher`` is not modified.  This subclass is intended only
for the Issue #64 confirmatory benchmark harness.  It reuses the existing
Vecna retrieval implementation as five isolated component calls:

- one visual-only call for each selected visual target feature;
- one OCR-only call when OCR is enabled;
- one ASR-only call when ASR is enabled.

Only the visual arms use the OpenCubee-derived model-weighted late fusion.
Vecna's existing outer visual/OCR/ASR weighting is then applied unchanged.
That isolates the donor variable and prevents OCR/ASR from being fused once per
visual model.
"""

from __future__ import annotations

from typing import Callable

from .experimental_fusion import fuse_model_results
from .searcher import Searcher as _BaseSearcher


_NO_VISUAL_SENTINEL = "__issue64_no_visual__"


def _identity(result: dict) -> str:
    entity = result.get("entity", {})
    frame_id = entity.get("frame_id") if isinstance(entity, dict) else None
    if frame_id:
        return str(frame_id)
    frame_id = result.get("frame_id")
    if frame_id:
        return str(frame_id)
    raise ValueError("Issue #64 result has no frame identity")


class OpenCubeeFusionSearcher(_BaseSearcher):
    """Experimental equal-weight OpenCubee visual late-fusion Searcher."""

    issue64_strategy = "opencubee_model_weighted"

    def _similarity_search(
        self,
        query_features: dict,
        video_ids: list[str],
        offset: int = 0,
        limit: int = 50,
        target_features: list = [],
        /,
        ocr_weight: float = 0.5,
        asr_weight: float = 0.0,
        ocr_alpha: float = 0.5,
        asr_alpha: float = 0.5,
        hybrid_alpha: float | None = None,
        nprobe: int = 8,
        exclude_video_ids: list[str] = [],
        cancel_event: object | Callable = None,
    ):
        # Match the production Searcher weight contract before splitting arms.
        if hybrid_alpha is not None:
            ocr_alpha = hybrid_alpha
            asr_alpha = hybrid_alpha
        ocr_weight = max(0.0, min(1.0, float(ocr_weight)))
        asr_weight = max(0.0, min(1.0 - ocr_weight, float(asr_weight)))
        visual_weight = 1.0 - ocr_weight - asr_weight

        cleaned_targets = [
            feature.strip()
            for feature in (target_features or [])
            if feature and feature.strip()
        ]
        if not cleaned_targets:
            cleaned_targets = list(self._features.keys())

        # 1. Visual models: preserve each model as its own normalized ranking.
        visual_results_by_model: dict[str, list[dict]] = {}
        if visual_weight > 0.0:
            for target_name in cleaned_targets:
                arm = super()._similarity_search(
                    query_features,
                    video_ids,
                    offset,
                    limit,
                    [target_name],
                    ocr_weight=0.0,
                    asr_weight=0.0,
                    ocr_alpha=ocr_alpha,
                    asr_alpha=asr_alpha,
                    hybrid_alpha=hybrid_alpha,
                    nprobe=nprobe,
                    exclude_video_ids=exclude_video_ids,
                    cancel_event=cancel_event,
                )
                if arm:
                    visual_results_by_model[target_name] = arm

        visual_weights = {model: 1.0 for model in visual_results_by_model}
        visual_results = fuse_model_results(visual_results_by_model, visual_weights)

        # 2. OCR / ASR: run once each, using the existing Vecna component logic.
        # The sentinel is never searched because clip_weight is zero in these
        # calls; it merely prevents an empty target list from expanding to all
        # configured visual features.
        ocr_results: list[dict] = []
        if ocr_weight > 0.0:
            ocr_results = super()._similarity_search(
                query_features,
                video_ids,
                offset,
                limit,
                [_NO_VISUAL_SENTINEL],
                ocr_weight=1.0,
                asr_weight=0.0,
                ocr_alpha=ocr_alpha,
                asr_alpha=asr_alpha,
                hybrid_alpha=hybrid_alpha,
                nprobe=nprobe,
                exclude_video_ids=exclude_video_ids,
                cancel_event=cancel_event,
            )

        asr_results: list[dict] = []
        if asr_weight > 0.0:
            asr_results = super()._similarity_search(
                query_features,
                video_ids,
                offset,
                limit,
                [_NO_VISUAL_SENTINEL],
                ocr_weight=0.0,
                asr_weight=1.0,
                ocr_alpha=ocr_alpha,
                asr_alpha=asr_alpha,
                hybrid_alpha=hybrid_alpha,
                nprobe=nprobe,
                exclude_video_ids=exclude_video_ids,
                cancel_event=cancel_event,
            )

        visual_map = {_identity(item): item for item in visual_results}
        ocr_map = {_identity(item): item for item in ocr_results}
        asr_map = {_identity(item): item for item in asr_results}
        all_ids = set(visual_map) | set(ocr_map) | set(asr_map)

        results: list[dict] = []
        for frame_id in all_ids:
            visual = visual_map.get(frame_id)
            ocr = ocr_map.get(frame_id)
            asr = asr_map.get(frame_id)
            source = visual or ocr or asr
            assert source is not None

            visual_score = float(visual.get("distance", 0.0)) if visual else 0.0
            ocr_score = float(ocr.get("distance", 0.0)) if ocr else 0.0
            asr_score = float(asr.get("distance", 0.0)) if asr else 0.0
            final_score = (
                visual_weight * visual_score
                + ocr_weight * ocr_score
                + asr_weight * asr_score
            )

            visual_meta = (visual or {}).get("experimental_fusion", {})
            results.append(
                {
                    "entity": source["entity"],
                    "distance": final_score,
                    "scores": {
                        "final": round(final_score, 6),
                        "clip": round(visual_score, 6),
                        "ocr": round(ocr_score, 6),
                        "asr": round(asr_score, 6),
                        "issue64_fusion_strategy": self.issue64_strategy,
                        "issue64_visual_model_weights": visual_meta.get(
                            "normalized_model_weights", {}
                        ),
                        "issue64_visual_model_scores": visual_meta.get("model_scores", {}),
                    },
                }
            )

        results.sort(key=lambda item: (-float(item["distance"]), _identity(item)))
        return self._filter_exclude_videos(results, exclude_video_ids)
