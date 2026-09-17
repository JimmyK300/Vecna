# Protected deeper frame-text ranking: exploratory positive

Job20260916T182140Z-d149c6291d completed at2026-09-16T19:44:59Z.
code/verify.py verified all policy dependencies,19756 source hashes,115 cache
hashes, exact temporal5s control, unchanged100-frame membership, first-frame
protection, deterministic ranking replay, and all2299 reused logits against
identical query hashes/text/model identities. All113 scored rows and aggregate
metrics reproduced; comparison to the exact PR91 control is included under
validation/vs-pr91. Two focused tests passed before inference.

| Distinct-video metric | Exact PR91 | Temporal5s | Temporal5s + protected text |
|---|---:|---:|---:|
| R@1 count |49|49|49|
| R@5 count |77|77|77|
| R@10 count |82|82|85|
| R@20 count |87|88|90|
| MRR@20 |0.5299890165650186|0.5306697517590282|0.5406434596816525|

Versus PR91, R@20 rescues are p2_q07,p2_q16,p3_q15,p3_q35; regression p3_q34.
Versus temporal5s, the same list excludes p3_q35 from rescues. R@10 has five
rescues and two regressions; R@5 has four rescues and four regressions. MRR
improves on16 queries and regresses on16. All paired IDs are retained in both
machine-readable comparison summaries.

PR91-relative R@20 delta +3/113; paired95% bootstrap interval
[-0.008849557522123894,0.07079646017699115]. MRR delta
+0.01065444311663386; interval[-0.004895938213255127,0.026729442161474538].
These intervals include zero. The frozen promotion gate passes on point
estimates, so this is the working best exploratory architecture, not a proven
generalization improvement. It preserves temporal5s candidate correct-video
presence94/113 and complete-target coverage80/113 (PR91:92 and78).

Workload:10823 pair scores,8524 new inference pairs,2299 reused exact saved
scores. New pairs include12 truncated at1024 tokens. New-pair inference wall
time4970.1720394 seconds in this session. No new corpus embedding or frame
extraction. CPU float32, batch2, eight threads; model loading audit retained.
Do not interpret this as a production speed result or hide truncation.

Policy SHA-256:
1ebb454de5206d425efec699933a940d4a519277a7c4a487b5f16d9e0058b867.
All data/code/model paths are hash-bound; runnable preparation, inference,
verification and focused tests are included. Verification was added after
inference and is separately bound by the archive manifest. Uncommitted branch
and inherited dirty-state caveat remain; no production changes or remote SHA.

Next experiment changes admission only upstream of this same ranker:80
temporal5s frames plus20 unique cached grounded-semantic frames. No double
reranking of the accepted final output; apply the protected RRF60 stage once.
