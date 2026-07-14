# Phase 2 Calibration Sampling Protocol

Status: **Phase 2 calibration complete**
Issue: [#1](https://github.com/Chloride233/CodePulse/issues/1)  
Sample version: `calibration-sample-v1`

## Source And Stratification

The source is the completed Phase 1 run at `results/pilot-v1/runs/20260713-v1/trials.jsonl` (120 Trial records). A fixed seed (`20260713`) selects 100 records with these invariants:

- 50 `deepseek-v4-flash-direct` and 50 `deepseek-v4-flash-iterative` records.
- All 20 HumanEval tasks represented.
- Both observed failures retained.
- Remaining records selected by deterministic round-robin task coverage within each Agent.

Observed sample composition:

| Stratum | Count |
|---|---:|
| Success | 98 |
| Failure (`wrong_answer`) | 2 |
| Total | 100 |

Artifacts:

- Sample JSONL: `results/phase2/calibration-sample-v1.jsonl`
- Sample SHA-256: `df237645d1fd04c1128c09fa0410d5186a9b9686ea7634e677f104091da983b6`
- Manifest: `results/phase2/calibration-sample-v1.manifest.json`
- Manifest SHA-256: `e0ea12e2a3b786df7a7c460998914614365090d3e4bd07913bada8c29dadae9a`

## Reproduction

```bash
python -m codepulse.eval.calibration_sampling \
  --input results/pilot-v1/runs/20260713-v1/trials.jsonl \
  --output results/phase2/calibration-sample-v1.jsonl \
  --sample-size 100 \
  --seed 20260713
```

## Evidence Boundary

In the 100-record functional extraction, every LLM Judge and human review score starts
as `null`; extraction does not count as annotation. Phase 1 preserved deterministic
test evidence and aggregate metrics but not final code or full transcripts. Therefore
that sample is eligible only for functional-evidence calibration and remains
ineligible for process-quality or experience-alignment judgment.

Before starting the rubric and two-pass review, CodePulse must capture full evidence
and pass `phase2-cohort-v1`. Pytest logs must not be presented to reviewers as a
substitute for the observable Trace or final code. The first 10-record diagnostic
capture is evidence-complete but process-homogeneous, so it is retained as capture
pipeline evidence and excluded from qualitative calibration.

Two later frozen candidate pools contain 80 additional complete records. Their
hash-preserving combined profile passes `phase2-cohort-v1` with 4 direct successes,
5 multi-attempt successes, and 1 final failure selected for the 10-record qualitative
cohort. One reviewer completed two independently shuffled blind rounds. Raw exact
repeatability was 90% with mean absolute error 0.2; the only disagreement was resolved
in a separate adjudication record without changing either raw round.

The approved functional-evidence rubric is now published at
`docs/phase2-human-rubric.md`. The existing sample remains ineligible for process or
alignment scores; `docs/phase2-calibration-runbook.md` defines the separate diagnostic
capture and two-round review workflow.

The completed Judge before/after evidence is stored in
`results/phase2/judge-calibration-before-after.json` and `.md`. Agreement in that
report uses deterministic functional evidence as the reference and is not represented
as human agreement.

The completed qualitative analysis is stored in
`results/phase2/calibration-analysis.json` and `results/phase2/calibration-report.md`.
Full and compact Judge variants each reached 90% exact agreement with the adjudicated
human reference and mean absolute error 0.4 over 10 records, with no missing Judge
observations. Pearson is not identifiable because the adjudicated human scores are
constant. Position bias and model self-preference are also `not_identifiable` under
the single-candidate, single-model-family design; length full-minus-compact score delta
is 0.0.
