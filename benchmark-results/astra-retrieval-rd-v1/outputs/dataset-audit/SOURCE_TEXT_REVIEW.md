# Bounded projected-text audit

All 38 frozen query/channel rows now have inspected stored text neighborhoods from 37 pinned per-video files. No pixels/audio or live sparse/dense ranking were inspected. Text availability does not establish extraction fidelity or a downstream failure cause.

| Channel | Query | Nonempty frames / distinct strings | Artifact observation |
|---|---|---:|---|
| ocr | p0_q13 | 2 / 2 | Year/event backdrop fragments exist; the long quoted support-board phrase is not established by these two records. |
| ocr | p0_q19 | 0 / 0 | No nonempty OCR frame record in the accepted window; whether decisive writing is visible requires pixels. |
| ocr | p0_q21 | 0 / 0 | No nonempty OCR frame record in the accepted window; recipe title/200g visual evidence remains uninspected. |
| ocr | p1_q17 | 23 / 14 | Stored OCR exposes the remember lesson despite substantial repeated/noisy text. |
| ocr | p1_q18 | 55 / 55 | Text exists, but the obligation is a colored three-level diagram; plain text cannot establish the layout. |
| ocr | p1_q24 | 12 / 12 | A headline supplies a candidate pass name; source readability/fidelity still needs pixels. |
| ocr | p1_q21 | 21 / 20 | OCR includes broadcast clocks and noise; the final scale value is not established by text alone. |
| ocr | p2_q15 | 23 / 23 | Table words and numbers survive; row association, red/blue counts, and the comparative claim require pixels. |
| ocr | p2_q26 | 7 / 7 | Window OCR is chiefly logos/noise; animal identity is not established through this text channel. |
| ocr | p2_q25 | 2 / 2 | Two nonempty OCR strings do not establish which pole number is absent over the first 16 seconds. |
| ocr | p3_q04 | 31 / 20 | Both described English examples are available in stored OCR; full temporal sequence is unverified. |
| ocr | p3_q02 | 1 / 1 | The one noisy OCR record does not establish class-number signs; provisional truth remains provisional. |
| ocr | p3_q05 | 23 / 22 | Stored slide OCR supplies a candidate province count; native source fidelity is unverified. |
| ocr | p3_q35 | 14 / 14 | OCR preserves a candidate group label and 2018 question text; the four-answer constraints still require direct verification. |
| ocr | p0_q20 | 3 / 3 | Name/poem fragments exist, but the requested full two lines are not recoverable faithfully from these records alone. |
| ocr | p1_q03 | 16 / 16 | London and weighing context survive; the animal/action sequence still requires pixels. |
| ocr | p1_q23 | 14 / 14 | Garbled labels/digits do not support counting map markers while excluding the legend. |
| ocr | p2_q13 | 1 / 1 | Only one noisy record appears; the quoted SẮC CỔ text is not established by it. |
| ocr | p2_q23 | 1 / 1 | Only one noisy record appears; the requested street name is not established in this window. |
| ocr | p2_q24 | 65 / 58 | Question/axis language survives, but the graph optimum requires a visual relation rather than bag-of-words evidence. |
| asr | p0_q02 | 30 / 3 | Tiger-birth context survives even though the saved visual baseline missed; phonetic fidelity is unverified. |
| asr | p0_q19 | 17 / 2 | Club/province context is present; the requested commune name is not established by the bounded window. |
| asr | p1_q17 | 23 / 2 | Spoken remember usage distinction is represented in stored ASR. |
| asr | p1_q24 | 19 / 2 | Stored speech contains a candidate pass name and landslide context. |
| asr | p2_q26 | 27 / 3 | Stored speech supplies a candidate topping identity in the plating window. |
| asr | p2_q28 | 18 / 1 | Shellfish identity appears despite a saved visual-baseline miss; no source-audio fidelity claim. |
| asr | p3_q04 | 31 / 3 | Examples and grammar explanation are represented in projected ASR. |
| asr | p3_q08 | 7 / 1 | Grandmother/game-collection clue survives; the requested neon text is a separate visual obligation. |
| asr | p3_q18 | 13 / 2 | Projected speech contains a candidate school identity; provisional truth and native spelling remain unverified. |
| asr | p0_q16 | 56 / 4 | Movie/year/shark context survives. The accepted window also spans unrelated following-news text. |
| asr | p0_q20 | 14 / 2 | A poem-like answer string exists but source audio is needed to judge its words; no CER/WER is claimed. |
| asr | p2_q23 | 51 / 3 | Lodging/donor context survives; the street name is not established in this bounded window. |
| asr | p2_q21 | 28 / 3 | Species and ingredient context are present; this does not prove sparse/dense visibility or source fidelity. |
| asr | p3_q06 | 28 / 4 | Author/work context survives; requested mountain-region answer is not established in this window. |
| asr | p3_q14 | 12 / 1 | Swimming interview is present, but the next grade is not established in this bounded window. |
| asr | p0_q01 | 39 / 3 | Four-person private mission and aurora-like wording survive; the latter needs audio to judge transcription. |
| asr | p3_q24 | 20 / 2 | Stored ASR contains a candidate soy-sauce quantity despite the saved visual-baseline miss. |
| asr | p3_q05 | 23 / 3 | Region context exists; the requested province count is not established by this bounded ASR window, while paired OCR contains a candidate count. |

The duplicate counts describe repeated frame projections within accepted windows. They do not measure candidate-list flooding. Native WhisperX intervals and OCR boxes/confidences are absent from this metadata format; timestamps use rounded-FPS keyframe projection and identical strings are grouped across empty frames.

Next direct checks: source pixels where OCR is absent/noisy; audio where candidate answers or questionable wording occur; exact sidecar discovery for retained native evidence; then sparse/dense visibility without answer-conditioned query rewriting. No broad re-extraction is authorized by this audit.
