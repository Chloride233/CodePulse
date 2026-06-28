"""Download MBPP benchmark to CodePulse JSONL format."""
import json, os
from datasets import load_dataset
from pathlib import Path

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

ds = load_dataset("mbpp", split="test")
out_dir = Path("datasets") / "mbpp"
out_dir.mkdir(parents=True, exist_ok=True)

with (out_dir / "mbpp.jsonl").open("w", encoding="utf-8") as f:
    for item in ds:
        task = {
            "task_id": f"mbpp/{item['task_id']}",
            "category": "feature",
            "difficulty": "medium",
            "language": "python",
            "source": "mbpp",
            "input": {
                "description": item["text"],
                "input_code": "",
            },
            "ground_truth": {
                "expected_output": item.get("code", ""),
                "test_cases": item.get("test_list", []),
            },
        }
        f.write(json.dumps(task, ensure_ascii=False) + "\n")

print(f"MBPP: {len(ds)} tasks saved to {out_dir / 'mbpp.jsonl'}")
