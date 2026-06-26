"""Tests for EvaluationHarness — 评测编排器。

覆盖初始化、任务执行、评分聚合和成功判定。
使用 MockAgent 和 mock sandbox，无需 Docker 和 LLM。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codepulse.data.models import (
    AgentConfig,
    Difficulty,
    Task,
    TaskCategory,
    TaskSource,
    Trial,
)
from codepulse.data.protocols import GraderResult
from codepulse.eval.harness import EvaluationHarness
from codepulse.eval.scoring import MAX_SCORES, PASS_THRESHOLD, ScoreDimension, aggregate_scores

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
def agent_config() -> AgentConfig:
    """测试用 Agent 配置。"""
    return AgentConfig(name="test-agent", model="test-model")


@pytest.fixture
def mock_sandbox() -> MagicMock:
    """Mock SandboxManager，避免调用真实 Docker daemon。"""
    return MagicMock()


@pytest.fixture
def passing_graders() -> list[MagicMock]:
    """五个各评一个维度且都给满分的 mock Grader 列表。

    五个维度各得 1.0 比例分 => 总分 = 100。
    """
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
def failing_graders() -> list[MagicMock]:
    """五个各评一个维度且都给零分的 mock Grader 列表。"""
    graders = []
    for dim in ScoreDimension:
        grader = MagicMock()
        grader.name = f"fail-{dim.value}"
        grader.grade = MagicMock(
            return_value=GraderResult(dimension=dim, score=0.0, details={})
        )
        graders.append(grader)
    return graders


@pytest.fixture
def single_dim_grader() -> MagicMock:
    """只评 FUNCTIONAL 维度（满分）的 mock Grader。"""
    grader = MagicMock()
    grader.name = "functional-only"
    grader.grade = MagicMock(
        return_value=GraderResult(
            dimension=ScoreDimension.FUNCTIONAL,
            score=1.0,
            details={"tests_passed": True},
        )
    )
    return grader


@pytest.fixture
def harness_with_graders(
    mock_sandbox: MagicMock, passing_graders: list[MagicMock]
) -> EvaluationHarness:
    """带五个满分 Grader 的 EvaluationHarness。"""
    return EvaluationHarness(sandbox=mock_sandbox, graders=passing_graders)


@pytest.fixture
def harness_no_graders(mock_sandbox: MagicMock) -> EvaluationHarness:
    """无 Grader 的 EvaluationHarness。"""
    return EvaluationHarness(sandbox=mock_sandbox)


# ---------------------------------------------------------------------------
# Harness initialization tests
# ---------------------------------------------------------------------------


class TestHarnessInit:
    """测试 EvaluationHarness 初始化。"""

    def test_init_stores_sandbox(self, mock_sandbox: MagicMock) -> None:
        """sandbox 属性必须保存传入的 sandbox 实例。"""
        harness = EvaluationHarness(sandbox=mock_sandbox)
        assert harness.sandbox is mock_sandbox

    def test_init_stores_graders(
        self, mock_sandbox: MagicMock, passing_graders: list[MagicMock]
    ) -> None:
        """graders 属性必须保存传入的 grader 列表。"""
        harness = EvaluationHarness(sandbox=mock_sandbox, graders=passing_graders)
        assert len(harness.graders) == len(passing_graders)
        for g in passing_graders:
            assert g in harness.graders

    def test_init_default_empty_graders(self, mock_sandbox: MagicMock) -> None:
        """未传入 graders 时默认为空列表。"""
        harness = EvaluationHarness(sandbox=mock_sandbox)
        assert harness.graders == []

    def test_init_multiple_graders(
        self, mock_sandbox: MagicMock, passing_graders: list[MagicMock], single_dim_grader: MagicMock
    ) -> None:
        """应支持传入多个 grader。"""
        harness = EvaluationHarness(
            sandbox=mock_sandbox, graders=[passing_graders[0], single_dim_grader]
        )
        assert len(harness.graders) == 2


# ---------------------------------------------------------------------------
# run_task tests
# ---------------------------------------------------------------------------


class TestRunTask:
    """测试 EvaluationHarness.run_task()。"""

    def test_run_task_returns_list(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """run_task 必须返回 list。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=1)
        assert isinstance(trials, list)

    def test_run_task_returns_trials(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """run_task 返回的每个元素必须是 Trial 实例。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=1)
        assert len(trials) == 1
        assert isinstance(trials[0], Trial)

    def test_run_task_n_trials_1(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """n_trials=1 时应返回恰好 1 个 Trial。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=1)
        assert len(trials) == 1

    def test_run_task_n_trials_5(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """n_trials=5 时应返回恰好 5 个 Trial。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=5)
        assert len(trials) == 5

    def test_run_task_trial_ids_unique(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """每次试运行的 trial_id 必须唯一。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=5)
        trial_ids = [t.trial_id for t in trials]
        assert len(set(trial_ids)) == 5

    def test_run_task_trial_ids_contain_task_id(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """trial_id 必须包含 task_id 前缀。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=3)
        for trial in trials:
            assert trial.task_id == sample_task.task_id
            assert sample_task.task_id in trial.trial_id

    def test_run_task_trial_stores_agent_config(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """Trial 必须保存 agent_config。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=1)
        assert trials[0].agent_config is agent_config

    def test_run_task_trial_has_outcome(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """Trial.outcome 必须包含 Transcript 摘要字段。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=1)
        outcome = trials[0].outcome
        assert "transcript_events" in outcome
        assert "total_tokens" in outcome
        assert "total_duration" in outcome
        assert "tool_call_count" in outcome

    def test_run_task_trial_has_scores(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """Trial.scores 必须包含评分结果。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=1)
        assert len(trials[0].scores) > 0

    def test_run_task_uses_mock_agent_internally(
        self,
        harness_with_graders: EvaluationHarness,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """run_task 应通过 MockAgent 生成 Transcript（验证集成路径）。"""
        trials = harness_with_graders.run_task(sample_task, agent_config, n_trials=1)
        # MockAgent produces 2 events (LLM_CALL + TOOL_CALL) and 150 tokens
        assert trials[0].outcome["transcript_events"] == 2
        assert trials[0].outcome["total_tokens"] == 150


# ---------------------------------------------------------------------------
# grade tests
# ---------------------------------------------------------------------------


class TestGrade:
    """测试 EvaluationHarness.grade()。"""

    def test_grade_returns_dict(
        self,
        sample_task: Task,
        mock_sandbox: MagicMock,
        single_dim_grader: MagicMock,
    ) -> None:
        """grade() 必须返回 dict。"""
        harness = EvaluationHarness(sandbox=mock_sandbox, graders=[single_dim_grader])
        trial = Trial(
            trial_id="t1",
            task_id=sample_task.task_id,
            agent_config=AgentConfig(name="a", model="m"),
        )
        result = harness.grade(sample_task, trial)
        assert isinstance(result, dict)

    def test_grade_returns_score_dimension_keys(
        self,
        sample_task: Task,
        mock_sandbox: MagicMock,
        single_dim_grader: MagicMock,
    ) -> None:
        """grade() 返回的 dict 键必须是 ScoreDimension 枚举值。"""
        harness = EvaluationHarness(sandbox=mock_sandbox, graders=[single_dim_grader])
        trial = Trial(
            trial_id="t1",
            task_id=sample_task.task_id,
            agent_config=AgentConfig(name="a", model="m"),
        )
        result = harness.grade(sample_task, trial)
        for key in result:
            assert isinstance(key, ScoreDimension)

    def test_grade_with_no_graders(
        self,
        sample_task: Task,
        harness_no_graders: EvaluationHarness,
    ) -> None:
        """无 grader 时 grade() 应返回空 dict。"""
        trial = Trial(
            trial_id="t1",
            task_id=sample_task.task_id,
            agent_config=AgentConfig(name="a", model="m"),
        )
        result = harness_no_graders.grade(sample_task, trial)
        assert result == {}

    def test_grade_collects_all_grader_dimensions(
        self,
        sample_task: Task,
        mock_sandbox: MagicMock,
        passing_graders: list[MagicMock],
    ) -> None:
        """多个 grader 的评分结果应全部收集。"""
        harness = EvaluationHarness(sandbox=mock_sandbox, graders=passing_graders)
        trial = Trial(
            trial_id="t1",
            task_id=sample_task.task_id,
            agent_config=AgentConfig(name="a", model="m"),
        )
        result = harness.grade(sample_task, trial)
        assert len(result) == 5
        for dim in ScoreDimension:
            assert dim in result

    def test_grade_skips_failing_grader(
        self,
        sample_task: Task,
        mock_sandbox: MagicMock,
        single_dim_grader: MagicMock,
    ) -> None:
        """评分失败的 grader 应被跳过，不影响其他 grader。"""
        broken_grader = MagicMock()
        broken_grader.name = "broken"
        broken_grader.grade = MagicMock(side_effect=RuntimeError("boom"))

        harness = EvaluationHarness(
            sandbox=mock_sandbox, graders=[broken_grader, single_dim_grader]
        )
        trial = Trial(
            trial_id="t1",
            task_id=sample_task.task_id,
            agent_config=AgentConfig(name="a", model="m"),
        )
        result = harness.grade(sample_task, trial)
        # broken_grader raises, single_dim_grader succeeds
        assert ScoreDimension.FUNCTIONAL in result
        assert len(result) == 1


# ---------------------------------------------------------------------------
# compute_total_score tests
# ---------------------------------------------------------------------------


class TestComputeTotalScore:
    """测试 EvaluationHarness.compute_total_score()。"""

    def test_full_scores_equals_100(
        self, harness_no_graders: EvaluationHarness
    ) -> None:
        """全部维度满分 => 总分 = 100。"""
        scores = {dim: 1.0 for dim in ScoreDimension}
        total = harness_no_graders.compute_total_score(scores)
        assert total == 100.0

    def test_zero_scores_equals_0(
        self, harness_no_graders: EvaluationHarness
    ) -> None:
        """全部维度零分 => 总分 = 0。"""
        scores = {dim: 0.0 for dim in ScoreDimension}
        total = harness_no_graders.compute_total_score(scores)
        assert total == 0.0

    def test_partial_scores(
        self, harness_no_graders: EvaluationHarness
    ) -> None:
        """部分维度得分应按权重正确聚合。"""
        scores = {dim: 0.5 for dim in ScoreDimension}
        total = harness_no_graders.compute_total_score(scores)
        # 0.5 * (30 + 25 + 15 + 20 + 10) = 0.5 * 100 = 50
        assert total == 50.0

    def test_only_functional_dimension(
        self, harness_no_graders: EvaluationHarness
    ) -> None:
        """只有 FUNCTIONAL 维度满分时，总分 = 30。"""
        scores = {ScoreDimension.FUNCTIONAL: 1.0}
        total = harness_no_graders.compute_total_score(scores)
        assert total == float(MAX_SCORES[ScoreDimension.FUNCTIONAL])

    def test_only_process_dimension(
        self, harness_no_graders: EvaluationHarness
    ) -> None:
        """只有 PROCESS 维度满分时，总分 = 25。"""
        scores = {ScoreDimension.PROCESS: 1.0}
        total = harness_no_graders.compute_total_score(scores)
        assert total == float(MAX_SCORES[ScoreDimension.PROCESS])

    def test_delegates_to_aggregate_scores(
        self, harness_no_graders: EvaluationHarness
    ) -> None:
        """compute_total_score 应与 aggregate_scores 结果一致。"""
        scores = {ScoreDimension.FUNCTIONAL: 0.8, ScoreDimension.ROBUSTNESS: 0.6}
        harness_result = harness_no_graders.compute_total_score(scores)
        direct_result = aggregate_scores(scores)
        assert harness_result == direct_result


# ---------------------------------------------------------------------------
# trial.success threshold tests
# ---------------------------------------------------------------------------


class TestTrialSuccess:
    """测试 trial.success 是否基于分数阈值正确设置。"""

    def test_success_true_when_above_threshold(
        self,
        mock_sandbox: MagicMock,
        passing_graders: list[MagicMock],
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """总分 >= PASS_THRESHOLD 时 trial.success 应为 True。"""
        harness = EvaluationHarness(sandbox=mock_sandbox, graders=passing_graders)
        trials = harness.run_task(sample_task, agent_config, n_trials=1)
        assert trials[0].success is True

    def test_success_false_when_below_threshold(
        self,
        mock_sandbox: MagicMock,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """总分 < PASS_THRESHOLD 时 trial.success 应为 False。"""
        low_grader = MagicMock()
        low_grader.name = "low"
        low_grader.grade = MagicMock(
            return_value=GraderResult(
                dimension=ScoreDimension.FUNCTIONAL, score=0.0, details={}
            )
        )
        harness = EvaluationHarness(sandbox=mock_sandbox, graders=[low_grader])
        trials = harness.run_task(sample_task, agent_config, n_trials=1)
        # Only FUNCTIONAL dimension scored at 0.0 => total = 0 < PASS_THRESHOLD
        assert trials[0].success is False

    def test_success_consistent_across_trials(
        self,
        mock_sandbox: MagicMock,
        passing_graders: list[MagicMock],
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """使用确定性 grader 时所有 trial 的 success 应一致。"""
        harness = EvaluationHarness(sandbox=mock_sandbox, graders=passing_graders)
        trials = harness.run_task(sample_task, agent_config, n_trials=5)
        successes = [t.success for t in trials]
        assert all(s == successes[0] for s in successes)

    def test_success_with_no_graders(
        self,
        mock_sandbox: MagicMock,
        sample_task: Task,
        agent_config: AgentConfig,
    ) -> None:
        """无 grader 时总分为 0，trial.success 应为 False。"""
        harness = EvaluationHarness(sandbox=mock_sandbox)
        trials = harness.run_task(sample_task, agent_config, n_trials=1)
        assert trials[0].success is False

    def test_success_threshold_boundary(
        self, mock_sandbox: MagicMock, sample_task: Task, agent_config: AgentConfig
    ) -> None:
        """总分恰好等于 PASS_THRESHOLD 时 trial.success 应为 True。"""
        # Craft dimension scores so total == PASS_THRESHOLD exactly:
        #   FUNCTIONAL=1.0 (30) + PROCESS=1.0 (25) + EFFICIENCY=1.0 (15)
        #   + ROBUSTNESS=0.5 (10) + ALIGNMENT=0.0 (0) = 80 = PASS_THRESHOLD
        expected_total = aggregate_scores({
            ScoreDimension.FUNCTIONAL: 1.0,
            ScoreDimension.PROCESS: 1.0,
            ScoreDimension.EFFICIENCY: 1.0,
            ScoreDimension.ROBUSTNESS: 0.5,
            ScoreDimension.ALIGNMENT: 0.0,
        })
        assert expected_total == PASS_THRESHOLD

        score_map = {
            ScoreDimension.FUNCTIONAL: 1.0,
            ScoreDimension.PROCESS: 1.0,
            ScoreDimension.EFFICIENCY: 1.0,
            ScoreDimension.ROBUSTNESS: 0.5,
            ScoreDimension.ALIGNMENT: 0.0,
        }
        boundary_graders = []
        for dim, score in score_map.items():
            grader = MagicMock()
            grader.name = f"boundary-{dim.value}"
            grader.grade = MagicMock(
                return_value=GraderResult(dimension=dim, score=score, details={})
            )
            boundary_graders.append(grader)
        harness = EvaluationHarness(sandbox=mock_sandbox, graders=boundary_graders)
        trials = harness.run_task(sample_task, agent_config, n_trials=1)
        assert trials[0].success is True
