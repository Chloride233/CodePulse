"""Tests for reproducible benchmark preflight gates."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from codepulse.benchmark.cli import benchmark_group
from codepulse.benchmark.pilot import (
    DIAGNOSTIC_TASK_IDS,
    PILOT_TASK_IDS,
    PilotBudgetGuard,
    build_pilot_schedule,
    deepseek_v4_flash_cost_cny,
    load_pilot_manifest,
    sha256_file,
    validate_pilot_manifest,
)

ROOT = Path(__file__).parents[1]


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
        "budget": {"total_cny": 10.0, "per_agent_cny": 5.0, "per_trial_cny": 0.1},
        "pricing": {
            "currency": "CNY",
            "unit_tokens": 1_000_000,
            "schedule_status": "pending_official_schedule",
            "off_peak": {"cache_hit": 0.02, "cache_miss": 1.0, "output": 2.0},
            "peak": {"cache_hit": 0.04, "cache_miss": 2.0, "output": 4.0},
            "budget_tier": "peak",
        },
    }


def test_pilot_preflight_valid_manifest_passes(tmp_path: Path) -> None:
    assert validate_pilot_manifest(_manifest(tmp_path), tmp_path) == []


def test_phase2_diagnostic_preflight_accepts_minimum_manifest(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    agents = manifest["agents"]
    assert isinstance(agents, list)
    manifest.update(
        {
            "protocol_version": "phase2-diagnostic-v1",
            "task_ids": DIAGNOSTIC_TASK_IDS,
            "n_trials": 1,
            "seed": 20260713,
            "agents": agents[:1],
            "budget": {
                "total_cny": 1.0,
                "per_agent_cny": 1.0,
                "per_trial_cny": 0.1,
            },
        }
    )

    assert validate_pilot_manifest(manifest, tmp_path) == []


def test_phase2_diagnostic_repository_manifest_hashes_match() -> None:
    manifest = load_pilot_manifest(
        ROOT / "experiments" / "phase2-diagnostic-v1" / "manifest.json"
    )

    assert validate_pilot_manifest(manifest, ROOT) == []


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


def test_pilot_run_cli_exposes_opt_in_evidence_capture() -> None:
    result = CliRunner().invoke(benchmark_group, ["pilot-run", "--help"])

    assert result.exit_code == 0
    assert "--capture-evidence" in result.output


def test_pilot_budget_guard_cost_limits_and_projection_stop() -> None:
    guard = PilotBudgetGuard()

    reasons = guard.record_trial("agent-a", 0.09)

    assert "projected_budget_exceeded" in reasons
    assert "per_trial_budget_reached" not in reasons
    assert guard.total_cost_cny == 0.09


def test_pilot_budget_guard_missing_cost_stops() -> None:
    guard = PilotBudgetGuard()

    assert guard.record_trial("agent-a", None) == ["cost_unavailable"]


def test_pilot_budget_guard_hard_cost_limits_stop() -> None:
    guard = PilotBudgetGuard(
        planned_trials=3,
        total_limit_cny=0.3,
        per_agent_limit_cny=0.2,
        per_trial_limit_cny=0.1,
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


def test_v4_flash_pricing_peak_is_double_off_peak() -> None:
    off_peak = deepseek_v4_flash_cost_cny(5_000, 1_000, 0, "off_peak")
    peak = deepseek_v4_flash_cost_cny(5_000, 1_000, 0, "peak")

    assert off_peak == 0.007
    assert peak == 0.014


def test_v4_flash_pricing_cache_hit_uses_lower_rate() -> None:
    assert deepseek_v4_flash_cost_cny(5_000, 1_000, 5_000, "off_peak") == 0.0021


def test_pilot_schedule_is_seeded_and_interleaves_agents() -> None:
    schedule = build_pilot_schedule(
        ["HumanEval/0", "HumanEval/1"], ["direct", "iterative"], 2, 20260712
    )

    assert schedule == build_pilot_schedule(
        ["HumanEval/0", "HumanEval/1"], ["direct", "iterative"], 2, 20260712
    )
    assert len(schedule) == 8
    for offset in range(0, len(schedule), 2):
        pair = schedule[offset : offset + 2]
        assert pair[0][:2] == pair[1][:2]
        assert {pair[0][2], pair[1][2]} == {"direct", "iterative"}
