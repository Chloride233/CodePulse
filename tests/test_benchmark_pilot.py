"""Tests for the Phase 1 pilot preflight gates."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from click.testing import CliRunner

from codepulse.benchmark.cli import benchmark_group
from codepulse.benchmark.pilot import (
    PILOT_TASK_IDS,
    PilotBudgetGuard,
    sha256_file,
    validate_pilot_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path


def _manifest(root: Path) -> dict[str, object]:
    for name in ("agent-a.yaml", "agent-b.yaml", "source.jsonl", "tasks.jsonl", "lock.txt"):
        (root / name).write_text(name, encoding="utf-8")
    agents = []
    for name, model in (("agent-a.yaml", "model-a-20260701"), ("agent-b.yaml", "model-b-20260701")):
        agents.append(
            {
                "name": name.removesuffix(".yaml"),
                "provider": "test-provider",
                "model_version": model,
                "provider_model_version": model,
                "profile_path": name,
                "profile_sha256": sha256_file(root / name),
            }
        )
    return {
        "protocol_version": "pilot-v1",
        "benchmark": "humaneval",
        "task_ids": PILOT_TASK_IDS,
        "n_trials": 3,
        "seed": 20260712,
        "agents": agents,
        "dataset": {
            "source_path": "source.jsonl",
            "source_sha256": sha256_file(root / "source.jsonl"),
            "task_path": "tasks.jsonl",
            "task_sha256": sha256_file(root / "tasks.jsonl"),
        },
        "dependencies": {
            "lockfile": "lock.txt",
            "lockfile_sha256": sha256_file(root / "lock.txt"),
        },
        "codepulse_commit": "a" * 40,
        "environment": {
            "image_digest": "sha256:" + "b" * 64,
            "cpus": 2,
            "memory_mb": 2048,
            "network": "none",
            "timeout_seconds": 300,
        },
        "budget": {"total_usd": 20.0, "per_agent_usd": 10.0, "per_trial_usd": 0.2},
    }


def test_pilot_preflight_valid_manifest_passes(tmp_path: Path) -> None:
    assert validate_pilot_manifest(_manifest(tmp_path), tmp_path) == []


def test_pilot_preflight_mutable_model_and_hash_mismatch_fail(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    agents = manifest["agents"]
    assert isinstance(agents, list)
    assert isinstance(agents[0], dict)
    agents[0]["model_version"] = "deepseek/deepseek-chat"
    (tmp_path / "agent-b.yaml").write_text("changed", encoding="utf-8")

    errors = validate_pilot_manifest(manifest, tmp_path)

    assert any("must be immutable" in error for error in errors)
    assert any("profile_sha256 mismatch" in error for error in errors)


def test_pilot_preflight_cli_reports_all_failures(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["n_trials"] = 1
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = CliRunner().invoke(
        benchmark_group,
        ["preflight", "--manifest", str(manifest_path), "--repo-root", str(tmp_path)],
    )

    assert result.exit_code != 0
    assert "n_trials must equal 3" in result.output


def test_pilot_preflight_cli_valid_manifest_passes(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest(tmp_path)), encoding="utf-8")

    result = CliRunner().invoke(
        benchmark_group,
        ["preflight", "--manifest", str(manifest_path), "--repo-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Pilot preflight passed" in result.output


def test_pilot_budget_guard_cost_limits_and_projection_stop() -> None:
    guard = PilotBudgetGuard()

    reasons = guard.record_trial("agent-a", 0.18)

    assert "projected_budget_exceeded" in reasons
    assert "per_trial_budget_reached" not in reasons
    assert guard.total_cost_usd == 0.18


def test_pilot_budget_guard_missing_cost_stops() -> None:
    guard = PilotBudgetGuard()

    assert guard.record_trial("agent-a", None) == ["cost_unavailable"]


def test_pilot_budget_guard_hard_cost_limits_stop() -> None:
    guard = PilotBudgetGuard(
        planned_trials=3,
        total_limit_usd=0.3,
        per_agent_limit_usd=0.2,
        per_trial_limit_usd=0.1,
    )

    first = guard.record_trial("agent-a", 0.1)
    second = guard.record_trial("agent-a", 0.1)
    third = guard.record_trial("agent-b", 0.1)

    assert "per_trial_budget_reached" in first
    assert "per_agent_budget_reached" in second
    assert "total_budget_reached" in third


def test_pilot_budget_guard_three_consecutive_infra_failures_stop() -> None:
    guard = PilotBudgetGuard()

    guard.record_trial("agent-a", 0.01, "provider_error")
    guard.record_trial("agent-b", 0.01, "agent_error")
    reasons = guard.record_trial("agent-a", 0.01, "sandbox_error")

    assert "consecutive_infrastructure_failures" in reasons


def test_pilot_budget_guard_infra_failure_rate_after_ten_trials_stop() -> None:
    guard = PilotBudgetGuard()
    for _ in range(8):
        guard.record_trial("agent-a", 0.01)
    guard.record_trial("agent-a", 0.01, "provider_error")

    reasons = guard.record_trial("agent-b", 0.01, "sandbox_error")

    assert "infrastructure_failure_rate_exceeded" in reasons
