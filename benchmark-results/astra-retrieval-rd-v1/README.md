# Astra retrieval R&D — Packet 0 and C

Research artifacts for Vecna #82. Production code is unchanged.

Packet 0 freezes the exact 115-query surface, 113 scoreable IDs and saved source blobs. Packet C reproduces the saved Qwen/reranker controls and provides per-query, capability, candidate-ceiling and latency evidence.

Run from this directory:

```bash
python code/preflight.py --check
python -m unittest discover -s tests -v
python code/analyze_reranker.py --help
```

See `outputs/control_manifest.json`, `outputs/PROVENANCE.md`, and `outputs/reranker/REPORT.md`. Later packets remain separately bounded work; this checkpoint does not claim their completion. No main merge is authorized.
