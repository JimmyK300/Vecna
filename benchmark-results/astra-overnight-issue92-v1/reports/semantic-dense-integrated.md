# semantic-dense-integrated: NEGATIVE

All counts use113 scoreable queries;115 canonical input rows. Parent control unchanged.

Video metrics: {"R@1": {"mean": 0.36283185840707965, "sum": 41.0}, "R@5": {"mean": 0.5752212389380531, "sum": 65.0}, "R@10": {"mean": 0.7079646017699115, "sum": 80.0}, "R@20": {"mean": 0.7787610619469026, "sum": 88.0}, "MRR@20": {"mean": 0.4728088969564763, "sum": 53.42740535608183}}

Workload: null

Paired changes (query bootstrap10000, seed82; exploratory, no pristine holdout):

- R@1: delta=-0.07079646017699115; CI=[-0.13274336283185842, -0.008849557522123894]; rescues=['p0_q23', 'p1_q23', 'p2_q20']; regressions=['p0_q01', 'p0_q04', 'p0_q07', 'p1_q03', 'p1_q10', 'p1_q24', 'p2_q12', 'p2_q15', 'p2_q29', 'p3_q04', 'p3_q23'].

- R@5: delta=-0.10619469026548672; CI=[-0.17699115044247787, -0.04424778761061947]; rescues=['p0_q20', 'p2_q07']; regressions=['p0_q18', 'p1_q01', 'p1_q09', 'p1_q21', 'p1_q24', 'p2_q02', 'p2_q10', 'p2_q14', 'p2_q17', 'p2_q18', 'p2_q22', 'p2_q30', 'p3_q20', 'p3_q30'].

- R@10: delta=-0.017699115044247787; CI=[-0.07079646017699115, 0.035398230088495575]; rescues=['p0_q20', 'p1_q13', 'p2_q07', 'p2_q25']; regressions=['p0_q17', 'p1_q01', 'p1_q25', 'p3_q01', 'p3_q20', 'p3_q30'].

- R@20: delta=0.008849557522123894; CI=[-0.04424778761061947, 0.07079646017699115]; rescues=['p0_q20', 'p1_q13', 'p1_q14', 'p2_q03', 'p2_q07', 'p3_q17']; regressions=['p0_q17', 'p3_q03', 'p3_q19', 'p3_q25', 'p3_q34'].

- MRR@20: delta=-0.05718011960854231; CI=[-0.10123929872400722, -0.014270922173869867]; rescues=['p0_q20', 'p0_q23', 'p1_q11', 'p1_q13', 'p1_q14', 'p1_q22', 'p1_q23', 'p2_q03', 'p2_q07', 'p2_q20', 'p2_q25', 'p3_q07', 'p3_q12', 'p3_q17']; regressions=['p0_q01', 'p0_q04', 'p0_q05', 'p0_q07', 'p0_q17', 'p0_q18', 'p1_q01', 'p1_q03', 'p1_q06', 'p1_q09', 'p1_q10', 'p1_q16', 'p1_q17', 'p1_q21', 'p1_q24', 'p1_q25', 'p2_q02', 'p2_q06', 'p2_q10', 'p2_q12', 'p2_q14', 'p2_q15', 'p2_q17', 'p2_q18', 'p2_q22', 'p2_q29', 'p2_q30', 'p3_q01', 'p3_q03', 'p3_q04', 'p3_q05', 'p3_q13', 'p3_q19', 'p3_q20', 'p3_q23', 'p3_q25', 'p3_q30', 'p3_q33', 'p3_q34'].

- Pool all_required_targets_present: 78->74; rescues=[]; regressions=['p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool target_coverage: 79.0->75.0; rescues=[]; regressions=['p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool accepted_video_present: 92->96; rescues=['p0_q20', 'p0_q22', 'p1_q13', 'p1_q14', 'p2_q01', 'p2_q03', 'p2_q07', 'p3_q17']; regressions=['p0_q24', 'p1_q02', 'p3_q15', 'p3_q32'].

All capability/truth/task/phase slices, diversity and failure classes: ../outputs/diagnostics-v2/arms.json and per_query.jsonl.
Frozen frame/range/event and frame-position-video metrics remain separate in the machine-readable summary.
