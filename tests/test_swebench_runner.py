"""Tests for the official SWE-bench runner boundary."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from codepulse.benchmark.cli import benchmark_group
from codepulse.benchmark.swebench_runner import (
    OfficialHarness,
    _evaluate_patch,
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


def test_swebench_runner_evaluation_resets_agent_workspace_before_applying_patch(
) -> None:
    commands: list[str] = []

    class OfficialContainer:
        def exec_run(self, command: str, **_: object) -> object:
            commands.append(command)
            return type("Result", (), {"exit_code": 0, "output": b""})()

    def copy_to_container(*_: object) -> None:
        return None

    def exec_run_with_timeout(*_: object) -> tuple[str, bool, float]:
        return "tests passed", False, 0.0

    harness = OfficialHarness(
        make_test_spec=lambda *_: None,
        build_instance_images=lambda *_: None,
        build_container=lambda *_: None,
        setup_logger=lambda *_: None,
        close_logger=lambda *_: None,
        copy_to_container=copy_to_container,
        exec_run_with_timeout=exec_run_with_timeout,
        get_eval_report=lambda *_: {"repo__issue-1": {"resolved": True}},
    )

    report, output = _evaluate_patch(
        harness,
        OfficialContainer(),
        type("TestSpec", (), {"eval_script": "echo tests"})(),
        {"instance_id": "repo__issue-1"},
        "diff --git a/a.py b/a.py",
        60,
    )

    assert commands == ["git reset --hard HEAD && git clean -fd && git apply --verbose /tmp/patch.diff"]
    assert report == {"repo__issue-1": {"resolved": True}}
    assert output == "tests passed"
