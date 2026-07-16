"""Tests for the official SWE-bench runner boundary."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from docker.errors import ImageNotFound

from codepulse.benchmark.cli import benchmark_group
from codepulse.benchmark.swebench_runner import (
    OfficialHarness,
    _evaluate_patch,
    _prepare_official_image,
    _start_isolated_container,
    _task_from_instance,
    _transcript_metrics,
    evaluate_swebench_screen,
    validate_swebench_evolution_manifest,
    validate_swebench_screen_manifest,
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


def test_swebench_runner_evolution_manifest_accepts_frozen_held_out_inputs() -> None:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "experiments/phase3-swebench-evolution-v1/manifest.json").read_text()
    )

    assert validate_swebench_evolution_manifest(manifest, root) == []

    v2_manifest = json.loads(
        (root / "experiments/phase3-swebench-evolution-v2/manifest.json").read_text()
    )
    assert validate_swebench_evolution_manifest(v2_manifest, root) == []

    v3_manifest = json.loads(
        (root / "experiments/phase3-swebench-evolution-v3/manifest.json").read_text()
    )
    assert validate_swebench_evolution_manifest(v3_manifest, root) == []

    v4_manifest = json.loads(
        (root / "experiments/phase3-swebench-evolution-v4/manifest.json").read_text()
    )
    assert validate_swebench_evolution_manifest(v4_manifest, root) == []


def test_swebench_runner_evolution_preflight_cli_avoids_docker() -> None:
    root = Path(__file__).parents[1]
    result = CliRunner().invoke(
        benchmark_group,
        [
            "swebench-evolution-preflight",
            "--manifest",
            str(root / "experiments/phase3-swebench-evolution-v1/manifest.json"),
            "--repo-root",
            str(root),
        ],
    )

    assert result.exit_code == 0
    assert "candidate, provenance, and tasks are frozen" in result.output


def test_swebench_runner_screen_manifest_accepts_frozen_training_inputs() -> None:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "experiments/phase3-swebench-screen-v1/manifest.json").read_text()
    )

    assert validate_swebench_screen_manifest(manifest, root) == []

    v2_manifest = json.loads(
        (root / "experiments/phase3-swebench-screen-v2/manifest.json").read_text()
    )
    assert validate_swebench_screen_manifest(v2_manifest, root) == []

    v3_manifest = json.loads(
        (root / "experiments/phase3-swebench-screen-v3/manifest.json").read_text()
    )
    assert validate_swebench_screen_manifest(v3_manifest, root) == []


def test_swebench_runner_screen_preflight_cli_avoids_docker() -> None:
    root = Path(__file__).parents[1]
    result = CliRunner().invoke(
        benchmark_group,
        [
            "swebench-screen-preflight",
            "--manifest",
            str(root / "experiments/phase3-swebench-screen-v1/manifest.json"),
            "--repo-root",
            str(root),
        ],
    )

    assert result.exit_code == 0
    assert "screen preflight passed" in result.output


def test_swebench_runner_screen_requires_patches_resolution_and_budget() -> None:
    manifest = {
        "task_ids": ["task-1", "task-2", "task-3"],
        "agents": [{"name": "candidate"}],
        "acceptance": {"min_non_empty_patches": 2, "min_resolved": 1},
        "budget": {"total_cny": 2.0, "per_agent_cny": 2.0, "per_trial_cny": 1.0},
    }
    rows = [
        {
            "task_id": f"task-{index}",
            "repetition": 0,
            "agent_name": "candidate",
            "success": index == 1,
            "outcome": {"patch": "diff" if index < 3 else ""},
            "metrics": {"cost_cny_peak": 0.2},
            "failure_type": "wrong_answer" if index > 1 else None,
        }
        for index in range(1, 4)
    ]

    accepted = evaluate_swebench_screen(rows, manifest)
    assert accepted == {
        "accepted": True,
        "rejection_reasons": [],
        "completed_trials": 3,
        "non_empty_patches": 2,
        "resolved": 1,
        "infrastructure_failures": 0,
        "total_cost_cny_peak": 0.6,
        "max_trial_cost_cny_peak": 0.2,
    }

    rows[0]["success"] = False
    rejected = evaluate_swebench_screen(rows, manifest)
    assert rejected["accepted"] is False
    assert rejected["rejection_reasons"] == ["insufficient_resolved"]


def test_swebench_runner_screen_v2_requires_paired_functional_and_resource_gain() -> None:
    manifest = {
        "protocol_version": "phase3-swebench-screen-v2",
        "task_ids": ["task-1", "task-2", "task-3"],
        "agents": [
            {"role": "baseline", "name": "baseline"},
            {"role": "candidate", "name": "candidate"},
        ],
        "acceptance": {
            "min_candidate_non_empty_patches": 2,
            "min_candidate_resolved": 2,
            "require_candidate_resolved_gte_baseline": True,
            "max_candidate_token_ratio": 1.25,
            "max_candidate_cost_ratio": 1.25,
        },
        "budget": {"total_cny": 2.0, "per_agent_cny": 2.0, "per_trial_cny": 1.0},
    }
    rows = []
    for agent_name in ("baseline", "candidate"):
        for index in range(1, 4):
            candidate = agent_name == "candidate"
            rows.append(
                {
                    "task_id": f"task-{index}",
                    "repetition": 0,
                    "agent_name": agent_name,
                    "success": index <= (2 if candidate else 1),
                    "outcome": {"patch": "diff" if candidate or index == 1 else ""},
                    "metrics": {
                        "total_tokens": 40 if candidate else 34,
                        "cost_cny_peak": 0.12 if candidate else 0.1,
                    },
                    "failure_type": None,
                }
            )

    accepted = evaluate_swebench_screen(rows, manifest)

    assert accepted["accepted"] is True
    assert accepted["completed_trials"] == 6
    assert accepted["baseline"]["resolved"] == 1
    assert accepted["candidate"]["resolved"] == 2
    assert accepted["candidate_token_ratio"] == 1.176471
    assert accepted["candidate_cost_ratio"] == 1.2

    for row in rows:
        if row["agent_name"] == "candidate":
            row["metrics"]["total_tokens"] = 50
            row["metrics"]["cost_cny_peak"] = 0.13
    rejected = evaluate_swebench_screen(rows, manifest)

    assert rejected["accepted"] is False
    assert rejected["rejection_reasons"] == [
        "candidate_token_ratio_exceeded",
        "candidate_cost_ratio_exceeded",
    ]

    manifest["protocol_version"] = "phase3-swebench-screen-v3"
    manifest["budget"] = {
        "total_cny": 1.0,
        "per_agent_cny": 0.6,
        "per_trial_cny": 0.25,
    }
    for row in rows:
        row["metrics"]["total_tokens"] = 40 if row["agent_name"] == "candidate" else 34
        row["metrics"]["cost_cny_peak"] = 0.12 if row["agent_name"] == "candidate" else 0.1
        row["failure_type"] = None
    rows[-1]["failure_type"] = "patch_guard_check_error"

    guard_failure = evaluate_swebench_screen(rows, manifest)

    assert guard_failure["accepted"] is False
    assert guard_failure["rejection_reasons"] == ["infrastructure_failure"]

    rows[-1]["failure_type"] = None
    for row in rows:
        if row["agent_name"] == "candidate":
            row["metrics"]["cost_cny_peak"] = 0.21

    agent_budget_failure = evaluate_swebench_screen(rows, manifest)

    assert "per_agent_budget_exceeded" in agent_budget_failure["rejection_reasons"]


def test_swebench_runner_evolution_resume_rejects_manifest_drift(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    output = tmp_path / "run"
    output.mkdir()
    (output / "manifest.json").write_text("{}\n", encoding="utf-8")
    (output / "trials.jsonl").write_text("", encoding="utf-8")

    result = CliRunner().invoke(
        benchmark_group,
        [
            "swebench-evolution-run",
            "--manifest",
            str(root / "experiments/phase3-swebench-evolution-v1/manifest.json"),
            "--output-dir",
            str(output),
            "--repo-root",
            str(root),
            "--resume",
        ],
    )

    assert result.exit_code != 0
    assert "output manifest differs" in result.output


def test_swebench_runner_evaluation_resets_agent_workspace_before_applying_patch(
) -> None:
    commands: list[object] = []

    class OfficialContainer:
        def exec_run(self, command: object, **_: object) -> object:
            commands.append(command)
            return type("Result", (), {"exit_code": 0, "output": b""})()

    def copy_to_container(*_: object) -> None:
        return None

    def exec_run_with_timeout(*_: object) -> tuple[str, bool, float]:
        return "tests passed", False, 0.0

    def get_eval_report(
        _: object, __: object, ___: object, include_tests_status: bool
    ) -> dict[str, object]:
        assert include_tests_status is True
        return {"repo__issue-1": {"resolved": True}}

    harness = OfficialHarness(
        make_test_spec=lambda *_: None,
        build_container=lambda *_: None,
        setup_logger=lambda *_: None,
        close_logger=lambda *_: None,
        copy_to_container=copy_to_container,
        exec_run_with_timeout=exec_run_with_timeout,
        get_eval_report=get_eval_report,
    )

    report, output = _evaluate_patch(
        harness,
        OfficialContainer(),
        type("TestSpec", (), {"eval_script": "echo tests"})(),
        {"instance_id": "repo__issue-1"},
        "diff --git a/a.py b/a.py",
        60,
    )

    assert commands == [
        ["git", "reset", "--hard", "HEAD"],
        ["git", "clean", "-fd"],
        ["git", "apply", "--verbose", "/tmp/patch.diff"],
    ]
    assert report == {"repo__issue-1": {"resolved": True}}
    assert output == "tests passed"


def test_swebench_runner_prepares_frozen_official_image_by_digest() -> None:
    calls: list[tuple[str, str]] = []

    class Image:
        def tag(self, repository: str, *, tag: str) -> None:
            calls.append((repository, tag))

    class Images:
        def get(self, image_ref: str) -> Image:
            calls.append(("get", image_ref))
            return Image()

    client = type("Client", (), {"images": Images()})()
    test_spec = type(
        "TestSpec",
        (),
        {"instance_image_key": "swebench/sweb.eval.x86_64.repo_1776_repo-1:latest"},
    )()

    image_ref = _prepare_official_image(client, test_spec, "sha256:" + "a" * 64)

    assert image_ref == (
        "swebench/sweb.eval.x86_64.repo_1776_repo-1@sha256:" + "a" * 64
    )
    assert calls == [
        ("get", image_ref),
        ("swebench/sweb.eval.x86_64.repo_1776_repo-1", "latest"),
    ]


def test_swebench_runner_uses_transport_prefix_without_changing_image_identity() -> None:
    calls: list[tuple[str, str]] = []

    class Image:
        def tag(self, repository: str, *, tag: str) -> None:
            calls.append((repository, tag))

    class Images:
        def get(self, image_ref: str) -> Image:
            calls.append(("get", image_ref))
            raise ImageNotFound("missing")

        def pull(self, image_ref: str) -> Image:
            calls.append(("pull", image_ref))
            return Image()

    client = type("Client", (), {"images": Images()})()
    test_spec = type(
        "TestSpec",
        (),
        {"instance_image_key": "swebench/sweb.eval.x86_64.repo_1776_repo-1:latest"},
    )()
    digest = "sha256:" + "a" * 64

    image_ref = _prepare_official_image(
        client,
        test_spec,
        digest,
        image_transport_prefix="docker.1ms.run",
    )

    official_ref = f"swebench/sweb.eval.x86_64.repo_1776_repo-1@{digest}"
    transport_ref = f"docker.1ms.run/swebench/sweb.eval.x86_64.repo_1776_repo-1@{digest}"
    assert image_ref == official_ref
    assert calls == [
        ("get", official_ref),
        ("get", transport_ref),
        ("pull", transport_ref),
        ("swebench/sweb.eval.x86_64.repo_1776_repo-1", "latest"),
    ]


def test_swebench_runner_starts_container_with_frozen_limits_and_no_network() -> None:
    calls: list[object] = []

    class Container:
        attrs: dict[str, object] = {"NetworkSettings": {"Networks": {"bridge": {}}}}

        def update(self, **kwargs: object) -> None:
            calls.append(("update", kwargs))

        def start(self) -> None:
            calls.append("start")

        def reload(self) -> None:
            calls.append("reload")

    class Network:
        def disconnect(self, container: object, *, force: bool) -> None:
            calls.append(("disconnect", container, force))

    class Networks:
        def get(self, name: str) -> Network:
            calls.append(("network", name))
            return Network()

    container = Container()
    client = type("Client", (), {"networks": Networks()})()

    _start_isolated_container(client, container, 2, 4096)

    assert calls == [
        (
            "update",
            {
                "cpu_period": 100_000,
                "cpu_quota": 200_000,
                "mem_limit": "4096m",
                "memswap_limit": "4096m",
            },
        ),
        "start",
        "reload",
        ("network", "bridge"),
        ("disconnect", container, True),
    ]


def test_swebench_runner_total_tokens_excludes_cache_double_count() -> None:
    transcript = type(
        "Transcript",
        (),
        {
            "agent_config": {
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_tokens": 60,
                "cost_usd": 0.01,
                "patch_guard_checks": 2,
                "patch_guard_retries_used": 1,
                "patch_guard_check_failures": 0,
                "base_max_iterations": 8,
                "effective_call_limit": 9,
            },
            "events": [
                type(
                    "Event",
                    (),
                    {
                        "event_type": "reflection",
                        "content": {"kind": "patch_guard"},
                    },
                )()
            ],
            "total_duration": 1.5,
        },
    )()

    assert _transcript_metrics(transcript) == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_tokens": 60,
        "total_tokens": 120,
        "duration_seconds": 1.5,
        "cost_usd": 0.01,
        "patch_guard_checks": 2,
        "patch_guard_triggers": 1,
        "patch_guard_retries_used": 1,
        "patch_guard_check_failures": 0,
        "base_max_iterations": 8,
        "effective_call_limit": 9,
    }
