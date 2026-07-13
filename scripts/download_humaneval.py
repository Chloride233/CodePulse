"""Download and convert the official HumanEval dataset for CodePulse."""

from __future__ import annotations

import argparse
import gzip
import json
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any

OFFICIAL_URL = (
    "https://raw.githubusercontent.com/openai/human-eval/"
    "master/data/HumanEval.jsonl.gz"
)
PILOT_TASK_IDS = [f"HumanEval/{task_id}" for task_id in range(20)]


def convert_records(
    records: Iterable[dict[str, Any]], *, task_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Convert a fixed HumanEval subset to CodePulse's flat JSONL schema."""
    selected_ids = PILOT_TASK_IDS if task_ids is None else task_ids
    by_id = {record.get("task_id"): record for record in records}
    missing = [task_id for task_id in selected_ids if task_id not in by_id]
    if missing:
        raise ValueError(f"Official HumanEval source is missing tasks: {missing}")

    converted: list[dict[str, Any]] = []
    for task_id in selected_ids:
        record = by_id[task_id]
        prompt = _required_text(record, "prompt", task_id)
        canonical_solution = _required_text(record, "canonical_solution", task_id)
        tests = _required_text(record, "test", task_id)
        entry_point = _required_text(record, "entry_point", task_id)
        converted.append(
            {
                "task_id": task_id,
                "source": "humaneval",
                "category": "feature",
                "difficulty": "medium",
                "language": "python",
                "description": prompt.strip(),
                "input_code": prompt,
                "expected_output": canonical_solution,
                "test_cases": [f"{tests.rstrip()}\ncheck({entry_point})"],
                "metadata": {"entry_point": entry_point},
            }
        )
    return converted


def prepare_pilot_dataset(source_path: Path, output_path: Path) -> int:
    """Read official gzip JSONL and write the fixed 20-task pilot JSONL."""
    return prepare_humaneval_dataset(source_path, output_path, PILOT_TASK_IDS)


def prepare_humaneval_dataset(
    source_path: Path, output_path: Path, task_ids: list[str]
) -> int:
    """Read official gzip JSONL and write an explicit HumanEval subset."""
    with gzip.open(source_path, "rt", encoding="utf-8") as source_file:
        records = [json.loads(line) for line in source_file if line.strip()]
    converted = convert_records(records, task_ids=task_ids)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        for record in converted:
            output_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return len(converted)


def download_official_dataset(destination: Path) -> None:
    """Download the immutable source artifact from OpenAI's repository."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(OFFICIAL_URL, destination)  # noqa: S310


def main() -> None:
    """Download the official source and prepare the pilot subset."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("datasets/humaneval/HumanEval.jsonl.gz"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("datasets/humaneval/pilot-v1.jsonl"),
    )
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--start-task", type=int, default=0)
    parser.add_argument("--task-count", type=int, default=20)
    args = parser.parse_args()

    if args.start_task < 0 or args.task_count < 1:
        raise ValueError("start-task must be non-negative and task-count must be positive")

    if not args.source.exists():
        if args.no_download:
            raise FileNotFoundError(args.source)
        download_official_dataset(args.source)
    task_ids = [
        f"HumanEval/{task_id}"
        for task_id in range(args.start_task, args.start_task + args.task_count)
    ]
    task_count = prepare_humaneval_dataset(args.source, args.output, task_ids)
    print(f"Prepared {task_count} tasks at {args.output}")


def _required_text(record: dict[str, Any], key: str, task_id: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{task_id} is missing required field: {key}")
    return value


if __name__ == "__main__":
    main()
