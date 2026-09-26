# Issue #34 — current 115-query headless benchmark authority

This directory is the durable authority root for the current headless benchmark under `JimmyK300/Vecna#34`.

## Current corpus

The current query inventory is 115 rows: P0 24, P1 25, P2 30, P3 36.

The benchmark truth is intentionally composite rather than rewritten into a new source of truth:

- **P0–P2:** 78 frozen executable rows from `benchmark/headless-p0-p1-p2-v1@e0981b9022723f0a8bb20d4ccb108f725f4f2e50`, `benchmark-results/headless-vnext-p0-p1-p2-v1/manifest.json`.
- **P3:** 35 provisional scoreable rows from `official-dataset-control@a8c15b94e576ea1c8a0acfe20d816112692b2639`, current 115-row ledger.
- **Unscoreable current rows:** `p0_q15` and `p3_q09`.

Therefore the current validated join is **113 scoreable / 115 current queries**. This is the same inventory recorded by Issue #79.

## Truth tiers are not flattened

The frozen P0–P2 Headless vNext truth and the newer P3 source-text truth do not have identical provenance. A generated projection must preserve that distinction. In particular, P3 remains provisional source-text-verified development truth; it is not organizer gold.

`AUTHORITY.json` pins the exact repositories, commits, paths, blobs, counts, exclusions, and invariants. It is the machine-readable ownership contract.

## Generated projection

`aic51-src/script/build_issue34_current_115_truth.py` builds:

- `benchmark-results/issue34-current-115/ground_truth_current_115.jsonl`
- `benchmark-results/issue34-current-115/ground_truth_current_115.meta.json`

The builder joins the current 115 query namespace to the frozen 78-row Vecna manifest by normalized query text and fails closed unless all count and exclusion invariants hold. It does not invent missing truth.

Downstream repositories may mirror the generated projection, but Vecna Issue #34 remains the benchmark authority lineage and mirrors must pin the exact generated commit/blob.
