# Issue #34 minimum headless retrieval runtime

## Proven execution path

The benchmark imports `setup_searcher()` directly. It does not start FastAPI,
the frontend, or the core/file/search HTTP services.

1. `GlobalConfig` reads `config.yaml` from the process current working directory.
2. `backends.search.collection` selects one collection. A bare
   `MilvusClient()` connects to `http://localhost:19530`, database `default`.
3. `backends.search.gpu` requests CUDA, then Apple MPS; otherwise the query
   encoders run on CPU.
4. `Searcher` eagerly loads every configured `searcher.language_models`
   encoder, even if a run selects only one of its target vector fields.
5. For each text condition, the encoder produces a query vector. Vecna runs
   Milvus ANN for each selected vector field, OCR BM25 when weighted, optional
   ASR BM25, and Python normalization/fusion/temporal combination.
6. The harness judges the first 20 stable-ranked
   `frame_id=<video_id>#<source-frame-counter>` results.

No corpus embedding is recomputed. Per-condition latency includes query
encoding, Milvus calls, and fusion; model initialization is recorded separately.

## Exact dependency classification

### Required for headless retrieval

- One collection-filtered Milvus logical backup containing the exact collection
  schema/functions, vector fields and indexes, OCR/ASR text and BM25 indexes,
  frame IDs, and corpus rows.
- The matching Milvus standalone, MinIO, and etcd services. Image identity,
  health, mount types/names/destinations, server version, collection row count,
  schema, and index definitions are captured and verified.
- The exact workspace `config.yaml` and exact benchmark CSV.
- Every snapshot/checkpoint/tokenizer required by all eagerly configured
  `searcher.language_models`. The packager copies only the resolved snapshot
  revision and its refs, not old Hugging Face snapshots or duplicate blob trees.
- A 38-file retrieval-only Vecna source slice (208,041 bytes in this checkout),
  including the imported feature registrations, config/search/index utilities,
  backend setup, benchmark, and bundle tool.
- Matching Python major/minor and critical retrieval package versions.

### Not required for headless retrieval

- Raw videos, audio, clips, keyframes, thumbnails, or playback `video_info`.
- Corpus-side `features/**/*.npy`; those are indexing inputs, not search inputs.
- Raw OCR/ASR extraction intermediates.
- FFmpeg, Tesseract execution, WhisperX checkpoints, and extraction-only models
  when the frozen search config does not execute them per query.
- Frontend files, Node dependencies, and core/file/search HTTP processes.

### Optional for error analysis / human verification

- Source videos/audio and FPS metadata.
- Thumbnails/keyframes for inspecting a hit.
- Raw OCR/ASR outputs and provenance sidecars.
- Corpus feature arrays only if a future decision explicitly authorizes index
  reconstruction. They are not part of this transfer contract.

The default Compose deployment stores durable state across three coordinated
volumes (etcd, MinIO, and Milvus standalone). A physical fallback is valid only
as a quiesced, coordinated snapshot of **all three** live volumes. Never copy
only the Milvus volume. Live `docker inspect` output, not assumed default names,
is authoritative.

## Query compute and AMD

The expensive corpus image/audio analysis is already represented by the Milvus
rows and indexes. Each Q0 still performs text-model inference plus database
search/fusion. On this Windows AMD machine, the current device chooser has no
DirectML path; a standard PyTorch build that reports neither CUDA nor MPS runs
the query encoders on CPU. AMD can therefore affect cold model load and
per-query text latency, but does not cause corpus re-embedding or make the
approximately 40 searches a corpus-scale GPU job.

Do not predict runtime from hardware specifications. Inventory records the
actual device facts and one real initialization/query latency on the source
machine; verification records the target behavior.

## Transfer safety contract

`issue34_runtime_bundle.py` has four stages:

1. `inventory` is read-only with respect to Docker/Milvus. It hashes the live
   inputs, forces model resolution offline, requires the existing collection to
   be nonempty/Loaded with nonempty Finished indexes, and runs one Q0 smoke
   query. Its only write is a local source manifest.
2. `package` rehashes every input, re-resolves the exact model snapshots,
   rechecks Python/Docker/Milvus, repeats the smoke query, then creates one
   `milvus-backup --filter <collection>` logical backup. It rejects changed
   inputs, unsafe paths/names, secrets in the transferable Vecna config, and
   existing output paths. It emits a closed file manifest, ZIP, out-of-band
   SHA-256 sidecar, this guide, a restore-config template, and an offline-cache
   activation script.
3. `preflight-restore` verifies the transferred file set/cache/Docker contract,
   proves the target collection does not already exist, validates the restore
   configuration, and prints the human-controlled restore command. It never
   restores or deletes anything.
4. `verify` waits for nonempty Finished indexes and a Loaded collection, checks
   exact schema/index/count/server/config/source/package identities, forces the
   bundled model cache offline, blocks Milvus write APIs during `Searcher`
   startup/search, and requires the same top-20 smoke frame IDs.

The source manifest may contain local paths and remains on the teammate machine.
The transferred manifest removes source/cache roots, Git status filenames, URL
credentials, and Docker host mount sources. Filled `backup-local*.yaml` files are
ignored and never copied into the bundle.

The generated `requirements.versions.txt` is an inspectable version manifest,
not a cross-platform wheel lock. CUDA/CPU wheel provenance and platform-specific
builds still require a deliberately recreated environment; the verifier catches
critical-version or smoke-result drift.

## Teammate workflow

First freeze the exact vector fields used by the intended baseline. This is a
product/evaluation decision: do not silently use every field in `config.yaml`.
Set the paths and selected fields once:

```powershell
$vecnaRepo = 'C:\path\to\Vecna'
$liveWorkspace = 'C:\path\to\the\live\Vecna-workspace'
$targetFeatures = 'EXACT_COMMA_SEPARATED_VECTOR_FIELDS'
$manifest = Join-Path $liveWorkspace 'issue34-runtime-manifest.json'
```

### 1. Read-only inventory and one smoke query

Purpose: identify the exact existing runtime without backing up or regenerating
the corpus.

```powershell
Set-Location -LiteralPath $liveWorkspace
python "$vecnaRepo\aic51-src\script\issue34_runtime_bundle.py" inventory `
  --workspace . `
  --csv "$vecnaRepo\aic51-src\benchmark\issue34_headless_queries.csv" `
  --compose "$vecnaRepo\aic51-src\aic51\resources\milvus-standalone\milvus-standalone-docker-compose.yaml" `
  --target-features $targetFeatures `
  --manifest $manifest
```

Success names the collection and nonzero row count, records one nonempty smoke
result, and prints the exact pre-backup byte total. Important failure signals are
a missing/empty/unloaded collection, zero/non-Finished indexes, missing offline
model snapshot, container/image/mount problem, secret-bearing runtime config, or
empty smoke result. Stop on any of them.

For nonstandard container names, repeat `--container <name>` three times; custom
values replace rather than append to the defaults.

### 2. Collection-filtered package

Copy `aic51-src/benchmark/backup-local.template.yaml` outside the repository as
`backup-local.yaml`. Set its live Milvus/MinIO values and set
`backup.storage.rootPath` to the same absolute directory used below. The file may
contain credentials: do not commit or transfer it.

Purpose: create the only long-running/data-producing source step, after all
runtime evidence is revalidated.

```powershell
$backupRoot = 'D:\vecna-logical-backups'
$backupName = 'vecna_issue34_current'
$bundleDir = Join-Path $liveWorkspace 'vecna-issue34-runtime'

python "$vecnaRepo\aic51-src\script\issue34_runtime_bundle.py" package `
  --manifest $manifest `
  --backup-config (Join-Path $liveWorkspace 'backup-local.yaml') `
  --backup-root $backupRoot `
  --backup-name $backupName `
  --bundle-dir $bundleDir
```

Success produces the bundle directory, `<bundle>.zip`, and
`<bundle>.zip.sha256`, and prints their exact byte sizes and archive SHA-256.
Important failure signals are any changed hash/runtime/smoke result, a backup
inspection that omits the selected collection, or a live collection that changes
during backup. Preserve all output and stop; do not rerun under the same name.

The package uses the current official Milvus Backup `check`, `create --filter`,
and `get` commands. The [official CLI restore guide](https://github.com/zilliztech/milvus-backup/blob/main/docs/user_guide/e2e_demo_cli.md#step-3-restore-the-backup)
states that indexes are omitted unless restore uses `--rebuild_index`; the
preflight therefore prints that flag and verification waits for Finished
indexes. If logical index rebuilding is unacceptable, stop and use the
separately approved quiesced three-volume snapshot fallback instead.

## Receiving-machine workflow

### 1. Check before extraction

```powershell
$archive = 'C:\path\to\vecna-issue34-runtime.zip'
$expected = ((Get-Content -LiteralPath "$archive.sha256" -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "Archive SHA-256 mismatch: $actual != $expected" }
Expand-Archive -LiteralPath $archive -DestinationPath (Split-Path -Parent $archive)
```

Success is no output from the comparison and one extracted bundle directory.
Any hash mismatch is a hard stop.

### 2. Recreate services/environment, but do not restore yet

Start the exact inventoried container images with the same mount destinations
and read/write contract. Target Compose project prefixes—and therefore target
named-volume names—may differ; the source names remain recorded for audit and
physical-fallback recovery. Recreate the recorded Python major/minor and critical package versions; use
`runtime/requirements.versions.txt` as evidence, not as a guarantee that the
same platform-specific wheels exist.

Create an empty local workspace and copy the bundled config:

```powershell
$bundle = 'C:\path\to\vecna-issue34-runtime'
$localWorkspace = 'C:\path\to\vecna-issue34-workspace'
docker compose -f "$bundle\runtime\milvus-compose.yaml" up -d
New-Item -ItemType Directory -Path $localWorkspace -Force | Out-Null
Copy-Item -LiteralPath "$bundle\runtime\config.yaml" -Destination "$localWorkspace\config.yaml"
. "$bundle\runtime\activate-offline.ps1"
$sourceRuntime = Get-Content -LiteralPath "$bundle\source-runtime-manifest.json" -Raw | ConvertFrom-Json
$targetFeatures = $sourceRuntime.smoke_query.target_features -join ','
```

Success is three healthy inventoried services plus offline environment variables
rooted inside `$bundle\model-cache`. A container/image/mount mismatch, missing
model snapshot, or any attempted network model fetch is a hard stop.

Create a target-specific `restore-local.yaml` outside the repository. Its
`backup.storage.provider` must be `local`, and
`backup.storage.rootPath` must be the absolute `$bundle\milvus-backup` directory.
Its Milvus/MinIO section must match the newly started target services.

### 3. Stop-gated restore preflight

Purpose: prove the target collection is absent and print—but not execute—the
exact restore command.

```powershell
$bundleTool = "$bundle\runtime\vecna-source\aic51-src\script\issue34_runtime_bundle.py"
python $bundleTool preflight-restore `
  --bundle-dir $bundle `
  --restore-config 'C:\path\to\restore-local.yaml'
```

Success explicitly says the target collection is absent and prints:

```text
milvus-backup --config <restore-local.yaml> restore -n <backup-name> --filter <collection> --rebuild_index
```

The important failure signal is especially “target collection already exists.”
Do not drop, rename, overwrite, or retry around that guard without a separate
human decision. Run the printed restore command manually only after reviewing
the target and expected collection.

### 4. Post-restore verification and one known query

```powershell
Set-Location -LiteralPath $localWorkspace
python $bundleTool verify `
  --bundle-dir $bundle `
  --workspace $localWorkspace
```

Success reports the exact collection/row count, Finished indexes, Loaded state,
offline cache root, `smoke_top_20_ids_match: true`,
`milvus_writes_blocked_during_smoke: true`, and
`corpus_regeneration_invoked: false`. Any mismatch is a hard stop; do not launch
the benchmark.

### 5. Benchmark launch remains validation-gated

The self-contained launch command is:

```powershell
$benchmarkTool = "$bundle\runtime\vecna-source\aic51-src\script\headless_benchmark.py"
python $benchmarkTool `
  --csv "$bundle\runtime\issue34_headless_queries.csv" `
  --target-features $targetFeatures `
  --output (Join-Path $localWorkspace 'issue34-q0.jsonl')
```

With the currently bundled CSV, the expected result is a refusal before model or
Milvus setup: all 21 current-corpus scoreable text keys remain provisional, not
formally current-corpus validated. That refusal is success for the present stop
gate. `--allow-provisional-ground-truth` exists only for explicitly labeled
exploration and must not be reported as the trustworthy baseline.

## Current stop state and exact next action

The exact transfer size is not inspectable on this machine because the live
config, collection, Docker volumes, and model caches exist only on the teammate
machine. The tool reports the exact code/config/model byte subtotal at inventory
and the exact final logical-backup/bundle/archive sizes after packaging. Nothing
in the traced headless path demonstrates a need for the approximately 60 GB raw
workspace tree.

The next action is **not** the full benchmark. First select the exact baseline
vector field(s), then have the teammate run only the inventory command above and
return `issue34-runtime-manifest.json` plus its console output for review. The
long-running package step remains a separate explicit handoff after that review.
