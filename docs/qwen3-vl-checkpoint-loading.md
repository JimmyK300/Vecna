The current Qwen3-VL embedding constructor can finish successfully while loading none of the checkpoint's 625 trained backbone tensors. In the captured Windows runtime—Sentence Transformers 5.4.0, Transformers 4.57.6 and PyTorch 2.8.0—the checkpoint has `model.language_model.*` and `model.visual.*` names, while `AutoModel` constructs `Qwen3VLModel` with `language_model.*` and `visual.*` names and an empty `base_model_prefix`. The structured loading audit reports 625 missing keys, 625 unexpected keys, zero shape-mismatch entries and zero error entries. Both language and vision components are affected. Successful construction and finite embeddings are therefore insufficient loading checks.

The repair keeps the existing Sentence Transformers model, prompt handling, pooling, normalization and encode methods. For `Qwen/Qwen3-VL-Embedding-2B` or a local matching 2B Sentence Transformers snapshot, it supplies the missing backbone-name mapping when the caller did not explicitly supply `key_mapping`. It then verifies that the constructed model has a complete, one-to-one, shape-exact checkpoint mapping and that **every loaded tensor value equals the checkpoint after casting to the loaded dtype**. Verification uses the local safetensors files in small row chunks and does not allocate a second model. Any missing key, extra key, collision, changed shape or incorrect value fails before the extractor can encode.

Caller policy is preserved: `model_kwargs=None` still selects float32 on CPU, while an explicit empty dictionary keeps the checkpoint/model default dtype. Explicit dtype, processor arguments and key mappings—including `None` and `{}`—are preserved. An explicitly supplied mapping that leaves weights unloaded now fails the post-load proof instead of returning an invalid extractor. Unrelated model paths keep their existing loading path. Quantized, meta or offloaded tensors that cannot support this exact comparison fail closed; this change makes no validation claim for those configurations.

The production changes belong at:

- `aic51-src/aic51/packages/analyse/features/qwen_vl.py`
- `aic51-src/aic51/packages/analyse/features/qwen_vl_checkpoint.py`

The regression test belongs at `aic51-src/tests/test_qwen_vl_checkpoint.py`, with fixture `aic51-src/tests/fixtures/qwen3_vl_2b_loading_schema.json`. The test imports the actual production helper and constructor from those paths; it does not import a second implementation. The original production source is Git blob `6b0299b95b848ad5f459b8158bb0f0bb183261c1`, LF SHA-256 `2b49052e371f9cb7b0299392a5e81c6433c09941b5bc95056c9aebcda285de80`.

Twelve local tests passed after applying the proposed production patch to an isolated copy of that exact source. They cover all 625 observed expected model names, observed header shape samples, partial/missing/colliding routes, shape mismatches, caller policies through the production constructor, random-value rejection despite correct shapes, corruption in the final chunk, and refusal to certify a meta tensor. The tensor-reader tests use small NumPy-backed stand-ins; they do not substitute for validation of real model weights. The fixture currently records all 625 actual model shapes and checkpoint names, with directly observed checkpoint header shape samples. Full checkpoint shapes will be added from the corrected runtime audit.

Run the installed regression test from the repository root:

```bash
python -m unittest discover -s aic51-src/tests -p test_qwen_vl_checkpoint.py -v
```

Before any repaired retrieval experiment, a supervised runtime audit must bind the exact wrapper and helper source hashes, model revision `9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda`, checkpoint file hashes and actual package versions. It must report all four loading-info lists empty and verify all 625 checkpoint tensors, including both language and vision weights, against the loaded state. The constructor exposes `_checkpoint_validation`, including the tensor count, revision and helper source hash. This real-weight validation is pending; the patch and test results alone do not claim it has passed.

The observed defect establishes the current loader's invalid state. It does not, by itself, establish that historical saved benchmark results or existing corpus embeddings were produced with the same runtime defect. Those retain their separate provenance and compatibility questions. This repair does not rewrite the corpus index, change benchmark truth, or merge into main.
