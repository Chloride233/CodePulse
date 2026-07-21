# Phase 2 Diagnostic Browser Review Design

Status: Plain-language revision approved on 2026-07-13
Issue: [#1](https://github.com/randy-labs/CodePulse/issues/1)

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
loopback-only server, and opens the local browser. The default view is a focused,
plain-language single-item layout with:

- Round number, completed count, total count, and previous/next navigation.
- Four deterministic facts: code writes, test runs, observed failures, and final pytest
  result.
- A Chinese timeline such as "wrote solution", "ran tests", "tests passed", or
  "recovered after failure", derived only from event types and tool results.
- A stable 1-5 segmented score control using the published rubric.
- Observable-reason checkboxes plus an optional custom note and one explicit
  save-and-continue action.

Task text, final `solution.py`, the complete normalized Trace, official verification,
and token/time metrics remain available under a collapsed "detailed evidence" section.
The reviewer does not need to read raw JSON for an ordinary direct run.

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

## Plain-Language Projection

The page computes its summary locally from fields already present in the blinded
packet. It does not call an LLM or add inferred facts:

- `write_file` tool calls increment "code writes" and render "wrote or updated code".
- `execute` tool calls increment "test or command runs" and render "ran verification".
- Error events and unsuccessful tool results increment "observed failures".
- Official `pytest_passed` and `pytest_total` render the final test result.
- Every original event remains available in the collapsed detailed Trace.

Reason options are neutral observable claims rather than score recommendations:

- Steps were direct with no repeated attempt.
- There were minor avoidable steps.
- A failure was followed by effective recovery.
- Recovery after failure was weak or missing.
- Similar attempts were repeated.
- Final code and official verification were consistent.
- Key process evidence was insufficient.

The reviewer selects one or more claims. The browser joins those selected claims into
the required rationale, with an optional custom note appended. No reason option changes
or suggests the selected 1-5 score.

## Data Flow

1. Startup validates diagnostic packet hashes, identity blinding, response coverage,
   immutable metadata, and every already completed row.
2. The browser requests one index through a token-protected loopback API.
3. A save request supplies packet ID, integer score, and a non-empty rationale assembled
   from reviewer-selected observable claims plus any optional note.
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
widths, including nonblank summary and timeline content, collapsed raw evidence,
score/reason interaction, stable layout, and no overlap. The test uses copied packets
and must not create human decisions for the real experiment.

Repository gates remain full pytest coverage, Ruff, mypy, and Bandit with no
high-severity findings.

## Acceptance Criteria

The feature is complete when the reviewer can open Round 1 with one command, understand
the default view without reading raw JSON, expand every underlying evidence field when
needed, save an explicit 1-5 score and reviewer-selected rationale, close and resume
without editing JSONL, and finish with the existing validator reporting all 10
responses valid. Browser state and network responses must contain no identity, private
mapping, Judge output, or other-round responses.
