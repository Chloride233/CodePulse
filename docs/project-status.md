# CodePulse Project Status

Status date: 2026-07-17

This document is the authoritative source for current project scope and phase status.
The original PRD and dated experiment specifications remain historical design records.

## Current Positioning

CodePulse is a reproducible evaluation, evidence, and regression-gating platform for
Code Agents. Mature open-source projects should provide repository Agent controllers,
sandbox runtimes, and optimization search. CodePulse should provide the experiment
control plane above them:

- frozen tasks, Agent profiles, models, dependencies, environments, seeds, and budgets;
- normalized Trial and Trace evidence;
- deterministic grading and calibrated qualitative Judge boundaries;
- exact baseline/candidate pairing, pass@k and pass^k metrics, and task attribution;
- provenance, Validation Gate decisions, and auditable reports.

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
The proposed mainline extraction boundary is documented in
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

Current candidates are mini-SWE-agent for the repository Agent controller, GEPA for
reflective optimization, and SWE-ReX for an optional runtime abstraction. None is a
required dependency until a focused compatibility test justifies adoption.

## Next Approved Direction

Phase 4 should first deliver a fully offline demo from committed fixtures. It must
generate a fixed report showing Agent comparison, stability, cost, Judge calibration,
failure cases, and a rejected Phase 3 candidate without calling a model or starting a
repository benchmark container.

No new paid experiment, candidate variant, custom controller feature, server rental,
or model-training effort is approved by this status document.
