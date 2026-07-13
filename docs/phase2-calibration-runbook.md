# Phase 2 Calibration Runbook

Status: functional calibration complete; full-evidence diagnostic study pending
Rubric: [`phase2-human-rubric.md`](phase2-human-rubric.md)

## 1. Functional Calibration

The 100-record stratified sample contains only official functional verification. Its
reference label is derived deterministically from exit status and pytest output; no
human annotation is required or methodologically useful for this dimension.

The completed DeepSeek runs are recorded in:

- `results/phase2/judge-calibration-before-after.json`
- `results/phase2/judge-calibration-before-after.md`
- `results/phase2/calibration-study-v1/judge-observations-v1.jsonl`
- `results/phase2/calibration-study-v1/judge-observations-v2.jsonl`

The v2 Judge reached 100/100 exact agreement with the deterministic oracle. This does
not establish reliability for process quality or experience alignment.

## 2. Capture The Diagnostic Batch

Create a frozen manifest for 10 tasks, one candidate model family, and one trial per
task. The manifest must record task IDs, profile and prompt hashes, provider model
version, environment digest, seed, and budget. Do not reuse the 120-trial Phase 1
manifest.

Run the new manifest with evidence capture enabled:

```bash
.venv/bin/python -m codepulse.cli benchmark pilot-run \
  --manifest experiments/phase2-diagnostic-v1/manifest.json \
  --output-dir results/phase2/diagnostic-run-v1 \
  --capture-evidence
```

Every accepted record must contain task text, final code, complete normalized Trace,
official test result, token counts, and immutable hashes. Stop if any required artifact
is missing; a partial packet is not eligible for human or Judge scoring.

## 3. Run Two Human Rounds

Generate two independently shuffled, identity-blind rounds from the 10 eligible
records. Review only process quality using `diagnostic-process-v1`. One reviewer may
complete both rounds, but the result must be reported as intra-rater repeatability.

This step requires 20 human decisions, not 200. Do not expose Judge output or the first
round while the second round is in progress. Preserve disagreements and adjudicate
them in a separate file.

The diagnostic packet generator and validator are not yet implemented. Empty
templates or functional-only packets do not satisfy this step.

## 4. Run Judge Bias Diagnostics

For each eligible record, run the qualitative Judge with the same rubric and persist
raw responses. Generate paired variants for:

- Position: candidate A/B order swapped when two candidates are available.
- Length: full Trace versus a deterministic compact projection.
- Identity: candidate and provider identifiers removed.

With one candidate/Judge family, report model self-preference as `not_identifiable`.
Do not manufacture a proxy from prompt profiles belonging to the same model family.

## 5. Analyze And Close Issue #1

The final report must contain:

- 100-record Judge-versus-deterministic-oracle functional agreement.
- Diagnostic human-human and Judge-human agreement with sample counts.
- Pearson correlation and absolute error for 1-5 diagnostic scores.
- Position and length results, plus explicit self-preference identifiability.
- Hard cases, adjudications, and held-out correction results when correction is fitted.
- Clear boundaries for deterministic Graders, LLM Judges, and human calibration.

Phase 3 must not start until these artifacts exist. Code, prompts, empty templates, or
mocked tests are implementation evidence, not completed calibration evidence.
