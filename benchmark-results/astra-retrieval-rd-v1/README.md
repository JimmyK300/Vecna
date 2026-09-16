# Vecna retrieval R&D review

Start with [REPORT.md](REPORT.md) for the decisions, [PROVENANCE.md](PROVENANCE.md) for exact identities and comparison limits, and [REPRODUCE.md](REPRODUCE.md) to verify the published snapshot without models or retrieval.

- [Unified 113-query failure ledger](outputs/failure-ledger/failure_ledger.jsonl)
- [Failure counts, capability slices and source overlays](outputs/failure-ledger/summary.json)
- [Matched fusion results](outputs/fusion/evaluation/summary.json)
- [Saved-set candidate coverage](outputs/fusion/evaluation/coverage_headroom.json)
- [Worker return](BTL-RETURN.md)

The review preserves 115 canonical identities and 113 scoreable queries. Its 82 observed successes and 31 remaining misses form a diagnostic union across different captures, not a single deployable ranking system.

Review stack: [Packet0/C #83](https://github.com/JimmyK300/Vecna/pull/83), [B #84](https://github.com/JimmyK300/Vecna/pull/84), [A #85](https://github.com/JimmyK300/Vecna/pull/85), [source/visibility #87](https://github.com/JimmyK300/Vecna/pull/87), [Qwen checkpoint repair #88](https://github.com/JimmyK300/Vecna/pull/88), [deterministic text ties #90](https://github.com/JimmyK300/Vecna/pull/90), [native dataset #18](https://github.com/JimmyK300/official-dataset-control/pull/18). All remain draft and unmerged.
