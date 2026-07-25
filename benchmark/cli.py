import json
from pathlib import Path
from typing import List, Optional

from aic51.packages.logger import logger
from .schema import QuerySample
from .evaluator import BenchmarkEvaluator
from .validator import QueryValidator


def run_benchmark_cli(
    work_dir: Path,
    queries_path: str = "benchmark/queries.json",
    output_path: str = "benchmark/results.json",
    report_path: str = "benchmark/report.md",
    collection_name: str = "milvus",
    device: str = "cpu",
    category_filter: Optional[str] = None,
    save_baseline: bool = False,
    validate_only: bool = False,
    validate_query_id: Optional[str] = None,
):
    q_path = work_dir / queries_path
    if not q_path.exists():
        q_path = Path(__file__).parent / "queries.json"

    if not q_path.exists():
        logger.error(f"Queries file not found at: {q_path}")
        return

    with open(q_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    queries = [QuerySample.from_dict(item) for item in raw_data]

    validator = QueryValidator(work_dir=work_dir)

    if validate_only:
        logger.info("Running query dataset validation checks...")
        val_results = validator.validate_dataset(queries)
        print(json.dumps(val_results, indent=2))
        return

    if category_filter:
        queries = [q for q in queries if q.primary_category == category_filter]
        logger.info(f"Filtered to {len(queries)} queries for category: {category_filter}")

    evaluator = BenchmarkEvaluator(collection_name=collection_name, work_dir=work_dir)
    evaluator.initialize_searcher(device=device)

    if validate_query_id:
        target_q = next((q for q in queries if q.query_id == validate_query_id), None)
        if not target_q:
            logger.error(f"Query ID '{validate_query_id}' not found in dataset.")
            return
        logger.info(f"Inspecting query candidates for '{validate_query_id}'...")
        insp = validator.inspect_query_candidates(target_q, evaluator.searcher)
        print(json.dumps(insp, indent=2))
        return

    report_data = evaluator.run_benchmark(queries)
    md_report = evaluator.generate_markdown_report(report_data)

    out_p = work_dir / output_path
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    logger.info(f"Saved evaluation results to: {out_p}")

    rep_p = work_dir / report_path
    rep_p.parent.mkdir(parents=True, exist_ok=True)
    with open(rep_p, "w", encoding="utf-8") as f:
        f.write(md_report)
    logger.info(f"Saved Markdown report to: {rep_p}")

    if save_baseline:
        base_p = work_dir / "benchmark" / "baseline.json"
        base_p.parent.mkdir(parents=True, exist_ok=True)
        with open(base_p, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        logger.info(f"Saved baseline results to: {base_p}")

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="ignore")
    except Exception:
        pass

    print("\n" + md_report)
