# Phase 2 LLM-as-Judge Calibration Design

Status: Approved for specification on 2026-07-13
Issue: [#1](https://github.com/Chloride233/CodePulse/issues/1)

## Objective

Phase 2 must establish where LLM-as-Judge scores are trustworthy, where they are
biased, and where deterministic evidence must remain authoritative. Completion is
measured against every acceptance item in Issue #1, not by the existence of a
calibration API alone.

The existing `calibration-sample-v1` remains the accepted 100-record stratified
sample. It contains only deterministic functional evidence. A smaller diagnostic
batch will add the full artifacts needed to study process-oriented judging and
presentation bias without rerunning all 100 records.

## Evidence Boundary

### Existing 100-record sample

The existing sample supports only the question:

> Does the presented deterministic evidence support a functional pass, a
> functional failure, or neither conclusion?

It does not support judgments about reasoning quality, code quality, maintainability,
or experience alignment because Phase 1 did not persist final code or full
transcripts. The sample file and manifest remain immutable inputs; review and judge
outputs are stored in separate files.

The functional-evidence rubric has three categorical labels:

- `supported_pass`: official deterministic evidence reports a completed passing run.
- `supported_fail`: official deterministic evidence reports a failed or incomplete run.
- `insufficient_evidence`: the record is contradictory, missing required fields, or
  cannot support either conclusion.

Reviewers and judges must not infer solution quality beyond those labels. The
deterministic Grader remains ground truth for this dimension; an LLM Judge result is
diagnostic and must never override it.

### Diagnostic batch

The diagnostic batch captures task text, final code, complete normalized Trace,
official test results, token counts, and immutable hashes before sandbox teardown.
It uses the same tasks and prompt policy for two candidate model families. Two Judge
model families score both candidate families, producing a crossed design rather than
confounding candidate and Judge identity.

The minimum diagnostic design is 10 tasks x 2 candidate model families, yielding 20
candidate records. The experiment manifest freezes task IDs, candidate profiles,
provider model versions, prompts, environment digest, seed, budgets, and Judge
models. If two provider families are unavailable, the study may still run but
`model_self_preference` must be reported as `not_identifiable`; it cannot be silently
replaced by a weaker proxy.

## Review Protocol

Two review rounds are performed without access to Agent identity, candidate model,
Judge model, Judge score, prior review, or deterministic success flags derived from
the target label. Review packets use stable opaque IDs and a seeded random order per
round.

The preferred mode is two independent human reviewers. When only one reviewer is
available, the same person may review both independently shuffled rounds; the
manifest must then identify the result as intra-rater repeatability rather than
inter-rater agreement. The software records reviewer IDs and mode but does not claim
that an LLM or this coding agent is a human reviewer.

Each annotation records:

- `sample_id`, `round`, `reviewer_id`, rubric version, and rubric label.
- A 1-5 score only for diagnostic dimensions whose evidence is complete.
- Evidence references and a short required rationale.
- `reviewed_at` and the exact review-packet SHA-256.

Raw round files are append-free, immutable experiment inputs after submission.
Disagreements are written to a separate adjudication file containing the resolution
and rationale. Adjudication never overwrites either original annotation.

Before analysis, a validator rejects duplicate sample IDs, unknown labels, incomplete
coverage, packet hash mismatches, reviewer leakage, and diagnostic scores on
ineligible dimensions.

## Judge Protocol

Judge prompts use the same published rubric version as humans and require strict JSON
with a categorical label or integer score plus evidence-grounded reasoning. Calls use
temperature 0, frozen provider model versions when the provider exposes them, bounded
retry, and raw-response persistence. Failed or malformed calls are recorded as
missing observations, not score zero.

The functional study presents the same evidence packet to the Judge that a human
reviews. The diagnostic study produces these paired variants:

- `position_ab` and `position_ba`: identical candidate pair with order swapped.
- `length_full` and `length_compact`: the same candidate evidence with a deterministic
  compact Trace projection that removes repetition but preserves every decision,
  tool result status, final artifact, and official test result.
- `identity_blind`: all candidate and provider identifiers removed from the prompt.

Model identity remains in private experiment metadata for crossed analysis but is
never shown in the identity-blind prompt.

## Bias Analysis

All metrics report the sample count and missing-observation count. No significance
claim is made from the small diagnostic batch.

- Agreement: exact agreement, within-one-point agreement for 1-5 scores, and Cohen's
  kappa for categorical labels. Human-human and each Judge-human comparison are
  reported separately.
- Correlation: Pearson correlation for score agreement, alongside kappa so correlation
  is not mistaken for absolute agreement.
- Calibration: mean signed error, mean absolute error, and score distribution before
  and after bias correction. Corrections are derived on a deterministic split and
  evaluated on held-out records; in-sample improvement is not accepted as evidence.
- Position bias: A/B preference flip rate and signed score delta after swapping order.
- Length bias: paired full-versus-compact score delta and correlation between evidence
  length and Judge-minus-human residual.
- Model self-preference: difference in Judge-minus-human residual for own-family versus
  other-family candidates in the crossed design.
- Hard cases: every human-human disagreement, Judge-human disagreement, malformed Judge
  result, official failure, and perturbation-sensitive record is listed with opaque ID
  and evidence references.

Degenerate kappa caused by class prevalence must be reported with the label
distribution and raw agreement. It must not be presented as proof of either strong or
weak Judge quality by itself.

## Components And Data Flow

Implementation remains intentionally small:

1. The adapter trial runner gains an opt-in evidence capture path. When enabled, it
   serializes collected output files and the normalized Transcript into the Trial
   before the container is destroyed. Default benchmark behavior is unchanged.
2. `codepulse.eval.calibration_study` provides deterministic `prepare`, `validate`,
   and `analyze` operations plus an explicit live `judge` operation. It reuses
   `call_llm_with_retry` but owns the study-specific prompt and schema.
3. Review packets and responses use JSONL. The rubric and experiment manifest are
   versioned documents. Statistics use the Python standard library; no analytics
   dependency is added for the required metrics.
4. A Markdown report is rendered from the validated analysis JSON. The JSON is the
   authoritative result; the report is the human-readable evidence artifact.

The data flow is:

```text
frozen benchmark inputs
  -> optional full-evidence capture
  -> immutable evidence JSONL + manifest + hashes
  -> blinded review packets / Judge variants
  -> two human response files + raw Judge responses
  -> validation
  -> analysis JSON
  -> calibration report Markdown
```

Expected artifacts:

```text
experiments/phase2/calibration-study-v1/manifest.json
docs/phase2-human-rubric.md
results/phase2/review-packets-round-1.jsonl
results/phase2/review-packets-round-2.jsonl
results/phase2/human-review-round-1.jsonl
results/phase2/human-review-round-2.jsonl
results/phase2/adjudication.jsonl
results/phase2/judge-observations.jsonl
results/phase2/calibration-analysis.json
results/phase2/calibration-report.md
```

The current sample and its manifest remain at their existing paths and are referenced
by hash from the study manifest.

## Failure Handling

- Existing output paths are never overwritten unless an explicit, safe `--force`
  option is supplied to a deterministic preparation step.
- Live runs stop on model-version drift, budget limits, repeated provider failures, or
  evidence-capture failure. Partial outputs remain marked `incomplete`.
- Judge retry exhaustion and invalid JSON remain explicit missing observations with
  raw error evidence.
- Review validation fails closed. Analysis cannot run with missing rounds, hash drift,
  or ineligible labels unless `--allow-incomplete` is explicitly used; such a report
  is stamped `incomplete` and cannot satisfy Issue #1.
- Secrets, environment variables, and hidden reasoning fields not returned by a
  provider are not captured. Only observable model messages and tool events are
  eligible evidence.

## Verification

Deterministic tests cover:

- Evidence serialization before sandbox teardown and unchanged default behavior.
- Stable packet IDs, seeded blinding, and absence of identity/Judge leakage.
- Round validation, coverage, label schema, hash checks, and immutable adjudication.
- Exact agreement, kappa, Pearson correlation, held-out correction metrics, and each
  paired bias calculation on fixed fixtures.
- Degenerate labels, malformed Judge responses, missing observations, and
  non-identifiable self-preference.
- Report generation from a known analysis fixture.

Repository gates are `pytest`, `ruff check`, `mypy`, and Bandit with no high-severity
findings. Live provider calls and human annotations are reproducible experiment steps,
not CI tests.

## Issue #1 Completion Evidence

Issue #1 is complete only when all rows below have authoritative artifacts:

| Acceptance item | Required evidence |
|---|---|
| At least 100 stratified samples | Existing v1 JSONL, manifest, hashes, and reproduction command |
| Rubric and two review rounds | Published rubric, two complete validated response files, reviewer mode, and adjudication |
| Agreement metric | Validated analysis JSON with counts, agreement, kappa, correlation, and distributions |
| Position, length, self-preference, hard cases | Paired diagnostic observations and explicit result or `not_identifiable` with reason |
| Grader usage boundaries | Final report section grounded in observed results |
| Resume evidence | Sample size, metrics, principal biases, and held-out before/after correction in the final report |

Code, prompts, empty templates, or dry-run fixtures do not satisfy experimental or
human-review acceptance items. Phase 3 must not start until this table is backed by
completed evidence or Issue #1 explicitly changes its acceptance criteria.
