# Benchmark status: FROZEN HISTORICAL INPUT

This branch is **not** the current complete headless benchmark.

It remains a frozen historical input to the current authority and should be preserved for provenance:
- P0/P1/P2 frozen benchmark lineage
- 78 historical scoreable rows consumed by the current 115-query authority
- pinned historical commit lineage beginning at `e0981b9022723f0a8bb20d4ccb108f725f4f2e50`

Current authority:
- PR #80
- branch `btl/issue-34-current-115-authority`
- 115 canonical queries, 113 scoreable
- exclusions: `p0_q15`, `p3_q09`

Do not add P3/current benchmark work here. Use this branch only when reproducing the frozen historical component or its provenance.
