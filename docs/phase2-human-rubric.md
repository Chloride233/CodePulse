# Phase 2 Human Calibration Rubric

Rubric version: `functional-evidence-v1`
Study: LLM-as-Judge calibration, Issue #1

## Reviewer Rules

Review only the evidence in the packet. Do not search for the opaque packet ID, infer
the Agent or model, or consult a Judge result or another review round. Record one
label and a short evidence-grounded rationale for every packet.

The current 100-record sample does not contain final code or a full Trace. It is not
eligible for process quality, code quality, robustness, or experience-alignment
scores. A passing test log is evidence of the recorded official test result, not proof
of untested behavior.

## Functional Evidence Labels

### `supported_pass`

Use when the official deterministic output is internally consistent and reports a
completed passing run. Typical evidence includes exit code 0 and a pytest summary
with no failed tests.

### `supported_fail`

Use when the official deterministic output reports a failed, errored, or incomplete
run. Typical evidence includes non-zero exit code, failed tests, collection errors,
timeouts, or an explicitly aborted verification.

### `insufficient_evidence`

Use when required verification fields are absent or contradictory, such as exit code
0 paired with failed tests, truncated output that omits the result, or no official
verification result at all. Do not guess pass or fail from token count, duration, or
Agent behavior.

## Decision Order

1. Confirm that an official verification result is present.
2. Check whether exit status and test summary agree.
3. Select `supported_pass` or `supported_fail` only when the conclusion is supported.
4. Select `insufficient_evidence` for missing or contradictory evidence.
5. Cite the decisive field or output line in the rationale.

## Two-Round Protocol

- Round 1 and Round 2 use different opaque packet IDs and seeded order.
- Reviewers cannot see source sample IDs, Agent/model identity, prior responses, or
  Judge observations.
- Two different reviewer IDs constitute inter-rater agreement. Reusing the same ID
  constitutes intra-rater repeatability and must be reported as such.
- A completed response requires `label`, `rationale`, and `reviewed_at`; packet IDs,
  hashes, round, reviewer ID, and rubric version must not be changed.
- Disagreements remain in the original round files. Resolution is recorded separately
  with source sample ID, final label, adjudicator ID, and rationale.

## Diagnostic 1-5 Scores

Only a diagnostic packet marked eligible and containing task text, final code, full
observable Trace, and official verification may receive these scores:

| Score | Meaning |
|---:|---|
| 5 | Evidence is complete; the approach is logically sound, efficient, and clearly justified. |
| 4 | Sound overall with a minor gap or avoidable step that does not undermine the result. |
| 3 | Adequate result with material reasoning, tool-use, or clarity weaknesses. |
| 2 | Major gaps, unjustified steps, or poor recovery despite partial useful work. |
| 1 | Missing or fundamentally unsound process evidence. |

The rationale must identify observable events. Hidden chain-of-thought is never a
required artifact and must not be inferred.

## Grader Boundary

- Deterministic Graders are authoritative for executable tests and static checks.
- LLM Judges may score evidence-complete qualitative dimensions but cannot override
  deterministic ground truth.
- Human review measures Judge agreement and resolves hard cases; it is not a substitute
  for missing task artifacts.
