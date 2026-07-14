# Phase 2 LLM-as-Judge Calibration Report

Status: **complete**

## Functional Oracle Calibration

- Sample size: 100
- Exact agreement before: 91.0%
- Exact agreement after: 100.0%
- Cohen's kappa before: 0.2936
- Cohen's kappa after: 1.0
- Reference: deterministic official functional verification, not human annotation.

## Qualitative Diagnostic Study

Sample size: **10**
Reviewer mode: **intra-rater**

## Agreement

- Intra-rater repeatability sample count: 10
- Intra-rater repeatability exact agreement: 0.9
- Intra-rater repeatability within one point: 0.9
- Intra-rater repeatability Cohen's kappa: 0.0
- Intra-rater repeatability Pearson: not_available
- Intra-rater repeatability Pearson reason: requires at least two non-constant aligned score distributions
- Intra-rater repeatability mean absolute error: 0.2
- Full Judge-human sample count: 10
- Full Judge-human exact agreement: 0.9
- Full Judge-human within one point: 0.9
- Full Judge-human Cohen's kappa: 0.0
- Full Judge-human Pearson: not_available
- Full Judge-human Pearson reason: requires at least two non-constant aligned score distributions
- Full Judge-human mean absolute error: 0.4
- Compact Judge-human sample count: 10
- Compact Judge-human exact agreement: 0.9
- Compact Judge-human within one point: 0.9
- Compact Judge-human Cohen's kappa: 0.0
- Compact Judge-human Pearson: not_available
- Compact Judge-human Pearson reason: requires at least two non-constant aligned score distributions
- Compact Judge-human mean absolute error: 0.4
- Missing Judge observations: 0

## Bias Diagnostics

- Position bias: not_identifiable
- Position bias reason: a single candidate provides no order-swapped A/B comparison
- Length full-minus-compact delta: 0.0
- Length/residual Pearson: 0.1907
- Model self-preference: not_identifiable
- Model self-preference reason: crossed candidate and Judge model families are unavailable

No significance claim is made from this small diagnostic batch.

## Hard Cases

Total: **4**

- human disagreement: 1
- judge human disagreement: 2
- official failure: 1

## Held-out Calibration

- Mean absolute error before: 0.0
- Mean absolute error after: 0.0

## Usage Boundaries

- **Deterministic Grader:** authoritative for executable official tests and static checks.
- **LLM Judge:** limited to evidence-complete qualitative dimensions with raw-response retention; observed full-evidence exact agreement 0.9 and mean absolute error 0.4.
- **Human calibration:** required for qualitative agreement and hard-case adjudication; observed 1 raw round disagreement and 1 adjudication.
