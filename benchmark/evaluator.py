import json
import statistics
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from aic51.packages.logger import logger
from aic51.packages.search.searcher import Searcher
from .schema import (
    QuerySample,
    QueryResult,
    AggregatedMetrics,
    FailureReasonEnum,
    CategoryEnum,
    ExpectedModalityEnum,
)


class BenchmarkEvaluator:
    """
    Core Evaluation Engine for Vecna (AIC51) benchmark suite.
    Strictly evaluates ImageCLIP, OCR, and ASR (excluding VideoCLIP).
    """

    def __init__(self, collection_name: str = "milvus", work_dir: Optional[Path] = None):
        self.collection_name = collection_name
        self.work_dir = work_dir or Path.cwd()
        self.searcher: Optional[Searcher] = None

    def initialize_searcher(self, device: str = "auto") -> Searcher:
        import torch
        if isinstance(device, str):
            dev_name = device.lower().strip()
            if dev_name in ["auto", "dml", "directml", "cuda", "gpu"]:
                if torch.cuda.is_available():
                    dev = torch.device("cuda")
                else:
                    try:
                        import torch_directml
                        if torch_directml.is_available():
                            dev = torch_directml.device()
                        else:
                            dev = torch.device("cpu")
                    except Exception:
                        dev = torch.device("cpu")
            else:
                dev = torch.device(device)
        else:
            dev = device

        logger.info(f"Initializing Searcher on collection '{self.collection_name}' with device '{dev}'...")
        self.searcher = Searcher(collection_name=self.collection_name, device=dev)
        return self.searcher

    def _get_fps(self, video_id: str) -> float:
        possible_info_files = [
            self.work_dir / "data" / "video_info" / f"{video_id}.json",
            self.work_dir / "workspace" / "data" / "video_info" / f"{video_id}.json",
        ]
        for info_file in possible_info_files:
            if info_file.exists():
                try:
                    with open(info_file, "r") as f:
                        data = json.load(f)
                        return float(data.get("fps", 25.0))
                except Exception as e:
                    logger.warning(f"Could not read fps for {video_id}: {e}")
        return 25.0

    def evaluate_query(
        self,
        sample: QuerySample,
        top_k: int = 20,
        nprobe: int = 8,
        tolerance_sec: float = 5.0,
    ) -> QueryResult:
        if self.searcher is None:
            raise RuntimeError("Searcher is not initialized. Call initialize_searcher() first.")

        target_features = []
        ocr_weight = 0.0
        asr_weight = 0.0

        modalities = sample.expected_modalities or ["image_clip"]
        has_clip = ExpectedModalityEnum.IMAGE_CLIP.value in modalities
        has_ocr = ExpectedModalityEnum.OCR.value in modalities
        has_asr = ExpectedModalityEnum.ASR.value in modalities

        if has_clip:
            target_features.append("image_clip_pe-l-14-336")

        if has_ocr and has_asr:
            ocr_weight = 0.35
            asr_weight = 0.35
        elif has_ocr:
            ocr_weight = 0.5
        elif has_asr:
            asr_weight = 0.5

        if not target_features and not has_ocr and not has_asr:
            target_features = ["image_clip_pe-l-14-336"]

        st = time.time()
        search_res = self.searcher.search_multimodal(
            sample.query,
            0,
            top_k,
            target_features,
            nprobe=nprobe,
            ocr_weight=ocr_weight,
            asr_weight=asr_weight,
        )
        latency_ms = (time.time() - st) * 1000.0

        raw_results = search_res.get("results", [])
        correct_fps = self._get_fps(sample.correct_video_id)

        hit_rank: Optional[int] = None
        top_1_res = None
        top_5_res = []
        top_20_res = []

        for idx, item in enumerate(raw_results, start=1):
            entity = item.get("entity", {})
            record_id = entity.get("frame_id", "")
            if "#" in record_id:
                vid, fid_str = record_id.split("#")
                fid = int(fid_str)
            else:
                vid, fid = record_id, 0

            time_sec = fid / correct_fps
            dist_score = float(item.get("distance", item.get("score", 0.0)))

            cand = {
                "rank": idx,
                "frame_id": record_id,
                "video_id": vid,
                "timestamp_sec": round(time_sec, 2),
                "score": round(dist_score, 4),
            }

            if idx == 1:
                top_1_res = cand
            if idx <= 5:
                top_5_res.append(cand)
            if idx <= 20:
                top_20_res.append(cand)

            is_vid_match = vid.lower() == sample.correct_video_id.lower()
            is_time_match = (
                (sample.correct_start_time - tolerance_sec) <= time_sec <= (sample.correct_end_time + tolerance_sec)
            )

            if is_vid_match and is_time_match and hit_rank is None:
                hit_rank = idx

        top_1_correct = hit_rank == 1
        top_5_correct = hit_rank is not None and hit_rank <= 5
        top_20_correct = hit_rank is not None and hit_rank <= 20

        failure_reason = FailureReasonEnum.NONE.value
        if not top_1_correct:
            if hit_rank is None:
                failure_reason = FailureReasonEnum.CORRECT_RESULT_OUTSIDE_TOP_20.value
            elif sample.primary_category == CategoryEnum.OCR_DEPENDENT.value and not has_ocr:
                failure_reason = FailureReasonEnum.MISSING_OCR_TEXT.value
            elif sample.primary_category == CategoryEnum.ASR_DEPENDENT.value and not has_asr:
                failure_reason = FailureReasonEnum.ASR_TRANSCRIPTION_ERROR.value
            elif sample.primary_category == CategoryEnum.TEMPORAL.value:
                failure_reason = FailureReasonEnum.TEMPORAL_UNDERSTANDING_REQUIRED.value
            else:
                failure_reason = FailureReasonEnum.MISSING_VISUAL_FEATURE.value

        mid_timestamp = (sample.correct_start_time + sample.correct_end_time) / 2.0

        return QueryResult(
            query_id=sample.query_id,
            query=sample.query,
            primary_category=sample.primary_category,
            expected_modalities=sample.expected_modalities,
            correct_video_id=sample.correct_video_id,
            correct_timestamp=round(mid_timestamp, 2),
            correct_result_rank=hit_rank,
            top_1_correct=top_1_correct,
            top_5_correct=top_5_correct,
            top_20_correct=top_20_correct,
            latency_ms=round(latency_ms, 2),
            failure_reason=failure_reason,
            top_1_result=top_1_res,
            top_5_results=top_5_res,
            top_20_results=top_20_res,
            notes=sample.notes,
        )

    def calculate_aggregate_metrics(self, results: List[QueryResult]) -> AggregatedMetrics:
        if not results:
            return AggregatedMetrics()

        total = len(results)
        r1_count = sum(1 for r in results if r.top_1_correct)
        r5_count = sum(1 for r in results if r.top_5_correct)
        r20_count = sum(1 for r in results if r.top_20_correct)

        mrr_sum = sum(1.0 / r.correct_result_rank if r.correct_result_rank else 0.0 for r in results)
        latencies = [r.latency_ms for r in results]

        ranks = [r.correct_result_rank for r in results if r.correct_result_rank is not None]
        med_rank = float(statistics.median(ranks)) if ranks else 0.0

        return AggregatedMetrics(
            total_queries=total,
            recall_at_1=round(r1_count / total, 4),
            recall_at_5=round(r5_count / total, 4),
            recall_at_20=round(r20_count / total, 4),
            mrr=round(mrr_sum / total, 4),
            median_rank=round(med_rank, 2),
            avg_latency_ms=round(sum(latencies) / total, 2),
        )

    def run_benchmark(self, queries: List[QuerySample]) -> Dict[str, Any]:
        query_results: List[QueryResult] = []

        logger.info(f"Running benchmark on {len(queries)} queries...")
        for sample in queries:
            res = self.evaluate_query(sample)
            query_results.append(res)

        overall_metrics = self.calculate_aggregate_metrics(query_results)

        categories = set(q.primary_category for q in queries)
        category_report = {}
        for cat in sorted(categories):
            cat_res = [r for r in query_results if r.primary_category == cat]
            category_report[cat] = self.calculate_aggregate_metrics(cat_res).to_dict()

        modality_groups: Dict[str, List[QueryResult]] = {}
        for res in query_results:
            key = "+".join(sorted(res.expected_modalities))
            if key not in modality_groups:
                modality_groups[key] = []
            modality_groups[key].append(res)

        modality_report = {}
        for mod_key, mod_res in modality_groups.items():
            modality_report[mod_key] = self.calculate_aggregate_metrics(mod_res).to_dict()

        failure_counts: Dict[str, int] = {}
        for res in query_results:
            if res.failure_reason != FailureReasonEnum.NONE.value:
                failure_counts[res.failure_reason] = failure_counts.get(res.failure_reason, 0) + 1

        return {
            "overall_metrics": overall_metrics.to_dict(),
            "category_breakdown": category_report,
            "modality_breakdown": modality_report,
            "failure_taxonomy_counts": failure_counts,
            "detailed_results": [r.to_dict() for r in query_results],
        }

    def generate_markdown_report(self, report_data: Dict[str, Any]) -> str:
        overall = report_data["overall_metrics"]
        cat_data = report_data["category_breakdown"]
        mod_data = report_data["modality_breakdown"]
        fail_data = report_data.get("failure_taxonomy_counts", {})

        md = []
        md.append("# Vecna Retrieval Benchmark Report\n")
        md.append("> **Scope**: Evaluated on ImageCLIP, OCR, and ASR modalities (VideoCLIP excluded).\n")

        md.append("## Overall Performance Summary\n")
        md.append("| Metric | Value |")
        md.append("| --- | ---: |")
        md.append(f"| **Total Queries** | {overall['total_queries']} |")
        md.append(f"| **Recall@1** | {overall['recall_at_1'] * 100:.1f}% |")
        md.append(f"| **Recall@5** | {overall['recall_at_5'] * 100:.1f}% |")
        md.append(f"| **Recall@20** | {overall['recall_at_20'] * 100:.1f}% |")
        md.append(f"| **MRR** | {overall['mrr']:.4f} |")
        md.append(f"| **Median Rank** | {overall['median_rank']} |")
        md.append(f"| **Avg Latency** | {overall['avg_latency_ms']} ms |\n")

        md.append("## Recall by Query Category\n")
        md.append("| Category | Queries | Recall@1 | Recall@5 | Recall@20 | MRR | Latency (ms) |")
        md.append("| :--- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for cat, m in cat_data.items():
            md.append(
                f"| `{cat}` | {m['total_queries']} | {m['recall_at_1']:.2f} | {m['recall_at_5']:.2f} | {m['recall_at_20']:.2f} | {m['mrr']:.4f} | {m['avg_latency_ms']} |"
            )
        md.append("\n")

        md.append("## Recall by Expected Modality\n")
        md.append("| Expected Modality | Queries | Recall@1 | Recall@5 | Recall@20 | MRR | Latency (ms) |")
        md.append("| :--- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for mod, m in mod_data.items():
            md.append(
                f"| `{mod}` | {m['total_queries']} | {m['recall_at_1']:.2f} | {m['recall_at_5']:.2f} | {m['recall_at_20']:.2f} | {m['mrr']:.4f} | {m['avg_latency_ms']} |"
            )
        md.append("\n")

        if fail_data:
            md.append("## Failure Taxonomy Analysis\n")
            md.append("| Failure Reason | Count |")
            md.append("| :--- | ---: |")
            for reason, count in fail_data.items():
                md.append(f"| `{reason}` | {count} |")
            md.append("\n")

        return "\n".join(md)
