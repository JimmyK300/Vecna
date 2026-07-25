import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from benchmark.cli import run_benchmark_cli

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vecna Retrieval Benchmark Runner")
    parser.add_argument("--queries", type=str, default="benchmark/queries.json")
    parser.add_argument("--output", type=str, default="benchmark/results.json")
    parser.add_argument("--report", type=str, default="benchmark/report.md")
    parser.add_argument("--collection", type=str, default="milvus")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--category", type=str, default=None)
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--validate-query", type=str, default=None)

    args = parser.parse_args()

    run_benchmark_cli(
        work_dir=project_root,
        queries_path=args.queries,
        output_path=args.output,
        report_path=args.report,
        collection_name=args.collection,
        device=args.device,
        category_filter=args.category,
        save_baseline=args.save_baseline,
        validate_only=args.validate,
        validate_query_id=args.validate_query,
    )
