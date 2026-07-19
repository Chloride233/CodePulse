# Phase 2 Calibration Architecture Simplification

Status: Approved; empirically corrected after v2/v3 candidate captures
Date: 2026-07-13
Issue: [#1](https://github.com/randy-labs/CodePulse/issues/1)

## Objective

Prevent CodePulse from spending Judge calls or human-review effort on a diagnostic
cohort that cannot produce useful qualitative calibration evidence. Simplify the
calibration code around the existing `Task`, `Trial`, and `Trajectory` models, while
extracting only the artifact and comparison primitives that Phase 3 can reuse.

This change remains part of Phase 2. It does not implement SkillOpt validation,
candidate promotion, or any other Phase 3 acceptance item.

## Current Evidence

The completed 100-record functional study remains valid: deterministic evidence is
the reference, and functional Judge v2 reached 100% exact agreement. Human review is
neither required nor methodologically useful for that study.

The first full-evidence diagnostic capture also remains valid as pipeline evidence:
10 of 10 trials completed with full artifacts and no infrastructure failures. It is
not an eligible qualitative calibration cohort. All trials passed, all wrote code
once, none showed an observed failed tool result, and nine executed once. Asking a
reviewer to assign 20 scores to that cohort would mostly repeat the same judgment and
could make correlation or kappa degenerate.

## Architecture Boundary

The existing evaluation models remain authoritative:

```text
Task -> Trial -> Trajectory -> GraderResult
```

No `StudyCase`, generic `Observation`, or second evidence model is introduced.
Phase 2 continues to consume serialized full-evidence trials. Phase 3 continues to
compare trajectories. The two phases may reuse artifact integrity and exact record
alignment, but they do not share rubrics, prompts, human response schemas, cohort
rules, or decision policies.

The reusable surface is intentionally small:

- Canonical JSON hashing and file hashing.
- JSONL loading and writing.
- Refusal to overwrite immutable experiment artifacts.
- Unique-key indexing and exact left/right alignment with duplicate and coverage
  validation.

## Phase 2 Components

### Diagnostic Cohort Profile

A deterministic profiler reads trial dictionaries and assigns each record exactly one
profile status in this order:

1. `infrastructure_failure`: provider, sandbox, or capture failure. Excluded.
2. `incomplete_evidence`: no explicit infrastructure failure exists, but required
   diagnostic evidence or its hash is invalid. Excluded.
3. `unresolved_failure`: complete evidence exists, but official verification failed.
4. `recovered_success`: official verification passed after an observable failed tool
   result or failed execution.
5. `multi_attempt_success`: official verification passed with more than one execution
   attempt or more than one code write, without an observed failure.
6. `direct_success`: every other eligible successful trial.

Classification uses only captured events and official verification. Token counts,
duration, model identity, and Judge output do not determine a stratum.

The profile records per-trial counts for execution attempts, code writes, failed tool
results, and LLM calls. These are descriptive evidence, not qualitative scores.

### Cohort Gate

The frozen `phase2-cohort-v1` policy requires:

- At least 10 eligible full-evidence trials.
- At least three of the four eligible process strata.
- No single eligible stratum above 50% of the selected cohort.
- At least one final success and one final failure.
- Variation in at least one recorded process count.

Infrastructure failures and structurally incomplete trials are reported separately
and never used to satisfy the sample size.

The gate produces a machine-readable profile before any blind packet, Judge call, or
human response template is created. A failed gate returns `not_ready` with exact
reasons and stratum counts. There is no force flag or runtime threshold override that
can bypass this methodological decision. A new versioned protocol is required to
change the policy.

The initial design required a recovered success in addition to three strata. Two
independent 40-record captures found no observed failed tool result followed by
success, even though they produced direct successes, multi-attempt successes, and a
real final failure. That requirement duplicated the three-strata rule and made cohort
eligibility depend on a rare event rather than demonstrated process diversity. The
frozen policy therefore keeps the three-strata, final-failure, 50% cap, and process
variation requirements, while treating recovery as a desirable eligible stratum
rather than a mandatory one.

### Stable Selection

One candidate pool may reference multiple independently frozen run artifacts. Every
source path and exact file hash is recorded in the diagnostic manifest before records
are combined. Duplicate trial IDs remain a hard failure.

When the combined candidate pool contains more than 10 eligible trials, records are grouped by
eligible stratum and shuffled within each group using the frozen seed. Selection then
takes one record at a time in this fixed round-robin order: recovered success,
unresolved failure, multi-attempt success, direct success. Empty groups are skipped
until 10 records are selected. The gate then validates the resulting cohort, including
the 50% cap. Selection never uses Judge or human scores. The selected trial IDs and
source hashes are frozen in the diagnostic manifest.

### Calibration Adapters

Functional calibration remains Judge-versus-deterministic-oracle. Obsolete functional
human response preparation and validation are removed from the active command path.

Diagnostic calibration keeps separate, explicit schemas for:

- Identity-blind review packets.
- External human annotations.
- Judge observations and missing-call records.
- Adjudications.

The loopback browser reviewer is retained only as an optional writer for the human
annotation contract. The core pipeline accepts validated external annotations and
does not require that server.

### Analysis

Analysis remains pure and runs only after packet hashes, complete response coverage,
Judge observation status, and private mappings validate. Functional and diagnostic
studies may share small statistical functions, but they keep separate reports because
their references and claims differ.

## Data Flow

```text
full-evidence candidate pool
  -> structural validation
  -> deterministic cohort profile
  -> phase2-cohort-v1 gate
      -> not_ready: profile + reasons; stop before Judge/human work
      -> ready: stable selection + frozen source hashes
          -> blind packets
          -> Judge observations + external human annotations
          -> validation and exact alignment
          -> calibration analysis JSON + Markdown report
```

The existing homogeneous 10-trial capture must produce `not_ready`. It remains valid
evidence that capture and hashing work; it is not relabeled as a failed experiment.

## Failure Handling

- Structural evidence failures and infrastructure failures remain distinct.
- A failed cohort gate writes only its profile when an output path is requested. It
  does not leave partial review packets or empty human templates.
- Existing experiment artifacts are not overwritten unless the operation is a
  deterministic rewrite that already exposes an explicit safe overwrite option.
  The cohort gate itself cannot be bypassed by that option.
- Malformed or exhausted Judge calls remain missing observations, never score zero.
- Missing human annotations keep the study incomplete; CodePulse never generates or
  impersonates a human reference.
- Duplicate IDs, missing aligned records, and hash drift fail before statistics run.

## Migration

1. Add focused artifact utilities and a Phase 2 cohort module.
2. Integrate the cohort gate before diagnostic packet preparation.
3. Add a read-only cohort profiling command so a candidate pool can be checked without
   reviewer IDs or an output study directory.
4. Remove active functional-human CLI routes and their duplicated preparation path,
   while preserving functional Judge reproducibility.
5. Update the runbook to capture a candidate pool, run the profile, and proceed only
   when `ready`.
6. Keep historical private mappings and real run directories untouched. They are
   evidence, not migration inputs.

## Verification

Deterministic tests must prove:

- The six profile outcomes are mutually exclusive and use the documented
  priority.
- Failed tool results followed by official success classify as recovery.
- Multiple successful executions or writes classify as multi-attempt success.
- Infrastructure and incomplete records are excluded and reported separately.
- Homogeneous all-success cohorts fail before packet construction.
- A diverse cohort passes, selects deterministically, and freezes its profile in the
  manifest.
- Multiple candidate sources preserve their individual paths and hashes in the
  manifest.
- Gate failure writes no review packets or human templates.
- Shared hashing/JSONL behavior preserves current artifact bytes and hashes.
- Existing packet blinding, response validation, Judge missing-observation handling,
  and analysis metrics remain correct.

Repository verification remains `pytest`, coverage at least 80%, `ruff check`, `mypy`,
and Bandit with no high-severity findings. The real homogeneous diagnostic batch is
also run through the new read-only profile command as experimental verification.

## Success Criteria

The architecture change is complete when:

- The real current diagnostic batch is automatically rejected as `not_ready` for
  qualitative calibration with understandable reasons.
- No Judge or human-review artifact can be prepared from that batch through the
  normal Phase 2 command path.
- Functional deterministic calibration remains reproducible without a human-labeling
  workflow.
- Tests and repository quality gates pass.
- Documentation no longer instructs a user to review a cohort before checking its
  methodological eligibility.
