"""Read-only edge and concurrent search checks against a running local Vecna server."""

import concurrent.futures
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests


URL = "http://127.0.0.1:6900/api/search_multimodal"
OUT = Path("hardtest-results") / f"edge-{datetime.now():%Y%m%d-%H%M%S}.json"
BASE = {"collection": "workspace", "limit": 3, "temporal_k": 10}


def search(name, params):
    started = time.perf_counter()
    try:
        response = requests.get(URL, params={**BASE, **params}, timeout=90)
        try:
            body = response.json()
        except ValueError:
            body = {}
        return {
            "name": name,
            "status": response.status_code,
            "seconds": round(time.perf_counter() - started, 3),
            "canceled": body.get("canceled") if isinstance(body, dict) else None,
            "error": body.get("detail") if isinstance(body, dict) and response.status_code >= 400 else None,
        }
    except requests.RequestException as exc:
        return {"name": name, "status": None, "seconds": round(time.perf_counter() - started, 3), "error": str(exc)}


def main():
    cases = [
        ("empty", {"q": ""}),
        ("whitespace", {"q": "   "}),
        *((f"special_{index}", {"q": value}) for index, value in enumerate(("*", "+", "?", "(", ")", "[", "]", "\\", ".*"))),
        ("long_500_words", {"q": "car " * 500}),
        ("unclosed_quote", {"q": '"red car'}),
        ("nested_quotes", {"q": '"red "car" on road"'}),
        ("diacritics", {"q": '"câu 3"'}),
        ("no_diacritics", {"q": '"cau 3"'}),
        ("temporal_2", {"q": "car\nperson"}),
        ("temporal_5", {"q": "car\nperson\nroad\ntruck\nbicycle"}),
        ("temporal_missing_first", {"q": "zzzxxyy\nperson"}),
        ("temporal_missing_middle", {"q": "car\nzzzxxyy\nperson"}),
        ("temporal_interval_0", {"q": "car\nperson", "max_interval": 0}),
        ("temporal_interval_100000", {"q": "car\nperson", "max_interval": 100000}),
        ("yolo_invalid", {"q": "traffic", "collection": "workspace2", "yolo_relation": "car:person:invalid_relation"}),
        ("yolo_colons", {"q": "traffic", "collection": "workspace2", "yolo_relation": ":::"}),
        ("yolo_injection", {"q": "traffic", "collection": "workspace2", "yolo_relation": "car'); DROP TABLE x; --"}),
        ("yolo_batch1", {"q": "car", "yolo_relation": "car left_of person"}),
        ("camera_invalid", {"q": "traffic", "collection": "workspace2", "road_type": "highway"}),
        ("lighting_invalid", {"q": "traffic", "collection": "workspace2", "lighting": "rain"}),
        ("alias_batch1", {"q": "car", "collection": "testcol1"}),
        ("alias_batch2", {"q": "traffic", "collection": "testcol2"}),
    ]
    edges = []
    for name, params in cases:
        result = search(name, params)
        edges.append(result)
        print(result, flush=True)

    # Concurrent searches intentionally supersede one another. Canceled responses
    # are valid; server errors and unresponsive requests are the signals of interest.
    variants = [
        {"q": "car", "collection": "workspace"},
        {"q": "person", "collection": "testcol1"},
        {"q": "traffic", "collection": "workspace2"},
        {"q": "road", "collection": "testcol2"},
        {"q": '"red car"', "collection": "workspace"},
        {"q": "car\nperson", "collection": "workspace"},
        {"q": "traffic", "collection": "workspace2", "road_type": "four_way"},
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda i: search(str(i), variants[i % len(variants)]), range(200)))
    report = {
        "finished_at": datetime.now().isoformat(),
        "edge_cases": edges,
        "concurrent_200": {
            "count": len(results),
            "statuses": dict(Counter(str(item["status"]) for item in results)),
            "canceled": sum(item["canceled"] is True for item in results),
            "max_seconds": max(item["seconds"] for item in results),
            "errors": [item for item in results if item["status"] is None or item["status"] >= 500],
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORT", OUT.resolve(), flush=True)
    print("CONCURRENT", report["concurrent_200"], flush=True)


if __name__ == "__main__":
    main()
