"""Tests for deterministic HumanEval pilot dataset preparation."""

from __future__ import annotations

import gzip
import json
from typing import TYPE_CHECKING

import pytest

from codepulse.data.custom_loader import CustomDatasetLoader
from scripts.download_humaneval import PILOT_TASK_IDS, convert_records, prepare_pilot_dataset

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any


def _records() -> list[dict[str, Any]]:
    return [
        {
            "task_id": task_id,
            "prompt": f"def task_{index}():\n    pass\n",
            "canonical_solution": "    return True\n",
            "test": "def check(candidate):\n    assert candidate()\n",
            "entry_point": f"task_{index}",
        }
        for index, task_id in enumerate(PILOT_TASK_IDS)
    ]


def test_humaneval_convert_records_fixed_order_and_flat_schema() -> None:
    converted = convert_records(reversed(_records()))

    assert [record["task_id"] for record in converted] == PILOT_TASK_IDS
    assert len(converted) == 20
    assert "input" not in converted[0]
    assert converted[0]["metadata"] == {"entry_point": "task_0"}


def test_humaneval_convert_records_missing_task_rejected() -> None:
    with pytest.raises(ValueError, match="HumanEval/19"):
        convert_records(_records()[:-1])


def test_humaneval_prepare_output_loads_in_codepulse(tmp_path: Path) -> None:
    source_path = tmp_path / "HumanEval.jsonl.gz"
    output_path = tmp_path / "pilot-v1.jsonl"
    with gzip.open(source_path, "wt", encoding="utf-8") as source_file:
        for record in _records():
            source_file.write(json.dumps(record) + "\n")

    assert prepare_pilot_dataset(source_path, output_path) == 20
    tasks = CustomDatasetLoader().load(str(output_path))

    assert [task.task_id for task in tasks] == PILOT_TASK_IDS
    assert all(task.input["input_code"] for task in tasks)
    assert all(task.ground_truth["test_cases"] for task in tasks)
