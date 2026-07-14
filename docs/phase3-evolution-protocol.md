# Phase 3 Evolution Protocol

Status: frozen, not yet run
Protocol version: `phase3-evolution-v1`
Issue: [#3](https://github.com/Chloride233/CodePulse/issues/3)

## Frozen comparison

`deepseek-v4-flash-direct` is the baseline and
`deepseek-v4-flash-iterative` is the candidate. They use the same pinned V4 Flash
model version and are distinguished only by their hashed profiles. This is a
controlled candidate comparison, not evidence that SkillOpt has improved an Agent.

The HumanEval task order, source and task-list hashes, seed, dependencies, sandbox
limits, pricing schedule and budget are fixed in
`experiments/phase3-evolution-v1/manifest.json`.

## Planned scale and preflight

The frozen run has 20 tasks, 3 trials per task, and 2 roles: 120 planned calls. Its
peak-price hard cost ceiling is CNY 10.00, split into CNY 5.00 per role and CNY 0.10
per call. No real-model calls are authorized by this document.

Before a real comparison, run:

```bash
codepulse benchmark preflight --manifest experiments/phase3-evolution-v1/manifest.json
```

The preflight rejects task, profile, dataset, dependency, environment, budget, role,
and model-version drift.

When results are available, `compare_phase3_pilot()` compares the two frozen roles by
`(task_id, repetition)`. It rejects duplicate, missing, or unpaired trials before
reporting success rate, `pass@3`, `pass^3`, token, CNY cost, and latency deltas.
