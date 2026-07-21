# Phase 4 Offline Evidence Demo Design

Status: implemented
Issue: [#4](https://github.com/randy-labs/CodePulse/issues/4)

## Goal

Provide one command that verifies the available committed evidence and generates a
deterministic Markdown decision report. The report demonstrates what CodePulse proved,
what it rejected, and which conclusions remain unsupported.

The Demo is a portfolio evidence dossier, not a general evaluation framework.

## Command

```bash
codepulse demo --output docs/codepulse-evidence-report.md
```

The command defaults the repository root to the current directory. It performs no
model call, Docker operation, network request, dataset download, database access, or
web-server startup.

## Committed Inputs

### Phase 1

- `results/pilot-v1/runs/20260713-v1/manifest.json`
- `results/pilot-v1/runs/20260713-v1/run-summary.json`
- `results/pilot-v1/runs/20260713-v1/trials.jsonl`

The Demo requires `protocol_version` `pilot-v1`, 20 `task_ids`, two `agents`,
`n_trials` 3, and 120 Trial rows. It reuses `summarize_pilot()` to reproduce the Agent
metrics from the committed Trial file.

### Phase 2

- `results/phase2/calibration-analysis.json`

The Demo requires final status `complete`, 100 functional calibration samples, 10
qualitative diagnostic samples, no missing Judge observations, and explicit usage
boundaries. It displays the stored calibration results; it does not rerun Judge calls or
statistical estimation.

This file is tracked in Git but omitted by the current sparse checkout. Before
implementation, materialize only this tracked file; do not add, inspect, or modify the
private untracked Phase 2 directories around it.

### Phase 3

- `experiments/phase3-swebench-evolution-v4/evidence.json`
- `experiments/phase3-swebench-evolution-v4/phase3-report.md`
- `experiments/phase3-swebench-screen-v3/evidence.json`
- `experiments/phase3-strong-model-screen-v1/evidence.json`

The Demo requires each experiment to report completed execution and rejected
acceptance. It verifies committed manifest/report hashes when the referenced committed
file is present. It does not require deleted `results/phase3/` raw files and must report
their absence as an evidence limitation.

## Output

The generated Markdown contains exactly these sections:

1. Executive conclusion
2. Proven and unsupported claims
3. Phase 1 reproducible Agent comparison
4. Phase 2 Judge calibration and usage boundaries
5. Phase 3 candidate rejection evidence
6. Why the Gate rejected apparent improvement
7. Evidence index and preservation boundary

The document contains no generation timestamp, absolute path, environment-dependent
value, external image, script, or remote asset. Running the command twice from the same
commit must produce identical bytes.

## Implementation Boundary

Use one small pure report module plus one Click command. Reuse existing JSON/JSONL and
hash helpers and `summarize_pilot()`. Do not introduce a new class hierarchy, manifest
schema, plugin system, template engine, database, or dependency.

Do not modify or extend:

- `RealAgent` or Agent tools;
- sandbox or SWE-bench execution;
- SkillOpt, candidate generation, attribution, or Validation Gate;
- the Vue dashboard or API;
- the existing Chart.js HTML renderer.

The Demo reads historical Gate outcomes from immutable evidence. It does not recompute
Phase 3 metrics from unavailable raw Trial data and does not imply that summaries are a
replacement for those raw records.

## Failure Behavior

The command exits non-zero when a required committed input is missing, malformed, has
an unexpected protocol/status/count, or fails an available committed hash check.

Deleted Phase 3 raw results are the one expected absence. They appear in the report as
`raw evidence not locally preserved` and do not cause the command to fail.

When an existing output is byte-identical, the command succeeds without writing it.
When the content differs, the command refuses to overwrite it unless `--force` is
supplied, reusing the repository's existing artifact overwrite guard.

## Tests

Focused tests must prove:

- the committed fixture bundle generates the expected headline metrics and rejection
  reasons;
- two runs produce byte-identical Markdown;
- a missing or malformed required summary fails clearly;
- a hash mismatch fails clearly;
- missing Phase 3 raw result paths are disclosed but accepted;
- an existing output is not overwritten without `--force`;
- CLI help and the one-command path work without model, Docker, network, or web setup.

No test creates a virtual environment, downloads a package, opens a browser, starts a
server, or accesses private Phase 2 files.

## Stop Conditions

Stop and review before implementation expands to any of the following:

- a generic evaluation or A/B API;
- new pass@k, assertion, Gate, provenance, or experiment schemas;
- HTML charts or dashboard work;
- Inspect AI, promptfoo, MLflow, mini-SWE-agent, GEPA, or CJE integration;
- paid calls, Docker images, raw Phase 3 restoration, or new experiments.

## Completion Bar

Phase 4's Demo slice is complete when the command generates the committed Markdown
report from a clean checkout, the output is byte-deterministic, focused tests pass, and
CI proves the path without external services. This slice does not itself complete all
of Issue #4's public delivery requirements.
