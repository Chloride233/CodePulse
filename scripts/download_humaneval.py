"""Download HumanEval benchmark to CodePulse JSONL format."""
import json, os
from datasets import load_dataset
from pathlib import Path

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

ds = load_dataset("openai/openai_humaneval", split="test")
out_dir = Path("datasets") / "humaneval"
out_dir.mkdir(parents=True, exist_ok=True)

with (out_dir / "humaneval.jsonl").open("w", encoding="utf-8") as f:
    for item in ds:
        task = {
            "task_id": f"humaneval/{item['task_id']}",
            "category": "bug_fix",
            "difficulty": "medium",
            "language": "python",
            "source": "humaneval",
            "input": {"description": item["prompt"].strip(), "input_code": item["prompt"]},
            "ground_truth": {
                "expected_output": item.get("canonical_solution", ""),
                "test_cases": [item["test"]],
            },
        }
        f.write(json.dumps(task, ensure_ascii=False) + "\n")

print(f"HumanEval: {len(ds)} tasks saved to {out_dir / 'humaneval.jsonl'}")
