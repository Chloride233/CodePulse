# CodePulse Evidence Report

## 1. Executive conclusion

CodePulse reproduced the Phase 1 comparison and verified the Phase 2 calibration boundary. All preserved Phase 3 candidates were rejected. The evidence does not support a claim that self-evolution improved stable Code Agent performance.

## 2. Proven and unsupported claims

**Supported by the preserved evidence:**

- Phase 1 contains a complete 120-Trial, two-Agent comparison over 20 tasks and 3 repetitions.
- Phase 2 calibrates functional Judge behavior against deterministic outcomes and limits qualitative Judge use to evidence-complete cases.
- Phase 3 Gate records reject candidates without stable gain or acceptable resource use.

**Not supported by the preserved evidence:**

- CodePulse does not show that self-evolution produces stable improvement.
- The small qualitative calibration does not justify unrestricted LLM-as-Judge use.
- Phase 3 summaries cannot replace the deleted raw Trial records.

## 3. Phase 1 reproducible Agent comparison

| Agent | pass@1 | pass@3 | pass^3 | Total tokens | Peak cost (CNY) | P50 / P95 |
|---|---:|---:|---:|---:|---:|---:|
| deepseek-v4-flash-direct | 96.7% | 100.0% | 90.0% | 151,318 | 0.356820 | 3.634s / 6.211s |
| deepseek-v4-flash-iterative | 100.0% | 100.0% | 100.0% | 284,148 | 0.642084 | 5.535s / 10.012s |

The iterative profile reached 100.0% pass^3; the direct profile reached 90.0%. These are pilot results on the frozen HumanEval subset, not a general repository-level claim.

## 4. Phase 2 Judge calibration and usage boundaries

- Functional exact agreement: 91.0% -> 100.0% over 100 samples.
- Full Judge-human exact agreement: 90.0% over 10 qualitative samples.
- Full Judge-human mean absolute error: 0.4.
- Missing Judge observations: 0.
- Deterministic grader: authoritative for executable official tests and static checks.
- LLM Judge: limited to evidence-complete qualitative dimensions with raw-response retention; observed full-evidence exact agreement 0.9 and mean absolute error 0.4.
- Human calibration: required for qualitative agreement and hard-case adjudication; observed 1 raw round disagreement and 1 adjudication.

## 5. Phase 3 candidate rejection evidence

| Experiment | Baseline | Candidate | Stable result | Decision |
|---|---:|---:|---|---|
| V4 Flash full comparison | 25.0% success | 29.2% success | pass^3 12.5% -> 12.5%; tokens +92.5% | Rejected: no_stable_improvement |
| Patch Guard screen | 0/3 resolved | 1/3 resolved | cost ratio 138.0% | Rejected: insufficient_candidate_non_empty_patches, insufficient_candidate_resolved, candidate_cost_ratio_exceeded |
| V4 Pro screen | 0/3 resolved | 0/3 resolved | stable delta 0 | Rejected: insufficient_candidate_non_empty_patches, insufficient_candidate_resolved, insufficient_candidate_resolved_delta |

## 6. Why the Gate rejected apparent improvement

The V4 Flash candidate raised single-run success from 25.0% to 29.2%, but pass^3 remained 12.5% -> 12.5% and task attribution contained no stable improvement. Its token use increased by 92.5%. The Patch Guard screen resolved 0/3 baseline tasks and 1/3 candidate tasks but exceeded the frozen cost ratio. The V4 Pro screen resolved 0/3 baseline tasks and 0/3 candidate tasks. The recorded decisions therefore separate occasional success from stable, zero-regression, resource-bounded improvement.

## 7. Evidence index and preservation boundary

- `results/pilot-v1/runs/20260713-v1/manifest.json`
- `results/pilot-v1/runs/20260713-v1/run-summary.json`
- `results/pilot-v1/runs/20260713-v1/trials.jsonl`
- `results/phase2/calibration-analysis.json`
- `experiments/phase3-swebench-evolution-v4/evidence.json`
- `experiments/phase3-swebench-screen-v3/evidence.json`
- `experiments/phase3-strong-model-screen-v1/evidence.json`

Phase 1 raw Trials and the Phase 2 calibration summary are locally preserved. Phase 3 raw evidence not locally preserved: the cleanup removed the referenced `results/phase3/` Trial and run-summary files. The committed evidence records retain their original paths and SHA-256 values, but those summaries are not substitutes for the raw records.
