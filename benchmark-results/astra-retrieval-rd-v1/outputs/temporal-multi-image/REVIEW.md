# Independent Packet A review

Decision: **`POSITIVE_TEMPORAL_SIGNAL`, restricted to exploratory correct-video ranking.** The independent reviewer read the exact A5 gate in `reference/issue82.md`, inspected the complete artifacts, and agreed that its allowance for meaningful ranking gains applies.

- Native3 promotes the accepted video on both informative queries. `p0_q23` moves from original baseline, matched center and sheet rank 2 to rank 1. `p3_q34` moves from original baseline/center rank 2 and sheet rank 3 to rank 1.
- Native3's winning score margins are about 0.015 and 0.023. These are clear model-score separations, not a statistical generalization claim.
- Six queries lack the accepted video in their top-three pool. No regression is observed, but the remaining rows cannot establish broad ranking robustness.
- None of 31 provisional event targets appears among the sampled frames. Localization remains unassessed; zero localization scores do not establish a negative model result.
- Distinct ordered input delivery was verified. No reversed or shuffled image control establishes that chronological order caused the ranking gain.
- Native3 and sheet means are both approximately three seconds per candidate. Possible concurrent load and the fixed arm order limit relative-speed interpretation.

The reviewer confirmed that query and image JSONL bytes and sizes exactly match the Windows manifest. No newline conversion was required. The scoring driver now normalizes Windows path separators when verifying recovered artifact basenames; encoder behavior was not changed.

Validation: 20 matched-run/scorer tests and 11 audit tests pass. Tests cover complete 8-query/72-image pairing, stale and duplicate inputs, source identity through the `p3_q34` rank swap, model-free planning, strict historical TRAKE versus fractional P3 scoring, separate center/window scoring, successful offline scoring of the Windows artifacts, and exact PTS coverage for all 72 sampled frames.

The review supports retaining native3 for the next separately frozen candidate-pool experiment. It does not support a production promotion, a localization claim, or an automatic new video model.
