"""Download standard benchmarks to CodePulse JSONL format.

Usage:
    python scripts/download_benchmarks.py               # download all
    python scripts/download_benchmarks.py humaneval      # single benchmark
"""

import json
import os
import sys
from pathlib import Path

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["CURL_CA_BUNDLE"] = ""

from datasets import load_dataset


def download_humaneval():
    ds = load_dataset("openai/openai_humaneval", split="test")
    out = Path("datasets/humaneval")
    out.mkdir(parents=True, exist_ok=True)
    with (out / "humaneval_test.jsonl").open("w", encoding="utf-8") as f:
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
    print(f"HumanEval: {len(ds)} → {out / 'humaneval_test.jsonl'}")


def download_mbpp():
    for split_name in ("test", "train"):
        ds = load_dataset("mbpp", split=split_name)
        out = Path("datasets/mbpp")
        out.mkdir(parents=True, exist_ok=True)
        fname = f"mbpp_{split_name}.jsonl"
        with (out / fname).open("w", encoding="utf-8") as f:
            for item in ds:
                task = {
                    "task_id": f"mbpp/{item['task_id']}",
                    "category": "feature",
                    "difficulty": "medium",
                    "language": "python",
                    "source": "mbpp",
                    "input": {"description": item["text"], "input_code": ""},
                    "ground_truth": {
                        "expected_output": item.get("code", ""),
                        "test_cases": item.get("test_list", []),
                    },
                }
                f.write(json.dumps(task, ensure_ascii=False) + "\n")
        print(f"MBPP {split_name}: {len(ds)} → {out / fname}")


def download_swe_bench():
    """Download SWE-bench Lite via HuggingFace datasets."""
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    out = Path("datasets/swe-bench")
    out.mkdir(parents=True, exist_ok=True)
    with (out / "swe_bench_lite.jsonl").open("w", encoding="utf-8") as f:
        for item in ds:
            task = {
                "task_id": f"swe-bench/{item['instance_id']}",
                "category": "bug_fix",
                "difficulty": item.get("difficulty", "medium"),
                "language": "python",
                "source": "swe-bench",
                "input": {
                    "description": item.get("problem_statement", ""),
                    "input_code": item.get("repo", ""),
                },
                "ground_truth": {
                    "expected_output": item.get("patch", ""),
                    "test_cases": item.get("test_patch", "").split("\n") if item.get("test_patch") else [],
                },
            }
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
    print(f"SWE-bench Lite: {len(ds)} → {out / 'swe_bench_lite.jsonl'}")


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["humaneval", "mbpp", "swe-bench"]
    if "humaneval" in targets:
        download_humaneval()
    if "mbpp" in targets:
        download_mbpp()
    if "swe-bench" in targets:
        download_swe_bench()
    print("Done.")
