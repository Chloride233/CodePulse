# Phase 2 Browser Review Design

Status: Approved on 2026-07-13
Issue: [#1](https://github.com/Chloride233/CodePulse/issues/1)

## Objective

Reduce the human reviewer's mechanical work without replacing human judgment. The
reviewer should only need to inspect one blinded evidence packet and choose the
supported conclusion. The software owns JSONL formatting, timestamps, progress,
validation, and crash-safe persistence.

This tool serves the existing Phase 2 intra-rater workflow. It does not change the
rubric, packets, reviewer identity, Judge experiment, or Issue #1 acceptance criteria.

## Reviewer Experience

The command is:

```bash
python -m codepulse.eval.calibration_study review \
  --packets <review-packets.jsonl> \
  --responses <human-review.jsonl>
```

It starts a loopback-only local server and opens a browser. The page uses a focused
single-record layout containing:

- Completed count, total count, and current task ID.
- Exit code, test summary, stderr, and the full official verification output.
- One action for each rubric label and its visible standard rationale, with keyboard
  shortcuts `1`, `2`, and `3`.
- An optional custom rationale field for unusual evidence.
- Previous-record navigation for correcting an earlier response.

The three actions pair each label with a concise rubric-derived rationale:

- `supported_pass`: the official exit status and test summary report a completed
  passing run.
- `supported_fail`: the official verification reports a failed, errored, or
  incomplete run.
- `insufficient_evidence`: the official verification is missing or contradictory.

Selecting an action immediately saves the displayed label and standard rationale; the
click or keyboard shortcut is the human confirmation, so an ordinary packet takes one
action. If the reviewer enters a custom rationale first, that text replaces the
standard rationale when the action is selected. The tool does not infer a label,
preselect an action, call an LLM, or save without an explicit reviewer action.

## Data Flow

The `review` command loads and validates the selected packet and response files, then
serves only those packet fields to the browser. It never loads private mappings,
Judge observations, or another review round.

On action selection, the server:

1. Rechecks the packet ID and SHA-256 against the loaded response row.
2. Writes the chosen label, rationale, and current UTC RFC 3339 timestamp.
3. Rewrites the response file through a temporary file in the same directory and
   atomically replaces the original.
4. Advances to the next incomplete response.

Completed rows are retained. Restarting the command resumes at the first incomplete
row, while previous navigation permits deliberate corrections. When every row is
complete, the existing response validator runs and the page reports either success or
the exact validation errors.

## Components

Implementation remains intentionally small:

- `codepulse.eval.calibration_study` adds the `review` CLI arguments and starts the
  server.
- A focused review-server module owns loopback HTTP handling, browser assets, response
  updates, and atomic persistence.
- Existing `load_jsonl`, `write_jsonl`, packet validation, and response validation
  remain authoritative for the experiment schema.

The page uses plain HTML, CSS, and JavaScript served by Python's standard library. No
frontend framework, database, external asset, analytics service, or runtime package is
added.

## Safety And Failure Handling

- The server binds to `127.0.0.1` and uses an unguessable session token in write
  requests. It does not accept remote connections.
- Packet and response paths come only from CLI arguments and are not exposed as
  arbitrary browser-controlled paths.
- Startup fails before opening the browser if packets are invalid, response coverage
  differs, immutable response metadata has drifted, or JSONL cannot be parsed.
- Partially completed templates are allowed at startup, but any already completed row
  must have a valid label, rationale, and timestamp.
- Empty or whitespace-only rationales cannot be saved.
- Atomic replacement prevents an interrupted write from leaving a partial JSONL file.
- The original two review rounds remain separate. The server never copies answers
  between rounds or reveals a prior round while reviewing the current one.

## Verification

Focused deterministic tests cover:

- Startup validation for pristine, partial, complete, mismatched, and malformed
  response files.
- Applying a human-selected label and rationale without changing immutable metadata.
- UTC timestamp creation and atomic persistence.
- Resume position and previous-record correction.
- Rejection of unknown packet IDs, bad session tokens, invalid labels, and empty
  rationales.
- Completion validation and unchanged behavior of existing `prepare`, `validate`,
  `judge`, and `analyze` commands.

Repository checks remain `pytest`, `ruff check`, `mypy`, and Bandit with no
high-severity findings. Browser automation may exercise the local page, but no live
model call or fabricated human annotation is part of testing.

## Acceptance Criteria

The feature is complete when the reviewer can start Round 1 with one command, make a
single explicit choice for an ordinary packet, close the page, restart, and continue
without editing JSONL. Every saved row must pass the existing response schema once the
round reaches 100/100, and no Judge or private mapping data may appear in the browser
or network traffic.
