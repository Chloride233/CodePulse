"""Tests for Protocol definitions — Agent, Grader, DatasetLoader.

Validates that protocols are importable, runtime-checkable, and that
mock implementations satisfy structural typing contracts.
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
)
from codepulse.data.protocols import Agent, DatasetLoader, Grader, GraderResult
from codepulse.eval.scoring import ScoreDimension
from codepulse.observe.trace import Transcript

# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class MockAgent:
    """Minimal Agent implementation for protocol checks."""

    name: str = "mock"
    model: str = "test"

    def run(self, task: Task, sandbox: object) -> Transcript:
        return Transcript(session_id="mock-session")


class MockGrader:
    """Minimal Grader implementation for protocol checks."""

    name: str = "mock"

    def grade(self, task: Task, trial: Trial) -> GraderResult:
        return GraderResult(
            dimension=ScoreDimension.FUNCTIONAL,
            score=1.0,
            details={"passed": True},
        )


class MockLoader:
    """Minimal DatasetLoader implementation for protocol checks."""

    def load(self, path: str) -> list[Task]:
        return []

    def validate(self, task: Task) -> bool:
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task() -> Task:
    return Task(
        task_id="t-001",
        source=TaskSource.CUSTOM,
        category=TaskCategory.BUG_FIX,
        difficulty=Difficulty.EASY,
        language="python",
        input={"prompt": "fix the bug"},
        ground_truth={"expected_output": "fixed"},
    )


def _make_trial() -> Trial:
    return Trial(
        trial_id="tr-001",
        task_id="t-001",
        agent_config=AgentConfig(name="mock", model="test"),
    )


# ---------------------------------------------------------------------------
# 1. Protocols exist and are importable
# ---------------------------------------------------------------------------


class TestProtocolImports:
    """Protocols can be imported from codepulse.data.protocols."""

    def test_agent_importable(self):
        assert Agent is not None

    def test_grader_importable(self):
        assert Grader is not None

    def test_dataset_loader_importable(self):
        assert DatasetLoader is not None


# ---------------------------------------------------------------------------
# 2. Mock implementations satisfy protocols (runtime_checkable)
# ---------------------------------------------------------------------------


class TestProtocolSatisfaction:
    """Mock classes pass isinstance checks against runtime_checkable protocols."""

    def test_mock_agent_satisfies_protocol(self):
        assert isinstance(MockAgent(), Agent)

    def test_mock_grader_satisfies_protocol(self):
        assert isinstance(MockGrader(), Grader)

    def test_mock_loader_satisfies_protocol(self):
        assert isinstance(MockLoader(), DatasetLoader)

    def test_plain_object_does_not_satisfy_agent(self):
        assert not isinstance(object(), Agent)

    def test_plain_object_does_not_satisfy_grader(self):
        assert not isinstance(object(), Grader)

    def test_plain_object_does_not_satisfy_loader(self):
        assert not isinstance(object(), DatasetLoader)


# ---------------------------------------------------------------------------
# 3. GraderResult creation and field validation
# ---------------------------------------------------------------------------


class TestGraderResult:
    """GraderResult dataclass behaviour and constraints."""

    def test_creation_with_correct_fields(self):
        result = GraderResult(
            dimension=ScoreDimension.FUNCTIONAL,
            score=0.85,
            details={"tests_passed": 8, "tests_total": 10},
        )
        assert result.dimension == ScoreDimension.FUNCTIONAL
        assert result.score == 0.85
        assert result.details == {"tests_passed": 8, "tests_total": 10}

    def test_score_zero(self):
        result = GraderResult(
            dimension=ScoreDimension.PROCESS,
            score=0.0,
            details={},
        )
        assert result.score == 0.0

    def test_score_one(self):
        result = GraderResult(
            dimension=ScoreDimension.ALIGNMENT,
            score=1.0,
            details={},
        )
        assert result.score == 1.0

    def test_score_below_zero_raises(self):
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            GraderResult(
                dimension=ScoreDimension.FUNCTIONAL,
                score=-0.1,
                details={},
            )

    def test_score_above_one_raises(self):
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            GraderResult(
                dimension=ScoreDimension.FUNCTIONAL,
                score=1.1,
                details={},
            )

    def test_frozen(self):
        result = GraderResult(
            dimension=ScoreDimension.EFFICIENCY,
            score=0.5,
            details={},
        )
        with pytest.raises(AttributeError):
            result.score = 0.9  # type: ignore[misc]

    def test_details_accepts_mixed_types(self):
        result = GraderResult(
            dimension=ScoreDimension.ROBUSTNESS,
            score=0.75,
            details={
                "string_val": "ok",
                "int_val": 42,
                "float_val": 3.14,
                "bool_val": True,
            },
        )
        assert result.details["string_val"] == "ok"
        assert result.details["bool_val"] is True

    def test_mock_grader_returns_valid_result(self):
        """MockGrader.grade() produces a well-formed GraderResult."""
        task = _make_task()
        trial = _make_trial()
        result = MockGrader().grade(task, trial)

        assert isinstance(result, GraderResult)
        assert result.dimension == ScoreDimension.FUNCTIONAL
        assert result.score == 1.0
        assert result.details == {"passed": True}
