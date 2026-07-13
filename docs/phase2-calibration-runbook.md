# Phase 2 Calibration Runbook

Status: functional calibration complete; diagnostic capture valid; qualitative cohort not ready
Rubric: [`phase2-human-rubric.md`](phase2-human-rubric.md)

## 1. Functional Calibration

The 100-record sample contains official functional verification but no complete Trace
or final artifact. Its reference label is derived deterministically from exit status
and pytest output. It is not a human task.

Completed evidence:

- `results/phase2/judge-calibration-before-after.json`
- `results/phase2/judge-calibration-before-after.md`
- `results/phase2/calibration-study-v1/judge-observations-v1.jsonl`
- `results/phase2/calibration-study-v1/judge-observations-v2.jsonl`

Judge v2 reached 100/100 exact agreement with the deterministic oracle. Reproduction
uses one functional packet set and does not create human response files:

```bash
.venv/bin/python -m codepulse.eval.calibration_study prepare-functional \
  --input results/phase2/calibration-sample-v1.jsonl \
  --output-dir results/phase2/functional-study-reproduction

.venv/bin/python -m codepulse.eval.calibration_study judge-functional \
  --packets results/phase2/functional-study-reproduction/functional-packets.jsonl \
  --output results/phase2/functional-study-reproduction/judge-observations.jsonl \
  --model deepseek/deepseek-chat
```

This result establishes only functional-evidence interpretation. It does not establish
Judge reliability for process quality or experience alignment.

## 2. Profile Before Spending

Every full-evidence candidate pool must pass `phase2-cohort-v1` before CodePulse
creates blind packets, calls the qualitative Judge, or asks for human review.

The completed first capture is checked with:

```bash
.venv/bin/python -m codepulse.eval.calibration_study profile-diagnostic \
  --input results/phase2/diagnostic-run-v1-retry-2/trials.jsonl
```

The command returns exit status 1 and `status: not_ready`. Its observed composition is
9 direct successes and 1 multi-attempt success. It has no final failure and no
recovered success. This capture proves that full evidence and immutable hashes work,
but it must not be sent to a reviewer or Judge for qualitative calibration.

## 3. Capture A Diverse Candidate Pool

The next frozen manifest uses the same two audited Agent profiles over all 20 pilot
tasks, once per profile. Forty candidate records provide a larger pool from which the
deterministic gate selects exactly 10; they do not increase the human-review count.

```bash
.venv/bin/python -m codepulse.cli benchmark preflight \
  --manifest experiments/phase2-diagnostic-v2/manifest.json \
  --repo-root .

.venv/bin/python -m codepulse.cli benchmark pilot-run \
  --manifest experiments/phase2-diagnostic-v2/manifest.json \
  --output-dir results/phase2/diagnostic-pool-v2 \
  --capture-evidence

.venv/bin/python -m codepulse.eval.calibration_study profile-diagnostic \
  --input results/phase2/diagnostic-pool-v2/trials.jsonl
```

Proceed only when the last command returns exit status 0 and `status: ready`. A
`not_ready` result names the missing process strata; it is not permission to lower the
gate or invent failure evidence. Provider, sandbox, and capture failures are excluded
and reported separately.

## 4. Prepare The Qualitative Study

Once the candidate pool is ready, create two independently shuffled identity-blind
rounds. The gate selects and freezes exactly 10 records before writing any review
artifact:

```bash
.venv/bin/python -m codepulse.eval.calibration_study prepare-diagnostic \
  --input results/phase2/diagnostic-pool-v2/trials.jsonl \
  --output-dir results/phase2/diagnostic-study-v2 \
  --reviewer-1 Chloride233 \
  --reviewer-2 Chloride233
```

One reviewer completing both rounds measures intra-rater repeatability. Two reviewer
IDs measure inter-rater agreement. The required human work remains 20 qualitative
decisions, not 200. CodePulse does not generate or impersonate either human round.

The optional loopback reviewer writes the validated annotation format directly and
resumes at the first incomplete item:

```bash
.venv/bin/python -m codepulse.eval.calibration_study review-diagnostic \
  --packets results/phase2/diagnostic-study-v2/review-packets-round-1.jsonl \
  --responses results/phase2/diagnostic-study-v2/human-review-round-1.jsonl
```

Finish and validate Round 1 before opening Round 2:

```bash
.venv/bin/python -m codepulse.eval.calibration_study validate-diagnostic \
  --packets results/phase2/diagnostic-study-v2/review-packets-round-1.jsonl \
  --responses results/phase2/diagnostic-study-v2/human-review-round-1.jsonl
```

The browser is only an annotation writer. Validation and analysis accept the same
external JSONL contract without requiring that server.

## 5. Run Judge Diagnostics And Analyze

After the cohort gate passes, run the qualitative Judge over full and deterministic
compact Trace variants:

```bash
.venv/bin/python -m codepulse.eval.calibration_study judge-diagnostic \
  --packets results/phase2/diagnostic-study-v2/review-packets-round-1.jsonl \
  --output results/phase2/diagnostic-study-v2/judge-observations.jsonl \
  --model deepseek/deepseek-chat
```

Malformed or exhausted calls remain missing observations, never score zero. With one
model family and no A/B candidate pair, position bias and model self-preference remain
`not_identifiable`; CodePulse does not manufacture weaker proxies.

After both human rounds validate, generate the authoritative JSON and Markdown report:

```bash
.venv/bin/python -m codepulse.eval.calibration_study analyze-diagnostic \
  --packets-1 results/phase2/diagnostic-study-v2/review-packets-round-1.jsonl \
  --mapping-1 results/phase2/diagnostic-study-v2/review-mapping-round-1.private.jsonl \
  --responses-1 results/phase2/diagnostic-study-v2/human-review-round-1.jsonl \
  --packets-2 results/phase2/diagnostic-study-v2/review-packets-round-2.jsonl \
  --mapping-2 results/phase2/diagnostic-study-v2/review-mapping-round-2.private.jsonl \
  --responses-2 results/phase2/diagnostic-study-v2/human-review-round-2.jsonl \
  --judge-observations results/phase2/diagnostic-study-v2/judge-observations.jsonl \
  --functional-result results/phase2/judge-calibration-before-after.json \
  --output-json results/phase2/calibration-analysis.json \
  --output-report results/phase2/calibration-report.md
```

Disagreements use a separate `--adjudications` JSONL artifact and never overwrite a
raw review round. Phase 3 must not start until these real human and Judge artifacts
satisfy Issue #1; code, prompts, empty templates, and mocked tests are not completion
evidence.
