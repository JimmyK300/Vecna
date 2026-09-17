# query-variants: NEGATIVE

All counts use113 scoreable queries;115 canonical input rows. Parent control unchanged.

Video metrics: {"R@1": {"mean": 0.4247787610619469, "sum": 48.0}, "R@5": {"mean": 0.5575221238938053, "sum": 63.0}, "R@10": {"mean": 0.6637168141592921, "sum": 75.0}, "R@20": {"mean": 0.7345132743362832, "sum": 83.0}, "MRR@20": {"mean": 0.4891404677635122, "sum": 55.27287285727688}}

Workload: {"new_inference_calls": 0, "provider_calls": 232, "max_query_variants": 3, "same_session_wall_ns": 1904804400, "source": "semantic BM25 only; no new visual embedding/index calls"}

Paired changes (query bootstrap10000, seed82; exploratory, no pristine holdout):

- R@1: delta=-0.008849557522123894; CI=[-0.035398230088495575, 0.017699115044247787]; rescues=['p1_q23']; regressions=['p2_q29', 'p3_q23'].

- R@5: delta=-0.12389380530973451; CI=[-0.19469026548672566, -0.05309734513274336]; rescues=['p0_q20', 'p1_q22', 'p2_q07']; regressions=['p0_q18', 'p1_q01', 'p1_q09', 'p1_q11', 'p1_q17', 'p2_q06', 'p2_q10', 'p2_q14', 'p2_q17', 'p2_q18', 'p2_q20', 'p2_q22', 'p2_q30', 'p3_q07', 'p3_q12', 'p3_q20', 'p3_q30'].

- R@10: delta=-0.061946902654867256; CI=[-0.12389380530973451, 0.0]; rescues=['p0_q20', 'p1_q13', 'p2_q07']; regressions=['p0_q17', 'p1_q01', 'p1_q11', 'p1_q25', 'p2_q18', 'p2_q22', 'p3_q01', 'p3_q20', 'p3_q30', 'p3_q33'].

- R@20: delta=-0.035398230088495575; CI=[-0.09734513274336283, 0.02654867256637168]; rescues=['p0_q20', 'p0_q22', 'p1_q13', 'p2_q07']; regressions=['p0_q17', 'p1_q25', 'p2_q25', 'p3_q03', 'p3_q19', 'p3_q25', 'p3_q30', 'p3_q34'].

- MRR@20: delta=-0.04084854880150642; CI=[-0.06610499365516627, -0.014754596102432689]; rescues=['p0_q20', 'p0_q22', 'p1_q13', 'p1_q22', 'p1_q23', 'p2_q07']; regressions=['p0_q02', 'p0_q05', 'p0_q17', 'p0_q18', 'p0_q23', 'p1_q01', 'p1_q06', 'p1_q09', 'p1_q11', 'p1_q16', 'p1_q17', 'p1_q21', 'p1_q25', 'p2_q02', 'p2_q06', 'p2_q10', 'p2_q14', 'p2_q17', 'p2_q18', 'p2_q20', 'p2_q22', 'p2_q25', 'p2_q29', 'p2_q30', 'p3_q01', 'p3_q03', 'p3_q05', 'p3_q07', 'p3_q12', 'p3_q13', 'p3_q14', 'p3_q19', 'p3_q20', 'p3_q23', 'p3_q25', 'p3_q30', 'p3_q33', 'p3_q34'].

- Pool all_required_targets_present: 78->73; rescues=[]; regressions=['p2_q16', 'p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool target_coverage: 79.0->74.0; rescues=[]; regressions=['p2_q16', 'p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool accepted_video_present: 92->89; rescues=['p0_q20', 'p0_q22', 'p1_q13', 'p2_q07']; regressions=['p0_q24', 'p1_q02', 'p2_q16', 'p3_q15', 'p3_q19', 'p3_q32', 'p3_q34'].

All capability/truth/task/phase slices, diversity and failure classes: ../outputs/diagnostics-v2/arms.json and per_query.jsonl.
Frozen frame/range/event and frame-position-video metrics remain separate in the machine-readable summary.
