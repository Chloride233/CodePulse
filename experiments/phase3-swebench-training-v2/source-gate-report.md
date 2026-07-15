# CodePulse Phase 3 Comparison Report

Status: generated from supplied Trial records; this report does not itself prove a real-model benefit.
Protocol: `phase3-swebench-evolution-v2` | Trials: 48 | k: 3

## Metric Comparison

| Metric | Baseline | Candidate | Candidate - Baseline |
|---|---:|---:|---:|
| success_rate | 0.0% | 0.0% | +0.0% |
| pass_at_k | 0.0% | 0.0% | +0.0% |
| pass_hat_k | 0.0% | 0.0% | +0.0% |
| avg_tokens | 133521.7 | 103896.6 | -29625.1 |
| total_tokens | 3204520.0 | 2493518.0 | -711002.0 |
| cost_cny_off_peak | 1.050658 CNY | 0.911077 CNY | -0.139581 CNY |
| cost_cny_peak | 2.101315 CNY | 1.822153 CNY | -0.279162 CNY |
| p50_seconds | 24.389 s | 19.858 s | -4.531 s |
| p95_seconds | 46.940 s | 60.428 s | +13.488 s |

## Attribution

| Improvements | Regressions | Persistent failures | Stable successes |
|---:|---:|---:|---:|
| 0 | 0 | 8 | 0 |

## Validation Gate

Accepted: `False` | Rejection reasons: `no_stable_improvement`

## Typical Cases

| Attribution | Task | Baseline trials | Candidate trials |
|---|---|---|---|
| persistent_failure | pydata__xarray-4695 | fail, fail, fail | fail, fail, fail |

## Reproduce

```bash
codepulse benchmark swebench-evolution-preflight --manifest experiments/phase3-swebench-evolution-v2/manifest.json --repo-root .
codepulse benchmark swebench-evolution-run --manifest experiments/phase3-swebench-evolution-v2/manifest.json --output-dir results/phase3/swebench-evolution-v2 --repo-root . --resume
codepulse benchmark phase3-report --manifest experiments/phase3-swebench-evolution-v2/manifest.json --run-dir results/phase3/swebench-evolution-v2
```
