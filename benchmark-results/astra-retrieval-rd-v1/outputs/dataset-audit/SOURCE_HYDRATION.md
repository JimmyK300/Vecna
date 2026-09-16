# Restore the pinned projected-text inputs

The 37 per-video JSON files total about 15 MB and already exist in `JimmyK300/official-dataset-control`. They can be omitted from this packet's Git commit. Keep `source_artifact_registry.json` and `source_text_run_manifest.json`: together they pin each file's exact commit/path, Git blob SHA, and SHA-256.

From this packet root, use an existing dataset Git checkout that contains commit `1f1ad1baef1e1d31817f6c5a12d4d94133611038`:

```bash
python code/dataset_text_audit.py --root . --dataset-repo /path/to/official-dataset-control --hydrate-only
python code/dataset_audit.py --root .
python code/dataset_text_audit.py --root .
python code/dataset_media_audit.py --root .
python code/dataset_remaining_media_audit.py --root .
```

On the Windows host, the dataset path is `D:/Official-Dataset`. The hydration command reads `git -C <dataset-repo> show <pinned-commit>:<pinned-path>`; it does not change that checkout or fetch a branch. All 37 source files must verify before any missing file is written into this packet's `outputs/dataset-audit/source-artifacts` cache. Existing matching files are left intact; existing mismatches fail instead of being overwritten. Only the declared projected-text JSON paths are read.

The three small source documentation files in `source-artifacts` may be retained in the packet; they are not part of the 37-file hydration step. Media review additionally needs all recovered assets and manifests in `outputs/source-audit/vecna82-source-media-review-v1`, `outputs/source-audit/vecna82-source-media-remaining-ocr-v1`, and `outputs/source-audit/vecna82-source-media-remaining-asr-v1`, plus `inputs/source_parity_probe.json` and `inputs/source_parity_probe_remaining.json`. The third stage verifies the original five assets and the explicit original/current sample-manifest bridge. The fourth stage verifies the remaining 17 images, 16 WAVs and 30 channel-row host parity results before applying the recorded image observations. Replay never generates a new source-media interpretation.

`source_text_audit.jsonl` preserves the bounded stored strings. `reviewed_audit.jsonl` adds 20 representative image inspections, 18 captured-but-unheard audio records, and 38 channel-row host parity results. Replaying with hydrated original Git blobs preserves these observation bytes exactly. The extra 17 image observations are fixed in `remaining_ocr_observations.jsonl`; `asr_listening_questions.json` contains the minimal source-reference questions for all 18 ASR cases.
