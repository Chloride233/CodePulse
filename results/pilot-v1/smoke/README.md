# Pilot V1 Smoke Test

Status: **passed**  
Execution commit: `b139669353df3aa63dc37f04ac2870dc6bec8892`  
Task: `HumanEval/0`  
Runs: 1 per Agent

| Agent | Official tests | Input tokens | Output tokens | Total tokens | Duration | Off-peak CNY | Peak CNY |
|---|---:|---:|---:|---:|---:|---:|---:|
| `deepseek-v4-flash-direct` | 1 passed | 2,561 | 677 | 3,238 | 5.439 s | 0.003915 | 0.007830 |
| `deepseek-v4-flash-iterative` | 1 passed | 8,090 | 1,420 | 9,510 | 10.771 s | 0.010930 | 0.021860 |

Valid smoke total: 12,748 tokens, 16.210 seconds, CNY 0.014845-0.029690.

## Reproduction

```bash
set -a
source .env.local
set +a

python -m codepulse.cli benchmark preflight \
  --manifest experiments/pilot-v1/manifest.json \
  --repo-root .

python -m codepulse.cli evaluate \
  --task-file /tmp/codepulse-pilot-smoke.jsonl \
  --agent agents/deepseek-v4-flash-direct.yaml \
  --n-trials 1 \
  --results-dir results/pilot-v1/smoke/direct

python -m codepulse.cli evaluate \
  --task-file /tmp/codepulse-pilot-smoke.jsonl \
  --agent agents/deepseek-v4-flash-iterative.yaml \
  --n-trials 1 \
  --results-dir results/pilot-v1/smoke/iterative
```

## Invalid Attempts

`direct-aborted-pre-success-fix/` preserves the pre-gate attempts. They exposed and led to fixes for three harness defects: HumanEval tests did not call `check(entry_point)`, slash-containing Trial IDs could not be persisted, and absolute `/workspace` tool paths did not overwrite the injected solution. A fourth classification defect marked official-test passes as failures when functional correctness was the only active grader. Invalid attempts are not merged into the valid smoke metrics above.
