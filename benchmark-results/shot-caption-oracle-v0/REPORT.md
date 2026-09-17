# Gemini shot-caption oracle sufficiency v0 — AGY capability gate report

Tracker: `JimmyK300/Vecna#95`

## Result

`NEEDS_DECISION`. The authorized AGY CLI route was evaluated against the frozen experiment requirements. While `gemini-3.8-flash-high` is available in the CLI model catalog, AGY CLI's headless execution protocol cannot satisfy the experiment's native video captioning contract. Specifically, headless stream input (`--input-format stream-json`) strictly supports only `"text"` content blocks and rejects non-text blocks with `error: stream input content block type "video" is not supported (only "text")`. Furthermore, the CLI provides no mechanism for static 4.0 fps sampling, high-resolution specification, audio track ingestion, or zero-shot unpolluted context isolation.

Per worker instructions, the worker halted at the capability gate rather than silently substituting frame montages, lower fps, audio omission, or tool-based file inspection.

## Completed proof and evidence

### 1. Model availability
- `agy models` was executed and lists `gemini-3.8-flash-high` (Gemini 3.8 Flash High) as an active model.

### 2. Headless stream input restriction
- Evaluated `agy --input-format stream-json --output-format stream-json --model gemini-3.8-flash-high`.
- Passing a standard text prompt succeeds (`status: SUCCESS`), but passing a non-text content block (e.g. `type: "video"`) immediately terminates with returncode 1 and exact error:
  ```
  error: stream input content block type "video" is not supported (only "text")
  ```
- Binary audit of `agy.EXE` confirms the format string at rodata offset:
  `stream input content block type %q is not supported (only %q)`
  with supported type hardcoded to `"text"`.

### 3. Missing video processing and audio parameters
- `agy --help` lists 21 flags; none provide video sampling control (`fps`), video processing mode (`static`), resolution control (`high`), or audio container handling.
- Passing a video path as text (e.g. `"Describe video C:\path\to\clip.mp4"`) does not pass multimodal video tokens to the underlying model; the model only receives the text string.

### 4. Context isolation violation
- AGY CLI operates as an interactive/agentic environment. In print/stream mode, it injects over 17,000 prompt tokens comprising agent system instructions and 57 built-in developer tools (e.g., `run_command`, `replace_file_content`, `grep_search`, `browser_*`) per turn.
- This violates the frozen contract requiring an isolated zero-shot completion context containing ONLY the generic prompt and neutral media.

### 5. Interactive paste boundary
- Official Antigravity documentation confirms that while clipboard paste (`ctrl+v`) in the interactive TUI can attach video recordings for UI debugging, interactive mode cannot be automated headlessly for batch processing across the 79 missing combinations, nor does it expose the required 4 fps / static sampling parameters.

### 6. Existing artifacts preserved
- 28 extracted oracle clips (380,423,946 bytes, 28 unique clip SHA-256s, 27 unique source SHA-256s) remain intact and immutable in `clips/`.
- 5 frozen successful captions and 2 error records from the initial API run remain untouched in `captions/`.
- Post-caption decomposition authority (`decompositions_113.jsonl`, blob `caf0a7b30a...`) remains preserved in `evaluation_inputs/`.

## Reproducible diagnostics

The diagnostic verification suite and evidence are preserved in:
- `diagnostics/agy_preflight/probe_agy_capabilities.py`
- `diagnostics/agy_preflight/agy_preflight_evidence.json`
- `diagnostics/agy_preflight/README.md`

Rerun command:
```powershell
.\.venv-issue95\Scripts\python.exe benchmark-results/shot-caption-oracle-v0/diagnostics/agy_preflight/probe_agy_capabilities.py
```

## Concrete decision options

1. **Authorize paid Google GenAI API quota / billing project (Recommended):**
   Attach billing or a standard-tier API key for `gemini-3.8-flash`. The existing, verified `code/shot_caption_oracle.py` harness will resume without `--force`, skipping the 5 frozen successes and completing the remaining 79 captions with 100% fidelity to the frozen contract (4.0 fps static sampling, high resolution, native audio track ingestion, query-independent zero-shot context).

2. **Authorize client-side frame extraction variance:**
   Allow local extraction of static 4.0 fps frames via ffmpeg and define an explicit contract variance to evaluate whether an image-montage or sequential image API route is acceptable.

3. **Authorize Google Cloud Vertex AI route:**
   If enterprise Google Cloud Vertex AI credentials / ADC are available on the host, adapt the harness to use the Vertex AI endpoint for `gemini-3.8-flash` with the frozen video processing configuration.

4. **Await free-tier quota reset:**
   If the free-tier quota resets on a rolling 24-hour cycle, resume after the reset window without modifying the contract.

## Scope check

- Branch: `local/issue-95-gemini-shot-caption-oracle`; no merge to `main`.
- No production retrieval changes, full-corpus pass, TransNetV2 dependency, prompt tuning, or answer leakage.
- No private OAuth tokens or credentials extracted or committed.

## Uncertainty

- Whether a future release of AGY CLI will add headless multimodal content blocks (`type: "video"`, `type: "image"`).
- The exact reset schedule or billing requirements of the user's Google GenAI API key.

Next state: `NEEDS_DECISION`.
