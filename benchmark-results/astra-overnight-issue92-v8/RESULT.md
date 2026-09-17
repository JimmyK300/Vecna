# English variant reranking: negative, no promotion

Job20260916T203910Z-a97dfe29df ran20:39:11Z to22:16:04Z and exited0.
Scientific verification passed all policy and19756 OCR/ASR source hashes,
115 cache hashes and variant identities, exact accepted v5 control, unchanged
100-frame membership/first frame, independent ranking reconstruction and
rescoring113 eligible queries. validation/vs-pr91 includes the original control.

| Video metric | PR91 | Accepted v5 | English variant |
|---|---:|---:|---:|
| R@1 |49|49|49|
| R@5 |77|77|78|
| R@10 |82|85|85|
| R@20 |87|90|88|
| MRR@20 |0.5299890165650186|0.5406434596816525|0.5382430499687137|

Candidate correct-video94 and complete-target80 remain unchanged. Versus v5,
R20 loses p2_q16,p3_q15 with no rescues. R5 rescues p3_q25,p3_q30 and loses
p2_q30. R10 rescues p1_q25,p3_q12 and loses p2_q07,p3_q15. MRR improves12
queries and regresses10; delta-0.0024004097129388235,95% interval
[-0.009608600140738008,0.0043244239587975]. Full IDs and all frame/event metrics
remain in machine-readable summaries/per_query files. No query-specific repairs.

Workload10823 new English pair scores;10823 canonical scores inherited from
v5 for the ranking mixture (the inference counter reused_pairs0 describes
English fallback only).10 English pairs truncated at1024 tokens. New-pair
wall5786.4058934seconds this session. No new translation, embedding, extraction
or download. Speed is not a generalizable result. Policy SHA256:
a1f6d204e6daf4b67c14629615ee0dc1f21034c9dacf82a37f8c23e27e7993c7.

v5 remains the strongest accepted arm. Further work addresses the separate
semantic candidate-admission coverage tradeoff rather than tuning this variant.
Repeated benchmark caveat, source branch/base and dirty state are in README.
Uncommitted, no production merge or remote SHA. Verification added post-run,
bound in this archive's manifest, with no inference rerun.
