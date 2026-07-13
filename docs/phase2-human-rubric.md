# Phase 2 Human Calibration Rubric

Rubric version: `diagnostic-process-v1`
Study: LLM-as-Judge calibration, Issue #1

## Scope

Human review applies only to a full-evidence diagnostic cohort that first passes
`phase2-cohort-v1`. Each eligible packet must contain the task, final code, complete
observable Trace, and official verification result. The gate selects 10 process-diverse
records for two independently shuffled rounds before any reviewer is asked to score.

The 100-record functional sample is not a human task. Its label is completely defined
by exit status and the official pytest result, so the deterministic Grader is the
reference for functional Judge agreement.

## Reviewer Rules

Review only the evidence in the diagnostic packet. Do not search for the opaque packet
ID, infer the Agent or model, or consult Judge output or the other review round. Score
the observable process, not hidden reasoning or model reputation.

## Process-Quality Score

| Score | Meaning |
|---:|---|
| 5 | The observable approach is sound, direct, and fully supported by the final artifact and verification. |
| 4 | The approach is sound overall, with a minor avoidable step or clarity gap that does not threaten the result. |
| 3 | The result is adequate, but the Trace shows a material reasoning, tool-use, or recovery weakness. |
| 2 | The approach has major gaps, repeated ineffective work, or weak recovery despite some useful progress. |
| 1 | The observable process is missing, fundamentally unsound, or unsupported by the final artifact and verification. |

A rationale must cite observable evidence such as a decision, tool result, recovery
step, final-code property, or verification outcome. Hidden chain-of-thought is never a
required artifact and must not be inferred.

## Decision Order

1. Confirm that all required evidence is present and internally consistent.
2. Check whether the Trace decisions and tool use plausibly lead to the final artifact.
3. Check recovery from failures, repeated work, and unnecessary context growth.
4. Check that the final artifact and official verification support the claimed result.
5. Assign one score and record the decisive observable reason.

If required evidence is missing, the packet is invalid and must be excluded rather
than guessed or scored as zero.

## Two-Round Protocol

- Round 1 and Round 2 use different opaque packet IDs and seeded order.
- Two different reviewer IDs measure inter-rater agreement. Reusing one reviewer ID
  measures intra-rater repeatability and must be reported as such.
- Reviewers cannot see source IDs, Agent/model identity, Judge output, or prior scores.
- A completed response requires score, rationale, `reviewed_at`, and the exact packet
  SHA-256.
- Disagreements remain in the original round files. Resolution is recorded separately
  and never overwrites either raw annotation.

## Grader Boundary

- Deterministic Graders are authoritative for executable tests and static checks.
- LLM Judges may score evidence-complete qualitative dimensions but cannot override
  deterministic ground truth.
- Human calibration measures qualitative Judge agreement and resolves hard cases; it
  must not duplicate a deterministic rule or substitute for missing artifacts.
