# Overnight return preparation

This versioned directory gathers the Issue92 overnight evidence. Research source
is PR91 commit37b321048432ccba5182a66bd39b1ca73c547537 on the isolated branch
codex/issue-92-overnight-20260916. Changes remain uncommitted. The inherited
publication-checkpoint metadata change has unknown ownership and is preserved.

The comparison builder re-scores saved rankings against the exact PR91 control,
without new retrieval, inference, truth edits or policy selection. Run only after
the terminal v11 result is verified or recorded as incomplete. It produces
exclusive per-query results, paired bootstrap intervals and complete-target
coverage deltas for every complete arm. Prior arm manifests retain code, tests,
configuration, immutable input hashes and negative results. The final report
must also apply each arm's original sequential-parent promotion guardrail;
positive deltas against PR91 alone do not establish promotion.

Contract: canonical115, scoreable113; exclusions p0_q15 and p3_q09. Use inherited
first-distinct-video ranking and exact scorer. Preserve provisional/proxy truth
qualifications and repeated-benchmark limitations. No independent holdout.

From the research worktree using the existing Vecna venv:
```
python -X utf8 -B benchmark-results/astra-overnight-issue92-return-v1/code/build_comparisons.py
```
These are preparation files, not a claim of final experiment acceptance.
