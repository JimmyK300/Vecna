# Packet B evidence recovery

The original 115-query provider capture is the input authority. The committed compact per-query file contains every scored query and all six surfaces, and the committed summary contains the complete aggregate and paired comparisons. The large transformed study, detailed per-query diagnostics and slices are regenerated together from the original capture. No model, database or new query is needed for that replay.

Use a research checkout that preserves committed LF bytes. From `benchmark-results/astra-retrieval-rd-v1`:

```sh
python code/hydrate_fusion_capture.py --root .
python code/hydrate_fusion_capture.py --root . --replay-outdir outputs/fusion/replay-local-v1
python code/analyze_fusion_headroom.py --root . --rankings outputs/fusion/capture-full115-v1/provider_rankings.jsonl --collection-manifest outputs/fusion/capture-full115-v1/collection_manifest.json --study outputs/fusion/replay-local-v1/study_results.jsonl --summary outputs/fusion/replay-local-v1/summary.json --output outputs/fusion/replay-local-v1/coverage_headroom.json
```

The helper expects `outputs/fusion/recovery-evaluation-v1/archives/provider_rankings.jsonl.xz`. Its exact compressed identity is 1,699,128 bytes, SHA256 `b793108e648605d413f8fd8d061fa6029f2a5e3b5a1c884f62e55849f004443f`. Decompression must produce 27,146,363 bytes, SHA256 `d6223381ea8cbf4b4efcb0cc295f60dccfcae36afe0d9fac004438410c152a82`. Both are checked before a new raw file is written. A pre-existing matching raw file is reused; a different file is preserved and rejected. See `raw_archive_manifest.json` for completed publication and transport receipts.

The replay directory must be new. The helper pins the frozen harness, evaluator, scorer adapter, configuration, query projection, collection manifest and compact reference. It checks every saved rank, target-coverage value and frozen metric for all six arms and 113 queries against the durable compact reference. The scorer separately verifies canonical truth and capability sources. The output summary binds the new study bytes. Keep the new study, summary and detailed per-query files together; do not mix a fresh study with an earlier summary.

The original local evaluation was independently checked before the shared workspace outage. The model-free recovery at Actions run35108003259 reproduced the same primary metrics from the original raw bytes. Its study SHA256 is `2291194ca558d490a9c32d969136176578e3ca913efbd9e77554c739b7a867d5`; the earlier local study SHA256 was `3a9fc4bd112260fcba775330d4b37f63a3d5255b0bf711fe32f88d665c4e1c0f`. Fusion CPU/wall timings are newly measured on each replay, so study/per-query byte hashes change even when all ranks and scores agree. The committed recovered summary is the LF-normalized metadata from that recovery, not a relabelled original timing result.

A consumer that finds a completed B summary but no matching full study must stop and request/reproduce the complete derived bundle. The compact projection is suitable for inspecting all 113 results; it is not a replacement for the frame-level evidence needed by Packet D's independent rescoring.

The headroom helper checks the exact original raw file and manifest, all 115 canonical IDs and query texts, the summary-to-study hash, every current-control frame/video ranking, provider-union target OR and nested retained-set target presence. It emits all 113 scored rows, per-provider presence and aggregate ceilings. It does not construct or score a new admission policy. The first-unique-video layer is an analysis projection: main returns frame hits, and these representative-frame losses do not establish a serving or historical-C timeline defect.

To check the recovery helpers:

```sh
python -m unittest discover -s tests -p test_fusion_recovery.py
```

Capture provenance remains separate from offline replay. The actual captured query providers used execution commit `0ee966b8ddfe367fbf5a9bb4ba8301c2d43b5e54` on `btl/issue-82-fusion-verified-loader`, with the two verified Qwen loader repairs from the separate PR88. The research branch does not overlay production files. Ordinary main with the old loader cannot pass the capture gate. No main merge was performed.

The current control preserves main's nested max normalization and established outer weights. The four alternative transforms use fixed nominal equal shares across the four active providers. Those effective coefficients differ: this is a comparison of frozen configurations, not an isolated flat-weight calibration. Both dense providers were explicitly disabled for all 115 capture rows. Historical C candidates and the corpus/index producer loading lineage remain separate, unresolved provenance questions.
