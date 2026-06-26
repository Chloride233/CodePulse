"""Tests for all grader implementations.

Covers PytestGrader, CodeQualityGrader, and EfficiencyGrader — verifying
protocol compliance, scoring logic, and diagnostic details.
"""

from __future__ import annotations

import pytest

from codepulse.data.models import (
    AgentConfig,
    Difficulty,
    Task,
    TaskCategory,
    TaskSource,
    Trial,
    TrialMetrics,
)
from codepulse.data.protocols import Grader, GraderResult
from codepulse.eval.code_quality_grader import CodeQualityGrader
from codepulse.eval.efficiency_grader import EfficiencyGrader
from codepulse.eval.pytest_grader import PytestGrader
from codepulse.eval.scoring import ScoreDimension

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_task(sample_task_data: dict) -> Task:
    """Build a Task object from the conftest sample_task_data fixture."""
    return Task(
        task_id=sample_task_data["task_id"],
        source=TaskSource(sample_task_data["source"]),
        category=TaskCategory(sample_task_data["category"]),
        difficulty=Difficulty(sample_task_data["difficulty"]),
        language=sample_task_data["language"],
        input=sample_task_data["input"],
        ground_truth=sample_task_data["ground_truth"],
    )


@pytest.fixture
def _agent_config() -> AgentConfig:
    return AgentConfig(name="test-agent", model="test-model")


@pytest.fixture
def passing_trial(_agent_config: AgentConfig) -> Trial:
    """A trial whose pytest run succeeded (exit_code=0)."""
    return Trial(
        trial_id="trial-pass",
        task_id="test-001",
        agent_config=_agent_config,
        outcome={
            "exit_code": 0,
            "stdout": "all tests passed",
            "stderr": "",
        },
    )


@pytest.fixture
def failing_trial(_agent_config: AgentConfig) -> Trial:
    """A trial whose pytest run failed (exit_code=1)."""
    return Trial(
        trial_id="trial-fail",
        task_id="test-001",
        agent_config=_agent_config,
        outcome={
            "exit_code": 1,
            "stdout": "",
            "stderr": "AssertionError: expected 2, got 3",
        },
    )


# ---------------------------------------------------------------------------
# PytestGrader tests
# ---------------------------------------------------------------------------


class TestPytestGrader:
    """Tests for the functional-correctness grader."""

    def test_satisfies_grader_protocol(self) -> None:
        grader = PytestGrader()
        assert isinstance(grader, Grader)

    def test_returns_functional_dimension(
        self, sample_task: Task, passing_trial: Trial
    ) -> None:
        grader = PytestGrader()
        result = grader.grade(sample_task, passing_trial)
        assert isinstance(result, GraderResult)
        assert result.dimension == ScoreDimension.FUNCTIONAL

    def test_score_one_when_exit_code_zero(
        self, sample_task: Task, passing_trial: Trial
    ) -> None:
        grader = PytestGrader()
        result = grader.grade(sample_task, passing_trial)
        assert result.score == 1.0

    def test_score_zero_when_exit_code_nonzero(
        self, sample_task: Task, failing_trial: Trial
    ) -> None:
        grader = PytestGrader()
        result = grader.grade(sample_task, failing_trial)
        assert result.score == 0.0

    def test_score_zero_when_exit_code_missing(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-no-exit",
            task_id="test-001",
            agent_config=_agent_config,
            outcome={},
        )
        grader = PytestGrader()
        result = grader.grade(sample_task, trial)
        assert result.score == 0.0

    def test_details_contain_exit_code(
        self, sample_task: Task, passing_trial: Trial
    ) -> None:
        grader = PytestGrader()
        result = grader.grade(sample_task, passing_trial)
        assert "exit_code" in result.details
        assert result.details["exit_code"] == 0

    def test_details_contain_stdout_stderr(
        self, sample_task: Task, passing_trial: Trial
    ) -> None:
        grader = PytestGrader()
        result = grader.grade(sample_task, passing_trial)
        assert "stdout" in result.details
        assert "stderr" in result.details
        assert "has_test_patch" in result.details


# ---------------------------------------------------------------------------
# CodeQualityGrader tests
# ---------------------------------------------------------------------------


class TestCodeQualityGrader:
    """Tests for the robustness/code-quality grader."""

    def test_satisfies_grader_protocol(self) -> None:
        grader = CodeQualityGrader()
        assert isinstance(grader, Grader)

    def test_returns_robustness_dimension(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-clean",
            task_id="test-001",
            agent_config=_agent_config,
            outcome={"ruff_violations": 0, "mypy_errors": 0, "bandit_high": 0},
        )
        grader = CodeQualityGrader()
        result = grader.grade(sample_task, trial)
        assert isinstance(result, GraderResult)
        assert result.dimension == ScoreDimension.ROBUSTNESS

    def test_score_one_when_no_violations(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-clean",
            task_id="test-001",
            agent_config=_agent_config,
            outcome={"ruff_violations": 0, "mypy_errors": 0, "bandit_high": 0},
        )
        grader = CodeQualityGrader()
        result = grader.grade(sample_task, trial)
        assert result.score == 1.0

    def test_score_decreases_with_violations(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-dirty",
            task_id="test-001",
            agent_config=_agent_config,
            outcome={"ruff_violations": 3, "mypy_errors": 2, "bandit_high": 1},
        )
        grader = CodeQualityGrader()
        result = grader.grade(sample_task, trial)
        # 6 total violations * 0.1 = 0.6 penalty; 1.0 - 0.6 = 0.4
        assert result.score == pytest.approx(0.4)

    def test_score_clamps_at_zero(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-very-dirty",
            task_id="test-001",
            agent_config=_agent_config,
            outcome={"ruff_violations": 10, "mypy_errors": 10, "bandit_high": 10},
        )
        grader = CodeQualityGrader()
        result = grader.grade(sample_task, trial)
        assert result.score == 0.0

    def test_details_contain_violation_counts(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-mixed",
            task_id="test-001",
            agent_config=_agent_config,
            outcome={"ruff_violations": 1, "mypy_errors": 2, "bandit_high": 0},
        )
        grader = CodeQualityGrader()
        result = grader.grade(sample_task, trial)
        assert result.details["ruff_violations"] == 1
        assert result.details["mypy_errors"] == 2
        assert result.details["bandit_high"] == 0
        assert result.details["total_violations"] == 3


# ---------------------------------------------------------------------------
# EfficiencyGrader tests
# ---------------------------------------------------------------------------


class TestEfficiencyGrader:
    """Tests for the efficiency/cost grader."""

    def test_satisfies_grader_protocol(self) -> None:
        grader = EfficiencyGrader()
        assert isinstance(grader, Grader)

    def test_returns_efficiency_dimension(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-efficient",
            task_id="test-001",
            agent_config=_agent_config,
            metrics=TrialMetrics(total_tokens=500, total_duration=30.0),
        )
        grader = EfficiencyGrader()
        result = grader.grade(sample_task, trial)
        assert isinstance(result, GraderResult)
        assert result.dimension == ScoreDimension.EFFICIENCY

    def test_score_one_when_within_baseline(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-efficient",
            task_id="test-001",
            agent_config=_agent_config,
            metrics=TrialMetrics(total_tokens=500, total_duration=30.0),
        )
        grader = EfficiencyGrader()
        result = grader.grade(sample_task, trial)
        assert result.score == 1.0

    def test_score_one_when_exactly_at_baseline(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-at-baseline",
            task_id="test-001",
            agent_config=_agent_config,
            metrics=TrialMetrics(total_tokens=1000, total_duration=60.0),
        )
        grader = EfficiencyGrader()
        result = grader.grade(sample_task, trial)
        assert result.score == 1.0

    def test_score_decreases_when_exceeding_baseline(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        # Tokens at 2000 (100% over baseline of 1000) => token_score = 0.9
        # Duration at 120 (100% over baseline of 60)   => duration_score = 0.9
        # Final = (0.9 + 0.9) / 2 = 0.9
        trial = Trial(
            trial_id="trial-over-baseline",
            task_id="test-001",
            agent_config=_agent_config,
            metrics=TrialMetrics(total_tokens=2000, total_duration=120.0),
        )
        grader = EfficiencyGrader()
        result = grader.grade(sample_task, trial)
        assert result.score == pytest.approx(0.9)

    def test_score_clamps_at_zero(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        # Extremely over budget should clamp each sub-score to 0.
        trial = Trial(
            trial_id="trial-huge",
            task_id="test-001",
            agent_config=_agent_config,
            metrics=TrialMetrics(total_tokens=100_000, total_duration=10_000.0),
        )
        grader = EfficiencyGrader()
        result = grader.grade(sample_task, trial)
        assert result.score == 0.0

    def test_details_contain_token_and_duration_metrics(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-metrics",
            task_id="test-001",
            agent_config=_agent_config,
            metrics=TrialMetrics(total_tokens=750, total_duration=45.0),
        )
        grader = EfficiencyGrader()
        result = grader.grade(sample_task, trial)
        assert result.details["total_tokens"] == 750
        assert result.details["baseline_tokens"] == 1000
        assert "token_score" in result.details
        assert result.details["total_duration"] == pytest.approx(45.0)
        assert result.details["baseline_duration"] == 60.0
        assert "duration_score" in result.details

    def test_custom_baselines(
        self, sample_task: Task, _agent_config: AgentConfig
    ) -> None:
        trial = Trial(
            trial_id="trial-custom",
            task_id="test-001",
            agent_config=_agent_config,
            metrics=TrialMetrics(total_tokens=2000, total_duration=200.0),
        )
        grader = EfficiencyGrader(baseline_tokens=2000, baseline_duration=200.0)
        result = grader.grade(sample_task, trial)
        assert result.score == 1.0
        assert result.details["baseline_tokens"] == 2000
        assert result.details["baseline_duration"] == 200.0
