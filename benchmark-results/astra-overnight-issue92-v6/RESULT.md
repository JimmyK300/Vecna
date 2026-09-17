# Semantic admission: coverage tradeoff, no promotion

Job20260916T200926Z-cb7370a67b ran20:09:27Z to20:32:40Z, exit0.
Scientific verification passed:18110 source hashes,115 caches,8567 reused
pair identities, exact accepted v5 control, deterministic admission and ranking
replay,100 unique candidates, first80 admission prefix, protected first frame,
and independent rescoring of113 eligible queries. See validation/accepted.json.

| Distinct-video metric | PR91 | Accepted v5 | Semantic80plus20 |
|---|---:|---:|---:|
| R@1 |49|49|49|
| R@5 |77|77|75|
| R@10 |82|85|83|
| R@20 |87|90|92|
| MRR@20 |0.5299890165650186|0.5406434596816525|0.5408393301417768|
| Complete-target candidate coverage |78|80|79|
| Correct-video candidate coverage |92|94|100|

The predeclared promotion gate fails because complete-target coverage drops.
This is a useful Pareto tradeoff, not an overall accepted improvement. Retain
v5 as the working parent. R20 rescues versus v5: p0_q20,p0_q22; no regressions.
Complete-target rescue p0_q20; losses p0_q02,p2_q07. Video presence gains six
queries without losses, but that does not imply exact-frame/target coverage.
R5 loses p2_q18,p3_q35; R10 loses p2_q07,p3_q15. MRR has7 improvements/8 losses.
Full IDs, frame/event metrics and paired intervals are in outputs/summary.json
and validation/vs-pr91/summary.json. No query-specific response to these losses.

Versus v5 MRR delta0.00019587046012427525,95% interval
[-0.004393642973706811,0.005194215178838039]. Versus PR91 R20+5/113,
MRR+0.010850313576758136. Repeated benchmark; no generalization claim.

Workload:2109 new pairs,8567 reused pairs,14 new truncated pairs at1024 tokens;
1350.9702767seconds new-pair wall time. No new extraction, embedding or download.
Policy cdb3136a1a5694ef8b0d46e3f82a3c40ef71d47414af43eedd6feb61aca85ba5.
Verification code added post-run and archived separately. Source branch/base
and dirty-state caveat remain as README documents; no commit/push/merge.
