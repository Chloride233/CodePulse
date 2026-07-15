# Phase 3 Tool-Contract Evolution V5 Design

Status: high-level approach approved on 2026-07-15; implementation awaits written spec review.

## Context

The frozen v4 SWE-bench experiment completed all 48 trials on the local machine at
`2 CPU / 4096 MB / no swap`. Peak-price cost was 1.733178 CNY, so GPU training, host
RAM, and model-call budget are not the current constraints. The candidate increased raw
success rate from 25.0% to 29.2%, but pass@3 remained 37.5% and pass^3 remained 12.5%.
The Validation Gate correctly rejected it with `no_stable_improvement`.

Candidate v3 also increased total tokens from 1,300,330 to 2,503,580, p50 latency from
21.054 seconds to 36.508 seconds, and peak-price cost from 0.757777 CNY to 0.975401 CNY.
Increasing `max_iterations` from 8 to 12 therefore consumed more resources without a
stable gain. Candidate v3 remains rejected evidence and must not become the next
baseline.

The v4 traces expose three shared tool-contract defects that confound further prompt
optimization:

- both profiles called an advertised-by-habit but unavailable `edit_file` tool;
- `read_file` silently ignored model-supplied `offset` and `limit`, returning large files
  and expanding later contexts;
- `execute` advertised package installation even though the frozen SWE-bench container
  has no network, contradicting the repository-agent prompt.

These are framework defects, not candidate advantages. They must be repaired once and
made identical for baseline and candidate before another comparison.

## Outcome

Introduce a small, deterministic repository-tool contract, then compare the accepted
candidate-v2 baseline against one new eight-iteration candidate with a compact execution
policy. Reject the candidate in a six-trial training-only screen unless it improves
functional outcomes without increasing resource use materially. Only a passing screen
may proceed to a fully frozen `k=3` comparison on eight new SWE-bench Verified tasks.

The Validation Gate remains unchanged. Phase 3 completes only with a positive pass^3
delta, zero task-level regressions, valid costs, complete frozen coverage, and all Issue
#3 acceptance evidence.

## Shared Tool Contract

Both v5 profiles receive exactly these tools in the same order:

1. `read_file`
2. `edit_file`
3. `write_file`
4. `execute`

Agent profile `tools` becomes an enforced runtime contract rather than descriptive
metadata. The profile loader passes the frozen tool names to `RealAgent`; the agent
builds a registry containing only those known tools and fails before a model call when a
profile names an unsupported tool. Historical profiles and manifests remain unchanged.

### Bounded Reads

`read_file` keeps `path` and adds optional positive integer `offset` and `limit`
arguments. `offset` is a one-based starting line and `limit` is the number of lines to
return. Omitting both preserves the current whole-file behavior and output cap. Invalid
values fail deterministically instead of being ignored. Paths are shell-quoted before
container execution.

This change prevents a request such as `offset=1507, limit=50` from returning an entire
large module and charging that content again on every later model call.

### Exact Edits

`edit_file` accepts `path`, `old_string`, and `new_string`. It replaces exactly one
occurrence while preserving the rest of the file. Zero matches and multiple matches
fail with an explicit diagnostic and never modify the file. Ambiguous `content`,
`offset`, or whole-file replacement variants are not supported; `write_file` remains the
explicit whole-file operation.

### Offline Execution Wording

`execute` remains a general shell command tool, but its schema describes repository
inspection, targeted transformations, and existing checks. It no longer recommends
installing packages. The tool itself does not add a command blocklist because generic
CodePulse tasks may legitimately need package commands; the SWE-bench profile and
network isolation remain the enforcement boundary.

## Baseline And Candidate

The baseline is candidate v2, not rejected candidate v3. A v5-specific frozen baseline
profile copies candidate v2's model, prompt, temperature, token limit, and
`max_iterations=8`, changing only the shared tool list and profile identity needed to
record the new contract. Candidate and baseline use the same DeepSeek model version and
the same tool implementations.

Candidate v4 starts from candidate v2 and records rejected candidate v3 in provenance.
It does not append the v3 instruction or inherit the 12-iteration limit. Instead, it
replaces the accumulated SkillOpt suffix with one compact policy:

- use at most two iterations to identify the likely code path;
- make one exact, minimal edit by iteration 4;
- do not overwrite a file from a partial read;
- use the repository's existing environment and do not spend iterations on unavailable
  dependencies or network access;
- use the remaining iterations for one targeted check and `git diff`;
- if a test cannot start for an environment reason, retain a defensible patch and verify
  it statically rather than reverting to an empty diff.

Candidate v4 keeps `max_iterations=8`, `max_tokens=4096`, and `temperature=0.0`. Its
provenance records the baseline profile hash, v4 training evidence hash, rejected v3
evidence hash, prompt replacement, unchanged iteration limit, tool-contract version,
and source trial IDs.

## Training Evidence

After v4 was evaluated, its eight task IDs became revealed and may be used only for
training or screening. They can never appear in v5 held-out evidence. Raw
`results/phase3/**` files remain untouched and uncommitted.

Curated training evidence contains only failed candidate-v2 rows from v4, excluding
provider, sandbox, grader, and authentication failures. It records the source trials
SHA256, selection predicate, source trial IDs, and deterministic counts for empty
patches, exhausted iterations, unsupported tool calls, oversized reads, and offline
package attempts. No oracle patch or hidden test content is added to the candidate
prompt.

## Training-Only Screen

The screen uses three already-revealed v4 tasks selected before candidate execution to
cover distinct observed failure modes:

- `pytest-dev__pytest-10081`: unsupported exact edit and empty-patch behavior;
- `scikit-learn__scikit-learn-13328`: dependency-installation and late-edit behavior;
- `sphinx-doc__sphinx-8621`: early finalization with an empty patch.

Run baseline and candidate once on each task, for six planned trials using existing v4
images. Proceed only when every condition holds:

- all six unique trial keys complete;
- candidate leaves a non-empty patch on at least two tasks;
- candidate officially resolves at least two tasks;
- candidate resolves at least as many tasks as baseline;
- candidate total tokens and peak-price cost are each no more than 125% of baseline;
- no provider, sandbox, grader, authentication, or model-version failure occurs;
- total screen cost is at most 2 CNY and each trial is at most 1 CNY.

If the screen fails, stop before selecting or downloading new held-out images. The
candidate is rejected and its edit is recorded; the screen is never presented as Phase
3 completion.

## Frozen V5 Evaluation

The source remains `princeton-nlp/SWE-bench_Verified` at revision
`c104f840cc67f8b6eec6f759ebc8b2693d585d4a`, using the already verified source artifact
SHA256. Selection excludes every task in v1 through v4 snapshots plus all training and
screen tasks. It filters to `<15 min fix`, shuffles with seed `20260721`, and takes at
most one task per repository until eight tasks are selected. Oracle patches do not
participate in selection.

Before any model call, commit and hash:

- the eight-task dataset snapshot and source revision;
- baseline and candidate profiles plus provenance;
- task IDs and official image digests;
- tool-contract version and CodePulse commit;
- seed, `k=3`, model versions, budgets, resource limits, timeout, and network policy;
- zero overlap with all training, screen, and prior held-out task IDs.

The final run remains 48 trials: eight tasks, two profiles, and three repetitions.
Resource isolation remains `2 CPU / 4096 MB / no swap / no container network`, with a
900-second trial timeout. Budgets remain 10 CNY total, 5 CNY per agent, and 1 CNY per
trial. The runner is serial and resumable.

## Storage And Local Execution

The screen reuses the eight preserved v4 images and requires no new image download.
Before final v5 image acquisition, record host free space and Docker usage. Estimate the
post-pull margin from actual v4 image usage; stop before pulling if the projected free
space is below 20 GiB. No image, dataset, raw result, log, or private Phase 2 file is
deleted without a new explicit approval.

This plan does not require a GPU or rented server. A server becomes relevant only if the
frozen storage preflight fails or the user chooses to parallelize beyond the validated
local resource envelope.

## Evidence And Gate

After 48 unique keys complete, generate and independently audit:

- success rate, pass@3, pass^3, tokens, peak/off-peak cost, p50/p95 latency;
- improvements, regressions, persistent failures, and stable successes;
- provider model versions, profile/dataset/image hashes, budget stops, and failure types;
- typical cases and exact reproduction commands.

The existing Validation Gate is not relaxed. Acceptance requires a positive candidate
pass^3 delta, zero regressions, complete coverage, frozen identity, and valid budgets.
A success-rate-only increase, a screen pass, or a generated report is insufficient.

## Failure Handling

- Tool-contract validation fails before a model call for unknown profile tools.
- Bounded read and exact edit validation errors are observable tool failures, not silent
  fallback behavior.
- Workspace reset or clean failure aborts the trial instead of becoming a wrong answer.
- Provider or model-version failures remain recorded; final trials are not selectively
  rerun.
- Dataset, profile, provenance, task-overlap, image-digest, or code-revision drift fails
  preflight.
- A rejected screen prevents image acquisition; a rejected final Gate remains committed
  negative evidence and does not complete Phase 3.

## Verification

Implementation adds focused deterministic tests for:

- profile tool-list enforcement and unsupported-tool rejection;
- bounded read defaults, line ranges, invalid values, quoting, and output caps;
- exact edit success, zero-match, multiple-match, and no-partial-write behavior;
- neutral `execute` schema wording;
- candidate-v4 prompt replacement, eight-iteration limit, rejected-v3 provenance, and
  non-duplication;
- six-trial screen coverage, functional/resource thresholds, and stop-before-download;
- v5 manifest identity, prior-task exclusion, frozen digests, resume uniqueness, and
  backward compatibility.

Before each commit, run only the affected Phase 3 pytest files, Ruff, mypy, Bandit at
the repository CI severity threshold, and the relevant preflight or minimal Docker
smoke check. Raw experiment output stays under `results/**` and is never staged.
