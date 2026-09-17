# AGY native-video caption quality pilot, v5

**Verdict: useful broad scene descriptions, not ready as reliable fine-grained retrieval evidence. Hold the full batch.** This is a six-clip diagnostic review, not a representative accuracy estimate or a retrieval benchmark.

## Completion versus acceptance

All 18 selected slots (6 clips x 3 frozen generic prompts) have hash-verified terminal records and native `view_file` calls to their assigned MP4s, with no unexpected tools recorded. One successful v4 result is reused by immutable hash/reference; v5 made 17 new calls. No original API captions were overwritten.

The runner's `candidate_valid` flag was too permissive: CLI SUCCESS and nonempty text do **not** imply a caption. Two outputs (p0_q13, both structured prompts) are Gemini filter messages. There are 16 substantive responses. Of 12 requested structured outputs, only 8 are raw JSON; 2 have extraneous prose before a recoverable JSON object; 2 are filter messages. Review-only parsed objects do not retroactively pass the raw contract. All 6 dense responses are prose; some are excessively long and include planning-like preambles.

## Independent review findings

| Clip | Useful evidence | Material failure or limitation |
|---|---|---|
| p0_q04 cooking | All prompts retain plating, colored wrappers, green filling and flower garnish, corroborated by extracted frames. | Extra exact counts disagree: dense says four pairs, evidence four pieces, temporal five. No exact-count acceptance. The extracted interval begins with the host, not plating. |
| p0_q13 hospital charity | Dense output identifies the event, year, stage and donation amount. | Both structured outputs are filter responses despite SUCCESS. Dense loses four-recipient clothing/layout and exact board text although visible at 6.77s. |
| p0_q19 charity commune | All retain Giang Ly and gift distribution; banner/building independently corroborate the place. | Dense reads FANA as VANA; evidence reads SANA; temporal omits FANA. Fine OCR is unreliable. This is visual QA support, not an independently verified speech result. |
| p1_q02 map/sequence | All capture main canal and T3/T4/T5 progression visible in the frames. | The supplied 105-128s interval shows a map in every sampled frame; required dam/rain sequence is not evidenced. Flag range sufficiency for inspection rather than charge the captioner for missing unavailable scenes. |
| p2_q14 cycling | Rear view, green light and 13 are preserved. | All three explicitly reverse the turn to LEFT; independent frame sequence shows RIGHT. Rider configuration is incomplete. Dense/evidence also label commentary as visible subtitles without corroboration in the inspected frames. |
| p2_q25 numbered poles | Lion, poles, stage, dragon and inset musicians are recognized. | No reliable number inventory. Dense/temporal repeat 5 in a partial list; evidence claims 1-7 clearly visible. Number 8 is plainly visible at 10.12s and omitted by all. The missing-number question cannot be safely answered from these captions. |

`review/atom_review.tsv` preserves 31 requirement-level comparisons for all three families. Statuses describe evidence coverage, not numeric gold labels. `review/artifact_audit.json` records format/integrity results separately. The QA truth surface has `qa_answer: false` for p0_q19 and p2_q25, so this review makes no official QA-accuracy claim. Giang Ly is independently read from the footage, not promoted into frozen truth.

## Prompt comparison and decision

- Dense natural produced substantive content on all six clips, but verbosity did not prevent direction, OCR, count and omission errors.
- Structured evidence produced five substantive outputs, only three as raw JSON. It retained useful categories but asserted an incorrect pole-number inventory.
- Structured temporal produced five substantive outputs, all five raw JSON. It organizes chronology well, but still reverses the cycling turn and misses the number inventory.

No prompt is accepted as the winner on semantic reliability. Structured temporal has the cleanest successful structured formatting in this small sample; that is not proof of better factual accuracy. Do not launch the remaining batch yet. Next bounded work should fix refusal/schema acceptance, inspect interval sufficiency, and verify high-resolution OCR/count/action evidence before a new versioned pilot. Do not silently change the frozen prompts or replace the failed outputs.

## Provenance and limitations

- Source branch: `local/issue-95-gemini-shot-caption-oracle`; generation source commit `4ee9b935739633e2c5fe169e6c83c8b3274bde02`. Generation manifests record dirty state. Pilot code/results were uncommitted during generation; this archive binds their final bytes separately.
- Model: `gemini-3.8-flash-high`, effort high, AGY CLI native `view_file`. Each generation ran in a fresh neutral media directory with only its assigned clip. Requests contain generic frozen prompts and neutral paths, not query text, IDs, answers, tags or evaluation requirements.
- Native sampling, image resolution and audio handling are not controlled or proven equivalent to the original Gemini API route. The text stream records tool invocation, not the multimedia payload. Visual agreement corroborates access; it does not establish a configured frame rate.
- Correction to earlier preliminary diagnostics: AGY **can inspect local video with native view_file**. Text-only CLI prompt input does not imply no video capability. Agent scaffolding alone does not establish query leakage. Keep the earlier failed probe as historical evidence, not a current capability verdict.
- Review was performed by the local Codex orchestrator after outputs were frozen, using the authoritative query/decomposition rows plus independently extracted frames, not another Gemini judge. Twelve frames per clip were sampled at `i*(duration-0.1)/11`; full-resolution key frames were inspected for text. Sampling can prove a visible number exists, but cannot prove absence across every frame. This review does not certify exhaustive visual truth or every incidental caption assertion.
- Audio was not independently listened to in this review. Claimed transcripts and inferred ingredient identities remain unverified where no visual text corroborates them. No sensitive attribute inferred by a caption is accepted merely because the caption says it.
- Input/query join is exact `query_id`, preserving P0/P1/P2 identity. Six IDs were selected before generation to stress fine detail, OCR/count, speech QA, sequence, motion and negation. No exclusions after seeing results. Failure outputs stay in the denominator. No truth, corpus, index or retrieval semantics changed; this pilot adds native-route inference only.
- Exact local MP4 paths, ranges, byte hashes and source-video hashes are in `manifest.json`. Complete frozen prompts, manifest and decomposition files remain in the parent archive. `review/input_provenance.json` hash-binds these and the truth surface. Videos are not redistributed. Reproduction requires those local media bytes, AGY access, Python, ffmpeg and Pillow; model generation is not deterministic.
- v1: pre-inference eligibility/DNS failure. v2: relative/guessed-path failure. v3: headless workspace permission failure. v4: one successful reused caption, followed by output-limit failure. v5: 17 new calls; all traces retained. Per-process permission bypass was used to permit native media reading, with a strict post-run tool/path audit; it is not a security sandbox or a global permission change.

## Reproduction / validation

From this directory:

```powershell
python -m unittest test_audit_artifacts.py
python audit_artifacts.py
python extract_review_frames.py
```

The audit asserts 18 unique slots, clip/prompt/request/caption hashes, recorded native tool paths, absence of recorded tool errors, and equality between stored caption and CLI result. Four regression tests cover SUCCESS filter text, extraneous JSON preamble, truncation and valid JSON. It deliberately does not auto-score semantic truth.

`run_pilot.py` refuses an existing manifest. Never rerun it in this completed directory. A future authorized generation requires a new version/path. `SHA256SUMS.txt` covers this archive; `review/input_provenance.json` binds prior failed pilot files and the reused v4 caption. Publication includes v1-v5 so failures remain reviewable.
