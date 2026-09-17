# query-translation: NEGATIVE

All counts use113 scoreable queries;115 canonical input rows. Parent control unchanged.

Video metrics: {"R@1": {"mean": 0.39823008849557523, "sum": 45.0}, "R@5": {"mean": 0.5398230088495575, "sum": 61.0}, "R@10": {"mean": 0.6371681415929203, "sum": 72.0}, "R@20": {"mean": 0.7079646017699115, "sum": 80.0}, "MRR@20": {"mean": 0.46937618168747786, "sum": 53.039508530685}}

Workload: null

Paired changes (query bootstrap10000, seed82; exploratory, no pristine holdout):

- R@1: delta=-0.035398230088495575; CI=[-0.08849557522123894, 0.017699115044247787]; rescues=['p1_q16', 'p1_q23', 'p3_q07']; regressions=['p0_q01', 'p0_q04', 'p1_q03', 'p1_q24', 'p2_q29', 'p3_q04', 'p3_q23'].

- R@5: delta=-0.1415929203539823; CI=[-0.20353982300884957, -0.07964601769911504]; rescues=[]; regressions=['p0_q18', 'p1_q01', 'p1_q09', 'p1_q11', 'p1_q17', 'p1_q21', 'p2_q10', 'p2_q14', 'p2_q17', 'p2_q18', 'p2_q20', 'p2_q22', 'p2_q30', 'p3_q12', 'p3_q20', 'p3_q30'].

- R@10: delta=-0.08849557522123894; CI=[-0.1415929203539823, -0.035398230088495575]; rescues=[]; regressions=['p0_q17', 'p1_q01', 'p1_q11', 'p1_q22', 'p1_q25', 'p2_q18', 'p3_q01', 'p3_q20', 'p3_q30', 'p3_q33'].

- R@20: delta=-0.061946902654867256; CI=[-0.10619469026548672, -0.017699115044247787]; rescues=[]; regressions=['p0_q17', 'p1_q25', 'p2_q25', 'p3_q03', 'p3_q19', 'p3_q25', 'p3_q34'].

- MRR@20: delta=-0.06061283487754076; CI=[-0.09339561945154735, -0.027370417193426047]; rescues=['p1_q16', 'p1_q23', 'p3_q07']; regressions=['p0_q01', 'p0_q04', 'p0_q05', 'p0_q17', 'p0_q18', 'p0_q23', 'p1_q01', 'p1_q03', 'p1_q06', 'p1_q09', 'p1_q11', 'p1_q17', 'p1_q21', 'p1_q22', 'p1_q24', 'p1_q25', 'p2_q02', 'p2_q06', 'p2_q10', 'p2_q14', 'p2_q17', 'p2_q18', 'p2_q20', 'p2_q22', 'p2_q25', 'p2_q29', 'p2_q30', 'p3_q01', 'p3_q03', 'p3_q04', 'p3_q05', 'p3_q12', 'p3_q13', 'p3_q19', 'p3_q20', 'p3_q23', 'p3_q25', 'p3_q30', 'p3_q33', 'p3_q34'].

- Pool all_required_targets_present: 78->73; rescues=[]; regressions=['p2_q16', 'p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool target_coverage: 79.0->74.0; rescues=[]; regressions=['p2_q16', 'p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool accepted_video_present: 92->89; rescues=['p1_q14', 'p2_q01', 'p2_q03']; regressions=['p0_q24', 'p1_q02', 'p2_q16', 'p3_q15', 'p3_q19', 'p3_q34'].

All capability/truth/task/phase slices, diversity and failure classes: ../outputs/diagnostics-v2/arms.json and per_query.jsonl.
Frozen frame/range/event and frame-position-video metrics remain separate in the machine-readable summary.
