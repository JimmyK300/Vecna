# Issue #58 failure-taxonomy report (Q0, current system)

Generated: `2026-08-25T15:17:14.114651+00:00`

Rules/thresholds are fixed constants declared at the top of `aic51-src/script/classify_issue58_failures.py`; every assignment carries evidence. `correct_result_outside_top20` is assigned literally whenever no ground-truth target appears within the judged top-20.

| query | task | class | categories / evidence |
|---|---|---|---|
| p1_q01 | tkis | hit | first-correct rank 1 |
| p1_q02 | trake | hit | first-correct rank 13; observation: ['duplicate_results'] (gold-video slots above first-correct: 1, other 3+-slot videos: {'L26_V208': 5}) |
| p1_q03 | tkis | hit | first-correct rank 1 |
| p1_q04 | tkis | hit | first-correct rank 6; observation: ['duplicate_results'] (gold-video slots above first-correct: 5, other 3+-slot videos: {}) |
| p1_q05 | tkis | hit | first-correct rank 1 |
| p1_q06 | tkis | hit | first-correct rank 1 |
| p1_q07 | tkis | hit | first-correct rank 11; observation: ['duplicate_results'] (gold-video slots above first-correct: 10, other 3+-slot videos: {}) |
| p1_q08 | tkis | hit | first-correct rank 1 |
| p1_q09 | tkis | hit | first-correct rank 1 |
| p1_q10 | tkis | hit | first-correct rank 1 |
| p1_q11 | tkis | hit | first-correct rank 1 |
| p1_q12 | tkis | hit | first-correct rank 3; observation: ['duplicate_results'] (gold-video slots above first-correct: 2, other 3+-slot videos: {}) |
| p1_q13 | qa | hit | first-correct rank 4; observation: ['duplicate_results'] (gold-video slots above first-correct: 3, other 3+-slot videos: {}) |
| p1_q14 | trake | hit | first-correct rank 3 |
| p1_q15 | tkis | hit | first-correct rank 1 |
| p1_q16 | trake | fail | `correct_result_outside_top20`; `temporal_understanding_required`; `poor_frame_sampling` -- serving_mode=similarity; latency=6.88s; nearest_gold_delta=21.44s; gold_entries=[{'rank': 7, 'video_id': 'L26_V072', 'frame_id': 4336}, {'rank': 18, 'video_id': 'L26_V072', 'frame_id': 4340}]; gold-video frames present in top-20 but all far from the gold time/interval |
| p1_q17 | qa | hit | first-correct rank 1 |
| p1_q18 | tkis | hit | first-correct rank 9; observation: ['duplicate_results'] (gold-video slots above first-correct: 8, other 3+-slot videos: {}) |
| p1_q19 | tkis | hit | first-correct rank 1 |
| p1_q20 | tkis | fail | `correct_result_outside_top20`; unresolved: no gold-video entry anywhere in top-20; cannot disambiguate which channel failed without owner-side corpus/annotation inspection -- serving_mode=similarity; latency=6.67s; gold_video_absent_from_top20=true; owner-evidence candidates: ['`missing_visual_feature`', '`missing_ocr_text`', '`asr_transcription_error`'] |
| p1_q21 | tkis | fail | `correct_result_outside_top20`; `poor_frame_sampling` -- serving_mode=similarity; latency=3.89s; nearest_gold_delta=158.64s; gold_entries=[{'rank': 4, 'video_id': 'L23_V025', 'frame_id': 12800}, {'rank': 5, 'video_id': 'L23_V025', 'frame_id': 12850}, {'rank': 10, 'video_id': 'L23_V025', 'frame_id': 12625}, {'rank': 11, 'video_id': 'L23_V025', 'frame_id': 12475}, {'rank': 13, 'video_id': 'L23_V025', 'frame_id': 20725}]; gold-video frames present in top-20 but all far from the gold time/interval |

Unscoreable (excluded from metrics): `p1_q22` (missing official answer ground truth (validation_state=source_text_verified_missing_ground_truth))
