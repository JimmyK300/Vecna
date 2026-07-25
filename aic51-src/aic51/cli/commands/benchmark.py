import sys
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parents[4]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from benchmark.cli import run_benchmark_cli
from .command import BaseCommand


class BenchmarkCommand(BaseCommand):
    """
    CLI Command for running Vecna retrieval benchmark using ImageCLIP, OCR, and ASR.
    Delegates to the unified benchmark/ package.
    """

    def __init__(self, *args, **kwargs):
        super(BenchmarkCommand, self).__init__(*args, **kwargs)

    def add_args(self, subparser):
        parser = subparser.add_parser("benchmark", help="Run benchmark evaluation across ImageCLIP, OCR, and ASR modalities.")

        parser.add_argument(
            "--queries",
            dest="queries_path",
            type=str,
            default="benchmark/queries.json",
            help="Path to benchmark queries JSON file.",
        )
        parser.add_argument(
            "--output",
            dest="output_path",
            type=str,
            default="benchmark/results.json",
            help="Path to output evaluation JSON file.",
        )
        parser.add_argument(
            "--report",
            dest="report_path",
            type=str,
            default="benchmark/report.md",
            help="Path to output Markdown report file.",
        )
        parser.add_argument(
            "--collection",
            dest="collection_name",
            type=str,
            default="milvus",
            help="Milvus collection name.",
        )
        parser.add_argument(
            "--device",
            dest="device",
            type=str,
            default="cpu",
            help="Execution device (cpu or cuda).",
        )
        parser.add_argument(
            "--category",
            dest="category_filter",
            type=str,
            default=None,
            help="Filter benchmark execution to a specific primary_category.",
        )
        parser.add_argument(
            "--save-baseline",
            dest="save_baseline",
            action="store_true",
            help="Save current benchmark output as baseline in benchmark/baseline.json.",
        )
        parser.add_argument(
            "--validate",
            dest="validate_only",
            action="store_true",
            help="Validate query dataset format and ground truth without running searcher.",
        )
        parser.add_argument(
            "--validate-query",
            dest="validate_query_id",
            type=str,
            default=None,
            help="Run dry-run candidate retrieval inspection for a specific query ID.",
        )

        parser.set_defaults(func=self)

    def __call__(
        self,
        queries_path: str,
        output_path: str,
        report_path: str,
        collection_name: str,
        device: str,
        category_filter: Optional[str],
        save_baseline: bool,
        validate_only: bool,
        validate_query_id: Optional[str],
        *args,
        **kwargs,
    ):
        run_benchmark_cli(
            work_dir=self._work_dir,
            queries_path=queries_path,
            output_path=output_path,
            report_path=report_path,
            collection_name=collection_name,
            device=device,
            category_filter=category_filter,
            save_baseline=save_baseline,
            validate_only=validate_only,
            validate_query_id=validate_query_id,
        )
