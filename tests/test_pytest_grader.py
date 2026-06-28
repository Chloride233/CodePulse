"""Tests for PytestGrader — 功能正确性评分器。"""

from __future__ import annotations

from unittest.mock import MagicMock

from codepulse.data.models import AgentConfig, Trial
from codepulse.eval.pytest_grader import PytestGrader
from codepulse.eval.scoring import ScoreDimension


def _make_trial(outcome: dict) -> Trial:
    """Create a trial with the given outcome."""
    return Trial(
        trial_id="t1",
        task_id="test-001",
        agent_config=AgentConfig(name="a", model="m"),
        outcome=outcome,
    )


def _make_task() -> MagicMock:
    """Create a mock task."""
    task = MagicMock()
    task.task_id = "test-001"
    task.ground_truth = {"test_cases": ["assert 1+1 == 2"]}
    return task


class TestPytestGraderExitCode:
    """Tests for exit code scoring mode."""

    def test_exit_code_zero(self) -> None:
        grader = PytestGrader(use_partial_scoring=False)
        trial = _make_trial({"exit_code": 0, "stdout": "", "stderr": ""})
        result = grader.grade(_make_task(), trial)
        assert result.score == 1.0
        assert result.dimension == ScoreDimension.FUNCTIONAL

    def test_exit_code_nonzero(self) -> None:
        grader = PytestGrader(use_partial_scoring=False)
        trial = _make_trial({"exit_code": 1, "stdout": "", "stderr": "FAIL"})
        result = grader.grade(_make_task(), trial)
        assert result.score == 0.0

    def test_missing_exit_code(self) -> None:
        grader = PytestGrader(use_partial_scoring=False)
        trial = _make_trial({})
        result = grader.grade(_make_task(), trial)
        assert result.score == 0.0

    def test_exit_code_string(self) -> None:
        grader = PytestGrader(use_partial_scoring=False)
        trial = _make_trial({"exit_code": "0"})
        result = grader.grade(_make_task(), trial)
        assert result.score == 1.0


class TestPytestGraderPartialScoring:
    """Tests for partial scoring mode."""

    def test_all_passed(self) -> None:
        grader = PytestGrader(use_partial_scoring=True)
        trial = _make_trial({
            "exit_code": 0,
            "pytest_total": 5,
            "pytest_passed": 5,
            "stdout": "",
            "stderr": "",
        })
        result = grader.grade(_make_task(), trial)
        assert result.score == 1.0
        assert result.details["scoring_mode"] == "partial"

    def test_partial_pass(self) -> None:
        grader = PytestGrader(use_partial_scoring=True)
        trial = _make_trial({
            "exit_code": 1,
            "pytest_total": 10,
            "pytest_passed": 7,
            "stdout": "",
            "stderr": "",
        })
        result = grader.grade(_make_task(), trial)
        assert result.score == 0.7

    def test_none_passed(self) -> None:
        grader = PytestGrader(use_partial_scoring=True)
        trial = _make_trial({
            "exit_code": 1,
            "pytest_total": 5,
            "pytest_passed": 0,
            "stdout": "",
            "stderr": "",
        })
        result = grader.grade(_make_task(), trial)
        assert result.score == 0.0

    def test_zero_total_falls_back_to_exit_code(self) -> None:
        grader = PytestGrader(use_partial_scoring=True)
        trial = _make_trial({
            "exit_code": 0,
            "pytest_total": 0,
            "pytest_passed": 0,
            "stdout": "",
            "stderr": "",
        })
        result = grader.grade(_make_task(), trial)
        assert result.score == 1.0
        assert result.details["scoring_mode"] == "exit_code"

    def test_missing_pytest_data_falls_back(self) -> None:
        grader = PytestGrader(use_partial_scoring=True)
        trial = _make_trial({"exit_code": 1, "stdout": "", "stderr": ""})
        result = grader.grade(_make_task(), trial)
        assert result.score == 0.0
        assert result.details["scoring_mode"] == "exit_code"


class TestPytestGraderDetails:
    """Tests for grader result details."""

    def test_details_include_metrics(self) -> None:
        grader = PytestGrader()
        trial = _make_trial({
            "exit_code": 0,
            "pytest_total": 3,
            "pytest_passed": 3,
            "stdout": "3 passed",
            "stderr": "",
        })
        result = grader.grade(_make_task(), trial)
        assert result.details["exit_code"] == 0
        assert result.details["pytest_total"] == 3
        assert result.details["pytest_passed"] == 3

    def test_stdout_truncated(self) -> None:
        grader = PytestGrader()
        long_stdout = "x" * 10000
        trial = _make_trial({
            "exit_code": 0,
            "stdout": long_stdout,
            "stderr": "",
        })
        result = grader.grade(_make_task(), trial)
        assert len(result.details["stdout"]) <= 4096
