"""Tests for the evolution framework — ForwardPass, ValidationGate, EditBuffer.

Covers the three core components of the SkillOpt self-evolution cycle:
- ForwardPass: run agent on dataset, collect Trajectories
- ValidationGate: compare candidate vs baseline, gate on improvement
- EditBuffer: accumulate rejected/accepted edits, surface patterns

Uses MockAgent, mock harness, and sample fixtures. No Docker or LLM calls.
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
from codepulse.evolve.buffer import EditBuffer
from codepulse.evolve.forward import ForwardPass, Trajectory, _compute_avg_scores
from codepulse.evolve.gate import ValidationGate
from codepulse.evolve.prompt_edit import EditType, PromptEdit, RejectedEdit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_tasks() -> list[Task]:
    """Three sample tasks for testing."""
    return [
        Task(
            task_id=f"task-{i}",
            source=TaskSource.CUSTOM,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.EASY,
            language="python",
            input={"description": f"Task {i}"},
            ground_truth={"expected": f"solution {i}"},
        )
        for i in range(3)
    ]


@pytest.fixture
def mock_harness() -> MagicMock:
    """Mock EvaluationHarness."""
    return MagicMock()


@pytest.fixture
def mock_agent() -> MagicMock:
    """Mock Agent satisfying the Agent Protocol."""
    agent = MagicMock()
    agent.name = "test-agent"
    agent.model = "test-model"
    return agent


@pytest.fixture
def sample_edit() -> PromptEdit:
    """A single sample PromptEdit."""
    return PromptEdit(
        edit_id="edit-001",
        edit_type=EditType.APPEND,
        target_section="system_prompt",
        content="Be more careful with edge cases.",
        reasoning="Agent missed edge case in task-0.",
        confidence=0.8,
    )


@pytest.fixture
def another_edit() -> PromptEdit:
    """A second sample PromptEdit with a different edit_type."""
    return PromptEdit(
        edit_id="edit-002",
        edit_type=EditType.REPLACE,
        target_section="constraints",
        content="Always validate inputs.",
        reasoning="Agent failed input validation.",
        confidence=0.7,
    )


@pytest.fixture
def third_edit() -> PromptEdit:
    """A third sample PromptEdit (same type as sample_edit)."""
    return PromptEdit(
        edit_id="edit-003",
        edit_type=EditType.APPEND,
        target_section="examples",
        content="Add edge case example.",
        reasoning="Need more examples.",
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trial(
    task_id: str,
    scores: dict[str, float],
    success: bool = False,
    trial_id: str = "trial-0",
) -> Trial:
    """Build a Trial with the given scores and success flag."""
    return Trial(
        trial_id=trial_id,
        task_id=task_id,
        agent_config=AgentConfig(name="test", model="test"),
        scores=scores,
        success=success,
    )


def _make_trajectory(
    task: Task,
    trials: list[Trial],
    success: bool | None = None,
    avg_scores: dict[str, float] | None = None,
) -> Trajectory:
    """Build a Trajectory, auto-computing success and avg_scores if omitted."""
    if success is None:
        success = all(t.success for t in trials)
    if avg_scores is None:
        avg_scores = _compute_avg_scores(trials)
    return Trajectory(
        task=task,
        trials=trials,
        success=success,
        avg_scores=avg_scores,
    )


# ===================================================================
# _compute_avg_scores tests
# ===================================================================


class TestComputeAvgScores:
    """Test the _compute_avg_scores helper."""

    def test_empty_trials(self) -> None:
        """Empty trial list returns empty dict."""
        assert _compute_avg_scores([]) == {}

    def test_single_trial(self) -> None:
        """Single trial: avg equals the trial's scores."""
        trial = _make_trial("t-0", {"functional": 0.8, "process": 0.6})
        result = _compute_avg_scores([trial])
        assert result == {"functional": 0.8, "process": 0.6}

    def test_multiple_trials_same_dimensions(self) -> None:
        """Average is computed correctly across trials with same dimensions."""
        trials = [
            _make_trial("t-0", {"functional": 0.8}, trial_id="r0"),
            _make_trial("t-0", {"functional": 0.6}, trial_id="r1"),
            _make_trial("t-0", {"functional": 1.0}, trial_id="r2"),
        ]
        result = _compute_avg_scores(trials)
        assert result["functional"] == pytest.approx(0.8)

    def test_multiple_trials_different_dimensions(self) -> None:
        """Dimensions present in only some trials are averaged over available."""
        trials = [
            _make_trial("t-0", {"functional": 0.8, "process": 0.6}, trial_id="r0"),
            _make_trial("t-0", {"functional": 0.4}, trial_id="r1"),
        ]
        result = _compute_avg_scores(trials)
        # functional: (0.8 + 0.4) / 2 = 0.6
        assert result["functional"] == pytest.approx(0.6)
        # process: 0.6 / 1 = 0.6 (only one trial has it)
        assert result["process"] == pytest.approx(0.6)


# ===================================================================
# ForwardPass tests
# ===================================================================


class TestForwardPassRun:
    """Test ForwardPass.run()."""

    def test_returns_list(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """run() must return a list."""
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        mock_harness.run_task.return_value = [
            _make_trial("task-0", {"functional": 0.5}, trial_id="r0")
        ]
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=1)
        assert isinstance(result, list)

    def test_returns_list_of_trajectory(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """Each element must be a Trajectory instance."""
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        mock_harness.run_task.return_value = [
            _make_trial("task-0", {"functional": 0.5}, trial_id="r0")
        ]
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=1)
        assert len(result) > 0
        for item in result:
            assert isinstance(item, Trajectory)

    def test_one_trajectory_per_task(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """Must produce exactly one Trajectory per task in the dataset."""
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        mock_harness.run_task.return_value = [
            _make_trial("task-0", {"functional": 0.5}, trial_id="r0")
        ]
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=1)
        assert len(result) == len(sample_tasks)

    def test_trajectory_has_task(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """Each Trajectory.task must correspond to the original task."""
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        mock_harness.run_task.return_value = [
            _make_trial("task-0", {"functional": 0.5}, trial_id="r0")
        ]
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=1)
        for traj, task in zip(result, sample_tasks, strict=True):
            assert traj.task is task

    def test_trajectory_has_trials(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """Each Trajectory.trials must contain the trials returned by harness."""
        trials = [
            _make_trial("task-0", {"functional": 0.5}, trial_id="r0"),
            _make_trial("task-0", {"functional": 0.6}, trial_id="r1"),
        ]
        mock_harness.run_task.return_value = trials
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=2)
        for traj in result:
            assert traj.trials is trials

    def test_success_true_when_all_trials_passed(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """Trajectory.success must be True when every trial succeeded."""
        trials = [
            _make_trial("task-0", {"functional": 1.0}, success=True, trial_id="r0"),
            _make_trial("task-0", {"functional": 1.0}, success=True, trial_id="r1"),
        ]
        mock_harness.run_task.return_value = trials
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=2)
        for traj in result:
            assert traj.success is True

    def test_success_false_when_any_trial_fails(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """Trajectory.success must be False when even one trial fails."""
        trials = [
            _make_trial("task-0", {"functional": 1.0}, success=True, trial_id="r0"),
            _make_trial("task-0", {"functional": 0.0}, success=False, trial_id="r1"),
        ]
        mock_harness.run_task.return_value = trials
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=2)
        for traj in result:
            assert traj.success is False

    def test_success_false_when_all_trials_fail(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """Trajectory.success is False when all trials fail."""
        trials = [
            _make_trial("task-0", {"functional": 0.0}, success=False, trial_id="r0"),
            _make_trial("task-0", {"functional": 0.0}, success=False, trial_id="r1"),
        ]
        mock_harness.run_task.return_value = trials
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=2)
        for traj in result:
            assert traj.success is False

    def test_avg_scores_has_correct_keys(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """avg_scores keys must match the score dimension names from trials."""
        trials = [
            _make_trial(
                "task-0",
                {"functional": 0.8, "process": 0.6, "robustness": 0.9},
                trial_id="r0",
            ),
            _make_trial(
                "task-0",
                {"functional": 0.7, "process": 0.5, "robustness": 0.8},
                trial_id="r1",
            ),
        ]
        mock_harness.run_task.return_value = trials
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=2)
        for traj in result:
            assert set(traj.avg_scores.keys()) == {
                "functional",
                "process",
                "robustness",
            }

    def test_avg_scores_values_are_averaged(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """avg_scores values must be the mean of per-trial scores."""
        trials = [
            _make_trial("task-0", {"functional": 0.8}, trial_id="r0"),
            _make_trial("task-0", {"functional": 0.6}, trial_id="r1"),
        ]
        mock_harness.run_task.return_value = trials
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=2)
        for traj in result:
            assert traj.avg_scores["functional"] == pytest.approx(0.7)

    def test_passes_n_trials_to_harness(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """ForwardPass must pass n_trials through to harness.run_task()."""
        mock_harness.run_task.return_value = [
            _make_trial("task-0", {"functional": 0.5}, trial_id="r0")
        ]
        forward = ForwardPass(harness=mock_harness, dataset=sample_tasks)
        mock_agent = MagicMock(name="agent", model="m")
        forward.run(mock_agent, n_trials=7)

        for call_args in mock_harness.run_task.call_args_list:
            assert call_args.args[2] == 7  # third positional arg is n_trials

    def test_empty_dataset(
        self, mock_harness: MagicMock
    ) -> None:
        """Empty dataset returns an empty trajectory list."""
        forward = ForwardPass(harness=mock_harness, dataset=[])
        result = forward.run(MagicMock(name="agent", model="m"), n_trials=1)
        assert result == []


# ===================================================================
# ValidationGate tests (beyond existing test_validation_gate.py)
# ===================================================================


class TestValidationGateScores:
    """Test that validate() returns a dict with all required score fields."""

    def test_validate_returns_dict_with_scores(
        self,
        mock_harness: MagicMock,
        sample_tasks: list[Task],
        mock_agent: MagicMock,
    ) -> None:
        """Return dict must contain candidate_score and baseline_score."""
        c_trajs = [
            _make_trajectory(t, [_make_trial(t.task_id, {"functional": 0.8}, trial_id="r0")])
            for t in sample_tasks
        ]
        b_trajs = [
            _make_trajectory(t, [_make_trial(t.task_id, {"functional": 0.5}, trial_id="r0")])
            for t in sample_tasks
        ]

        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)
        with patch("codepulse.evolve.gate.ForwardPass") as mock_fp:
            mock_fp.return_value.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=1)

        assert "candidate_score" in result
        assert "baseline_score" in result
        assert isinstance(result["candidate_score"], float)
        assert isinstance(result["baseline_score"], float)

    def test_improved_true_when_candidate_better(
        self,
        mock_harness: MagicMock,
        sample_tasks: list[Task],
        mock_agent: MagicMock,
    ) -> None:
        """improved is True when candidate aggregate score > baseline."""
        c_trajs = [
            _make_trajectory(
                t,
                [_make_trial(t.task_id, {"functional": 1.0}, trial_id="r0")],
                avg_scores={"functional": 1.0},
            )
            for t in sample_tasks
        ]
        b_trajs = [
            _make_trajectory(
                t,
                [_make_trial(t.task_id, {"functional": 0.3}, trial_id="r0")],
                avg_scores={"functional": 0.3},
            )
            for t in sample_tasks
        ]

        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)
        with patch("codepulse.evolve.gate.ForwardPass") as mock_fp:
            mock_fp.return_value.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=1)

        assert result["improved"] is True

    def test_improvement_rate_calculated_correctly(
        self,
        mock_harness: MagicMock,
        mock_agent: MagicMock,
    ) -> None:
        """improvement_rate = (tasks where candidate > baseline) / total tasks."""
        tasks = [
            Task(
                task_id=f"t{i}",
                source=TaskSource.CUSTOM,
                category=TaskCategory.BUG_FIX,
                difficulty=Difficulty.EASY,
                language="python",
                input={"description": f"Task {i}"},
                ground_truth={"expected": f"solution {i}"},
            )
            for i in range(4)
        ]
        # t0: candidate better, t1: baseline better, t2: equal, t3: candidate better
        c_trajs = [
            _make_trajectory(tasks[0], [], avg_scores={"functional": 1.0}),
            _make_trajectory(tasks[1], [], avg_scores={"functional": 0.2}),
            _make_trajectory(tasks[2], [], avg_scores={"functional": 0.5}),
            _make_trajectory(tasks[3], [], avg_scores={"functional": 0.9}),
        ]
        b_trajs = [
            _make_trajectory(tasks[0], [], avg_scores={"functional": 0.5}),
            _make_trajectory(tasks[1], [], avg_scores={"functional": 0.8}),
            _make_trajectory(tasks[2], [], avg_scores={"functional": 0.5}),
            _make_trajectory(tasks[3], [], avg_scores={"functional": 0.4}),
        ]

        gate = ValidationGate(harness=mock_harness, dataset=tasks)
        with patch("codepulse.evolve.gate.ForwardPass") as mock_fp:
            mock_fp.return_value.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=1)

        # 2 out of 4 tasks improved
        assert result["improvement_rate"] == pytest.approx(0.5)

    def test_regression_rate_calculated_correctly(
        self,
        mock_harness: MagicMock,
        mock_agent: MagicMock,
    ) -> None:
        """regression_rate = (tasks where candidate < baseline) / total tasks."""
        tasks = [
            Task(
                task_id=f"t{i}",
                source=TaskSource.CUSTOM,
                category=TaskCategory.BUG_FIX,
                difficulty=Difficulty.EASY,
                language="python",
                input={"description": f"Task {i}"},
                ground_truth={"expected": f"solution {i}"},
            )
            for i in range(4)
        ]
        c_trajs = [
            _make_trajectory(tasks[0], [], avg_scores={"functional": 1.0}),
            _make_trajectory(tasks[1], [], avg_scores={"functional": 0.2}),
            _make_trajectory(tasks[2], [], avg_scores={"functional": 0.5}),
            _make_trajectory(tasks[3], [], avg_scores={"functional": 0.9}),
        ]
        b_trajs = [
            _make_trajectory(tasks[0], [], avg_scores={"functional": 0.5}),
            _make_trajectory(tasks[1], [], avg_scores={"functional": 0.8}),
            _make_trajectory(tasks[2], [], avg_scores={"functional": 0.5}),
            _make_trajectory(tasks[3], [], avg_scores={"functional": 0.4}),
        ]

        gate = ValidationGate(harness=mock_harness, dataset=tasks)
        with patch("codepulse.evolve.gate.ForwardPass") as mock_fp:
            mock_fp.return_value.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=1)

        # 1 out of 4 tasks regressed (t1)
        assert result["regression_rate"] == pytest.approx(0.25)


# ===================================================================
# EditBuffer tests
# ===================================================================


class TestEditBufferRejected:
    """Test EditBuffer.add_rejected() and retrieval."""

    def test_add_rejected_stores_rejected_edit(
        self, sample_edit: PromptEdit
    ) -> None:
        """add_rejected() must create a RejectedEdit in the buffer."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-2.5, reason="caused regression")

        rejected = buf.get_negative_signals()
        assert len(rejected) == 1
        assert isinstance(rejected[0], RejectedEdit)
        assert rejected[0].edit is sample_edit
        assert rejected[0].score_delta == -2.5
        assert rejected[0].rejection_reason == "caused regression"

    def test_add_rejected_multiple(
        self, sample_edit: PromptEdit, another_edit: PromptEdit
    ) -> None:
        """Multiple rejected edits are stored in order."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-1.0, reason="r1")
        buf.add_rejected(another_edit, score_delta=-3.0, reason="r2")

        rejected = buf.get_negative_signals()
        assert len(rejected) == 2
        assert rejected[0].edit is sample_edit
        assert rejected[1].edit is another_edit


class TestEditBufferAccepted:
    """Test EditBuffer.add_accepted() and retrieval."""

    def test_add_accepted_stores_edit_and_delta(
        self, sample_edit: PromptEdit
    ) -> None:
        """add_accepted() must store the edit and its score_delta."""
        buf = EditBuffer()
        buf.add_accepted(sample_edit, score_delta=3.0)

        stats = buf.get_stats()
        assert stats["accepted_count"] == 1

    def test_add_accepted_multiple(
        self, sample_edit: PromptEdit, another_edit: PromptEdit
    ) -> None:
        """Multiple accepted edits increment the accepted_count."""
        buf = EditBuffer()
        buf.add_accepted(sample_edit, score_delta=2.0)
        buf.add_accepted(another_edit, score_delta=1.5)

        stats = buf.get_stats()
        assert stats["accepted_count"] == 2


class TestEditBufferNegativeSignals:
    """Test EditBuffer.get_negative_signals()."""

    def test_returns_empty_list_when_no_rejected(self) -> None:
        """Buffer with no rejections returns empty list."""
        buf = EditBuffer()
        assert buf.get_negative_signals() == []

    def test_returns_negative_deltas(
        self, sample_edit: PromptEdit, another_edit: PromptEdit
    ) -> None:
        """All returned RejectedEdit records have negative score_delta."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-2.0, reason="r1")
        buf.add_rejected(another_edit, score_delta=-5.0, reason="r2")

        signals = buf.get_negative_signals()
        for signal in signals:
            assert signal.score_delta < 0

    def test_does_not_include_accepted(
        self, sample_edit: PromptEdit, another_edit: PromptEdit
    ) -> None:
        """get_negative_signals() returns only rejected edits, not accepted."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-1.0, reason="bad")
        buf.add_accepted(another_edit, score_delta=2.0)

        signals = buf.get_negative_signals()
        assert len(signals) == 1
        assert signals[0].edit is sample_edit


class TestEditBufferPatterns:
    """Test EditBuffer.get_patterns()."""

    def test_groups_by_edit_type(
        self, sample_edit: PromptEdit, another_edit: PromptEdit
    ) -> None:
        """Rejected edits must be grouped by their edit_type."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-1.0, reason="r1")
        buf.add_rejected(another_edit, score_delta=-2.0, reason="r2")

        patterns = buf.get_patterns()
        # sample_edit has edit_type APPEND, another_edit has REPLACE
        assert EditType.APPEND in patterns
        assert EditType.REPLACE in patterns
        assert len(patterns[EditType.APPEND]) == 1
        assert len(patterns[EditType.REPLACE]) == 1

    def test_same_type_grouped_together(
        self, sample_edit: PromptEdit, third_edit: PromptEdit
    ) -> None:
        """Multiple rejected edits of the same type end up in one group."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-1.0, reason="r1")
        buf.add_rejected(third_edit, score_delta=-2.0, reason="r2")

        patterns = buf.get_patterns()
        # Both are APPEND type
        assert len(patterns) == 1
        assert EditType.APPEND in patterns
        assert len(patterns[EditType.APPEND]) == 2

    def test_empty_buffer_returns_empty_dict(self) -> None:
        """No rejections means empty patterns dict."""
        buf = EditBuffer()
        assert buf.get_patterns() == {}

    def test_accepted_edits_not_in_patterns(
        self, sample_edit: PromptEdit, another_edit: PromptEdit
    ) -> None:
        """Only rejected edits appear in patterns, not accepted ones."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-1.0, reason="bad")
        buf.add_accepted(another_edit, score_delta=2.0)

        patterns = buf.get_patterns()
        # another_edit is REPLACE type, but it was accepted so should not appear
        assert EditType.REPLACE not in patterns


class TestEditBufferStats:
    """Test EditBuffer.get_stats()."""

    def test_empty_buffer(self) -> None:
        """Fresh buffer has all zero counts and zero averages."""
        buf = EditBuffer()
        stats = buf.get_stats()
        assert stats["rejected_count"] == 0
        assert stats["accepted_count"] == 0
        assert stats["avg_rejected_delta"] == 0.0
        assert stats["avg_accepted_delta"] == 0.0

    def test_counts_after_adding(
        self, sample_edit: PromptEdit, another_edit: PromptEdit
    ) -> None:
        """Counts must reflect the number of rejected and accepted edits."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-1.0, reason="r1")
        buf.add_rejected(another_edit, score_delta=-3.0, reason="r2")
        buf.add_accepted(sample_edit, score_delta=2.0)

        stats = buf.get_stats()
        assert stats["rejected_count"] == 2
        assert stats["accepted_count"] == 1

    def test_avg_rejected_delta(
        self, sample_edit: PromptEdit, another_edit: PromptEdit
    ) -> None:
        """avg_rejected_delta is the mean of all rejected score_deltas."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-2.0, reason="r1")
        buf.add_rejected(another_edit, score_delta=-4.0, reason="r2")

        stats = buf.get_stats()
        assert stats["avg_rejected_delta"] == pytest.approx(-3.0)

    def test_avg_accepted_delta(
        self, sample_edit: PromptEdit, another_edit: PromptEdit
    ) -> None:
        """avg_accepted_delta is the mean of all accepted score_deltas."""
        buf = EditBuffer()
        buf.add_accepted(sample_edit, score_delta=2.0)
        buf.add_accepted(another_edit, score_delta=4.0)

        stats = buf.get_stats()
        assert stats["avg_accepted_delta"] == pytest.approx(3.0)

    def test_stats_only_rejected(
        self, sample_edit: PromptEdit
    ) -> None:
        """Stats with only rejected edits: accepted count is 0, avg is 0."""
        buf = EditBuffer()
        buf.add_rejected(sample_edit, score_delta=-5.0, reason="bad")

        stats = buf.get_stats()
        assert stats["rejected_count"] == 1
        assert stats["accepted_count"] == 0
        assert stats["avg_accepted_delta"] == 0.0

    def test_stats_only_accepted(
        self, sample_edit: PromptEdit
    ) -> None:
        """Stats with only accepted edits: rejected count is 0, avg is 0."""
        buf = EditBuffer()
        buf.add_accepted(sample_edit, score_delta=3.0)

        stats = buf.get_stats()
        assert stats["rejected_count"] == 0
        assert stats["accepted_count"] == 1
        assert stats["avg_rejected_delta"] == 0.0
