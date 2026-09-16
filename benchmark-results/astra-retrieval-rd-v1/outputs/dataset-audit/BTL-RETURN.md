# BTL return

The unchanged 20-OCR/18-ASR sample now has one directly inspected representative source frame for every OCR query. All 18 bounded ASR source excerpts are captured and verified, but none was heard because this assistant context does not support audio input. Stored-text inspection covers all 38 rows.

All 38 query/channel host metadata comparisons (37 unique files) and 61 decoded feature-text comparisons match the pinned projected-text archive. All 76 native evidence/analysis directory checks report absent paths. Five exact sampled anchors lose query-critical visible writing at or before stored OCR features: p0_q13, p0_q19, p0_q20, p0_q21, p1_q24. The precise detector/recognizer/normalization cause is unresolved; one of these queries retains its answer text elsewhere in the accepted window. No retrieval-failure rate or CER/WER is inferred.

Structured diagrams, tables, curves and map counts require spatial relationships; some small sign writing is not reliably legible at the representative frame. One still does not adjudicate full event sequences, final states, absence across time, or new truth boundaries. All benchmark truth remains unchanged, including provisional P3 rows.

The original/current sample SHA bridge is exact: only appended input-registry provenance changed, with selected rows, order, metadata, seed/method and truth inputs preserved.

Next source task: use AUDIO_REVIEW_REQUEST.md for the 18 minimal listening checks. The remaining OCR findings are documented source-readability, structural-representation and temporal-coverage limitations; they do not authorize broad extraction or truth edits. Sparse/dense visibility has not been assessed in this dataset audit.

Replay dataset_audit.py, dataset_text_audit.py, dataset_media_audit.py and dataset_remaining_media_audit.py in that order with --root .; hydrate pinned source JSON first if needed.
