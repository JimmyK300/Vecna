# Vecna #82 control provenance

The saved control is reproducible: 115 exact query identities/texts, 113
scoreable rows, exclusions `p0_q15` and `p3_q09`. `p2_q17` has no saved
candidates and remains in the denominator. All 18 source Git blobs are verified
against embedded immutable pins before any reference code is imported.

- Vecna main at inspection: `95d63a6abf10c598e0e54af7d2071bedbe542d1e`.
- Canonical truth projection ref: `f0b0f4707ceab91ba7e266f72fa982dce3ae1c4b` (PR #80).
- Dataset main at inspection: `1f1ad1baef1e1d31817f6c5a12d4d94133611038`.
- Canonical truth SHA-256: `63f80eb6ff54ef3c623f6ae4926eba404dac8bb5543b86e31f8fa0da842b4c9f`.
- Exact query-text SHA-256: `bd15d05f6c8f00597cced4f50914547ca0b3de75a9e57ee262a4f4ba292485aa`.

The canonical projection is rebuilt byte-for-byte from 78 historical rows and
the original 115-row identity/P3 ledger. Joining uses provenance-backed source
identity; exact query text is an additional check. Six historical TRAKE rows
retain submission-derived event proxies; 35 P3 rows retain provisional
source-text truth. Historical TRAKE is scored by strict all-events coverage;
P3 preserves its existing fractional event semantics.

Direct scoring of canonical truth and saved candidates reproduces every frozen
per-query control and the aggregates: baseline R@20 **68/113**, reranker
R@20 **76/113**; MRR@20 **0.4243397949150161 → 0.4320209888728889**.
The input pool is top100, while the reranker artifact stores only its top20.
Every one of the 2,280 saved reranker candidates maps to the same query's
baseline pool and recorded original rank. No new retrieval or inference runs.

Historical-manifest and comparison raw-checksum differences are fully explained
by CRLF versus LF. Reranker reconciliation is
`line_endings_only_host_lf_normalization_and_json_verified`. The archive copy and current dataset file share
Git blob `71b751c36cbf5cab6611b10ab5edf391ee078e0f`; the optional broker identity
record proves host LF-normalized bytes and canonical JSON equal the Git copy.
The older comparison's separate reranker checksum remains an unverified older
byte identity; its stored P3 metrics reproduce exactly and are not used as truth.

Local model snapshot/config observations are recorded separately from historical
package versions. Snapshot presence does not establish the model actually loaded
for a run, full weights, collection contents, current package versions, or disabled
query transformations. Packet A and Packet B must supply their own remaining
runtime/provider evidence. Their readiness does not block Packet C's saved-data
analysis. Local checkout HEADs never override pinned truth authority.

The optional #79 temporal control contains the same113 query identities but a
different baseline lineage: 78 frozen historical results plus35 P3-only results.
It is recorded separately in `baseline_lineage`; cached temporal scores cannot
be substituted for the current115-export control. Packet A needs a matched run;
exact frame-cache identity may permit reuse without claiming score parity.

Reproduce with `python code/preflight.py`; verify generated artifacts without
rewriting with `python code/preflight.py --check`. Run regression checks with
`python -m unittest discover -s tests -p test_preflight.py -v`.

All paths, hashes, model/config observations, readiness limits and source URLs are
in `control_manifest.json`. Source locations are relative to this experiment root.
