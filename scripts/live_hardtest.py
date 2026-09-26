"""Read-only live API and resource smoke test for a running Vecna server."""

import concurrent.futures
import json
import statistics
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil
import requests


BASE = "http://127.0.0.1:6900"
OUT = Path("hardtest-results") / f"live-{datetime.now():%Y%m%d-%H%M%S}.json"
PORTS = {6900: "core", 1337: "search", 4200: "file"}
metrics = []
stop_monitor = threading.Event()


def gpu_used_mb():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return int(result.stdout.strip().splitlines()[0])
    except Exception:
        return None


def monitor():
    processes = {}
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr.port in PORTS and conn.pid:
            processes[conn.laddr.port] = psutil.Process(conn.pid)
    for proc in processes.values():
        proc.cpu_percent(None)
    while not stop_monitor.is_set():
        row = {"time": time.time(), "gpu_used_mb": gpu_used_mb(), "system_ram_percent": psutil.virtual_memory().percent}
        for port, name in PORTS.items():
            try:
                proc = processes[port]
                row[f"{name}_rss_mb"] = round(proc.memory_info().rss / 1048576, 1)
                row[f"{name}_cpu_percent"] = proc.cpu_percent(None)
            except (KeyError, psutil.NoSuchProcess):
                row[f"{name}_rss_mb"] = None
                row[f"{name}_cpu_percent"] = None
        metrics.append(row)
        stop_monitor.wait(1)


def get(path, params=None, timeout=90, base=BASE):
    started = time.perf_counter()
    try:
        response = requests.get(base + path, params=params, timeout=timeout)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return {"status": response.status_code, "seconds": round(time.perf_counter() - started, 3),
                "total": payload.get("total"), "canceled": payload.get("canceled"),
                "available": payload.get("available"), "error": payload.get("message") if response.status_code >= 400 else None}
    except Exception as exc:
        return {"status": None, "seconds": round(time.perf_counter() - started, 3), "error": str(exc)}


def summary(values):
    times = sorted(item["seconds"] for item in values)
    return {"count": len(values), "ok": sum(item["status"] == 200 for item in values),
            "p50_seconds": round(statistics.median(times), 3) if times else None,
            "p95_seconds": times[min(len(times) - 1, int(len(times) * 0.95))] if times else None,
            "max_seconds": max(times) if times else None}


def main():
    OUT.parent.mkdir(exist_ok=True)
    report = {"started_at": datetime.now().isoformat(), "health": {}, "search": {}, "map_load": {}, "transcripts": {}}
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    try:
        for port, name in PORTS.items():
            path = "/api/collections" if port == 6900 else "/api/health"
            report["health"][name] = get(path, base=f"http://127.0.0.1:{port}")
        cases = [
            ("batch1", {"q": "car", "collection": "workspace", "limit": 5}),
            ("batch2", {"q": "traffic", "collection": "workspace2", "limit": 5}),
            ("exact_phrase", {"q": '"xe hơi"', "collection": "workspace", "limit": 5, "ocr_weight": 0.5}),
            ("temporal", {"q": "car\nperson", "collection": "workspace", "limit": 5, "temporal_k": 20}),
            ("camera_filter", {"q": "traffic", "collection": "workspace2", "limit": 5, "road_type": "four_way"}),
        ]
        for name, params in cases:
            report["search"][name] = get("/api/search_multimodal", params=params)
            print(name, report["search"][name], flush=True)
            if report["search"][name]["status"] is None:
                break
        video_id = "L21_V001"
        path = f"/api/video/map-keyframes-around/{video_id}/25"
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: get(path, timeout=15), range(500)))
        report["map_load"] = summary(results)
        report["map_load"]["statuses"] = {str(status): sum(r["status"] == status for r in results) for status in set(r["status"] for r in results)}
        print("map_load", report["map_load"], flush=True)
        ids = [p.name for p in Path("features").iterdir() if p.is_dir()][:100]
        transcript_results = [get(f"/api/video/transcript/{video_id}", timeout=20) for video_id in ids]
        report["transcripts"] = summary(transcript_results)
        report["transcripts"]["statuses"] = {str(status): sum(r["status"] == status for r in transcript_results) for status in set(r["status"] for r in transcript_results)}
        print("transcripts", report["transcripts"], flush=True)
    finally:
        stop_monitor.set()
        monitor_thread.join(timeout=7)
        report["finished_at"] = datetime.now().isoformat()
        report["metrics"] = metrics
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("REPORT", OUT.resolve(), flush=True)


if __name__ == "__main__":
    main()
