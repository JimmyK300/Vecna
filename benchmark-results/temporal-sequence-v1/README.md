# Temporal sequence retrieval v1

Vecna issue #79: test whether query-only event decomposition plus ordered
sequence search recovers temporal signal from the existing frame-embedding
surface.

## Result

The experiment did not recover a temporal gain. On the eight-query live subset,
the saved baseline reached video R@20 `0.750`, independent-max reached `0.500`,
and ordered-chain reached `0.000`. The ordered arm therefore fails this
control; independent-max is not an improvement.

## Packet contents

- `REPORT.md` — concise report, metrics, caveats, and reproduction commands.
- `PROVENANCE.md` — source, input, runtime, contract, scoring, and evidence
  boundaries.
- `runner/temporal_sequence_v1.py` — exact runnable copy used for the archive.
- `control_113.jsonl`, `decompositions_113.jsonl` — frozen control and
  auditable query-only event decompositions.
- `event_rankings.jsonl`, `scored_variants.jsonl`, `mapping_ledger.jsonl` —
  live evidence, arm outputs, and query/event mapping.
- `*_manifest.json`, `surface_parity.json` — run and retrieval-surface
  provenance.
- `SHA256SUMS.txt` — hashes for the packet's non-self-referential files.

This is an experiment archive only: no new video model, full-corpus
re-embedding, or production retrieval rewrite.
