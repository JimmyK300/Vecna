# Issue #34 historical headless benchmark

This directory contains the inspectable historical inventory for
[Vecna Issue #34](https://github.com/JimmyK300/Vecna/issues/34). It is an
evaluation dataset, not corpus content.

## Inventory and completeness

`issue34_headless_queries.csv` has 42 stable records:

- `set1_q01`-`set1_q20`: the 20 records in the Issue attachment
  `Questions.txt`.
- `p1_q01`-`p1_q22`: 21 numbered records plus the standalone unsolved item
  `22:` in the Issue attachment `p1.txt`.

The Issue comment says `p1.txt` contains 20 questions, but the attachment is
authoritative and contains 22 recoverable items. Two records are external-media
VKIS queries. Their actual Issue asset URLs are recorded in `media_source_url`,
but the assets and their byte hashes are not bundled because the current backend
cannot execute external-media queries. `p1_q22` has no official answer.
`set1_q20` preserves the official reversed key `2985 -> 2955` but is unscoreable
until endpoint semantics are reviewed.

The `p1.txt` footer labels Questions `(1, 21, 22)` as unsolved even though its
Question 1 and Question 21 blocks also provide answer keys (Question 21 provides
two alternatives). Those keys are retained as provisional and the contradiction
is explicit in the two row notes; Question 22 alone has no key.

The CSV preserves every nonempty official query, hint, and answer string after
newline normalization. It includes the text/key attachment URL and SHA-256 on
every row, plus separate media-asset URLs for Questions 4 and 12.
`validation_state` deliberately does **not** claim corpus validation: source text
has been verified, but no result set has been manually adjudicated on the current
corpus. Formally validated rows therefore remain zero.

As a reviewed local scope policy (not metadata asserted by the source
attachments), all 20 `Questions.txt` records are marked
`exclude_different_dataset` and all 22 `p1.txt` records are marked
`include_current_dataset`. The `V###` versus `L##_V###` answer-key namespaces are
the supporting evidence. The default harness scope therefore selects 22
current-corpus records: 21 provisional scoreable text queries and one
unscoreable query. `--evaluation-scope all` is partition-only historical audit
mode; it must not produce a mixed-corpus primary metric.

## Conditions

- `Q0`: the official text in `query`, unchanged.
- `Q1`: Q0 plus `hint_1`.
- `Q2`: Q0 plus `hint_1` and `hint_2`.
- `QN`: Q0 plus every available hint, in order.

For TKIS records whose source supplies only `Hint 1` and no distinct question
body, that first official text is preserved verbatim as Q0. The mapping is
explicit in `official_text_mapping`; it is not a paraphrase or optimization.
Q0 is the primary baseline. Hint-condition summaries use the questions that
actually have that many hints, so denominators are reported per condition.

## Ground-truth semantics

Official integer coordinates are treated as source-frame counters, matching the
indexed `<video_id>#<frame_id>` coordinate. The current harness performs no
frame-to-timestamp conversion.

- Video IDs are normalized case-insensitively and may include an `L##_` prefix.
- Interval endpoints are inclusive.
- Point labels use exact-frame matching by default. A tolerance is allowed only
  as an explicit command-line value and must be justified in the run report.
- Multiple answers in `answer` and `answer_alt_N` are alternatives; any complete
  accepted target may match.
- TRAKE comma-separated points are separate required events and report event
  recall.
- Video-only official keys match any frame in that video, but the three such
  records are outside the current-corpus default and are flagged for interval
  review.
- QA text after a key is preserved but not judged. This benchmark measures
  supporting-frame retrieval, not answer extraction correctness.

Metrics are judged only from the first 20 deterministic results: Recall@1,
Recall@5, primary Recall@10, Recall@20, reciprocal rank/MRR@20, median first-hit
rank within 20, no-hit-within-20 count, and retrieval latency. Equal scores are
tie-broken by stable frame identity.

## Safe commands

Dataset-only validation does not load models or connect to Milvus:

```powershell
python script/headless_benchmark.py `
  --csv benchmark/issue34_headless_queries.csv `
  --target-features image_clip_pe-l-14-336 `
  --dry-run
```

A real run must be launched from the exact Vecna workspace containing
`config.yaml`, after the runtime inventory and restore verification pass. The
harness directly checks that the configured collection already exists and is
nonempty before constructing `Searcher`, preventing accidental empty-collection
creation. By default it refuses a real run while selected answer keys remain
provisional. `--allow-provisional-ground-truth` is an explicit exploratory
override; such results remain separately labeled and never become the validated
primary baseline. Do not run the full benchmark until corpus scope and remaining
ground-truth flags have been reviewed.
