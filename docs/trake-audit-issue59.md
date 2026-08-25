# TRAKE exact-event audit (Issue #59)

Read-only diagnosis of why the stack misses exact TRAKE event timing despite
video-level retrieval success. Full report and evidence:

- Report: [`../benchmark-results/issue59-trake-audit/REPORT.md`](../benchmark-results/issue59-trake-audit/REPORT.md)
- Per-query evidence (k=1000 exposure): `../benchmark-results/issue59-trake-audit/trake-audit.jsonl`
- Keyframe density around gold points: `../benchmark-results/issue59-trake-audit/keyframe-density.json`
- Mechanism counts: `../benchmark-results/issue59-trake-audit/mechanism-counts.json`
- Run provenance + incidents: `../benchmark-results/issue59-trake-audit/audit.launcher.json`

Headline: video-level R@20 = 3/3 (pinned sweep) but exact-event recall@20 is
1–3 of 12 events; even at k=1000 only 6/12 events ever surface. Dominant
mechanisms: multi-event paragraphs embedded as one vector (temporal path
unreachable — parser splits only on `/`), OCR/ASR sparse fusion inverting
visual rankings with transcript junk, near-duplicate-video crowding, and
duplicate slot flooding. Frame sampling ruled out at ±2 s tolerance (max
gold-to-indexed-frame distance 0.97 s). No retrieval code, config, or index
was changed by this audit.
