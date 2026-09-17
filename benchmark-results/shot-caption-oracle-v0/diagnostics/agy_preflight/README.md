# AGY CLI Capability Preflight Diagnostics

Tracker: `JimmyK300/Vecna#95`

## Purpose

Verify whether the authenticated Antigravity CLI (`agy`) can serve as a headless captioning driver for the frozen Issue #95 shot-caption oracle experiment in place of the quota-exhausted Google GenAI API route.

## Experiment Requirements vs. AGY Observed Capabilities

| Requirement | Experiment Specification | AGY CLI Observed Capability | Verdict |
| :--- | :--- | :--- | :--- |
| **Model** | `gemini-3.8-flash` | `gemini-3.8-flash-high` available in `agy models` | **PASS** |
| **Media Input** | Native multimodal video container ingestion | Headless stream input (`stream-json`) only supports `"text"` blocks; rejects `"video"` with `stream input content block type "video" is not supported (only "text")` | **FAIL** |
| **Video Sampling** | Static sampling at 4.0 fps | No CLI flags or configuration parameters for video sampling rate or static mode | **FAIL** |
| **Resolution** | `resolution: high` | No CLI flags or parameters for video input resolution | **FAIL** |
| **Audio Handling** | Direct container audio track processing | No headless audio track ingestion mechanism | **FAIL** |
| **Harness Context** | Isolated zero-shot context containing ONLY the frozen generic prompt and neutral media (no query leakage or prompt pollution) | Full agent scaffolding boots: injects 57 tools, system instructions, and >17,000 prompt tokens per turn | **FAIL** |

## Artifacts in this Directory

1. `probe_agy_capabilities.py`: Automated reproducible probe verifying CLI flags, model list, text streaming, non-text block rejection, and Go binary inspection.
2. `agy_preflight_evidence.json`: Machine-readable execution output capturing exact stdout, stderr, return codes, binary string offsets, and token consumption metrics.

## Conclusion

AGY CLI headless mode does not possess native multimodal video ingestion, static 4 fps sampling, high-resolution configuration, or unpolluted zero-shot completion semantics. Per instructions in `worker-prompt.txt`, execution stops at the capability gate with `NEEDS_DECISION` without silently switching to unsupported workarounds (e.g. frame montages, lower fps, audio omission, or tool-based file inspection).
