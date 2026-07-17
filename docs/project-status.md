# CodePulse Project Status

Status date: 2026-07-17

This document is the authoritative source for current project scope and phase status.
The original PRD and dated experiment specifications remain historical design records.

## Current Positioning

CodePulse is an evidence-verification and acceptance-policy layer for Code Agent
experiments. Mature open-source projects should provide Agent controllers, evaluation
execution, sandbox runtimes, logs, dashboards, and optimization search. CodePulse
should remain a thin decision layer above them:

- verify the identity and declared boundary of frozen evidence;
- distinguish single-run success from stable task success;
- require task-level zero regression and explicit resource limits;
- preserve calibrated qualitative Judge boundaries;
- explain candidate acceptance or rejection with auditable evidence links.

CodePulse does not currently claim that self-evolution improves Agent performance.

## Phase Status

| Phase | Status | Evidence boundary |
|---|---|---|
| Phase 1: reproducible benchmark | Complete | 120 real trials, paired Agent metrics, cost and latency report |
| Phase 2: Judge calibration | Complete | 100 functional samples and 10 full-evidence qualitative diagnostics |
| Phase 3: evolution benefit | Closed without acceptance | Real SWE-bench candidates did not improve pass^3 and were rejected by the Gate |
| Phase 4: portfolio delivery | Not started | Offline demo, public report, README path, and demo CI remain required |

Phase 3 engineering produced reusable comparison, attribution, provenance, Gate, and
reporting assets. Its custom Agent/controller, candidate mutation, and repository
runtime work are research implementations, not differentiated product capabilities.
The completed mainline extraction boundary is documented in
[phase3-integration-plan.md](phase3-integration-plan.md).

## Phase 3 Closure

The complete V4 Flash comparison ran 48 paired SWE-bench trials. Candidate single-run
success increased from 25.0% to 29.2%, while pass@3 and pass^3 remained unchanged.
Candidate Token use increased by about 92.5%, so the Gate rejected it with
`no_stable_improvement`.

The final V4 Pro screen completed six trials and resolved no task in either arm. Its
candidate was also rejected. These results close the attempted low-resource and
strong-model branches without proving self-evolution benefit.

Large raw `results/phase3/` directories were deleted during project cleanup. Committed
manifests, evidence summaries, reports, provenance, and hashes remain, but local
per-Trial raw logs are no longer available. Historical evidence files record the state
at the time they were written; this closure record defines the current preservation
boundary.

## Build-Or-Buy Rule

Before adding an Agent controller, sandbox backend, optimizer, benchmark harness, or
other infrastructure component:

1. inspect maintained open-source alternatives and their licenses;
2. prefer a small adapter over an internal reimplementation;
3. keep custom code only where it supports CodePulse's evidence and gating value;
4. require an offline compatibility test before adopting a dependency;
5. do not expand a legacy implementation while a maintained upstream solution covers
   the same responsibility.

Current reuse candidates are Inspect AI for evaluation execution and logs,
mini-SWE-agent for the repository Agent controller, the official SWE-bench harness for
grading, GEPA for optional reflective optimization, and CJE for future Judge
calibration. Promptfoo covers general evaluation assertions and CI quality gates;
Inspect AI and MLflow cover evaluation logs, tracing, experiment tracking, and
dashboards. None is a required dependency for the offline Demo.

## Phase 4 Offline Evidence Demo

The first Phase 4 slice is implemented as a fully offline evidence report from
committed fixtures. `codepulse demo` verifies the available evidence boundary and
generates one deterministic Markdown document showing Agent comparison, stability,
cost, Judge calibration, failure cases, and rejected Phase 3 candidates. It does not
implement a generic evaluation, A/B, assertion, tracing, or reporting framework. See
the [design](phase4-offline-evidence-demo-design.md) and the generated
[evidence report](codepulse-evidence-report.md).

No new paid experiment, candidate variant, custom controller feature, server rental,
or model-training effort is approved by this status document.
