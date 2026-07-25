# Vecna Retrieval Benchmark Report

> **Scope**: Evaluated on ImageCLIP, OCR, and ASR modalities (VideoCLIP excluded).

## Overall Performance Summary

| Metric | Value |
| --- | ---: |
| **Total Queries** | 16 |
| **Recall@1** | 0.0% |
| **Recall@5** | 0.0% |
| **Recall@20** | 0.0% |
| **MRR** | 0.0000 |
| **Median Rank** | 0.0 |
| **Avg Latency** | 133.29 ms |

## Recall by Query Category

| Category | Queries | Recall@1 | Recall@5 | Recall@20 | MRR | Latency (ms) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `actions` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 169.36 |
| `asr_dependent` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 8.69 |
| `combined` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 159.19 |
| `hard_negatives` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 170.28 |
| `ocr_dependent` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 43.73 |
| `people_and_attributes` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 159.36 |
| `temporal` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 162.76 |
| `visual_objects_and_scenes` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 192.93 |


## Recall by Expected Modality

| Expected Modality | Queries | Recall@1 | Recall@5 | Recall@20 | MRR | Latency (ms) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `image_clip` | 10 | 0.00 | 0.00 | 0.00 | 0.0000 | 170.94 |
| `ocr` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 43.73 |
| `asr` | 2 | 0.00 | 0.00 | 0.00 | 0.0000 | 8.69 |
| `asr+image_clip` | 1 | 0.00 | 0.00 | 0.00 | 0.0000 | 157.58 |
| `image_clip+ocr` | 1 | 0.00 | 0.00 | 0.00 | 0.0000 | 160.8 |


## Failure Taxonomy Analysis

| Failure Reason | Count |
| :--- | ---: |
| `correct_result_outside_top_20` | 16 |

