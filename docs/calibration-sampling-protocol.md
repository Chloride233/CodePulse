# Phase 2 Calibration Sampling Protocol

Status: **Judge calibration complete; human annotation not started**
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

Every LLM Judge and human review score is `null`; extraction does not count as annotation. Phase 1 preserved deterministic test evidence and aggregate metrics but not final code or full transcripts. Therefore this sample is currently eligible only for functional-evidence calibration and is explicitly ineligible for process-quality or experience-alignment judgment.

Before starting the rubric and two-pass review, CodePulse must capture the missing judge inputs or create a new evidence batch. Pytest logs must not be presented to reviewers as a substitute for agent reasoning or final code.

The approved functional-evidence rubric is now published at
`docs/phase2-human-rubric.md`. The existing sample remains ineligible for process or
alignment scores; `docs/phase2-calibration-runbook.md` defines the separate diagnostic
capture and two-round review workflow.

The completed Judge before/after evidence is stored in
`results/phase2/judge-calibration-before-after.json` and `.md`. Agreement in that
report uses deterministic functional evidence as the reference and is not represented
as human agreement.
