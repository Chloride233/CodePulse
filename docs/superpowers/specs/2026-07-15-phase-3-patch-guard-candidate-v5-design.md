# Phase 3 Patch Guard Candidate V5 Design

Status: high-level approach approved on 2026-07-15; implementation awaits written spec review.

## Context

The paired screen v2 completed all six trials for 0.198434 CNY and rejected candidate
v4. Baseline and candidate each produced zero non-empty patches and zero resolved tasks.
Candidate v4 used 29.36% more tokens and 22.30% more peak-price cost than baseline, so
the compact prompt replacement did not improve the process.

The six traces isolate the next failure boundary:

- neither profile called `edit_file`, `write_file`, or a modifying `execute` command;
- four trials returned a no-tool final response after five to seven model calls while
  `git diff` was still empty;
- two scikit-learn trials consumed all eight calls on inspection and ended without an
  edit;
- the repaired bounded reads worked and no infrastructure failure occurred.

The model therefore failed at the transition from analysis to mutation. Another prompt
edit would repeat a rejected approach. The next candidate changes only the controller's
empty-patch stopping condition.

## Outcome

Compare the accepted v2 baseline against candidate v5, which may recover once from an
otherwise terminal empty-diff state. The model, system prompt, tools, temperature,
token limit, and eight-call base budget remain identical. Candidate v5 receives at most
one deterministic Patch Guard correction and at most one ninth model call.

Run a paired six-trial training-only screen on the existing three revealed tasks. Only
a passing screen may resume the previously approved v5 held-out plan. A rejected screen
ends the low-resource same-model branch; it must not trigger another prompt or retry
iteration automatically.

## Naming And Baseline

- Controller edit: `patch-guard-v1`
- Candidate profile: `deepseek-v4-flash-swebench-direct-skillopt-v5`
- Training screen: `phase3-swebench-screen-v3`
- Eventual fresh evaluation, if unlocked: `phase3-swebench-evolution-v5`

Baseline remains
`deepseek-v4-flash-swebench-direct-skillopt-v2-tools-v2`. Rejected candidates v3 and v4
are never promoted. Candidate v5 copies the baseline model, system prompt, four-tool
contract, `max_iterations=8`, `max_tokens=4096`, and `temperature=0.0`. Its only runtime
difference is `empty_patch_retries=1`.

## Profile Contract

`AgentProfile` and `RealAgent` add an integer `empty_patch_retries` setting. It defaults
to zero, must be non-negative, and is serialized for protocol profiles. Existing profiles
therefore retain current behavior. `_load_agent_class` passes the frozen value only to
`RealAgent` implementations.

The candidate provenance records:

- baseline and candidate profile paths and SHA256 values;
- screen v2 trials and rejection-evidence SHA256 values;
- source trial IDs and the observed zero-mutation counts;
- unchanged model, prompt, tools, base iterations, temperature, and token limit;
- controller edit ID and canonical edit SHA256;
- `empty_patch_retries` changing from 0 to 1.

No oracle patch or hidden test content is used.

## Patch Detection

Patch Guard is disabled when `empty_patch_retries=0`. When enabled, the controller checks
the active repository only at a potential stopping boundary:

```text
cd /workspace && git diff --quiet --
```

Exit code 0 means the tracked diff is empty. Exit code 1 means a patch exists. Any other
exit code is a guard-check failure. Untracked files do not count because the SWE-bench
submission path also captures `git diff`; treating them as a patch would produce false
evidence.

The check is controller-internal and does not appear as a model tool call. It uses the
same active, network-isolated container and has no external side effect.

## Controller Flow

RealAgent tracks `calls_made`, `guard_checks`, `guard_retries`, and a dynamic
`call_limit`, initially equal to `max_iterations`.

### No-Tool Boundary

When the model returns no tool calls:

1. If Patch Guard is disabled, stop exactly as today.
2. If a patch exists, stop successfully without a retry.
3. If the diff is empty and the single retry is unused, append the assistant response,
   append the fixed correction message, consume the retry, and continue.
4. If the retry was already used, stop with the empty patch observable.
5. If the diff check fails, record the failure and stop without another model call.

An early correction uses the remaining eight-call base budget. It does not automatically
raise the limit to nine. If the no-tool boundary is the eighth call, no base budget
remains, so consuming the retry raises `call_limit` to 9 exactly as at the tool-call
boundary below.

### Base-Budget Boundary

After processing tool calls from the eighth base call, check the diff only when no retry
has been used. If the diff is empty, append the fixed correction, consume the retry, and
raise `call_limit` from 8 to 9. The ninth response and any tool calls it contains are
processed normally. No tenth call is possible.

If the eighth call already produced a patch, stop at the original limit. If an early
correction consumed the retry, the controller stops at eight calls even when the diff is
still empty.

## Fixed Correction

The controller appends this user message verbatim:

> No repository edit exists (`git diff` is empty). Stop exploring. Use `edit_file` or a
> targeted `execute` command now to make the smallest defensible code change, then
> inspect `git diff`. Do not return a final answer without a patch.

The message is fixed code, not generated by an LLM and not configurable per task.

## Observability

Each guard trigger adds a `reflection` TraceEvent with:

- `kind: patch_guard`;
- trigger: `no_tool_final` or `base_budget_exhausted`;
- diff status: `empty`, `non_empty`, or `check_error`;
- calls made, base limit, retry count, and whether one extra call was granted.

Transcript `agent_config` records:

- `empty_patch_retries`;
- `patch_guard_checks`;
- `patch_guard_retries_used`;
- `patch_guard_check_failures`;
- `base_max_iterations`;
- `effective_call_limit`.

Token, cost, and duration accounting already includes any recovery call. The trial record
and report require no hidden adjustment.

## Training Evidence

Create compact training evidence from all six screen v2 functional failures. Preserve
the raw screen files and bind them by SHA256. Each compact row records only:

- trial, task, and agent identity;
- LLM-call and tool-call counts;
- whether the last response had tools;
- whether the base budget was exhausted;
- modifying-tool-call count;
- final patch emptiness and failure type.

The deterministic aggregate must show six empty patches, zero modifying calls, four
no-tool final responses, and two base-budget exhaustions. Candidate v5 materialization
uses these counts plus the rejected screen evidence, not task solutions.

## Paired Screen V3

Reuse the same three revealed training tasks and preserved image digests:

- `pytest-dev__pytest-10081`
- `scikit-learn__scikit-learn-13328`
- `sphinx-doc__sphinx-8621`

Run baseline and candidate once per task for six unique trials with seed `20260722`.
Freeze the same `2 CPU / 4096 MB / no swap / no network` container policy and 900-second
trial timeout. No image download is required.

Screen budgets are 1.0 CNY total, 0.6 CNY per agent, and 0.25 CNY per trial. Proceed only
when all conditions hold:

- all six unique keys complete;
- candidate leaves non-empty patches on at least two tasks;
- candidate officially resolves at least two tasks;
- candidate resolves at least as many tasks as baseline;
- candidate total tokens and peak-price cost are each no more than 125% of baseline;
- no provider, sandbox, grader, authentication, model-version, or Patch Guard check
  failure occurs.

The screen report additionally records guard checks, triggers, retries, and effective
call limits for each profile.

## Stopping Rules

If screen v3 fails, commit its negative evidence and stop the low-resource same-model
branch. Do not create a candidate v6, run another training screen, select held-out tasks,
or download images without a new design decision. The next legitimate choices are a
stronger base model or closing Phase 3 with negative evidence.

If screen v3 passes, resume the approved fresh held-out flow from the tool-contract v5
design: exclude all prior and training tasks, select eight new `<15 min fix` tasks with
seed `20260721`, freeze 48 trials and the 10/5/1 CNY budgets, then run only after storage
preflight and explicit paid-call approval.

## Failure Handling

- A diff-check exit code other than 0 or 1 is recorded as `patch_guard_check_error` and
  receives no retry.
- Provider and authentication failures retain existing budget-stop behavior and never
  become Guard retries.
- Guard state resets for every trial and cannot leak across tasks or agents.
- Resume validation preserves completed raw trials; it never replays a rejected result.
- Candidate patch application and official grading remain unchanged.
- Raw `results/**`, logs, `.learnings/`, and Phase 2 private files remain uncommitted.

## Verification

Add deterministic tests for:

- `AgentProfile` YAML round-trip and validation of `empty_patch_retries`;
- historical zero-retry behavior;
- no-tool empty diff triggering one correction;
- no-tool non-empty diff stopping without a correction;
- eighth-call empty diff granting exactly one ninth call;
- early retry consuming the only retry without increasing the base limit;
- diff-check error stopping without a model call;
- reflection events and transcript guard metrics;
- candidate-v5 provenance and unchanged prompt/model/tool hashes;
- compact screen-v2 training evidence counts;
- screen-v3 coverage, budgets, resource ratios, guard failures, and backward compatibility.

Before each commit, run only affected Phase 3 tests plus Ruff, mypy, Bandit at the CI
high-severity threshold, and the relevant preflight. External model calls require a
separate confirmation after code, candidate, and manifest are frozen.
