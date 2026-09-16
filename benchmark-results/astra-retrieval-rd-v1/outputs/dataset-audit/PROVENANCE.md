# Provenance

Authority: JimmyK300/Vecna#34 PR80 lineage, canonical projection pinned by inputs/canonical_truth.meta.json; supporting work: official-dataset-control#16 and #17. Exact remote source repository/path/commit/blob identities remain in inputs/sources.json.

Canonical SHA-256: `63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f`.

Frozen sample SHA-256: `b4fd944228a033c37ea4d69ad757ceeae9635bfb026cf018e0d60f5b3c661be9`.

The sample reads only the explicit query-side metadata allowlist. Historical target-video and result columns are ignored. Saved visual Qwen/reranker scores are supplied by outputs/control-reproduction/per_query_scores.jsonl after selection. No live retrieval, model execution, source transcription, truth proposal, or canonical mutation occurs.

Run: `python code/dataset_audit.py --root .`

SHA256SUMS.txt binds every generated artifact except itself. run_manifest.json records code, input, and saved-score hashes. Generation contains no wall-clock timestamp or absolute runtime paths, so repeated runs over identical inputs produce identical bytes.

## Later audit stages

The text above describes preparation. Four replay stages now preserve all 38 bounded text inspections, 20 directly viewed source frames, 18 captured-but-unheard WAVs, and 38 channel-row host parity checks. Capture manifests retain original timestamps, source file size/mtime, ffprobe, exact source paths and asset hashes; whole source-video hashes and historical extraction sidecars are unavailable. sample_provenance_bridge.json proves that the original/current sample SHA delta changes only appended source-registry provenance. The fourth stage verifies all remaining source identities and replays the recorded observations without generating new source interpretations. Run all four stages in the order documented in SOURCE_HYDRATION.md.
