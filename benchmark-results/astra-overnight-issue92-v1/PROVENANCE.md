# Provenance and scoring contract

## Ancestry and workspace

Base/source commit: `37b321048432ccba5182a66bd39b1ca73c547537`.
Source branch: PR91 `btl/issue-82-failure-ledger-and-proposal`.
Research branch: `codex/issue-92-overnight-20260916`.
Worktree: `C:/Users/minhc/Code/Vecna-issue92-overnight`.
Research files are uncommitted; no remote research SHA or PR is claimed.

Dirty-state caveat: the fresh worktree contains an unattributed change to inherited
`outputs/synthesis/PUBLICATION_CHECKPOINT.json` (IN_PROGRESS to READY metadata).
Its contents/diff are preserved under `provenance/`; ownership was not established,
so it was not reverted or staged. This metadata is not a new scientific input.
Hydrated inherited raw rankings/study files are expected untracked reconstruction
artifacts and match their published hashes. Primary/friend worktrees were read
only. No parent/friend branch was reset, rebased, committed or written by this run.

## Frozen benchmark

115 canonical query IDs/texts;113 scored. Exclusions `p0_q15`, `p3_q09`.
No renumbering or truth/source-quality adjudication. Parent code and truth are
hash-bound by `control_manifest.json`; published ledger verifier checks49 inputs
and four byte-identical derived ledger files.

Raw provider rankings SHA256:
`d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82`.
Study SHA256:
`ba47bd96eb842d0bb57811e247cbd2ea29de8794c5dd3b289dce24a3032c10b1`.
Run identity:
`f0d32893564111064d47f6f2f72f7b03dbb14ebbfbb3d05c48e49e30ef165755`.

Exact query-ID joins, unique ordered frames, maximum100 frames, then first unique
video projection. Distinct-video R@1/5/10/20 and MRR@20 are separate from frame
position/video and frozen mixed frame/range/event scoring. Historical TRAKE and
P3 fractional/proxy semantics remain the inherited scorer's contract. Required
target coverage at100 is a candidate diagnostic, not official MRR.41 queries
retain provisional/proxy qualifications. This repeatedly inspected benchmark is
not a pristine holdout. Bootstrap10000/seed82 is descriptive paired uncertainty,
not evidence that adaptive family selection generalizes.

E1 changes admission only: cyclic qwen/siglip/ocr_sparse/asr_sparse, skip seen,
one unique frame/provider/turn up to100. Current whole-union fusion scores and
normalization remain unchanged; ties use exported order. Generic fusion sweeps
were not reopened. Semantic integrations use one fixed equal RRF60 rule per
representation, because the provider surface changed materially.

## Inputs and semantic changes

- Existing five-video segment map copied and hashed; unmapped frames remain
  singleton identities. Sparse coverage prevents corpus-wide claims.
- Semantic2956 records/873 videos snapshotted, unchanged. Tokenizer/BM25 source,
  FPS/frame catalog and deterministic interval midpoint mapping are archived.
  Underlying source records are hypotheses, not truth. No source text repair.
- Dense semantic representation is NEW offline inference over those2956 records
  and115 canonical queries, not an external corpus/index update. Cached BGE-M3
  snapshot, file hashes, AST source pin, loading checks and exhaustive active
  parameter comparison are in `outputs/semantic-dense/model_audit.json`.
  CPU float32, CLS/L2,1024-token limit,4/text batch,8 threads; no truncations.
- Grounding is one further frozen mapping interaction: maximum existing current
  fusion score within the semantic interval, original tie order, midpoint fallback.
  It uses no answer-conditioned mapping or new embeddings and is not promoted.
- YOLO inputs are existing detections;843 consumed source-file hashes and the
  actual label evidence are retained. Dictionary/applicability was query-only and
  frozen before scoring. No count or relation inference was asserted.
- Translation uses cached Helsinki vi-en snapshot
  `c8d2853e77f5fae31124d993e0b35176b1c8914e`, pinned consumed file hashes,
  CPU float32, deterministic4 beams/two outputs. Entire transformed query set
  saved before retrieval/scoring. Canonical route retained; no answer repairs.
- No model downloads, new image extraction, external index writes, truth edits,
  production-default changes or source-quality rewrites.

Ranking outputs are written before truth is opened by scoring. Diagnostic code
does inspect truth to attribute hits and compute ceilings; it never generates
deployable candidates. The semantic interval ceiling expands to thousands of
existing frames and is explicitly outside the100-frame budget. It is not an arm.

## Reproduction limits

The archive retains all derived rankings and query transformations needed to
re-score. It binds inherited inputs to exact local paths/hashes and Git ancestry.
Original YOLO binaries/model cache paths remain external and must match recorded
hashes for fresh inference/retrieval reproduction. Label snapshots suffice to audit
the performed boost; saved dense vectors suffice to repeat dense search. Mutable
external paths are not described as intrinsically immutable: their SHA256 gates
define the required identity. Missing files fail verification rather than being
silently replaced. See README for commands and `runtime.json` for package identity.
