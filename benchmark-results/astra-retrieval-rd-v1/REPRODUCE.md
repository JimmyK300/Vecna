# Reproduce the published Vecna82 ledger

The review snapshot contains every consumed small input and the lossless B capture archive. The large B study is reconstructed from the capture plus its 9,301-byte timing sidecar. No model, database, retrieval request, package installation or expiring Actions download is needed.

Use the recorded **Windows Python 3.12.1** runtime for exact study and output bytes. All commands below run from `benchmark-results/astra-retrieval-rd-v1` in a separate checkout of this review branch. The scoped `.gitattributes` disables automatic line-ending conversion: committed LF inputs and original CRLF outputs must retain their exact hashes.

```sh
python -B code/verify_published_ledger.py --root .
```

This command verifies and hydrates the 27,146,363-byte raw capture, reconstructs the exact saved study if absent, checks all 49 ledger input hashes plus the generator hash, generates a complete ledger in a temporary directory, and compares all four outputs byte for byte with the published snapshot. Existing raw/study files must match their recorded hashes. The original committed outputs are preserved.

For individual restoration steps:

```sh
python -B code/hydrate_fusion_capture.py --root .
python -B code/fusion_study_storage.py rebuild --rankings outputs/fusion/capture-full115-v1/provider_rankings.jsonl --config outputs/fusion/frozen_config.json --queries outputs/fusion/queries.jsonl --collection-manifest outputs/fusion/capture-full115-v1/collection_manifest.json --sidecar outputs/fusion/evaluation/study_timings.json --sidecar-sha256 6af4e2a4fbd7095e3bdd4461485f9a9e6f03792fb34dbfd3218e09a5c7236fcf --output outputs/fusion/evaluation/study_results.jsonl
python -B code/build_failure_ledger.py --root . --require-complete --out-dir outputs/failure-ledger-replay
```

The rebuild command requires an absent study output. The source study SHA-256 must be `ba47bd96eb842d0bb57811e247cbd2ea29de8794c5dd3b289dce24a3032c10b1`. Any Python/platform/libm difference that changes a non-timing value fails the complete file SHA check; do not weaken that gate.

The 40 fusion/recovery/storage tests and 27 ledger tests are:

```sh
python -B -m unittest discover -s tests -p "test_fusion*.py" -v
python -B -m unittest discover -s tests -p "test_*ledger.py" -v
```

The original host had the optional Milvus protobuf path installed and passed all 40 fusion tests. An environment lacking that optional package can skip its wire-format probe; it does not need a model or database connection. The full recorded host results are in `outputs/synthesis/final-analysis-v1/logs/`.

To deliberately create a separate timing generation, use `hydrate_fusion_capture.py --replay-outdir outputs/fusion/replay-new`. That path must be fresh. It verifies every saved query/arm rank, coverage value and frozen score against the compact reference. Its new study/summary identity must not be mixed with the existing ledger snapshot.

The independent D reviewer is available as `code/review_failure_ledger.js`, with its saved result under `outputs/synthesis/independent_d_review.json`. It checks schema, historical/fresh separation, all observed pool records, source overlays and the 82/31 success union against separately recovered references.

Packet E remains a proposal in `outputs/synthesis/PROPOSAL.md` and `outputs/synthesis/decision.json`. Reproduction commands do not construct that candidate-admission arm.

The published Git snapshot was independently verified on the recorded Windows runtime: see [published-snapshot-verification.json](outputs/synthesis/published-snapshot-verification.json). The final proof/editorial commit leaves every verified scientific input and output unchanged.
