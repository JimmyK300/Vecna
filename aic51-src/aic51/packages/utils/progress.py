from aic51.packages.config import GlobalConfig
import os
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from concurrent.futures import ThreadPoolExecutor
from aic51.packages.logger import logger

def get_progress(disable : bool) -> Progress:
    return Progress(
        TextColumn("{task.fields[name]}"),
        TextColumn(":"),
        SpinnerColumn(),
        *Progress.get_default_columns(),
        TimeElapsedColumn(),
        disable=disable,
    )

def get_executor(workers : int | None = None) -> ThreadPoolExecutor:
    if workers is None:
        max_workers_ratio = GlobalConfig.get("max_workers_ratio") or 0

        cpu_count = os.cpu_count()
        if cpu_count is None:
            logger.warning("Could not determine CPU count, falling back to 1")
            cpu_count = 1

        workers = max(1, int(max_workers_ratio * cpu_count))
    
    return ThreadPoolExecutor(workers)
