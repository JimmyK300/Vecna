# Vecna82 Browser Task Lead return

**Next state: READY_FOR_PARENT_REVIEW.** Packets0–D are complete with the documented evidence limits. Packet E is exactly one proposal and has not been implemented. All work is on owned review branches.

## Result

| Packet | Answer |
|---|---|
| 0 | Frozen 115 canonical identities, 113 scoreable rows, unchanged exclusions and exact source/control hashes. |
| A | Native ordered images improve correct-video top1 from 0/8 to 2/8 in the fixed three-window pool. This is a narrow positive ranking signal; zero of 31 required event anchors are exposed. |
| B | Current fusion is the best supported frozen family: distinct-video R20 87/113 and MRR 0.529989. RRF/minmax/robust/softmax reach 85/84/81/86, respectively, with lower MRR. Current versus matched Qwen gives 3 R20 rescues and 0 regressions; uncertainty remains. |
| C | Historical frozen range/event R20 rises 68→76/113 with 9 rescues and 1 regression. Average observed reranking latency is 28.219s; retain experimental/operator-triggered use. |
| D | 113 complete rows, 82 descriptive observed successes and 31 misses: 6 missing accepted videos, 18 missing required frame/event targets, 7 unresolved. Labels describe the inspected saved pools. |
| E | One fixed provider-balanced admission proposal at the existing100-frame budget, using saved lists and unchanged fusion scores. Its ceiling is 3 full-target opportunities and 1 partial opportunity; no new arm was constructed. |

## Proof

The report and per-query files preserve all ranks, source observations, paired uncertainty, representative candidate movement and exact comparison boundaries. `outputs/failure-ledger/provenance.json` hashes 49 consumed inputs and the generator. The final [host run](https://github.com/JimmyK300/ai-routing-hub/actions/runs/35112926368) passed 40 fusion/recovery/storage tests and 27 ledger tests, reconstructed the full study byte for byte and repeated all four ledger outputs byte for byte. Independent D review passed 3,611 assertions with no material finding.

The ledger SHA-256 is `f344d6a572fcccaf7ee927774f0f76fd22008820514298f23a7ffeefd16abd6d`. The exact study SHA-256 is `ba47bd96eb842d0bb57811e247cbd2ea29de8794c5dd3b289dce24a3032c10b1`. Its lossless raw archive and timing sidecar are durable Git artifacts; a fresh checkout can reproduce them without an expiring execution download.

Separately, PR88 verifies all 625 Qwen tensors  / 2,127,532,032 elements and empty loading diagnostics. PR90 passes9 production-method tests over 13 fixtures and three independent process seeds. Neither repair is silently inserted into the frozen historical evidence.

The fresh published Git snapshot also passed remote-binary hydration, exact study reconstruction, all 49 input hashes and all four ledger output comparisons in [run35114902098](https://github.com/JimmyK300/ai-routing-hub/actions/runs/35114902098). Its result is `outputs/synthesis/published-snapshot-verification.json`.

## Uncertainty

Forty-one queries retain provisional/proxy truth qualifications. All 18 captured ASR excerpts remain unheard. Historical corpus encoder/index lineage is unresolved. The native-image pool contains correct videos for only 2/8 queries and no required event anchor. Historical C and fresh B use different candidate surfaces; their success union and interaction sets are descriptive. Bootstrap intervals use the same cohort and are not held-out validation. Exact study reconstruction was proved on Windows Python3.12.1 and must fail if another platform changes any non-timing byte.

## Work location

| Work | Branch / review |
|---|---|
| Consolidated D/E/report | `btl/issue-82-failure-ledger-and-proposal` |
| Packet0/C | `btl/issue-82-astra-retrieval-rd`, PR83 |
| Packet B | `btl/issue-82-fusion-study`, PR84 |
| Packet A | `btl/issue-82-native-images`, PR85 |
| Source and text visibility | `btl/issue-82-source-review`, PR87 |
| Verified loader correction | `btl/issue-86-qwen-checkpoint-loading`, PR88 |
| Deterministic text-score ties | `btl/issue-89-deterministic-text-ties`, PR90 |
| Native dataset overlays | `astra/dataset-review-16-17-20260916`, dataset PR18 |

Supporting issues16/17 received their evidence-backed returns and remain open for the unresolved source-truth and audio/lineage questions.

## Scope check and next state

Vecna main remains `95d63a6abf10c598e0e54af7d2071bedbe542d1e`; dataset main remains `1f1ad1baef1e1d31817f6c5a12d4d94133611038`. No merges occurred. No production fusion integration, model-family expansion, full-corpus re-embedding, training, truth promotion or query rewriting was performed. Scratch loss was handled through verified model-free recovery, and both completed captures were preserved.

The review branches are ready for parent review. E's admission experiment remains proposed. This return does not authorize or perform an integration into main.
