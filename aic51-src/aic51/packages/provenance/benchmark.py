"""Small HTTP replay harness for frozen Vecna search experiments."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def run_search_benchmark(
    queries: list[dict[str, Any]],
    endpoint: str,
    *,
    timeout_s: float = 30.0,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    records = []
    for query in queries:
        label = query.get("label", "unlabelled")
        params = query.get("params") or {key: value for key, value in query.items() if key not in {"label", "mode"}}
        started = time.perf_counter()
        record: dict[str, Any] = {"label": label, "mode": query.get("mode", "production"), "params": params}
        try:
            request = Request(f"{endpoint}?{urlencode(params, doseq=True)}", method="GET")
            with opener(request, timeout=timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
                record["status"] = response.status
                record["result_ids"] = [frame.get("id") for frame in payload.get("frames", [])]
                record["response"] = payload
        except Exception as error:  # benchmark records failures instead of hiding them
            record["status"] = "error"
            record["error"] = f"{type(error).__name__}: {error}"
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        records.append(record)

    return {"benchmark_version": "1", "endpoint": endpoint, "queries": records}


def load_queries(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, list):
        raise ValueError("query file must contain a JSON list")
    return payload
