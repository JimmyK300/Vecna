# packet-e: NEGATIVE

All counts use113 scoreable queries;115 canonical input rows. Parent control unchanged.

Video metrics: {"R@1": {"mean": 0.4336283185840708, "sum": 49.0}, "R@5": {"mean": 0.6814159292035398, "sum": 77.0}, "R@10": {"mean": 0.7168141592920354, "sum": 81.0}, "R@20": {"mean": 0.7345132743362832, "sum": 83.0}, "MRR@20": {"mean": 0.533912228381255, "sum": 60.332081807081806}}

Workload: {"new_provider_calls": 0, "new_inference_calls": 0, "query_variants": 0, "queries_replayed": 115, "max_admitted_frames": 100, "membership_changed_queries": 115, "same_session_wall_ns_total": {"control": 87245600, "e1": 67680900}}

Paired changes (query bootstrap10000, seed82; exploratory, no pristine holdout):

- R@1: delta=0.0; CI=[-0.02654867256637168, 0.02654867256637168]; rescues=['p1_q16']; regressions=['p0_q16'].

- R@5: delta=0.0; CI=[-0.02654867256637168, 0.02654867256637168]; rescues=['p3_q33']; regressions=['p0_q16'].

- R@10: delta=-0.008849557522123894; CI=[-0.02654867256637168, 0.0]; rescues=[]; regressions=['p1_q25'].

- R@20: delta=-0.035398230088495575; CI=[-0.07079646017699115, -0.008849557522123894]; rescues=[]; regressions=['p1_q25', 'p2_q25', 'p3_q19', 'p3_q34'].

- MRR@20: delta=0.003923211816236282; CI=[-0.016966100498928452, 0.02114246573528847]; rescues=['p0_q05', 'p0_q18', 'p1_q16', 'p1_q22', 'p2_q06', 'p2_q10', 'p2_q14', 'p2_q17', 'p2_q20', 'p2_q22', 'p3_q03', 'p3_q07', 'p3_q33']; regressions=['p0_q16', 'p1_q25', 'p2_q25', 'p3_q19', 'p3_q34'].

- Pool all_required_targets_present: 78->71; rescues=['p0_q02', 'p0_q20']; regressions=['p0_q04', 'p0_q18', 'p1_q01', 'p1_q22', 'p2_q16', 'p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool target_coverage: 79.0->71.75; rescues=['p0_q02', 'p0_q20']; regressions=['p0_q04', 'p0_q18', 'p1_q01', 'p1_q22', 'p2_q16', 'p2_q30', 'p3_q03', 'p3_q15', 'p3_q20', 'p3_q30'].

- Pool accepted_video_present: 92->90; rescues=['p0_q20', 'p0_q22', 'p2_q07', 'p3_q17', 'p3_q21', 'p3_q29']; regressions=['p1_q02', 'p1_q25', 'p2_q16', 'p2_q25', 'p3_q15', 'p3_q19', 'p3_q32', 'p3_q34'].

All capability/truth/task/phase slices, diversity and failure classes: ../outputs/diagnostics-v2/arms.json and per_query.jsonl.
Frozen frame/range/event and frame-position-video metrics remain separate in the machine-readable summary.
