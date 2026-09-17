# yolo: INCONCLUSIVE

All counts use113 scoreable queries;115 canonical input rows. Parent control unchanged.

Video metrics: {"R@1": {"mean": 0.4424778761061947, "sum": 50.0}, "R@5": {"mean": 0.672566371681416, "sum": 76.0}, "R@10": {"mean": 0.7256637168141593, "sum": 82.0}, "R@20": {"mean": 0.7699115044247787, "sum": 87.0}, "MRR@20": {"mean": 0.5370686625827178, "sum": 60.68875887184711}}

Workload: {"new_inference_calls": 0, "provider_calls": 0, "read_detection_files": 843, "applicable_queries": 38, "queries_with_detection_coverage": 22, "queries_with_boost": 5, "boosted_frame_appearances": 20, "same_session_wall_ns": 4399439800}

Paired changes (query bootstrap10000, seed82; exploratory, no pristine holdout):

- R@1: delta=0.008849557522123894; CI=[0.0, 0.02654867256637168]; rescues=['p2_q30']; regressions=[].

- R@5: delta=-0.008849557522123894; CI=[-0.02654867256637168, 0.0]; rescues=[]; regressions=['p3_q07'].

- R@10: delta=0.0; CI=[0.0, 0.0]; rescues=[]; regressions=[].

- R@20: delta=0.0; CI=[0.0, 0.0]; rescues=[]; regressions=[].

- MRR@20: delta=0.007079646017699114; CI=[-0.003244837758112095, 0.02359882005899705]; rescues=['p2_q18', 'p2_q30']; regressions=['p3_q07', 'p3_q13'].

- Pool all_required_targets_present: 78->78; rescues=[]; regressions=[].

- Pool target_coverage: 79.0->79.0; rescues=[]; regressions=[].

- Pool accepted_video_present: 92->92; rescues=[]; regressions=[].

All capability/truth/task/phase slices, diversity and failure classes: ../outputs/diagnostics-v2/arms.json and per_query.jsonl.
Frozen frame/range/event and frame-position-video metrics remain separate in the machine-readable summary.
