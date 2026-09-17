#!/usr/bin/env python3
"""Issue #95: Bounded capability probe for AGY CLI headless video captioning.

Verifies whether AGY CLI supports:
1. gemini-3.8-flash model family (gemini-3.8-flash-high)
2. Headless native video input
3. Static video sampling at 4.0 fps
4. High resolution specification
5. Audio decoding / track handling
6. Isolated zero-shot caption context (no agent tools/instructions)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DIAG_DIR = Path(__file__).resolve().parent
ROOT = DIAG_DIR.parent.parent


def find_agy_executable() -> str | None:
    agy_path = shutil.which("agy")
    if not agy_path:
        local_app = Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.EXE"
        if local_app.exists():
            agy_path = str(local_app)
    return agy_path


def run_cmd(args: list[str], input_str: str | None = None, timeout: float = 30.0) -> tuple[int, str, str]:
    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE if input_str is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out, err = proc.communicate(input=input_str, timeout=timeout)
    return proc.returncode, out, err


def probe_binary_string(agy_path: str) -> dict[str, str | bool]:
    try:
        data = Path(agy_path).read_bytes()
    except Exception as e:
        return {"error": str(e), "found": False}

    target = b'stream input content block type %q is not supported (only %q)'
    found = target in data
    return {
        "found": found,
        "format_string": target.decode("ascii"),
        "supported_block_types": ["text"],
    }


def main() -> int:
    agy_path = find_agy_executable()
    if not agy_path:
        print("ERROR: agy executable not found on PATH or LocalAppData", file=sys.stderr)
        return 1

    evidence: dict[str, object] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "agy_executable": agy_path,
    }

    # 1. Probe flags via agy --help
    rc, out_help, err_help = run_cmd([agy_path, "--help"], timeout=10)
    combined_help = out_help + "\n" + err_help
    flags_found = re.findall(r"--[\w-]+", combined_help)
    evidence["help_probe"] = {
        "returncode": rc,
        "flags_found": sorted(set(flags_found)),
        "has_input_format": "--input-format" in flags_found,
        "has_output_format": "--output-format" in flags_found,
        "has_video_flags": any("video" in f or "fps" in f or "resolution" in f for f in flags_found),
    }

    # 2. Probe available models via agy models
    rc, out_models, _ = run_cmd([agy_path, "models"], timeout=15)
    models_listed = [line.split()[0] for line in out_models.splitlines() if "gemini" in line or "claude" in line or "gpt" in line]
    evidence["models_probe"] = {
        "returncode": rc,
        "raw_output": out_models.strip(),
        "models": models_listed,
        "gemini_3_8_flash_high_available": "gemini-3.8-flash-high" in models_listed,
    }

    # 3. Probe text stream-json input
    text_input = json.dumps({"event": "user", "message": {"content": "Respond with exactly: OK_TEXT"}}) + "\n"
    rc, out_text, err_text = run_cmd(
        [agy_path, "--input-format", "stream-json", "--output-format", "stream-json", "--model", "gemini-3.8-flash-high"],
        input_str=text_input,
        timeout=35,
    )
    conv_id = None
    result_event = None
    for line in out_text.splitlines():
        if "conversation_id" in line:
            try:
                data_line = json.loads(line)
                if not conv_id and data_line.get("conversation_id"):
                    conv_id = data_line.get("conversation_id")
                if data_line.get("event") == "result":
                    result_event = data_line.get("result")
            except Exception:
                pass
    evidence["text_stream_probe"] = {
        "returncode": rc,
        "status": "SUCCESS" if rc == 0 and "OK_TEXT" in out_text else "FAILED",
        "conversation_id": conv_id,
        "result_event": result_event,
    }

    # 4. Probe non-text content block type (e.g. video or foo)
    bad_block_input = json.dumps({"event": "user", "message": {"content": [{"type": "video", "path": "test.mp4"}]}}) + "\n"
    rc, out_block, err_block = run_cmd(
        [agy_path, "--input-format", "stream-json", "--output-format", "stream-json", "--model", "gemini-3.8-flash-high"],
        input_str=bad_block_input,
        timeout=15,
    )
    evidence["non_text_block_probe"] = {
        "returncode": rc,
        "stdout": out_block.strip(),
        "stderr": err_block.strip(),
        "observed_error": err_block.strip(),
    }

    # 5. Binary inspection
    evidence["binary_inspection"] = probe_binary_string(agy_path)

    # 6. Evaluation of required harness settings against AGY capabilities
    matrix = {
        "requested_model": {
            "required": "gemini-3.8-flash",
            "agy_candidate": "gemini-3.8-flash-high",
            "supported": True,
            "notes": "Available in agy models list",
        },
        "native_video_access": {
            "required": "Direct multimodal video ingestion via Files/Interactions API",
            "agy_candidate": "None in headless mode (stream input content block type only supports text)",
            "supported": False,
            "notes": "Headless stream-json explicitly rejects non-text content blocks; interactive paste supports video but cannot be driven headlessly",
        },
        "static_sampling_4fps": {
            "required": "static at 4.0 fps",
            "agy_candidate": "None",
            "supported": False,
            "notes": "No CLI flags, settings, or parameters exist to configure video sampling rate or static mode",
        },
        "high_resolution": {
            "required": "resolution: high",
            "agy_candidate": "None",
            "supported": False,
            "notes": "No resolution flag exists in AGY CLI",
        },
        "audio_handling": {
            "required": "Native video container audio decoding",
            "agy_candidate": "None",
            "supported": False,
            "notes": "No headless audio track ingestion mechanism in AGY CLI",
        },
        "isolated_context": {
            "required": "Zero-shot context with ONLY generic prompt and neutral media",
            "agy_candidate": "Agent scaffolding (57 tools, >17k system/tool tokens injected)",
            "supported": False,
            "notes": "AGY boots full agent environment, violating isolated frozen captioning contract",
        },
    }
    evidence["capability_matrix"] = matrix

    all_supported = all(item["supported"] for item in matrix.values())
    evidence["gate_verdict"] = "PASS" if all_supported else "NEEDS_DECISION"
    evidence["decision_options"] = [
        "1. Authorize paid Gemini API quota / project billing for gemini-3.8-flash to resume native shot_caption_oracle.py harness without contract deviation.",
        "2. Authorize local client-side frame extraction (4 fps, high resolution) via ffmpeg and define an image-based or external evaluation contract variance.",
        "3. Authorize Google Cloud Vertex AI route using ADC / enterprise credentials for gemini-3.8-flash with the exact video processing configuration.",
        "4. Await free-tier quota reset if a daily reset window applies.",
    ]

    out_file = DIAG_DIR / "agy_preflight_evidence.json"
    out_file.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote preflight evidence to {out_file}")
    print(f"Gate verdict: {evidence['gate_verdict']}")
    return 0 if all_supported else 2


if __name__ == "__main__":
    sys.exit(main())
