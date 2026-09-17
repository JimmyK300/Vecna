#!/usr/bin/env python3
"""Create a secret-free, hash-bound manifest for the Issue #95 run archive."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def included_files() -> list[Path]:
    excluded = {"run_manifest.json", "SHA256SUMS.txt"}
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name in excluded or "__pycache__" in path.parts or path.suffix.lower() == ".mp4":
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def main() -> int:
    manifest_rows = read_jsonl(ROOT / "oracle_manifest.jsonl")
    clip_rows = read_jsonl(ROOT / "clips" / "clips.jsonl")
    caption_rows = []
    for path in sorted((ROOT / "captions").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        caption_rows.append((path.name, row))
    successful = {(r.get("query_id"), r.get("prompt_family"), r.get("cache_key")) for _, r in caption_rows if r.get("status") == "ok"}
    errors = [{"file": name, "query_id": r.get("query_id"), "prompt_family": r.get("prompt_family"), "error_type": r.get("error_type"), "error": r.get("error"), "attempt_count": len(r.get("attempt_errors", []))} for name, r in caption_rows if r.get("status") == "error"]
    inventory = [{"path": p.relative_to(ROOT).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)} for p in included_files()]
    run = {
        "schema": "shot-caption-oracle-run-manifest-v0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tracker": "JimmyK300/Vecna#95",
        "git": {"branch": git("branch", "--show-current"), "head": git("rev-parse", "HEAD")},
        "authority": {
            "truth_sha256": sha256(ROOT.parent / "issue34-current-115" / "ground_truth_current_115.jsonl"),
            "decomposition_commit": "1f1ad1baef1e1d31817f6c5a12d4d94133611038",
            "decomposition_blob": "caf0a7b30a275b9ed47cab354fbb21bda00bf899",
            "decomposition_sha256": sha256(ROOT / "evaluation_inputs" / "decompositions_113.jsonl"),
        },
        "frozen_caption_config": json.loads((ROOT / "pilot_config.json").read_text(encoding="utf-8"))["caption_processing"],
        "environment": {"python": platform.python_version(), "google_genai": "2.24.0", "ffmpeg": clip_rows[0]["ffmpeg"] if clip_rows else None},
        "commands": [
            "python benchmark-results/shot-caption-oracle-v0/code/shot_caption_oracle.py build-manifest",
            "python benchmark-results/shot-caption-oracle-v0/code/shot_caption_oracle.py extract-clips --dataset-root D:\\Official-Dataset",
            ".\\.venv-issue95\\Scripts\\python.exe benchmark-results/shot-caption-oracle-v0/code/shot_caption_oracle.py caption --prompt all --model gemini-3.8-flash --fps 4 --resolution high --stop-on-error",
        ],
        "stages": {
            "manifest": {"pilot_count": len(manifest_rows), "eligible_count": sum(bool(r.get("eligible")) for r in manifest_rows), "ineligible": {r["query_id"]: r.get("eligibility_reason") for r in manifest_rows if not r.get("eligible")}},
            "clips": {"count": len(clip_rows), "unique_clip_sha256": len({r["clip_sha256"] for r in clip_rows}), "unique_source_sha256": len({r["source_sha256"] for r in clip_rows}), "total_bytes": sum(r["clip_size"] for r in clip_rows)},
            "captions": {"planned": sum(bool(r.get("eligible")) for r in manifest_rows) * 3, "successful_unique_cache_entries": len(successful), "error_record_count": len(errors), "errors": errors},
            "evaluation": {"status": "not_started_incomplete_caption_freeze"},
        },
        "stop_condition": "current Gemini account quota rejects remaining gemini-3.8-flash interactions with HTTP 429 free-tier request limit 20",
        "resume_command": ".\\.venv-issue95\\Scripts\\python.exe benchmark-results/shot-caption-oracle-v0/code/shot_caption_oracle.py caption --prompt all --model gemini-3.8-flash --fps 4 --resolution high --stop-on-error",
        "artifact_inventory": inventory,
    }
    (ROOT / "run_manifest.json").write_text(json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum_lines = [f"{item['sha256']}  {item['path']}" for item in inventory]
    checksum_lines.append(f"{sha256(ROOT / 'run_manifest.json')}  run_manifest.json")
    (ROOT / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(json.dumps({"artifacts": len(inventory) + 1, "successful_captions": len(successful), "errors": len(errors)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
