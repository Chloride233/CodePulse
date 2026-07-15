# Phase 3 Low-Resource Evolution V4 Design

Status: approved for implementation on 2026-07-15.

## Context

Phase 3 must prove stable functional improvement on real repository tasks. The v1-v3
SWE-bench runs completed generation, but their grader boundary was invalid: Docker SDK
received a compound shell string as argv, and the pinned SWE-bench 4.1.0 grader was
called without `include_tests_status`. Commit `a16495c` fixes both defects. Official
container regrading proved that existing Astropy and Flask patches resolve their tasks,
but corrected v3 still has no pass^3 gain, so Issue #3 remains incomplete.

The local machine can run the workload at the frozen `2 CPU / 4096 MB / no swap`
container limit. The constraints are model-call cost and Docker image storage, not GPU
training or host RAM.

## Outcome

Derive a third SkillOpt candidate from unambiguous v3 empty-patch traces, reject it with
a cheap training-only screen unless it demonstrates functional promise, then run one
fully frozen `k=3` comparison on eight new SWE-bench Verified tasks. The final report
must satisfy the existing Validation Gate without relaxing pass^3, regression, or budget
requirements.

## Candidate V3

Training input contains only candidate-v2 rows whose captured patch is empty. An empty
patch cannot resolve a verified failing task, so these 20 rows remain valid training
failures without rewriting the grader-corrupted raw v3 results. Raw files under
`results/phase3/**` remain untouched.

When `iteration_exhaustion` remains dominant after candidate v2 already applied the
first iteration-exhaustion edit, candidate materialization will:

- classify the signal as `persistent_iteration_exhaustion`;
- increase `max_iterations` from 8 to 12 while keeping the model, temperature, token
  limit, and tool set unchanged;
- append one non-duplicated instruction that stops broad exploration, requires the
  smallest defensible patch by iteration 6, reserves the remaining iterations for
  `git diff` and targeted checks, and avoids spending iterations installing missing
  dependencies or retrying unavailable network access;
- record the prompt edit and `max_iterations` change in candidate provenance.

The materializer must not increase the limit again for unrelated failure patterns or
silently duplicate a previous prompt edit.

## Training-Only Screen

Run candidate v3 once on each of these existing training tasks:

- `django__django-10554`
- `mwaskom__seaborn-3069`
- `psf__requests-1142`

All three produced empty patches in every candidate-v2 repetition. They are now training
tasks and can never appear in final v4 evidence. Existing pinned images are reused, so
the screen requires no image download.

Proceed to v4 only when all conditions hold:

- at least two of three trials leave a non-empty patch;
- at least one of three trials is officially resolved;
- no provider, sandbox, or grader infrastructure failure occurs;
- total peak-price cost is at most 2 CNY and each trial is at most 1 CNY.

If the screen fails, stop before acquiring new images and use its traces for another
candidate iteration.

## Frozen V4 Evaluation

The source dataset remains `princeton-nlp/SWE-bench_Verified` at revision
`c104f840cc67f8b6eec6f759ebc8b2693d585d4a`. The downloaded Parquet SHA256 is
`a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd`.

Selection is deterministic: exclude all 21 tasks in the committed v1/v2 snapshots,
filter to `<15 min fix`, shuffle with seed `20260720`, and take the first task from each
repository not yet represented in the v4 cohort until eight tasks are selected. The
holdout guarantee is task-level disjointness; repositories may have appeared in earlier
stages. Only `repo`, `instance_id`, and `difficulty` participate in selection; oracle
patches do not.

The frozen cohort is:

| Task | Official image digest |
|---|---|
| `django__django-15741` | `sha256:dc13c5ff23bfcfa71332e92e5ffa9c87e84319977e74ad182cd1dd083f658099` |
| `pytest-dev__pytest-10081` | `sha256:cb98e7a43ca4a8499a80ae446d100c6afb9ecac747dfafe1f4eca287a8321ecb` |
| `sympy__sympy-16886` | `sha256:73b31a743dab3e473a76cc20328a4876dfafbdfced13bfb76c44d64ad79b508f` |
| `scikit-learn__scikit-learn-13328` | `sha256:9e667cbb7eb011b5c0ec93dac6f00c8ef10b31d2ecf622ab6c8ee98f935258d1` |
| `pydata__xarray-4629` | `sha256:6ae425c05645572e9d1b05cc1677489daadf7fb9fec507927736efc7242a8db5` |
| `psf__requests-5414` | `sha256:168ae94842a3fb649583fe31fddea447fe17504fef03a858750dc8d8f21a8326` |
| `pylint-dev__pylint-7277` | `sha256:c7121ec1ea545d8116c960b75dcfc80ed4911539964bfbb446121ce0a2c8b4e7` |
| `sphinx-doc__sphinx-8621` | `sha256:6eaeb2da91d08b25f8f38c074cc9b5d70f52f31d4b71b233df4789208498ad47` |

Baseline is candidate v2 and candidate is candidate v3. Each task runs three times per
profile: 48 planned trials, seed `20260720`, 10 CNY total, 5 CNY per agent, and 1 CNY
per trial. Resource and network isolation remain `2 CPU / 4096 MB / no swap / no
container network`, with a 900-second trial timeout.

## Image Transport

Experiment identity is the official `swebench/...@sha256` digest. Retrieval may use the
reachable `docker.1ms.run` prefix, but the mirror is transport only. The runner will pull
the mirror reference by the frozen digest, tag it with the official image key expected by
SWE-bench, and record both the official identity and transport reference in the outcome.
Existing v1-v3 manifests without a transport prefix remain valid.

Before pulling v4 images, inspect disk use. Removing old Docker images is a destructive
external action and requires separate user confirmation. Dataset snapshots, raw results,
Phase 2 private files, and committed experiment evidence are never deleted.

## Evidence Flow

1. Curate the 20 empty-patch candidate-v2 rows into committed training evidence with
   source trial SHA256 and selection criteria.
2. Materialize and hash candidate v3 plus provenance.
3. Freeze and run the three-task training screen.
4. If the screen passes, freeze the v4 dataset snapshot, profiles, task IDs, image
   digests, budgets, resource limits, seed, source revision, and CodePulse commit.
5. Run with resume support and generate the comparison report only after all 48 unique
   trial keys complete.
6. Audit success rate, pass@3, pass^3, tokens, peak/off-peak cost, latency, all four
   attribution classes, typical cases, reproduction commands, and Gate verdict.

## Failure Handling

- Workspace reset or clean failure aborts the run instead of becoming a wrong answer.
- Candidate patch apply failure is a functional failure and remains observable.
- Provider, sandbox, and model-version mismatches trigger the existing budget guard or
  resume protections.
- Dataset/profile/provenance/image hash drift fails preflight.
- A rejected final Gate remains a negative experiment; it is never relabeled as Phase 3
  completion.

## Verification

Implementation adds focused tests for persistent-exhaustion materialization, provenance
of the iteration-limit change, v4 manifest validation, mirror pull/tag identity, screen
stopping rules, and backward compatibility for v1-v3 manifests. Before each commit run
only Phase 3-related pytest files plus Ruff, mypy, and Bandit on affected modules.

Phase 3 is complete only when the final real-model report proves positive pass^3 delta,
zero regressions, valid costs, complete frozen coverage, and every Issue #3 acceptance
item. A successful screen or generated report alone is not completion.
