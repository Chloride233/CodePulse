"""Tests for pilot report aggregation."""

from codepulse.benchmark.pilot_report import summarize_pilot


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
