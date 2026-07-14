"""Tests for pilot report aggregation and Phase 3 paired comparisons."""

from __future__ import annotations

import pytest

from codepulse.benchmark.pilot_report import compare_phase3_pilot, summarize_pilot


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
