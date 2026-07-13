# Phase 2 Judge Calibration: Before And After

Status: **Functional oracle calibration complete; diagnostic study pending**

## Evidence

- Sample: 100 stratified Phase 1 records, SHA-256
  `df237645d1fd04c1128c09fa0410d5186a9b9686ea7634e677f104091da983b6`.
- Judge: `deepseek/deepseek-v4-flash`, temperature 0.
- Comparison reference: deterministic functional success, not human annotation.
- Both runs completed 100/100 calls with zero missing observations.

## Result

| Metric | v1 | v2 |
|---|---:|---:|
| Exact agreement | 91% | 100% |
| Cohen's kappa | 0.2936 | 1.0000 |
| `supported_pass` | 89 | 98 |
| `supported_fail` | 2 | 2 |
| `insufficient_evidence` | 9 | 0 |

All nine v1 disagreements had the same cause: the Judge treated the expected absence
of final code and a full transcript as contradictory functional evidence. The v2
prompt explicitly confines that limitation to non-functional review and instructs the
Judge to use official verification fields for the functional label. All nine errors
disappeared on the full rerun; both real failures remained `supported_fail`.

## Boundaries

- Deterministic Graders remain authoritative for executable functional checks.
- LLM Judges need dimension-specific evidence boundaries; generic artifact-completeness
  cautions can cause false abstention even when official functional evidence is valid.
- Human annotation is not required for this functional sample because the reference
  label is completely determined by official verification. Human calibration is
  reserved for the pending full-evidence qualitative diagnostic batch.
- Position and length diagnostics have not run. Model self-preference is not
  identifiable with the single available model family.

The authoritative machine-readable result is
`results/phase2/judge-calibration-before-after.json`.
