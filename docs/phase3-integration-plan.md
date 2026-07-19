# Phase 3 Archive and Mainline Integration Plan

Status: archive and selective mainline integration completed
Archive anchor: `5fbc52789558a71b812f8d494a0fb885c63a626e`
Mainline base: `4a30ca5c15b660a03942883836364b32b1623535`
Integration branch: `codex/phase4-truth-reset`
Status commit: `fe0166e`
Evidence commit: `a22f334`

## Decision

Do not merge or cherry-pick the Phase 3 branch wholesale.

The branch contains 57 commits, 85 changed files, and 8,739 inserted lines relative to
the current remote mainline. Its largest additions implement an experiment-specific
SWE-bench runner, rule-based candidate materialization, Phase 3 CLI commands, and a
custom Agent controller. Those responsibilities overlap maintained open-source
projects and are not CodePulse's differentiated value.

The complete branch is preserved as `archive/phase3-negative-20260716`. The clean
integration branch contains only the status documents and final evidence listed below.

## Preserve in the Archive Only

The following code and intermediate artifacts remain reachable through the archive
anchor but do not enter the supported mainline:

- `codepulse/benchmark/swebench_runner.py` and its tests;
- `codepulse/evolve/candidate.py` and candidate materialization commands;
- Patch Guard changes in `codepulse/agent/real_agent.py`;
- Phase 3 training, evolution, screen, retry, image, and pricing CLI commands;
- hand-authored `skillopt-v1` through `skillopt-v5` Agent profiles;
- intermediate training cohorts, manifests, traces, and dated design specifications;
- the evolving `docs/phase3-evolution-protocol.md` runbook, whose commands reference
  archived intermediate files;
- local proxy and image-transport fixes that only supported the archived experiment.

The repository tool-contract change at `80140b8` is not selected automatically. Its
bounded reads and exact edit behavior are reasonable correctness fixes, but they belong
to the legacy `RealAgent`. Reconsider them only if that backend remains in the supported
public surface after an external Agent backend is adopted.

## Publish on the Mainline

### Current status and policy

- `README.md` positioning and evidence boundary;
- `AGENTS.md` build-or-buy rule and phase progression rule;
- `docs/project-status.md`;
- historical notices in `docs/PRD.md` and `docs/architecture.md`;
- this archive and integration plan.

### Final Phase 3 evidence

Copy these small, immutable evidence groups with their original contents and paths:

1. Complete V4 Flash paired comparison:
   - `experiments/phase3-swebench-evolution-v4/manifest.json`
   - `experiments/phase3-swebench-evolution-v4/evidence.json`
   - `experiments/phase3-swebench-evolution-v4/phase3-report.md`
2. Final same-model Patch Guard screen:
   - `experiments/phase3-swebench-screen-v3/manifest.json`
   - `experiments/phase3-swebench-screen-v3/candidate-provenance.json`
   - `experiments/phase3-swebench-screen-v3/evidence.json`
   - `experiments/phase3-swebench-screen-v3/screen-report.json`
3. Final V4 Pro screen:
   - `experiments/phase3-strong-model-screen-v1/manifest.json`
   - `experiments/phase3-strong-model-screen-v1/profile-provenance.json`
   - `experiments/phase3-strong-model-screen-v1/aborted-evidence-v1.json`
   - `experiments/phase3-strong-model-screen-v1/evidence.json`
   - `experiments/phase3-strong-model-screen-v1/screen-report.json`

These groups total less than 50 KiB. They preserve the final claims, configuration,
provenance, environment failure, and rejection decisions without restoring large raw
results or Docker assets.

Historical evidence files must remain byte-for-byte unchanged. The current cleanup
boundary belongs in `docs/project-status.md`, not in rewritten historical JSON.

## Do Not Reimplement Generic Evaluation Behavior

Do not cherry-pick commits `b1dca50`, `0f5ecbc`, `b7d92cb`, `651376d`, or `9e6b712`
verbatim, and do not recreate them as a new generic framework. Inspect AI covers
general evaluation execution and logs; promptfoo covers evaluation configuration,
assertions, and CI quality gates; MLflow covers tracing, experiment tracking, and
dashboards.

The Phase 4 offline report retains only these project-specific policy statements:

- stable task success is distinct from single-run success;
- a candidate needs positive stable gain, task-level zero regression, and acceptable
  resource use;
- Judge conclusions are limited by the completed human calibration;
- missing raw Phase 3 results must be disclosed rather than reconstructed;
- historical Gate decisions are displayed from immutable evidence, not recomputed.

The Demo may reuse `summarize_pilot()` for the Phase 1 raw Trial file. It must not add a
new task runner, comparison abstraction, Gate engine, provenance schema, dashboard, or
HTML chart renderer.

## Mainline Integration Sequence

1. Completed: preserve the archive anchor as
   `archive/phase3-negative-20260716`.
2. Completed: create `codex/phase4-truth-reset` from the remote mainline.
3. Completed: apply the status and policy documents in `fe0166e`.
4. Completed: copy the three final evidence groups in `a22f334` and verify their hashes.
5. Next: implement the offline evidence report in a separate change with fixture-only
   tests and no model, Docker, dataset download, or network dependency.

## Stop Conditions

Stop and review the plan again if integration requires any of the following:

- merging the full Phase 3 branch;
- restoring raw `results/phase3/` or Docker images;
- adding mini-SWE-agent, GEPA, SWE-ReX, or another dependency before the offline Demo;
- preserving a Phase 3-specific command solely to make an old reproduction command
  executable;
- changing historical evidence to make it match the cleaned local filesystem;
- starting a paid model call or a new candidate experiment.

## Verification Bar

The archive is remotely reachable at the exact anchor, and the 12 selected evidence
files match it byte-for-byte. Phase 4 is complete only when the offline evidence report
passes CI from committed fixtures and produces no network, model, Docker, database, or
web-server activity.
