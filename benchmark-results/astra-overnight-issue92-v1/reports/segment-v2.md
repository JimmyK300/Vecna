# segment-v2: INCONCLUSIVE

All counts use113 scoreable queries;115 canonical input rows. Parent control unchanged.

Video metrics: {"R@1": {"mean": 0.4336283185840708, "sum": 49.0}, "R@5": {"mean": 0.6814159292035398, "sum": 77.0}, "R@10": {"mean": 0.7256637168141593, "sum": 82.0}, "R@20": {"mean": 0.7699115044247787, "sum": 87.0}, "MRR@20": {"mean": 0.5299890165650186, "sum": 59.88875887184711}}

Workload: {"new_inference_calls": 0, "provider_calls": 0, "wall_ns_total": 187564300}

Paired changes (query bootstrap10000, seed82; exploratory, no pristine holdout):

- R@1: delta=0.0; CI=[0.0, 0.0]; rescues=[]; regressions=[].

- R@5: delta=0.0; CI=[0.0, 0.0]; rescues=[]; regressions=[].

- R@10: delta=0.0; CI=[0.0, 0.0]; rescues=[]; regressions=[].

- R@20: delta=0.0; CI=[0.0, 0.0]; rescues=[]; regressions=[].

- MRR@20: delta=0.0; CI=[0.0, 0.0]; rescues=[]; regressions=[].

- Pool all_required_targets_present: 78->78; rescues=[]; regressions=[].

- Pool target_coverage: 79.0->79.0; rescues=[]; regressions=[].

- Pool accepted_video_present: 92->92; rescues=[]; regressions=[].

All capability/truth/task/phase slices, diversity and failure classes: ../outputs/diagnostics-v2/arms.json and per_query.jsonl.
Frozen frame/range/event and frame-position-video metrics remain separate in the machine-readable summary.
