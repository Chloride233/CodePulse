"""Tests for pilot report aggregation and Phase 3 paired comparisons."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from codepulse.benchmark.pilot_report import (
    classify_phase3_pilot,
    compare_phase3_pilot,
    summarize_pilot,
    validate_phase3_pilot,
    write_phase3_reports,
)


def test_pilot_report_pass_metrics_and_nearest_rank() -> None:
    rows = []
    for repetition, success in enumerate((True, False, True)):
        rows.append(
            {
                "agent_name": "agent-a",
                "task_id": "task-1",
                "success": success,
                "failure_type": None,
                "metrics": {
                    "duration_seconds": repetition + 1,
                    "total_tokens": 100,
                    "cost_cny_off_peak": 0.01,
                    "cost_cny_peak": 0.02,
                },
            }
        )

    summary = summarize_pilot(rows)[0]

    assert summary["pass_at_1"] == 2 / 3
    assert summary["pass_at_3"] == 1.0
    assert summary["pass_hat_3"] == 0.0
    assert summary["p50_seconds"] == 2
    assert summary["p95_seconds"] == 3


def _phase3_manifest() -> dict[str, object]:
    return {
        "protocol_version": "phase3-evolution-v1",
        "n_trials": 3,
        "task_ids": ["task-0", "task-1"],
        "budget": {"per_trial_cny": 0.1, "per_agent_cny": 5.0},
        "agents": [
            {"role": "baseline", "name": "baseline"},
            {"role": "candidate", "name": "candidate"},
        ],
    }


def _phase3_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    outcomes = {
        "baseline": ((True, True, False), (False, False, False)),
        "candidate": ((True, True, True), (True, False, True)),
    }
    for agent_name, task_outcomes in outcomes.items():
        for task_number, successes in enumerate(task_outcomes):
            for repetition, success in enumerate(successes):
                rows.append(
                    {
                        "agent_name": agent_name,
                        "task_id": f"task-{task_number}",
                        "repetition": repetition,
                        "success": success,
                        "failure_type": None if success else "wrong_answer",
                        "metrics": {
                            "duration_seconds": 1.0 + repetition + task_number,
                            "total_tokens": 100 + 10 * task_number,
                            "cost_cny_off_peak": 0.001,
                            "cost_cny_peak": 0.002,
                        },
                    }
                )
    return rows


def test_phase3_pilot_compares_frozen_roles_and_metric_deltas() -> None:
    comparison = compare_phase3_pilot(_phase3_rows(), _phase3_manifest())

    assert comparison["k"] == 3
    assert comparison["baseline"]["success_rate"] == pytest.approx(2 / 6)
    assert comparison["candidate"]["success_rate"] == pytest.approx(5 / 6)
    assert comparison["deltas"]["success_rate"] == pytest.approx(0.5)
    assert comparison["deltas"]["pass_hat_k"] == pytest.approx(0.5)
    assert comparison["deltas"]["total_tokens"] == 0.0
    assert comparison["deltas"]["cost_cny_peak"] == 0.0


def test_phase3_pilot_rejects_unpaired_trials_or_unknown_agents() -> None:
    unpaired = _phase3_rows()[1:]
    with pytest.raises(ValueError, match="coverage mismatch"):
        compare_phase3_pilot(unpaired, _phase3_manifest())

    contaminated = _phase3_rows()
    contaminated[0]["agent_name"] = "other-agent"
    with pytest.raises(ValueError, match="exactly the frozen baseline and candidate"):
        compare_phase3_pilot(contaminated, _phase3_manifest())


def test_phase3_pilot_rejects_trials_missing_from_both_roles() -> None:
    incomplete = [
        row for index, row in enumerate(_phase3_rows()) if index not in {0, 6}
    ]

    with pytest.raises(ValueError, match="does not match the frozen task set"):
        compare_phase3_pilot(incomplete, _phase3_manifest())


def test_phase3_pilot_classifies_pass_hat_states() -> None:
    manifest = _phase3_manifest()
    manifest["task_ids"] = ["improvement", "regression", "persistent", "stable"]
    outcomes = {
        "baseline": ((False, False, False), (True, True, True), (False, False, False), (True, True, True)),
        "candidate": ((True, True, True), (False, False, False), (False, False, False), (True, True, True)),
    }
    task_ids = manifest["task_ids"]
    assert isinstance(task_ids, list)
    rows: list[dict[str, object]] = []
    for agent_name, task_outcomes in outcomes.items():
        for task_id, successes in zip(task_ids, task_outcomes, strict=True):
            for repetition, success in enumerate(successes):
                rows.append(
                    {
                        "agent_name": agent_name,
                        "task_id": task_id,
                        "repetition": repetition,
                        "success": success,
                        "failure_type": None if success else "wrong_answer",
                        "metrics": {
                            "duration_seconds": 1.0,
                            "total_tokens": 100,
                            "cost_cny_off_peak": 0.001,
                            "cost_cny_peak": 0.002,
                        },
                    }
                )

    result = classify_phase3_pilot(rows, manifest)

    assert result["by_task"] == {
        "improvement": "improvement",
        "regression": "regression",
        "persistent": "persistent_failure",
        "stable": "stable_success",
    }
    assert result["summary"] == {
        "improvements": 1,
        "regressions": 1,
        "persistent_failures": 1,
        "stable_successes": 1,
        "improvement_rate": 0.25,
        "regression_rate": 0.25,
        "total": 4,
    }


def test_phase3_pilot_gate_accepts_stable_improvement_and_rejects_invalid_rows() -> None:
    accepted = validate_phase3_pilot(_phase3_rows(), _phase3_manifest())

    assert accepted["accepted"] is True
    assert accepted["stable_pass_gain"] == pytest.approx(0.5)

    rejected = validate_phase3_pilot(_phase3_rows()[1:], _phase3_manifest())

    assert rejected["accepted"] is False
    assert rejected["rejection_reasons"] == ["invalid_trial_coverage"]


def test_phase3_pilot_gate_rejects_regressive_candidate() -> None:
    rows = _phase3_rows()
    for row in rows:
        if row["task_id"] != "task-0":
            continue
        row["success"] = row["agent_name"] == "baseline"
        row["failure_type"] = None if row["success"] else "wrong_answer"

    rejected = validate_phase3_pilot(rows, _phase3_manifest())

    assert rejected["accepted"] is False
    assert "regression_detected" in rejected["rejection_reasons"]


def test_phase3_report_writes_metrics_cases_and_reproduction_commands(tmp_path: Path) -> None:
    (tmp_path / "trials.jsonl").write_text(
        "\n".join(json.dumps(row) for row in _phase3_rows()) + "\n",
        encoding="utf-8",
    )

    markdown_path, html_path = write_phase3_reports(tmp_path, _phase3_manifest())
    markdown = markdown_path.read_text(encoding="utf-8")

    assert html_path.is_file()
    assert "# CodePulse Phase 3 Comparison Report" in markdown
    assert "| improvement | task-0 | pass, pass, fail | pass, pass, pass |" in markdown
    assert "codepulse benchmark phase3-report" in markdown


def test_phase3_report_uses_swebench_reproduction_commands(tmp_path: Path) -> None:
    manifest = _phase3_manifest()
    manifest["protocol_version"] = "phase3-swebench-evolution-v4"
    (tmp_path / "trials.jsonl").write_text(
        "\n".join(json.dumps(row) for row in _phase3_rows()) + "\n",
        encoding="utf-8",
    )

    markdown_path, _ = write_phase3_reports(tmp_path, manifest)
    markdown = markdown_path.read_text(encoding="utf-8")

    assert "swebench-evolution-preflight" in markdown
    assert "swebench-evolution-run" in markdown
    assert "phase3-swebench-evolution-v4/manifest.json" in markdown
