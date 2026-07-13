# CodePulse Pilot V1 Report

Trials: 120 | Model versions: ['deepseek-v4-flash']

| Agent | pass@1 | pass@3 | pass^3 | Avg tokens | Cost CNY (off/peak) | P50/P95 | Failures |
|---|---:|---:|---:|---:|---:|---:|---|
| deepseek-v4-flash-direct | 96.7% | 100.0% | 90.0% | 2522.0 | 0.178410/0.356820 | 3.634s/6.211s | {'success': 58, 'wrong_answer': 2} |
| deepseek-v4-flash-iterative | 100.0% | 100.0% | 100.0% | 4735.8 | 0.321042/0.642084 | 5.535s/10.012s | {'success': 60} |

Pricing schedule is pending; costs are reported as off-peak/peak bounds.
