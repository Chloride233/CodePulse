# CodePulse Phase 3 Comparison Report

Status: generated from supplied Trial records; this report does not itself prove a real-model benefit.
Protocol: `phase3-swebench-evolution-v4` | Trials: 48 | k: 3

## Metric Comparison

| Metric | Baseline | Candidate | Candidate - Baseline |
|---|---:|---:|---:|
| success_rate | 25.0% | 29.2% | +4.2% |
| pass_at_k | 37.5% | 37.5% | +0.0% |
| pass_hat_k | 12.5% | 12.5% | +0.0% |
| avg_tokens | 54180.4 | 104315.8 | +50135.4 |
| total_tokens | 1300330.0 | 2503580.0 | +1203250.0 |
| cost_cny_off_peak | 0.378891 CNY | 0.487703 CNY | +0.108812 CNY |
| cost_cny_peak | 0.757777 CNY | 0.975401 CNY | +0.217624 CNY |
| p50_seconds | 21.054 s | 36.508 s | +15.454 s |
| p95_seconds | 45.960 s | 53.551 s | +7.591 s |

## Attribution

| Improvements | Regressions | Persistent failures | Stable successes |
|---:|---:|---:|---:|
| 0 | 0 | 7 | 1 |

## Validation Gate

Accepted: `False` | Rejection reasons: `no_stable_improvement`

## Typical Cases

| Attribution | Task | Baseline trials | Candidate trials |
|---|---|---|---|
| persistent_failure | django__django-15741 | fail, pass, fail | fail, fail, fail |
| stable_success | pylint-dev__pylint-7277 | pass, pass, pass | pass, pass, pass |

## Reproduce

```bash
codepulse benchmark swebench-evolution-preflight --manifest experiments/phase3-swebench-evolution-v4/manifest.json --repo-root .
codepulse benchmark swebench-evolution-run --manifest experiments/phase3-swebench-evolution-v4/manifest.json --output-dir results/phase3/swebench-evolution-v4 --repo-root . --resume
codepulse benchmark phase3-report --manifest experiments/phase3-swebench-evolution-v4/manifest.json --run-dir results/phase3/swebench-evolution-v4
```
