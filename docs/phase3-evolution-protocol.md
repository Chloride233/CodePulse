# Phase 3 Evolution Protocol

Status: repository training complete; trace-derived candidate frozen; paired evaluation pending
Protocol version: `phase3-evolution-v1`
Issue: [#3](https://github.com/Chloride233/CodePulse/issues/3)

## Current evidence status

The two disjoint HumanEval training cohorts completed with 20/20 successful baseline
trials. Their peak-price costs were CNY 0.084882 and CNY 0.083796. Because neither
cohort contains a failed baseline trial, they cannot legally produce the Phase 3
candidate and do not prove self-evolution benefit.

The repository-level training route is frozen in
`experiments/phase3-swebench-training-v1/manifest.json`. It uses five SWE-bench
Verified training instances and keeps eight disjoint instances in the dataset snapshot
for evaluation. Seven earlier local attempts stopped before the first trial and produced
empty JSONL files. The official-image run then completed all five baseline trials: 0/5
resolved, 256,794 input-plus-output tokens, 0.177450 CNY peak-price cost, and no
infrastructure or budget stop. The normalized failed-trial evidence is stored at
`experiments/phase3-swebench-training-v1/trials.jsonl`.

The runner now pulls official `swebench` instance images by immutable digest instead
of rebuilding base, environment, and instance layers. A no-model smoke test ran the
oldest frozen Django image on the local ARM Mac through x86 emulation with Python
3.5.6. The real container limits were also verified at 2 CPUs, 4096 MiB memory, no
additional swap, and no attached Docker network. The 13 frozen images total 17.416 GiB
when summing registry layer sizes before cross-image deduplication. This removes the
known need for a separate x86 build server.

Before the first repository training call, run only the focused checks:

```bash
.venv/bin/pytest tests/test_swebench_runner.py tests/test_candidate.py --no-cov
.venv/bin/ruff check codepulse/benchmark/swebench_runner.py codepulse/benchmark/cli.py codepulse/evolve/candidate.py tests/test_swebench_runner.py tests/test_candidate.py
.venv/bin/mypy codepulse/benchmark/swebench_runner.py codepulse/benchmark/cli.py codepulse/evolve/candidate.py tests/test_swebench_runner.py tests/test_candidate.py
.venv/bin/python -m codepulse.cli benchmark swebench-training-preflight --manifest experiments/phase3-swebench-training-v1/manifest.json --repo-root .
```

The baseline training cohort retains each Agent patch and observable trace. Candidate
materialization ignores infrastructure failures and deterministically chooses one
PromptEdit from the dominant trace failure pattern, adding no backward-pass model call.
The observed pattern was `empty_patch` in four of five failed trials. The frozen
candidate profile SHA-256 is
`4b89905aafdabc665a413cbaded67ad292485caa584d4e61d990760a4c354073`.

```bash
.venv/bin/python -m codepulse.cli benchmark swebench-training-run --manifest experiments/phase3-swebench-training-v1/manifest.json --output-dir results/phase3/swebench-training-v1-official-images --repo-root .
```

The final comparison is frozen in
`experiments/phase3-swebench-evolution-v1/manifest.json`: eight held-out tasks, three
trials per task, and two roles produce 48 paired calls in a seeded interleaved order.
Run its preflight before downloading evaluation images or calling the model:

```bash
.venv/bin/python -m codepulse.cli benchmark swebench-evolution-preflight --manifest experiments/phase3-swebench-evolution-v1/manifest.json --repo-root .
.venv/bin/python -m codepulse.cli benchmark swebench-evolution-run --manifest experiments/phase3-swebench-evolution-v1/manifest.json --output-dir results/phase3/swebench-evolution-v1 --repo-root . --resume
```

The paired evaluation has not yet run. The existing HumanEval
`phase3-evolution-v1` manifest remains only a comparison/reporting template and must
not be reported as the repository-level final experiment.

## Frozen comparison

`deepseek-v4-flash-direct` is the baseline. The frozen iterative profile is only a
controlled-comparison template, not a SkillOpt candidate. A final evaluation requires
a newly materialized candidate and a provenance file that binds its profile to failed,
disjoint baseline training trials.

The HumanEval task order, source and task-list hashes, seed, dependencies, sandbox
limits, pricing schedule and budget are fixed in
`experiments/phase3-evolution-v1/manifest.json`.

Before that evaluation, `phase3-training-v1` runs the disjoint HumanEval/100-109
training set once with the baseline. A failed training Trial is the only permitted
source for the `PromptEdit` used to materialize the candidate profile and provenance.
If the first cohort has no failures, `phase3-training-v2` uses the distinct
HumanEval/130-139 cohort within the remaining CNY 0.9 training budget.

## Planned scale and preflight

The frozen run has 20 tasks, 3 trials per task, and 2 roles: 120 planned calls. Its
peak-price hard cost ceiling is CNY 10.00, split into CNY 5.00 per role and CNY 0.10
per call. No real-model calls are authorized by this document.

Before a real comparison, run:

```bash
codepulse benchmark preflight --manifest experiments/phase3-evolution-v1/manifest.json
```

The preflight rejects task, profile, dataset, dependency, environment, budget, role,
model-version drift, and a candidate without matching trace provenance. It also checks
that the provenance source tasks failed for the frozen baseline and are absent from the
evaluation task set.

When results are available, `compare_phase3_pilot()` compares the two frozen roles by
`(task_id, repetition)`. It rejects duplicate, missing, or unpaired trials before
reporting success rate, `pass@3`, `pass^3`, token, CNY cost, and latency deltas.

`classify_phase3_pilot()` uses each role's `pass^3` state per task to count
improvements, regressions, persistent failures, and stable successes. It reports
observed categories only; a real run is still required before making a benefit claim.

`validate_phase3_pilot()` rejects invalid coverage, any task regression, no positive
`pass^3` gain, a per-trial peak-cost breach, or a per-role peak-cost breach. It can
only accept a fully paired, stably improved candidate within the frozen budget.

After a completed run, generate the shareable Markdown and HTML report with:

```bash
codepulse benchmark phase3-report --manifest experiments/phase3-evolution-v1/manifest.json --run-dir results/phase3/evolution-v1
```

The report lists aggregate metrics, four-way attribution, Gate verdict, and one
fully observable task example from each populated attribution class.
