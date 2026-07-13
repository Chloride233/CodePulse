# Phase 2 Calibration Runbook

Status: implementation ready; live Judge and human review not completed
Rubric: [`phase2-human-rubric.md`](phase2-human-rubric.md)

## 1. Prepare Two Blind Review Rounds

Use distinct reviewer IDs for inter-rater agreement. Use the same reviewer ID for both
rounds only when intentionally measuring intra-rater repeatability.

```bash
python -m codepulse.eval.calibration_study prepare \
  --input results/phase2/calibration-sample-v1.jsonl \
  --output-dir results/phase2/calibration-study-v1 \
  --seed 20260713 \
  --reviewer-1 REVIEWER_ID_1 \
  --reviewer-2 REVIEWER_ID_2
```

This writes two packet files, two private mapping files, two unscored human response
templates, and a manifest. It refuses to overwrite an existing study.

## 2. Run The Functional Evidence Judge

The Judge sees the same identity-blind evidence as the human reviewer. A provider
failure or malformed response is stored as a missing observation, never score zero.

```bash
python -m codepulse.eval.calibration_study judge \
  --packets results/phase2/calibration-study-v1/review-packets-round-1.jsonl \
  --output results/phase2/calibration-study-v1/judge-observations.jsonl \
  --model PINNED_JUDGE_MODEL
```

Record the immutable provider model version in the experiment notes before accepting
the output. A mutable alias does not satisfy the study protocol.

## 3. Complete And Validate Human Reviews

Reviewers fill only `label`, `rationale`, and `reviewed_at` in their assigned response
file. Validate each round independently:

```bash
python -m codepulse.eval.calibration_study validate \
  --packets results/phase2/calibration-study-v1/review-packets-round-1.jsonl \
  --responses results/phase2/calibration-study-v1/human-review-round-1.jsonl
```

Repeat for Round 2. Resolve disagreements in a separate `adjudication.jsonl`; never
edit either raw round to force agreement.

## 4. Capture Diagnostic Evidence

The existing Phase 1 run lacks full artifacts. A new run must opt in explicitly:

```bash
codepulse benchmark pilot-run \
  --manifest experiments/pilot-v1/manifest.json \
  --output-dir results/phase2/diagnostic-run-v1 \
  --capture-evidence
```

Do not overwrite or merge with the Phase 1 baseline. Diagnostic score, position-pair,
length-pair, and crossed model-family JSONL files must be derived from this new
evidence. If a second candidate/Judge family is unavailable, record model self-
preference as `not_identifiable` with that reason.

## 5. Analyze And Render The Report

```bash
python -m codepulse.eval.calibration_study analyze \
  --packets-1 results/phase2/calibration-study-v1/review-packets-round-1.jsonl \
  --mapping-1 results/phase2/calibration-study-v1/review-mapping-round-1.private.jsonl \
  --responses-1 results/phase2/calibration-study-v1/human-review-round-1.jsonl \
  --packets-2 results/phase2/calibration-study-v1/review-packets-round-2.jsonl \
  --mapping-2 results/phase2/calibration-study-v1/review-mapping-round-2.private.jsonl \
  --responses-2 results/phase2/calibration-study-v1/human-review-round-2.jsonl \
  --judge-observations results/phase2/calibration-study-v1/judge-observations.jsonl \
  --adjudications results/phase2/calibration-study-v1/adjudication.jsonl \
  --score-rows results/phase2/calibration-study-v1/score-rows.jsonl \
  --position-pairs results/phase2/calibration-study-v1/position-pairs.jsonl \
  --length-pairs results/phase2/calibration-study-v1/length-pairs.jsonl \
  --self-preference-rows results/phase2/calibration-study-v1/self-preference-rows.jsonl \
  --output-json results/phase2/calibration-analysis.json \
  --output-report results/phase2/calibration-report.md
```

The command reports `complete` only when the full Issue #1 evidence gate passes.
Generated templates, mocked tests, and an `incomplete` report are implementation
evidence, not completed calibration results.
