# Phase 3 Strong-Model Local Screen Design

Status: approved at the approach level on 2026-07-16; implementation and paid calls
remain separate gates.

## Context

The DeepSeek V4 Flash Patch Guard screen completed all six trials for 0.216108 CNY with
zero infrastructure failures. Patch Guard recovered and officially resolved
`pytest-dev__pytest-10081`, but candidate v5 produced only one non-empty patch and one
resolved task. Its peak-price cost was 138.04% of baseline, above the 125% limit. The
screen was therefore rejected and the same-model low-resource branch was stopped.

Issue #3 still requires stable improvement, not merely evidence that the Validation Gate
rejects weak candidates. The next branch changes the shared base model for both arms and
keeps the controller delta isolated. It must run locally; renting or switching to a
server is outside the approved plan.

## Outcome

Run one paired, training-only screen using DeepSeek V4 Pro on the same three revealed
repository tasks. Baseline and candidate share the model, prompt, tools, temperature,
token limit, and eight-call base budget. The candidate alone enables the already frozen
`patch-guard-v1` controller with `empty_patch_retries=1`.

The experiment is not candidate v6. It is a new model-family branch that tests whether a
stronger underlying model can turn the existing controller edit into strict paired
functional gain. A passing screen permits a separate fresh held-out design. A failed
screen closes Phase 3 with negative evidence.

## Naming

- Screen protocol: `phase3-strong-model-screen-v1`
- Baseline profile: `deepseek-v4-pro-swebench-baseline-v1`
- Candidate profile: `deepseek-v4-pro-swebench-patch-guard-v1`
- Controller edit: `patch-guard-v1`
- Seed: `20260723`

## Frozen Profiles

Both profiles copy these fields from
`agents/deepseek-v4-flash-swebench-skillopt-v2-tools-v2.yaml`:

- the complete system prompt;
- `read_file`, `edit_file`, `write_file`, and `execute`;
- `max_iterations=8`;
- `max_tokens=4096`;
- `temperature=0.0`;
- `tool_contract_version=repository-tools-v2`.

Both profiles change the model to `deepseek/deepseek-v4-pro`. Baseline sets
`empty_patch_retries=0`; candidate sets it to 1. No prompt edit, task-specific hint,
oracle patch, hidden test, or additional tool is permitted.

Provenance binds the source profile, the rejected screen-v3 evidence, the candidate-v5
controller edit and digest, both generated profiles, and a field-by-field equality check
showing that `empty_patch_retries` is the only paired runtime difference.

## Model-Aware Costing

The current SWE-bench record path always applies V4 Flash CNY pricing. The strong-model
screen must first replace that call site with a frozen model-aware calculator while
preserving historical V4 Flash results.

Authoritative V4 Pro budget pricing is conservative CNY per one million tokens:

| Tier | Cache hit | Cache miss | Output |
|---|---:|---:|---:|
| off-peak | 1.0 | 4.0 | 16.0 |
| peak | 1.0 | 4.0 | 16.0 |

No off-peak discount is assumed. Unknown models produce `cost_unavailable` and stop the
run instead of silently recording zero cost. Tests cover both frozen model tables,
cache-hit accounting, negative token validation, unknown models, and propagation into
the trial budget guard.

Applying this table to the completed Flash screen's token counts projects 0.857104 CNY
for six V4 Pro trials. The frozen limits are:

- total: 2.0 CNY;
- per agent: 1.2 CNY;
- per trial: 0.4 CNY.

The runner retains projected-budget stopping, so an unexpectedly expensive early trial
ends the screen without consuming the remaining schedule.

## Task And Environment Freeze

Reuse the three revealed training tasks and existing local image digests:

- `pytest-dev__pytest-10081`;
- `scikit-learn__scikit-learn-13328`;
- `sphinx-doc__sphinx-8621`.

Run baseline and candidate once per task for six unique trials. Preserve the existing
`2 CPU / 4096 MB / no swap / no network` policy and 900-second trial timeout. Preflight
must confirm all three image digests are already local. The screen must not pull or
delete an image.

The provider must report exactly one frozen model version, `deepseek-v4-pro`, across all
six trials. Authentication, provider, sandbox, grader, model-version, cost-accounting,
or Patch Guard check failures reject the screen.

## Acceptance Gate

The screen passes only when every condition holds:

- all six unique trial keys complete;
- candidate produces non-empty patches on at least two tasks;
- candidate officially resolves at least two tasks;
- candidate resolves at least one more task than baseline;
- candidate resolves every task resolved by baseline;
- candidate total tokens are no more than 125% of baseline;
- candidate peak-price cost is no more than 125% of baseline;
- total, per-agent, and per-trial budgets remain within their limits;
- infrastructure failure count is zero.

The report records per-task attribution as improvement, regression, persistent failure,
or stable success, plus token, cost, latency, Patch Guard, provider-version, and budget
metrics. A strict paired gain is required; a tie cannot pass.

## Local-Only Storage Policy

No server may be rented or used for this branch. The strong-model screen adds no images.
Before any later fresh held-out work, a separate manifest and storage preflight are
required.

If the screen passes, the held-out design will group all repetitions and agents by task.
Only one newly selected task image may be resident at a time. After all six trials for a
task are durably written and hash-checked, the runner may remove only that newly pulled
image before advancing. Existing frozen evidence images, datasets, raw results, logs,
and private files remain untouched.

Every pull requires a free-space threshold. Falling below it stops the run. Persistent
local disk, download, or runtime failure is recorded as blocked work; it never authorizes
renting a server or silently changing the task set.

## Stopping Rules

If the strong-model screen fails, commit its negative evidence, end the active experiment
line with Phase 3 still incomplete, and do not try another model, prompt, controller,
task screen, or held-out cohort without a new explicit project decision.

If it passes, stop after committing positive screen evidence. Design and freeze the fresh
held-out cohort, image lifecycle, `k=3` schedule, and V4 Pro budgets separately. Passing
this training screen does not authorize those model calls.

## Verification And Approval

Before freezing the screen, run only the affected Phase 3 tests plus Ruff, mypy, Bandit,
manifest preflight, local image inspection, and storage preflight. Preserve all current
untracked Phase 2 private files and raw Phase 3 results.

Profile materialization, manifest creation, and paid execution are distinct commits.
External V4 Pro calls require a separate explicit approval after profiles, provenance,
pricing, tasks, budgets, and manifest hashes are frozen.
