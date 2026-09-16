# Dataset issue preparation

Canonical identity reproduces 115 rows, 113 scoreable, with p0_q15 and p3_q09 still excluded. The eight temporal controls preserve their existing event points, source provenance, and separate row/event truth tiers. All source-motion review remains pending.

| Query | Stored event frames | Mechanical flags |
|---|---|---|
| p0_q22 | 4707, 5139, 5427, 5865 | none |
| p0_q23 | 15945, 16006, 16354, 16901 | none |
| p0_q24 | 2466, 3133, 3420, 3800 | repeated_event_label_in_canonical_query |
| p1_q25 | 9785, 10135, 10191 | none |
| p2_q29 | 3793, 3870, 4014, 4098 | provenance_anchor_list_differs_from_event_truth |
| p2_q30 | 2076, 2129, 2168, 2228 | provenance_anchor_list_differs_from_event_truth |
| p3_q21 | 3260, 3766, 4788, 6730 | none |
| p3_q34 | 9900, 10218, 10330, 10576 | none |

The P2 provenance/event arrays disagree; inspect the exact source CSV and its version before correcting either list. The repeated E2 label in p0_q24 is preserved verbatim. P3 canonical truth contains point groups; this packet does not manufacture event intervals or import null-endpoint ranges from older experiment projections.

The 15-second contexts in temporal_evidence_requests.jsonl are inspection windows only. Verify actual FPS/timebase before converting frame anchors into times. For motion-defined events, inspect transitions and event order; do not promote a still or a scoring proxy into an interval.

The OCR/ASR sample is frozen using canonical source identity and query-side capability tags, stratified by phase, task, and combined text-channel status. Current display ordinals are not used as organizer ordinals. Baseline outcomes are attached only after selection. No extraction or ranking cause has yet been diagnosed.

## Later audit stages

The preparation notes above are followed by complete stored-text inspection and one directly inspected representative source frame for each of the 20 OCR queries. All 18 bounded ASR excerpts are captured but unheard because audio input is unsupported. Five exact sampled OCR anchors lose visible query-critical writing at or before persisted features. All 38 host metadata comparisons and 61 feature-text comparisons pass; native sidecars checked for all cases are absent. Source readability, structural relationships and full temporal obligations retain their per-row limits. All truth remains unchanged. See SOURCE_MEDIA_REVIEW.md and reviewed_audit.jsonl for the combined current state.
