# semantic-grounding: NEGATIVE

All counts use113 scoreable queries;115 canonical input rows. Parent control unchanged.

Video metrics: {"R@1": {"mean": 0.3893805309734513, "sum": 44.0}, "R@5": {"mean": 0.5663716814159292, "sum": 64.0}, "R@10": {"mean": 0.6548672566371682, "sum": 74.0}, "R@20": {"mean": 0.7876106194690266, "sum": 89.0}, "MRR@20": {"mean": 0.4685216077641212, "sum": 52.9429416773457}}

Workload: null

Paired changes (query bootstrap10000, seed82; exploratory, no pristine holdout):

- R@1: delta=-0.04424778761061947; CI=[-0.12389380530973451, 0.035398230088495575]; rescues=['p0_q02', 'p0_q23', 'p1_q11', 'p1_q17', 'p2_q02', 'p2_q18', 'p3_q05', 'p3_q12', 'p3_q20']; regressions=['p1_q07', 'p1_q08', 'p1_q10', 'p1_q12', 'p1_q20', 'p1_q24', 'p2_q04', 'p2_q08', 'p2_q09', 'p2_q13', 'p2_q21', 'p3_q27', 'p3_q28', 'p3_q36'].

- R@5: delta=-0.11504424778761062; CI=[-0.19469026548672566, -0.04424778761061947]; rescues=['p1_q22', 'p1_q25', 'p3_q01', 'p3_q33']; regressions=['p1_q06', 'p1_q07', 'p1_q08', 'p1_q09', 'p1_q12', 'p1_q16', 'p1_q21', 'p2_q04', 'p2_q08', 'p2_q09', 'p2_q10', 'p2_q13', 'p2_q14', 'p2_q17', 'p2_q22', 'p2_q30', 'p3_q30'].

- R@10: delta=-0.07079646017699115; CI=[-0.13274336283185842, -0.008849557522123894]; rescues=['p2_q07', 'p2_q16', 'p2_q25']; regressions=['p0_q17', 'p1_q06', 'p1_q09', 'p1_q16', 'p1_q21', 'p2_q08', 'p2_q09', 'p2_q14', 'p2_q17', 'p2_q22', 'p3_q30'].

- R@20: delta=0.017699115044247787; CI=[-0.02654867256637168, 0.07079646017699115]; rescues=['p0_q20', 'p1_q13', 'p2_q03', 'p2_q07', 'p2_q16']; regressions=['p0_q17', 'p1_q16', 'p3_q25'].

- MRR@20: delta=-0.06146740880089739; CI=[-0.12720578926520357, 0.0019583892211395668]; rescues=['p0_q02', 'p0_q20', 'p0_q23', 'p1_q01', 'p1_q11', 'p1_q13', 'p1_q17', 'p1_q22', 'p1_q25', 'p2_q02', 'p2_q03', 'p2_q06', 'p2_q07', 'p2_q16', 'p2_q18', 'p2_q20', 'p2_q25', 'p3_q01', 'p3_q03', 'p3_q05', 'p3_q07', 'p3_q12', 'p3_q19', 'p3_q20', 'p3_q33']; regressions=['p0_q05', 'p0_q17', 'p1_q06', 'p1_q07', 'p1_q08', 'p1_q09', 'p1_q10', 'p1_q12', 'p1_q16', 'p1_q20', 'p1_q21', 'p1_q24', 'p2_q04', 'p2_q08', 'p2_q09', 'p2_q10', 'p2_q13', 'p2_q14', 'p2_q17', 'p2_q21', 'p2_q22', 'p2_q30', 'p3_q25', 'p3_q27', 'p3_q28', 'p3_q30', 'p3_q36'].

- Pool all_required_targets_present: 78->75; rescues=['p0_q20']; regressions=['p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool target_coverage: 79.0->76.0; rescues=['p0_q20']; regressions=['p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool accepted_video_present: 92->96; rescues=['p0_q20', 'p0_q22', 'p1_q13', 'p1_q14', 'p2_q01', 'p2_q03', 'p2_q07', 'p3_q17']; regressions=['p0_q24', 'p1_q02', 'p3_q15', 'p3_q32'].

All capability/truth/task/phase slices, diversity and failure classes: ../outputs/diagnostics-v2/arms.json and per_query.jsonl.
Frozen frame/range/event and frame-position-video metrics remain separate in the machine-readable summary.
