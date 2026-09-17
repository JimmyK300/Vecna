# Vecna92 measurement checkpoint

**Packet E: NEGATIVE. Strongest supported architecture: unchanged PR91 control.**
This packet is prepared before the23:50 UTC bound; final run closure awaits the
single closing integrity audit. No quota exhaustion or eight-hour active compute
claim is made. A later closing return records the actual end state.

E1 changes100-frame admission while preserving fusion scores. Video R@20 falls
87->83/113 (zero rescues, four regressions: p1_q25,p2_q25,p3_q19,p3_q34).
MRR20 increases0.5299890165650186->0.533912228381255, but complete-target pools
fall78->71 (two rescues, nine regressions), and fractional coverage
0.6991150442477876->0.6349557522123894. R20 paired95%CI is
[-0.07079646017699115,-0.008849557522123894]. E1 is not promoted.

Mean distinct videos within100 slots falls34.6283->27.5664; repeated-video slot
fraction rises0.65372->0.72434. This is concentration, not proof every repeated
video frame is redundant.600 newly admitted useful frames are attributed to the
actual admitting provider and all supplying providers in diagnostics-v2.

## Completed families

- Segment dedup: INCONCLUSIVE. Existing map covers five videos/3365 frames;
  video metrics unchanged. Numeric frame normalization corrected an invalid first
  implementation, preserved separately. No full-corpus dedup conclusion.
- Saved reranker integration: INCONCLUSIVE/not executed. Zero identical ordered
  current/historical pools; only two queries have all current top10 scores and
  zero have all top20. No censored score was invented.
- Semantic BM25: unique video contribution exists, but integrationR20=84/113,
  MRR=.483334478871. NEGATIVE; coverage-positive ranking unresolved.
- Existing YOLO boost: R20 remains87, R1=50 vs49 and MRR=.537068662583.
  INCONCLUSIVE under the frozen promotion gate; only five queries actually boosted.
  MRR delta95%CI[-.00324484,.02359882]; no confident end-to-end improvement.
- Lexical query transforms: R20=83, MRR=.489140467764; NEGATIVE. They are not
  paraphrases. Additional canonical+two alternate English translations produce
  R20=80, MRR=.469376181687; NEGATIVE, zero fallback queries.
- Cached multilingual dense semantic representation: integrationR20=88,
  MRR=.472808896956, complete-target pools74. NEGATIVE despite video-pool
  coverage92->96. Exactly one new long embedding job; no download.
- One semantic-to-frame grounding interaction: integrationR20=89,
  MRR=.468521607764, complete-target pools75. R20 five rescues/three regressions,
  CI[-.02654867,.07079646]. NEGATIVE under the gate; not selected by cherry-pickingR20.

Full R1/5/10/20/MRR and target counts: METRICS.md. Exact deltas, all rescues and
regressions, three scoring layers, overlapping capability/phase/task/truth slices:
arms.json, reports/, outputs/diagnostics-v2/.12 scored arms,1356 paired rows.

## Bottleneck and limits

The retained parent pool has21 candidate-absent video misses and five cases with
the video present outside the top20. Candidate generation remains the larger
video bottleneck. Dense semantic integration changes these to17 and eight:
new video evidence helps coverage but can displace early correct results.

Scoring-only dense interval ceiling contains complete targets for73 queries,
versus23 midpoint representatives. It expands to a mean16639 frames/query and
cannot be called a100-frame win. Score-guided grounding raises standalone target
coverage to42, but does not solve final ranking. Broad semantic intervals may
contain targets by coincidence; this does not establish precise semantic grounding.

Benchmark adaptive reuse,41 provisional/proxy qualifications, sparse shot/object
coverage, unresolved historical encoder/index lineage and local contention limit
generalization. No production speed claims. Follow-up should use a genuinely
independent evaluation and a representation/localization hypothesis, not another
weight grid on these answers.

## Usage and work location

Actual own-thread model is gpt-6-astra. Harness cumulative/delta counters and
observed quota fields are in usage_report.json; cached context is explicitly
separated. Counters are not dollar cost or inferred from elapsed time. No hard
quota error observed at this checkpoint. Notifications resumed the semantic,
dense and translation jobs; no recurring status polling occurred while waiting.

BGE:3071 texts,768 batches,339940 cosine pairs,690.2674s same-session encoding.
Translation:115 generation calls,342 BM25 routes,161.6049s generation. These
timings are not comparable production benchmarks; stable workloads are primary.

Branch `codex/issue-92-overnight-20260916` in
`C:/Users/minhc/Code/Vecna-issue92-overnight`, research directory
`benchmark-results/astra-overnight-issue92-v1`. Files remain uncommitted; no push,
remote SHA, draft PR or production merge is claimed. Parent commit and input
hashes are in PROVENANCE.md/control_manifest.json. ARCHIVE_MANIFEST.json binds
the final measurement snapshot; validation logs and closing audit carry proof.

No truth changes, friend/parent branch writes or external index mutations.
An unattributed parent checkpoint metadata diff is preserved, not staged/reverted.
The measurement packet is reviewable; overall overnight closure is pending the
deadline audit. No further combinations are queued because none met the frozen
promotion rule, and the declared tiny families and single grounding interaction
have been exhausted.
