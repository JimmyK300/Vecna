# ASR-only reranker modality ablation

Parent is accepted v5, temporal5s admission plus protected-first text ranking.
Use exactly its 100 candidates, original query, model configuration and RRF60
rule, replacing combined OCR/ASR text with `ASR: ` plus stripped ASR text, or
empty. Preserve first frame and empty-text slots. No OCR fallback or query
specific selection. This complementary global ablation tests whether OCR adds
distracting context. It does not inherit rejected OCR-only rankings.

All 9878 inherited frame records are retained; 9224 have nonempty ASR. Source
hashes, queries, model configuration and exact score reuse identities are frozen
in policy.json. Only identical v5 query/frame/text/model scores may be reused.
CPU float32, batch2, threads8, max1024. No new extraction, embedding, model
download, corpus or index mutation. Two focused tests passed before launch.

Save rankings before scoring; 115 canonical queries, 113 scoreable, exclusions
p0_q15 and p3_q09. Preserve provisional/proxy qualifiers and all disagreement
evidence. Repeated benchmark, exploratory results without a holdout.

Source branch codex/issue-92-overnight-20260916, base
37b321048432ccba5182a66bd39b1ca73c547537. Uncommitted code; inherited dirty-state
caveat is documented in v1. Compute cutoff 2026-09-16T23:40Z; overall bound
23:50Z. A deadline stop is incomplete, not a scored benchmark result.

Reproduction requires a fresh versioned output directory because output writes
are exclusive. From the research worktree, using the existing Vecna venv:
```
python -X utf8 -B -m unittest discover -s benchmark-results/astra-overnight-issue92-v11/code -p test_frame_text.py -v
python -X utf8 -B benchmark-results/astra-overnight-issue92-v11/code/prepare.py
python -X utf8 -B benchmark-results/astra-overnight-issue92-v11/code/frame_text.py
```
Acceptance requires source/policy/cache hashes, exact ASR transformation,
independent ranking replay, 100-member and first-frame preservation, reuse
identity checks, 113-row rescoring, and comparisons against v5 and exact PR91.
