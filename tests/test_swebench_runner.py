"""Tests for the official SWE-bench runner boundary."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from codepulse.benchmark.cli import benchmark_group
from codepulse.benchmark.swebench_runner import (
    _task_from_instance,
    validate_swebench_training_manifest,
)


def test_swebench_runner_task_exposes_issue_but_not_oracle_data() -> None:
    task = _task_from_instance(
        {
            "instance_id": "repo__issue-1",
            "repo": "org/repo",
            "base_commit": "abc123",
            "problem_statement": "Fix the regression.",
            "patch": "secret solution patch",
            "test_patch": "secret test patch",
        }
    )

    assert task.task_id == "repo__issue-1"
    assert task.input == {"description": "Fix the regression."}
    assert task.ground_truth == {}
    assert task.metadata == {"repo": "org/repo", "base_commit": "abc123"}


def test_swebench_runner_training_manifest_accepts_frozen_repository_inputs() -> None:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "experiments/phase3-swebench-training-v1/manifest.json").read_text()
    )

    assert validate_swebench_training_manifest(manifest, root) == []


def test_swebench_runner_training_preflight_cli_avoids_docker() -> None:
    root = Path(__file__).parents[1]
    result = CliRunner().invoke(
        benchmark_group,
        [
            "swebench-training-preflight",
            "--manifest",
            str(root / "experiments/phase3-swebench-training-v1/manifest.json"),
            "--repo-root",
            str(root),
        ],
    )

    assert result.exit_code == 0
    assert "preflight passed" in result.output
