# Issue #62 local compatibility matrix

Generated: `2026-08-25T19:57:55.145866+00:00`  |  branch `codex/issue-62-compat-bench` @ `9b8a871e8531`

Machine: Intel(R) Core(TM) i5-14600K cores=14 logical=20 ram_gb=31.8

GPU: AMD Radeon RX 6900 XT|driver=32.0.21045.1000

- **pytorch-cpu** (`C:\Users\minhc\Code\Vecna\.venv\Scripts\python.exe`): python 3.12.1, torch 2.8.0, torchvision 0.23.0, torch-directml 0.2.5.dev240914, open-clip 3.3.0, transformers 4.57.6, onnxruntime 1.27.0, numpy 1.26.4
- **pytorch-directml** (`C:\Users\minhc\Code\Vecna\.venv-amd\Scripts\python.exe`): python 3.12.1, torch 2.4.1, torchvision 0.19.1, torch-directml 0.2.5.dev240914, open-clip 3.3.0, transformers 5.13.1, onnxruntime None, numpy 2.5.1

Workload: 12 keyframes from `C:\Users\minhc\Code\Vecna\data-staging\keyframes\sample_video` (4 for Qwen embed), 6 fixed vi/en queries, batch levels [1, 4, 16, 32, 64], 2 image reps, 3 text reps. Offline env enforced; zero downloads.

## Embedding throughput (image)

| model | harness | side | status | device | img/s | p50 batch ms | batch ceiling | peak RSS | load s | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| image_clip_pe-l-14-336 | pytorch-cpu | embed | ok | cpu | 1.56 | 3870.0ms/batch@4 | 4 | 5562.2MB | 5.9s | fp32; cpu |
| image_siglip_so400m-384 | pytorch-cpu | embed | ok | cpu | 0.96 | 6288.0ms/batch@4 | 4 | 7142.0MB | 6.0s | fp32; cpu |
| qwen_vl | pytorch-cpu | embed | ok | cpu | 0.023 | 43.53s/img | 1 | 4322.0MB | 0.6s | bf16; cpu; frames=4 (capped) |
| image_clip_pe-l-14-336 | pytorch-directml | embed | ok | AMD Radeon RX 6900 XT | 4.28 | 1532.0ms/batch@1 | 1 | 5600.7MB | 6.9s | fp32; privateuseone:0; batch>=4 failed[RuntimeError]: Could not allocate tensor with 28340220 bytes. There is not enough GPU video mem |
| image_siglip_so400m-384 | pytorch-directml | embed | ok | AMD Radeon RX 6900 XT | 3.73 | 1832.0ms/batch@1 | 1 | 7186.9MB | 9.1s | fp32; tok-fallback; privateuseone:0; batch>=16 failed[RuntimeError]: Could not allocate tensor with 408146688 bytes. There is not enough GPU video me |
| qwen_vl_fp32_forced | pytorch-directml | embed | failed[RuntimeError] | - | - | - | - | - | -s | input must be 4-dimensional |

## Query-time text behavior

| model | harness | side | status | device | texts/s | p50 ms/query | batch ceiling | peak RSS | load s | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| image_clip_pe-l-14-336 | pytorch-cpu | query_text | ok | cpu | 23.23/s | 42.9ms/query | - | 5560.1MB | 4.7s | fp32; cpu |
| image_siglip_so400m-384 | pytorch-cpu | query_text | ok | cpu | 10.89/s | 92.06ms/query | - | 7141.8MB | 6.1s | fp32; cpu |
| qwen_vl | pytorch-cpu | query_text | ok | cpu | 1.02/s | 976.04ms/query | - | 3367.6MB | 0.5s | bf16; cpu |
| text_bge_m3_pytorch | pytorch-cpu | query_text | ok | cpu | 44.9/s | 21.98ms/query | - | 3040.6MB | 4.6s | fp32; cpu |
| image_clip_pe-l-14-336 | pytorch-directml | query_text | ok | AMD Radeon RX 6900 XT | 170.79/s | 5.79ms/query | - | 5601.5MB | 6.9s | fp32; privateuseone:0 |
| image_siglip_so400m-384 | pytorch-directml | query_text | ok | AMD Radeon RX 6900 XT | 13.69/s | 73.12ms/query | - | 7188.7MB | 8.7s | fp32; tok-fallback; privateuseone:0 |
| qwen_vl_bf16_registered | pytorch-directml | query_text | failed[DirectMLFatalAbort_BFloat16Unsupported] | - | - | - | - | - | -s | DirectML fatal abort: Invalid or unsupported data type BFloat16 (torch-directml cannot execute bf16 ops) |
| qwen_vl_fp32_forced | pytorch-directml | query_text | ok | AMD Radeon RX 6900 XT | 17.34/s | 73.55ms/query | - | 14897.2MB | 9.4s | fp32(forced); privateuseone:0 |
| text_bge_m3_pytorch | pytorch-directml | query_text | failed[ValueError] | - | - | - | - | - | -s | Due to a serious vulnerability issue in `torch.load`, even with `weights_only=True`, we now require users to upgrade torch to at least v2.6  |
| text_bge_m3_onnx_local_artifact | onnxruntime-cpu | query_text | ok | - | 47.49/s | 22.36ms/query | - | 1870.4MB | -s | fp32 |

## Not runnable locally (inventory, no execution)

| candidate | status | evidence |
|---|---|---|
| torch-directml inside primary .venv (any model) | failed-not-runnable | import torch_directml -> ImportError: DLL load failed while importing torch_directml_native: The specified procedure could not be found (torch-directml 0.2.5.dev240914 vs torch 2.8.0 in C:\Users\minhc\Code\Vecna\.venv) |
| onnxruntime DirectML EP (both venvs) | not-installed-locally | .venv has onnxruntime==1.27.0 with providers [AzureExecutionProvider, CPUExecutionProvider]; onnxruntime-directml not installed anywhere; installing it is a new dependency (out of scope) |
| qwen_vl repo path in .venv-amd | dependency-missing | repo feature module imports qwen_vl_utils; .venv-amd does not have qwen_vl_utils installed; harness uses self-contained preprocessing instead |
| registered BGE-M3 ONNX backend artifact (fp16 dense-only) | artifact-absent-locally | bge_onnx.py expects BAAI-bge-m3_fp16.onnx (hotchpotch/vespa-onnx-BAAI-bge-m3-only-dense); no such file found under C:\Users\minhc\Code\Vecna; downloading is prohibited by issue #62 |

