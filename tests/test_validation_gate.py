"""Validation Gate 测试。

覆盖初始化、改进/退化/持平场景、边界条件和空数据集。
使用 mock ForwardPass 和 mock harness，无需 Docker 和 LLM。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codepulse.data.models import (
    Difficulty,
    Task,
    TaskCategory,
    TaskSource,
)
from codepulse.evolve.forward import Trajectory
from codepulse.evolve.gate import ValidationGate, _to_dimension_scores

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_tasks() -> list[Task]:
    """构造两个测试任务。"""
    return [
        Task(
            task_id=f"task-{i}",
            source=TaskSource.CUSTOM,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.EASY,
            language="python",
            input={"description": f"Task {i}"},
            ground_truth={"expected_output": f"solution {i}"},
        )
        for i in range(2)
    ]


@pytest.fixture
def mock_harness() -> MagicMock:
    """Mock EvaluationHarness。"""
    return MagicMock()


@pytest.fixture
def mock_agent() -> MagicMock:
    """Mock Agent，满足 Agent Protocol。"""
    agent = MagicMock()
    agent.name = "test-agent"
    agent.model = "test-model"
    return agent


def _make_trajectory(
    task: Task, avg_scores: dict[str, float]
) -> Trajectory:
    """构造带有指定平均分的 Trajectory。"""
    return Trajectory(
        task=task,
        trials=[],
        success=False,
        avg_scores=avg_scores,
    )


# ---------------------------------------------------------------------------
# _to_dimension_scores tests
# ---------------------------------------------------------------------------


class TestToDimensionScores:
    """测试 _to_dimension_scores 辅助函数。"""

    def test_valid_keys(self) -> None:
        """有效维度字符串应正确转换为 ScoreDimension。"""
        from codepulse.eval.scoring import ScoreDimension

        raw = {"functional": 0.8, "process": 0.6}
        result = _to_dimension_scores(raw)
        assert result[ScoreDimension.FUNCTIONAL] == 0.8
        assert result[ScoreDimension.PROCESS] == 0.6

    def test_all_dimensions(self) -> None:
        """五个维度全部转换。"""
        from codepulse.eval.scoring import ScoreDimension

        raw = {dim.value: 0.5 for dim in ScoreDimension}
        result = _to_dimension_scores(raw)
        assert len(result) == 5
        for dim in ScoreDimension:
            assert dim in result

    def test_unknown_key_skipped(self) -> None:
        """未知维度键应被跳过。"""
        raw = {"functional": 0.9, "unknown_dim": 0.5}
        result = _to_dimension_scores(raw)
        assert "unknown_dim" not in result
        assert len(result) == 1

    def test_empty_dict(self) -> None:
        """空字典返回空字典。"""
        assert _to_dimension_scores({}) == {}


# ---------------------------------------------------------------------------
# ValidationGate 初始化测试
# ---------------------------------------------------------------------------


class TestValidationGateInit:
    """测试 ValidationGate 初始化。"""

    def test_stores_harness(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """harness 属性必须保存传入的实例。"""
        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)
        assert gate.harness is mock_harness

    def test_stores_dataset(
        self, mock_harness: MagicMock, sample_tasks: list[Task]
    ) -> None:
        """dataset 属性必须保存传入的列表。"""
        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)
        assert gate.dataset is sample_tasks

    def test_empty_dataset(self, mock_harness: MagicMock) -> None:
        """应支持空数据集。"""
        gate = ValidationGate(harness=mock_harness, dataset=[])
        assert gate.dataset == []


# ---------------------------------------------------------------------------
# ValidationGate.validate 测试
# ---------------------------------------------------------------------------


class TestValidationGateValidate:
    """测试 ValidationGate.validate()。"""

    def test_candidate_better_than_baseline(
        self,
        mock_harness: MagicMock,
        sample_tasks: list[Task],
        mock_agent: MagicMock,
    ) -> None:
        """候选分数高于基线时 improved=True。"""
        c_trajs = [
            _make_trajectory(t, {"functional": 1.0}) for t in sample_tasks
        ]
        b_trajs = [
            _make_trajectory(t, {"functional": 0.5}) for t in sample_tasks
        ]

        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)

        with patch(
            "codepulse.evolve.gate.ForwardPass"
        ) as mock_fp:
            instance = mock_fp.return_value
            instance.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=2)

        assert result["improved"] is True
        assert result["candidate_score"] > result["baseline_score"]
        assert result["improvement_rate"] == 1.0
        assert result["regression_rate"] == 0.0

    def test_baseline_better_than_candidate(
        self,
        mock_harness: MagicMock,
        sample_tasks: list[Task],
        mock_agent: MagicMock,
    ) -> None:
        """候选分数低于基线时 improved=False。"""
        c_trajs = [
            _make_trajectory(t, {"functional": 0.3}) for t in sample_tasks
        ]
        b_trajs = [
            _make_trajectory(t, {"functional": 0.8}) for t in sample_tasks
        ]

        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)

        with patch(
            "codepulse.evolve.gate.ForwardPass"
        ) as mock_fp:
            instance = mock_fp.return_value
            instance.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=2)

        assert result["improved"] is False
        assert result["candidate_score"] < result["baseline_score"]
        assert result["improvement_rate"] == 0.0
        assert result["regression_rate"] == 1.0

    def test_equal_scores(
        self,
        mock_harness: MagicMock,
        sample_tasks: list[Task],
        mock_agent: MagicMock,
    ) -> None:
        """候选与基线分数相等时 improved=False，改进率和回归率均为 0。"""
        scores = {"functional": 0.7}
        c_trajs = [_make_trajectory(t, scores) for t in sample_tasks]
        b_trajs = [_make_trajectory(t, scores) for t in sample_tasks]

        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)

        with patch(
            "codepulse.evolve.gate.ForwardPass"
        ) as mock_fp:
            instance = mock_fp.return_value
            instance.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=2)

        assert result["improved"] is False
        assert result["candidate_score"] == result["baseline_score"]
        assert result["improvement_rate"] == 0.0
        assert result["regression_rate"] == 0.0

    def test_mixed_results(
        self,
        mock_harness: MagicMock,
        mock_agent: MagicMock,
    ) -> None:
        """部分任务改进、部分退化的混合场景。"""
        tasks = [
            Task(
                task_id=f"t{i}",
                source=TaskSource.CUSTOM,
                category=TaskCategory.BUG_FIX,
                difficulty=Difficulty.EASY,
                language="python",
                input={"description": f"Task {i}"},
                ground_truth={"expected_output": f"solution {i}"},
            )
            for i in range(4)
        ]
        # t0: candidate better, t1: baseline better, t2: equal, t3: candidate better
        c_trajs = [
            _make_trajectory(tasks[0], {"functional": 1.0}),
            _make_trajectory(tasks[1], {"functional": 0.3}),
            _make_trajectory(tasks[2], {"functional": 0.5}),
            _make_trajectory(tasks[3], {"functional": 0.9}),
        ]
        b_trajs = [
            _make_trajectory(tasks[0], {"functional": 0.5}),
            _make_trajectory(tasks[1], {"functional": 0.8}),
            _make_trajectory(tasks[2], {"functional": 0.5}),
            _make_trajectory(tasks[3], {"functional": 0.4}),
        ]

        gate = ValidationGate(harness=mock_harness, dataset=tasks)

        with patch(
            "codepulse.evolve.gate.ForwardPass"
        ) as mock_fp:
            instance = mock_fp.return_value
            instance.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=2)

        # t0: improved, t1: regressed, t2: equal, t3: improved
        assert result["improvement_rate"] == 0.5
        assert result["regression_rate"] == 0.25

    def test_result_contains_all_required_keys(
        self,
        mock_harness: MagicMock,
        sample_tasks: list[Task],
        mock_agent: MagicMock,
    ) -> None:
        """返回字典必须包含所有要求的键。"""
        c_trajs = [_make_trajectory(t, {"functional": 0.5}) for t in sample_tasks]
        b_trajs = [_make_trajectory(t, {"functional": 0.5}) for t in sample_tasks]

        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)

        with patch(
            "codepulse.evolve.gate.ForwardPass"
        ) as mock_fp:
            instance = mock_fp.return_value
            instance.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=2)

        assert "candidate_score" in result
        assert "baseline_score" in result
        assert "improved" in result
        assert "improvement_rate" in result
        assert "regression_rate" in result

    def test_result_types(
        self,
        mock_harness: MagicMock,
        sample_tasks: list[Task],
        mock_agent: MagicMock,
    ) -> None:
        """返回值类型必须正确。"""
        c_trajs = [_make_trajectory(t, {"functional": 0.6}) for t in sample_tasks]
        b_trajs = [_make_trajectory(t, {"functional": 0.4}) for t in sample_tasks]

        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)

        with patch(
            "codepulse.evolve.gate.ForwardPass"
        ) as mock_fp:
            instance = mock_fp.return_value
            instance.run.side_effect = [c_trajs, b_trajs]
            result = gate.validate(mock_agent, mock_agent, n_trials=2)

        assert isinstance(result["candidate_score"], float)
        assert isinstance(result["baseline_score"], float)
        assert isinstance(result["improved"], bool)
        assert isinstance(result["improvement_rate"], float)
        assert isinstance(result["regression_rate"], float)


# ---------------------------------------------------------------------------
# 空数据集测试
# ---------------------------------------------------------------------------


class TestValidationGateEmptyDataset:
    """空数据集边界条件。"""

    def test_empty_dataset_returns_zeros(
        self, mock_harness: MagicMock, mock_agent: MagicMock
    ) -> None:
        """空数据集应返回全零结果，improved=False。"""
        gate = ValidationGate(harness=mock_harness, dataset=[])

        with patch(
            "codepulse.evolve.gate.ForwardPass"
        ) as mock_fp:
            instance = mock_fp.return_value
            instance.run.return_value = []
            result = gate.validate(mock_agent, mock_agent, n_trials=2)

        assert result["candidate_score"] == 0.0
        assert result["baseline_score"] == 0.0
        assert result["improved"] is False
        assert result["improvement_rate"] == 0.0
        assert result["regression_rate"] == 0.0


def test_validation_gate_aligns_trajectories_by_task_id(
    mock_harness: MagicMock, sample_tasks: list[Task]
) -> None:
    candidate = [
        _make_trajectory(sample_tasks[0], {"functional": 0.9}),
        _make_trajectory(sample_tasks[1], {"functional": 0.1}),
    ]
    baseline = [
        _make_trajectory(sample_tasks[1], {"functional": 0.1}),
        _make_trajectory(sample_tasks[0], {"functional": 0.9}),
    ]

    result = ValidationGate(mock_harness, sample_tasks)._compare(candidate, baseline)

    assert result["improvement_rate"] == 0.0
    assert result["regression_rate"] == 0.0


# ---------------------------------------------------------------------------
# ForwardPass 调用测试
# ---------------------------------------------------------------------------


class TestForwardPassIntegration:
    """验证 ValidationGate 正确调用 ForwardPass。"""

    def test_creates_forward_pass_with_correct_args(
        self,
        mock_harness: MagicMock,
        sample_tasks: list[Task],
        mock_agent: MagicMock,
    ) -> None:
        """应使用正确的 harness 和 dataset 创建 ForwardPass。"""
        c_trajs = [_make_trajectory(t, {"functional": 0.5}) for t in sample_tasks]
        b_trajs = [_make_trajectory(t, {"functional": 0.5}) for t in sample_tasks]

        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)

        with patch(
            "codepulse.evolve.gate.ForwardPass"
        ) as mock_fp:
            instance = mock_fp.return_value
            instance.run.side_effect = [c_trajs, b_trajs]
            gate.validate(mock_agent, mock_agent, n_trials=3)

            # ForwardPass 应以 harness 和 dataset 初始化
            mock_fp.assert_called_once_with(mock_harness, sample_tasks)
            # run 应被调用两次（candidate 和 baseline）
            assert instance.run.call_count == 2

    def test_passes_n_trials_to_forward_pass(
        self,
        mock_harness: MagicMock,
        sample_tasks: list[Task],
        mock_agent: MagicMock,
    ) -> None:
        """n_trials 参数应正确传递给 ForwardPass.run()。"""
        c_trajs = [_make_trajectory(t, {"functional": 0.5}) for t in sample_tasks]
        b_trajs = [_make_trajectory(t, {"functional": 0.5}) for t in sample_tasks]

        gate = ValidationGate(harness=mock_harness, dataset=sample_tasks)

        with patch(
            "codepulse.evolve.gate.ForwardPass"
        ) as mock_fp:
            instance = mock_fp.return_value
            instance.run.side_effect = [c_trajs, b_trajs]
            gate.validate(mock_agent, mock_agent, n_trials=7)

            calls = instance.run.call_args_list
            # run(agent, n_trials) 是位置参数
            assert calls[0].args == (mock_agent, 7)
            assert calls[1].args == (mock_agent, 7)
