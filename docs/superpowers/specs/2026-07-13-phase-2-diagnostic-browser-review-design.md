# Phase 2 Diagnostic Browser Review Design

Status: Approved on 2026-07-13
Issue: [#1](https://github.com/Chloride233/CodePulse/issues/1)

## Objective

Reduce the reviewer's mechanical work for the required qualitative calibration
without replacing human judgment. The reviewer inspects one identity-blind,
full-evidence diagnostic packet, assigns a 1-5 process-quality score, and records one
observable reason. The software owns JSONL updates, timestamps, progress, validation,
and crash-safe persistence.

This tool is only for the 10-record `diagnostic-process-v1` study. It must not be used
to repeat deterministic functional labeling.

## Reviewer Experience

The command accepts exactly one packet file and its matching response file, starts a
loopback-only server, and opens the local browser. The page uses a focused single-item
layout with:

- Round number, completed count, total count, and previous/next navigation.
- Task description and supplied code.
- Final `solution.py`.
- The complete observable Trace, including tool results and recovery evidence.
- Official pytest verification and token/time metrics.
- A stable 1-5 segmented score control using the published rubric.
- A required rationale field and one explicit save-and-continue action.

Saving immediately persists the selected score, rationale, and UTC timestamp. Closing
and restarting resumes at the first incomplete item. Previously completed items remain
editable through navigation.

## Evidence Boundary

The server loads only the selected round's public packets and response template. It
never loads or serves:

- Private packet-to-trial mappings.
- Agent, provider, model, or session identity.
- Judge observations or scores.
- Responses from the other blind round.

No score is inferred, preselected, or generated from official tests. The same pytest
result can accompany different process-quality scores because the human decision is
about observable approach quality, not functional correctness.

## Data Flow

1. Startup validates diagnostic packet hashes, identity blinding, response coverage,
   immutable metadata, and every already completed row.
2. The browser requests one index through a token-protected loopback API.
3. A save request supplies packet ID, integer score, and non-empty rationale.
4. The server rechecks the packet ID and immutable metadata, adds the current UTC
   timestamp, writes a temporary JSONL file in the same directory, and atomically
   replaces the response file.
5. When all 10 rows are complete, the existing authoritative diagnostic response
   validator runs and the page displays its result.

The server binds to `127.0.0.1` on an ephemeral port. A per-process random token is
required for reads and writes. Request bodies are size-limited, browser-controlled
paths are forbidden, and response security headers deny framing and external content.

## Components

- `codepulse.eval.calibration_diagnostic_review_server` owns partial-response
  validation, in-memory session state, atomic persistence, loopback HTTP handling, and
  the dependency-free HTML/CSS/JavaScript page.
- `codepulse.eval.calibration_study` adds a `review-diagnostic` command that accepts
  `--packets` and `--responses` and starts the server.
- Existing packet and response validators remain authoritative; the browser layer does
  not define a second schema.

No frontend framework, database, external asset, analytics service, or new runtime
dependency is added.

## Failure Handling

- Invalid or mismatched files fail before the browser opens.
- A row with only some human fields populated is rejected as corrupt partial state.
- Invalid score, empty rationale, unknown packet, bad token, oversized request, and
  malformed JSON are rejected without changing the response file.
- A failed atomic replacement rolls in-memory state back to the prior response.
- Round 2 is started with a separate command only after Round 1 validates; no answer is
  copied between rounds.

## Verification

Deterministic tests cover pristine, partial, complete, mismatched, and malformed
response state; valid save and resume; immutable-field preservation; rollback on write
failure; invalid update rejection; token enforcement; and CLI routing.

After implementation, Playwright verifies the real local page at desktop and mobile
widths, including nonblank content, score/rationale interaction, stable layout, and no
overlap. The test uses synthetic packets and must not create human decisions for the
real experiment.

Repository gates remain full pytest coverage, Ruff, mypy, and Bandit with no
high-severity findings.

## Acceptance Criteria

The feature is complete when the reviewer can open Round 1 with one command, inspect
all required qualitative evidence, save an explicit 1-5 score and rationale, close and
resume without editing JSONL, and finish with the existing validator reporting all 10
responses valid. Browser state and network responses must contain no identity, private
mapping, Judge output, or other-round responses.
