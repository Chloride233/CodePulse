"""Tests for the official SWE-bench runner boundary."""

from __future__ import annotations

from codepulse.benchmark.swebench_runner import _task_from_instance


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
