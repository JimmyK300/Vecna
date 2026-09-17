# Vecna92 bounded overnight research v1

Start: 2026-09-16 15:50 UTC. Hard research deadline: 23:50 UTC. Fresh branch
`codex/issue-92-overnight-20260916`, based on PR91 commit
`37b321048432ccba5182a66bd39b1ca73c547537`, not main.

Read `OVERNIGHT_RETURN.md`, `METRICS.md`, `arms.json`, and `PROVENANCE.md`.
The selected architecture remains the exact PR91 current-fusion control.
No production merge, benchmark edit, model download, or external index write.

## Evidence map

- `control_manifest.json`: inherited input identities, exclusions and run identity.
- `config.json`, `*_policy.json`, `architecture_policy.json`: frozen rules.
- `outputs/packet-e`:100-frame provider-balanced membership, unchanged fusion.
- `outputs/segment-v2`: valid sparse-map segment experiment. `outputs/segment`
  is an INVALID zero-padded string/integer lookup attempt, retained but excluded.
- `outputs/reranker-compatibility`: missing matched saved-score evidence; no
  invented scores and no emulated full-benchmark reranker claim.
- `outputs/semantic*`: existing semantic records, lexical/dense providers,
  fixed integrations, interval ceiling and one score-guided grounding interaction.
- `outputs/yolo`: existing object-label boost, frozen applicability and labels.
- `outputs/query-variants`: lexical transforms; these are NOT paraphrases.
- `outputs/query-translation`: canonical plus two deterministic alternate English
  translations. These are cross-language reformulations, not Vietnamese paraphrases.
- `outputs/diagnostics-v2`: authoritative12-arm re-scoring,113 paired queries per
  arm,20/50/100-frame coverage/diversity, inherited capability/phase/task/truth
  slices, failure classes and600 new useful E1 frames with provider attribution.
  `diagnostics-v1` is the preceding10-arm checkpoint, preserved unchanged.
- `reports/`: exact paired R@K/MRR deltas and rescue/regression IDs per arm.
- `usage_report.json`: actual own-thread harness counters, with scope caveats.
- `ARCHIVE_MANIFEST.json`: SHA256/bytes for the archived snapshot. Operational
  checkpoint/job spec and later closing artifacts have separate identities.

## Reproduce acceptance from saved evidence

Use the original Windows Python3.12 runtime (paths here are absolute so missing
external dependencies fail clearly):

```powershell
Set-Location C:/Users/minhc/Code/Vecna-issue92-overnight
C:/Users/minhc/Code/Vecna/.venv/Scripts/python.exe -X utf8 -B benchmark-results/astra-overnight-issue92-v1/code/archive.py verify --output C:/absolute/new-verification.json
C:/Users/minhc/Code/Vecna/.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v1/code -p 'test_*.py'
```

The verifier hashes the archive and parent inputs, rebuilds the inherited ledger
byte-for-byte and recomputes all12 arms' saved scores. It makes no model or
retrieval calls. Output must be a new path. The inherited verifier restores the
published timing sidecar; exact Python/libm identity matters.

## Generation commands and immutable output discipline

All scripts live in `code/` and were run using the interpreter above with
`-X utf8 -B`. Order:

1. `evaluate_e.py`
2. `segment.py`, `reranker_audit.py`
3. `semantic.py`, `yolo.py`, `query_variants.py`
4. `semantic_dense.py`
5. `query_translation.py`
6. `semantic_ceiling.py`, `semantic_grounding.py`
7. `diagnostics.py`, `archive.py report`, `archive.py manifest`, `archive.py verify`

These original generation scripts deliberately refuse existing result paths.
Do not rerun them inside this archive. For a new generation, create a new sibling
research directory/worktree, copy the frozen code/policies, explicitly rebind
absolute input paths to the same hash-verified files and select empty output
directories. Record that new configuration identity. Do not delete these outputs
to make a script run. Saved rankings plus the acceptance verifier are the simplest
reproduction path; not every original mutable external source is bundled.

Dense inference used one cached BGE model,2956 semantic documents and115 queries,
with768 independently hash-bound batches. Batch metadata permits recovery of a
partial computation only; completed jobs must not be relaunched. Translation
generation has115 saved query-only outputs and requires no regeneration to score.

The terminal callback verifies process completion separately from scientific
acceptance. Long jobs use the installed overnight-jobs completion transport;
there is no recurring model polling. `transport/` stores accepted job metadata.
