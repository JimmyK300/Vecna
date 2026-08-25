# Issue #60 corpus integrity audit (pointer)

Machine-readable integrity audit of the currently analyzed Vecna corpus
(collection `official_l21_l30_all_v2`, index generation
`idx_6baede5b9bc447e099c0004d8428ca7e`).

- Checker: `aic51-src/script/audit_corpus_issue60.py`
  (stdlib + numpy only, offline, strictly read-only against the corpus root;
  writes only into its `--output-dir`).
- Report bundle: `benchmark-results/issue60-corpus-audit/`
  - `issue60-audit-report.json` / `.md` - counts by category x status,
    provenance coverage, duplicates, hashes.
  - `flags.jsonl` - every flagged item with concrete path/ID + reason.
  - `foreign-artifacts-listing.jsonl` - full per-entry listing of
    foreign/unowned and legacy artifacts.
  - `per-video-stats.json` - frame/artifact counts for all 873 videos.
  - `manifest-hashes.json` - SHA-256 manifest of outputs + inputs.
  - `RERUN.md` - exact rerun command and determinism notes.

Determinism: reruns reproduce `report_content_sha256`
(`6c0e2ab56fb04db1ed625621d255d43af5942259c0d06407169d605eb03641b7`)
as long as the corpus is unchanged; sampling is deterministic (sorted IDs,
evenly spaced indices), wall-clock time is excluded from the digest.

Nothing in the audited corpus is modified, deleted, or rewritten by this
audit; flagged artifacts remain untouched by policy.
