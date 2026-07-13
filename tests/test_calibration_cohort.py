"""Tests for the deterministic Phase 2 diagnostic cohort gate."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from codepulse.eval.calibration_cohort import (
    profile_diagnostic_cohort,
    select_diagnostic_cohort,
)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _tool_event(tool: str, *, success: bool = True) -> dict[str, Any]:
    return {
        "event_type": "tool_call",
        "content": {"tool": tool, "success": success, "error": ""},
    }


def _result_event(tool: str, *, success: bool = True) -> dict[str, Any]:
    return {
        "event_type": "tool_result",
        "content": {
            "tool": tool,
            "success": success,
            "error": "" if success else "command failed",
        },
    }


def _trial(
    index: int,
    *,
    passed: bool = True,
    events: list[dict[str, Any]] | None = None,
    failure_type: str | None = None,
) -> dict[str, Any]:
    trace_events = events or [
        {"event_type": "llm_call", "content": {}},
        _tool_event("write_file"),
        _result_event("write_file"),
        _tool_event("execute"),
        _result_event("execute"),
    ]
    evidence: dict[str, Any] = {
        "schema_version": "calibration-evidence-v1",
        "task": {
            "task_id": f"HumanEval/{index}",
            "description": "Return the input value.",
        },
        "output_files": {"solution.py": "def identity(value):\n    return value\n"},
        "transcript": {
            "events": trace_events,
            "total_tokens": 100 + index,
            "total_duration": 1.0,
            "tool_call_count": sum(
                event["event_type"] == "tool_call" for event in trace_events
            ),
        },
        "verification": {
            "exit_code": 0 if passed else 1,
            "stdout": "1 passed" if passed else "1 failed",
            "stderr": "",
            "pytest_total": 1,
            "pytest_passed": 1 if passed else 0,
        },
    }
    evidence["sha256"] = _canonical_sha256(evidence)
    return {
        "trial_id": f"HumanEval/{index}--r0--agent",
        "task_id": f"HumanEval/{index}",
        "agent_name": "agent",
        "success": passed,
        "outcome": {"evidence": evidence, "failure_type": failure_type},
        "metrics": {"total_tokens": 100 + index},
    }


def _recovered_trial(index: int) -> dict[str, Any]:
    return _trial(
        index,
        events=[
            {"event_type": "llm_call", "content": {}},
            _tool_event("write_file"),
            _tool_event("execute", success=False),
            _result_event("execute", success=False),
            _tool_event("write_file"),
            _tool_event("execute"),
            _result_event("execute"),
        ],
    )


def _multi_attempt_trial(index: int) -> dict[str, Any]:
    return _trial(
        index,
        events=[
            {"event_type": "llm_call", "content": {}},
            _tool_event("write_file"),
            _tool_event("execute"),
            _result_event("execute"),
            _tool_event("execute"),
            _result_event("execute"),
        ],
    )


def test_calibration_cohort_classification_is_mutually_exclusive() -> None:
    incomplete = copy.deepcopy(_trial(1))
    evidence = incomplete["outcome"]["evidence"]
    evidence["output_files"] = {}
    evidence["sha256"] = _canonical_sha256(
        {key: value for key, value in evidence.items() if key != "sha256"}
    )
    trials = [
        _trial(0, failure_type="provider_error"),
        incomplete,
        _trial(2, passed=False),
        _recovered_trial(3),
        _multi_attempt_trial(4),
        _trial(5),
    ]

    profile = profile_diagnostic_cohort(trials, seed=7)

    assert [record["status"] for record in profile["records"]] == [
        "infrastructure_failure",
        "incomplete_evidence",
        "unresolved_failure",
        "recovered_success",
        "multi_attempt_success",
        "direct_success",
    ]
    assert profile["eligible_count"] == 4
    assert profile["excluded_count"] == 2


def test_calibration_cohort_homogeneous_successes_are_not_ready() -> None:
    profile = profile_diagnostic_cohort([_trial(index) for index in range(10)], seed=7)

    assert profile["status"] == "not_ready"
    assert profile["stratum_counts"] == {"direct_success": 10}
    reason_codes = {reason["code"] for reason in profile["reasons"]}
    assert "insufficient_strata" in reason_codes
    assert "dominant_stratum" in reason_codes
    assert "missing_failure" in reason_codes


def test_calibration_cohort_three_strata_can_pass_without_recovery() -> None:
    trials = [
        *[_trial(index) for index in range(4)],
        *[_multi_attempt_trial(index) for index in range(4, 9)],
        _trial(9, passed=False),
    ]

    profile = profile_diagnostic_cohort(trials, seed=7)

    assert profile["status"] == "ready"
    assert profile["stratum_counts"] == {
        "direct_success": 4,
        "multi_attempt_success": 5,
        "unresolved_failure": 1,
    }


def test_calibration_cohort_diverse_pool_selects_stably() -> None:
    trials = [
        *[_trial(index) for index in range(3)],
        *[_multi_attempt_trial(index) for index in range(3, 6)],
        *[_recovered_trial(index) for index in range(6, 9)],
        *[_trial(index, passed=False) for index in range(9, 12)],
    ]

    first = profile_diagnostic_cohort(trials, seed=7)
    second = profile_diagnostic_cohort(list(reversed(trials)), seed=7)
    selected, selected_profile = select_diagnostic_cohort(trials, seed=7)

    assert first["status"] == "ready"
    assert first["selected_trial_ids"] == second["selected_trial_ids"]
    assert len(selected) == 10
    assert selected_profile == first
    assert {row["trial_id"] for row in selected} == set(first["selected_trial_ids"])
    assert max(first["stratum_counts"].values()) <= 5


def test_calibration_cohort_recovery_takes_priority_over_multiple_attempts() -> None:
    profile = profile_diagnostic_cohort([_recovered_trial(0)], seed=7)

    record = profile["records"][0]
    assert record["status"] == "recovered_success"
    assert record["execution_attempts"] == 2
    assert record["code_writes"] == 2
    assert record["failed_tool_results"] == 1
