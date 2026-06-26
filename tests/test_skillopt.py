"""Tests for SkillOpt — 自进化主循环。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codepulse.data.models import (
    Difficulty,
    Task,
    TaskCategory,
    TaskSource,
)
from codepulse.data.protocols import GraderResult
from codepulse.env.mock_agent import MockAgent
from codepulse.eval.harness import EvaluationHarness
from codepulse.eval.scoring import ScoreDimension
from codepulse.evolve.skillopt import EvolutionResult, SkillOpt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_task(sample_task_data: dict) -> Task:
    """从 conftest sample_task_data 构造 Task 实例。"""
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
def mock_sandbox() -> MagicMock:
    """Mock SandboxManager。"""
    return MagicMock()


@pytest.fixture
def passing_graders() -> list[MagicMock]:
    """五个各评一个维度且都给满分的 mock Grader 列表。"""
    graders = []
    for dim in ScoreDimension:
        grader = MagicMock()
        grader.name = f"pass-{dim.value}"
        grader.grade = MagicMock(
            return_value=GraderResult(dimension=dim, score=1.0, details={})
        )
        graders.append(grader)
    return graders


@pytest.fixture
def harness(mock_sandbox: MagicMock, passing_graders: list[MagicMock]) -> EvaluationHarness:
    """带五个满分 Grader 的 EvaluationHarness。"""
    return EvaluationHarness(sandbox=mock_sandbox, graders=passing_graders)


@pytest.fixture
def baseline_agent() -> MockAgent:
    """基线 Agent。"""
    return MockAgent(name="baseline", model="model-v1")


@pytest.fixture
def candidate_agent() -> MockAgent:
    """候选 Agent。"""
    return MockAgent(name="candidate", model="model-v2")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSkillOptInit:
    """测试 SkillOpt 初始化。"""

    def test_init_stores_harness(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
    ) -> None:
        """harness 属性必须保存传入的 harness 实例。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        assert opt.harness is harness

    def test_init_stores_dataset(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
    ) -> None:
        """dataset 属性必须保存传入的数据集。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        assert opt.dataset == [sample_task]

    def test_init_creates_buffer(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
    ) -> None:
        """初始化时必须创建 EditBuffer。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        assert opt.buffer is not None

    def test_init_creates_attribution(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
    ) -> None:
        """初始化时必须创建 SampleAttribution。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        assert opt.attribution is not None


class TestSkillOptEvolve:
    """测试 SkillOpt.evolve()。"""

    def test_evolve_returns_list(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
        baseline_agent: MockAgent,
        candidate_agent: MockAgent,
    ) -> None:
        """evolve() 必须返回列表。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        results = opt.evolve(baseline_agent, candidate_agent, n_epochs=1, n_trials=1)
        assert isinstance(results, list)

    def test_evolve_returns_evolution_results(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
        baseline_agent: MockAgent,
        candidate_agent: MockAgent,
    ) -> None:
        """evolve() 返回的每个元素必须是 EvolutionResult。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        results = opt.evolve(baseline_agent, candidate_agent, n_epochs=1, n_trials=1)
        assert len(results) == 1
        assert isinstance(results[0], EvolutionResult)

    def test_evolve_n_epochs(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
        baseline_agent: MockAgent,
        candidate_agent: MockAgent,
    ) -> None:
        """evolve() 必须执行指定轮数。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        results = opt.evolve(baseline_agent, candidate_agent, n_epochs=3, n_trials=1)
        assert len(results) == 3

    def test_evolve_result_has_epoch(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
        baseline_agent: MockAgent,
        candidate_agent: MockAgent,
    ) -> None:
        """EvolutionResult 必须包含 epoch。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        results = opt.evolve(baseline_agent, candidate_agent, n_epochs=1, n_trials=1)
        assert results[0].epoch == 0

    def test_evolve_result_has_scores(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
        baseline_agent: MockAgent,
        candidate_agent: MockAgent,
    ) -> None:
        """EvolutionResult 必须包含分数。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        results = opt.evolve(baseline_agent, candidate_agent, n_epochs=1, n_trials=1)
        assert "baseline_score" in results[0].__dict__
        assert "candidate_score" in results[0].__dict__

    def test_evolve_result_has_attribution(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
        baseline_agent: MockAgent,
        candidate_agent: MockAgent,
    ) -> None:
        """EvolutionResult 必须包含归因报告。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        results = opt.evolve(baseline_agent, candidate_agent, n_epochs=1, n_trials=1)
        report = results[0].attribution_report
        assert "improvements" in report
        assert "regressions" in report


class TestSkillOptBuffer:
    """测试 SkillOpt 缓冲区。"""

    def test_get_buffer_stats_returns_dict(
        self,
        harness: EvaluationHarness,
        sample_task: Task,
    ) -> None:
        """get_buffer_stats() 必须返回字典。"""
        opt = SkillOpt(harness=harness, dataset=[sample_task])
        stats = opt.get_buffer_stats()
        assert isinstance(stats, dict)
