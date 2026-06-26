"""Tests for LLM-based graders (RubricGrader and ReasoningGrader).

Covers protocol compliance, scoring logic, mock LLM interactions,
and edge cases like missing data and unparseable responses.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codepulse.data.models import (
    AgentConfig,
    Difficulty,
    Task,
    TaskCategory,
    TaskSource,
    Trial,
)
from codepulse.data.protocols import Grader, GraderResult
from codepulse.eval.reasoning_grader import ReasoningGrader
from codepulse.eval.rubric_grader import RubricGrader
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
def trial_with_output(_agent_config: AgentConfig) -> Trial:
    """A trial with output suitable for rubric grading."""
    return Trial(
        trial_id="trial-rubric",
        task_id="test-001",
        agent_config=_agent_config,
        outcome={
            "output": "def add(a, b): return a + b",
            "reasoning_steps": [
                "Analyzed the bug in the add function",
                "Identified missing return statement",
                "Implemented fix with proper return",
            ],
        },
    )


@pytest.fixture
def trial_without_reasoning(_agent_config: AgentConfig) -> Trial:
    """A trial with no reasoning steps."""
    return Trial(
        trial_id="trial-no-reasoning",
        task_id="test-001",
        agent_config=_agent_config,
        outcome={
            "output": "def add(a, b): return a + b",
        },
    )


@pytest.fixture
def mock_llm_response() -> MagicMock:
    """Create a mock LLM response with score 4 and reasoning."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = '{"score": 4, "reasoning": "Code is correct with minor improvements possible."}'
    return response


@pytest.fixture
def mock_llm_response_high_score() -> MagicMock:
    """Create a mock LLM response with perfect score."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = '{"score": 5, "reasoning": "Excellent implementation."}'
    return response


@pytest.fixture
def mock_llm_response_low_score() -> MagicMock:
    """Create a mock LLM response with low score."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = '{"score": 2, "reasoning": "Code has significant issues."}'
    return response


@pytest.fixture
def mock_llm_response_invalid_json() -> MagicMock:
    """Create a mock LLM response with invalid JSON."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "This is not valid JSON"
    return response


# ---------------------------------------------------------------------------
# RubricGrader tests
# ---------------------------------------------------------------------------


class TestRubricGrader:
    """Tests for the rubric-based LLM judge grader."""

    def test_satisfies_grader_protocol(self) -> None:
        grader = RubricGrader()
        assert isinstance(grader, Grader)

    def test_default_model(self) -> None:
        grader = RubricGrader()
        assert grader.model == "deepseek-chat"

    def test_default_rubric(self) -> None:
        grader = RubricGrader()
        assert "1-5" in grader.rubric
        assert "5" in grader.rubric
        assert "1" in grader.rubric

    def test_custom_model_and_rubric(self) -> None:
        custom_rubric = "Custom rubric text"
        grader = RubricGrader(model="gpt-4", rubric=custom_rubric)
        assert grader.model == "gpt-4"
        assert grader.rubric == custom_rubric

    @patch("litellm.completion")
    def test_returns_process_dimension(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert isinstance(result, GraderResult)
        assert result.dimension == ScoreDimension.PROCESS

    @patch("litellm.completion")
    def test_score_in_valid_range(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert 0.0 <= result.score <= 1.0

    @patch("litellm.completion")
    def test_score_normalization(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        # Score 4 out of 5 should be 0.8
        assert result.score == pytest.approx(0.8)

    @patch("litellm.completion")
    def test_details_contain_reasoning(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert "reasoning" in result.details
        assert len(result.details["reasoning"]) > 0

    @patch("litellm.completion")
    def test_details_contain_raw_score(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert "raw_score" in result.details
        assert result.details["raw_score"] == 4

    @patch("litellm.completion")
    def test_details_contain_model(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert "model" in result.details
        assert result.details["model"] == "deepseek-chat"

    @patch("litellm.completion")
    def test_high_score_normalization(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response_high_score: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response_high_score
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert result.score == pytest.approx(1.0)

    @patch("litellm.completion")
    def test_low_score_normalization(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response_low_score: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response_low_score
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert result.score == pytest.approx(0.4)

    @patch("litellm.completion")
    def test_llm_call_failure_returns_zero(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
    ) -> None:
        mock_completion.side_effect = Exception("API error")
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert result.score == 0.0
        assert result.dimension == ScoreDimension.PROCESS
        assert "error" in result.details

    @patch("litellm.completion")
    def test_invalid_json_response_returns_zero(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response_invalid_json: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response_invalid_json
        grader = RubricGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert result.score == 0.0
        assert "error" in result.details
        assert "raw_response" in result.details

    @patch("litellm.completion")
    def test_missing_description_and_output(
        self,
        mock_completion: MagicMock,
        _agent_config: AgentConfig,
        mock_llm_response: MagicMock,
    ) -> None:
        """Grader handles missing description and output gracefully."""
        mock_completion.return_value = mock_llm_response
        task = Task(
            task_id="test-empty",
            source=TaskSource.CUSTOM,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.EASY,
            language="python",
            input={},
            ground_truth={},
        )
        trial = Trial(
            trial_id="trial-empty",
            task_id="test-empty",
            agent_config=_agent_config,
            outcome={},
        )
        grader = RubricGrader()
        result = grader.grade(task, trial)
        assert isinstance(result, GraderResult)
        assert result.dimension == ScoreDimension.PROCESS

    @patch("litellm.completion")
    def test_llm_called_with_correct_messages(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = RubricGrader()
        grader.grade(sample_task, trial_with_output)
        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args
        assert call_kwargs.kwargs["model"] == "deepseek-chat"
        assert call_kwargs.kwargs["temperature"] == 0.0
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


# ---------------------------------------------------------------------------
# ReasoningGrader tests
# ---------------------------------------------------------------------------


class TestReasoningGrader:
    """Tests for the reasoning quality LLM judge grader."""

    def test_satisfies_grader_protocol(self) -> None:
        grader = ReasoningGrader()
        assert isinstance(grader, Grader)

    def test_default_model(self) -> None:
        grader = ReasoningGrader()
        assert grader.model == "deepseek-chat"

    @patch("litellm.completion")
    def test_returns_process_dimension(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert isinstance(result, GraderResult)
        assert result.dimension == ScoreDimension.PROCESS

    @patch("litellm.completion")
    def test_score_in_valid_range(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert 0.0 <= result.score <= 1.0

    @patch("litellm.completion")
    def test_score_normalization(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert result.score == pytest.approx(0.8)

    @patch("litellm.completion")
    def test_details_contain_reasoning(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert "reasoning" in result.details
        assert len(result.details["reasoning"]) > 0

    @patch("litellm.completion")
    def test_details_contain_step_count(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert "step_count" in result.details
        assert result.details["step_count"] == 3

    @patch("litellm.completion")
    def test_details_contain_model(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert "model" in result.details
        assert result.details["model"] == "deepseek-chat"

    def test_missing_reasoning_steps_returns_zero(
        self,
        sample_task: Task,
        trial_without_reasoning: Trial,
    ) -> None:
        """When no reasoning steps are present, score is 0 without LLM call."""
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial_without_reasoning)
        assert result.score == 0.0
        assert result.dimension == ScoreDimension.PROCESS
        assert "error" in result.details
        assert result.details["error"] == "no reasoning steps found"

    def test_empty_reasoning_steps_returns_zero(
        self,
        sample_task: Task,
        _agent_config: AgentConfig,
    ) -> None:
        """Empty reasoning steps list also triggers the no-reasoning path."""
        trial = Trial(
            trial_id="trial-empty-steps",
            task_id="test-001",
            agent_config=_agent_config,
            outcome={
                "output": "some output",
                "reasoning_steps": [],
            },
        )
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial)
        assert result.score == 0.0
        assert "error" in result.details

    @patch("litellm.completion")
    def test_llm_call_failure_returns_zero(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
    ) -> None:
        mock_completion.side_effect = Exception("API error")
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert result.score == 0.0
        assert result.dimension == ScoreDimension.PROCESS
        assert "error" in result.details

    @patch("litellm.completion")
    def test_invalid_json_response_returns_zero(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response_invalid_json: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response_invalid_json
        grader = ReasoningGrader()
        result = grader.grade(sample_task, trial_with_output)
        assert result.score == 0.0
        assert "error" in result.details
        assert "raw_response" in result.details

    @patch("litellm.completion")
    def test_llm_called_with_formatted_steps(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = ReasoningGrader()
        grader.grade(sample_task, trial_with_output)
        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args
        messages = call_kwargs.kwargs["messages"]
        user_content = messages[1]["content"]
        # Verify the reasoning steps are formatted with step numbers
        assert "Step 1:" in user_content
        assert "Step 2:" in user_content
        assert "Step 3:" in user_content

    @patch("litellm.completion")
    def test_custom_model(
        self,
        mock_completion: MagicMock,
        sample_task: Task,
        trial_with_output: Trial,
        mock_llm_response: MagicMock,
    ) -> None:
        mock_completion.return_value = mock_llm_response
        grader = ReasoningGrader(model="gpt-4")
        result = grader.grade(sample_task, trial_with_output)
        assert result.details["model"] == "gpt-4"
        call_kwargs = mock_completion.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4"
