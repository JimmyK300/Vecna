# Video-preserving admission: video gains, target losses

Job20260916T222511Z-5a0277a9ee ran22:25:12Z to22:31:14Z, exit0.
Acceptance passed17984 source hashes,115 cache hashes,10222 reused scores from
v5/v6 with identical query/text/model, deterministic admission/ranking replay,
100membership, first-frame and every-incumbent-video guarantees,113 rescored
rows and original PR91 comparison. See validation/accepted.json.

| Metric | PR91 | Accepted v5 | Video-preserving semantic |
|---|---:|---:|---:|
| R@1 |49|49|49|
| R@5 |77|77|75|
| R@10 |82|85|83|
| R@20 |87|90|92|
| MRR@20 |0.5299890165650186|0.5406434596816525|0.5407327877577063|
| Complete-target candidate coverage |78|80|78|
| Correct-video candidate coverage |92|94|101|

No promotion: exact-target coverage worsens despite guaranteed incumbent video
retention. This distinguishes video-level diversity from useful exact-frame
coverage. Complete-target rescue p0_q20; losses p0_q02,p0_q06,p2_q07. Fractional
coverage also loses p2_q29. R20 rescues p0_q20,p0_q22, no losses versus v5.
Video-pool gains p0_q20,p0_q22,p1_q13,p1_q14,p2_q01,p2_q03,p3_q17, no losses.
R5 and R10 each lose2. All disagreement IDs/layers and intervals are preserved
in outputs and validation/vs-pr91; no answer-aware frame protection or repair.

MRR delta versus v5+0.00008932807605373976;95% interval
[-0.0045024621816366125,0.0050977806705275255]. Repeated benchmark, exploratory.
Versus PR91 R20+5/113 and MRR+0.0107437711926876, with complete78 unchanged;
this does not supersede the stronger v5 coverage. Workload441 new pairs,
10222 reused,5 new truncated pairs;332.9943835seconds new-pair inference.
No extraction/embedding/download. Policy SHA256:
49ae2b218d0b3a5736c5d6c91d59205029e83ccd32d1efd8d14419ee8e772066.
Verification added post-run and bound in archive; uncommitted, no remote SHA.
