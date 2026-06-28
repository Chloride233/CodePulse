"""报告生成器测试。"""

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
from codepulse.evolve.attribution import AttributionReport
from codepulse.output.report import ReportGenerator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def generator() -> ReportGenerator:
    return ReportGenerator()


@pytest.fixture()
def sample_task() -> Task:
    return Task(
        task_id="task-001",
        source=TaskSource.SWE_BENCH,
        category=TaskCategory.BUG_FIX,
        difficulty=Difficulty.MEDIUM,
        language="python",
        input={"description": "Fix the login bug"},
        ground_truth={"expected_output": "fixed"},
    )


@pytest.fixture()
def sample_trial() -> Trial:
    return Trial(
        trial_id="trial-001",
        task_id="task-001",
        agent_config=AgentConfig(
            name="test-agent",
            model="deepseek-chat",
            temperature=0.0,
            max_tokens=4096,
        ),
        scores={
            "correctness": 28.0,
            "process_quality": 20.0,
            "efficiency": 12.0,
            "robustness": 18.0,
            "alignment": 8.0,
        },
        metrics=TrialMetrics(
            total_tokens=5000,
            input_tokens=3000,
            output_tokens=2000,
            total_duration=12.5,
            tool_call_count=4,
            self_correction_count=1,
            cost_usd=0.0025,
        ),
        success=True,
    )


@pytest.fixture()
def failed_trial() -> Trial:
    return Trial(
        trial_id="trial-002",
        task_id="task-001",
        agent_config=AgentConfig(
            name="weak-agent",
            model="gpt-3.5-turbo",
            temperature=0.7,
            max_tokens=2048,
        ),
        scores={
            "correctness": 10.0,
            "process_quality": 8.0,
            "efficiency": 5.0,
            "robustness": 6.0,
            "alignment": 3.0,
        },
        metrics=TrialMetrics(
            total_tokens=8000,
            input_tokens=5000,
            output_tokens=3000,
            total_duration=30.0,
            tool_call_count=10,
            self_correction_count=5,
            cost_usd=0.008,
        ),
        success=False,
    )


@pytest.fixture()
def sample_attribution() -> AttributionReport:
    return AttributionReport(
        improvements=3,
        regressions=1,
        persistent_failures=2,
        stable_successes=4,
        improvement_rate=0.3,
        regression_rate=0.1,
    )


@pytest.fixture()
def comparison_results() -> dict[str, dict[str, object]]:
    return {
        "Agent-A": {"pass_rate": 0.85, "avg_score": 82.5, "avg_tokens": 4200},
        "Agent-B": {"pass_rate": 0.60, "avg_score": 65.0, "avg_tokens": 6800},
        "Agent-C": {"pass_rate": 0.92, "avg_score": 91.0, "avg_tokens": 3100},
    }


# ---------------------------------------------------------------------------
# TestReportGenerator.generate_trial_report
# ---------------------------------------------------------------------------


class TestTrialReport:
    """generate_trial_report 测试。"""

    def test_returns_string(
        self,
        generator: ReportGenerator,
        sample_trial: Trial,
        sample_task: Task,
    ) -> None:
        """返回值为字符串。"""
        result = generator.generate_trial_report(sample_trial, sample_task)
        assert isinstance(result, str)

    def test_contains_task_id(
        self,
        generator: ReportGenerator,
        sample_trial: Trial,
        sample_task: Task,
    ) -> None:
        """报告包含任务 ID。"""
        result = generator.generate_trial_report(sample_trial, sample_task)
        assert sample_task.task_id in result

    def test_contains_scores(
        self,
        generator: ReportGenerator,
        sample_trial: Trial,
        sample_task: Task,
    ) -> None:
        """报告包含各维度得分。"""
        result = generator.generate_trial_report(sample_trial, sample_task)
        for score in sample_trial.scores.values():
            assert f"{score:.1f}" in result

    def test_contains_success_status(
        self,
        generator: ReportGenerator,
        sample_trial: Trial,
        sample_task: Task,
    ) -> None:
        """通过试运行报告包含'通过'。"""
        result = generator.generate_trial_report(sample_trial, sample_task)
        assert "通过" in result

    def test_contains_failure_status(
        self,
        generator: ReportGenerator,
        failed_trial: Trial,
        sample_task: Task,
    ) -> None:
        """失败试运行报告包含'未通过'。"""
        result = generator.generate_trial_report(failed_trial, sample_task)
        assert "未通过" in result

    def test_contains_agent_name(
        self,
        generator: ReportGenerator,
        sample_trial: Trial,
        sample_task: Task,
    ) -> None:
        """报告包含 Agent 名称。"""
        result = generator.generate_trial_report(sample_trial, sample_task)
        assert sample_trial.agent_config.name in result

    def test_contains_model(
        self,
        generator: ReportGenerator,
        sample_trial: Trial,
        sample_task: Task,
    ) -> None:
        """报告包含模型名称。"""
        result = generator.generate_trial_report(sample_trial, sample_task)
        assert sample_trial.agent_config.model in result


# ---------------------------------------------------------------------------
# TestReportGenerator.generate_comparison_report
# ---------------------------------------------------------------------------


class TestComparisonReport:
    """generate_comparison_report 测试。"""

    def test_returns_string(
        self,
        generator: ReportGenerator,
        comparison_results: dict[str, dict[str, object]],
    ) -> None:
        """返回值为字符串。"""
        result = generator.generate_comparison_report(comparison_results)
        assert isinstance(result, str)

    def test_contains_agent_names(
        self,
        generator: ReportGenerator,
        comparison_results: dict[str, dict[str, object]],
    ) -> None:
        """报告包含所有 Agent 名称。"""
        result = generator.generate_comparison_report(comparison_results)
        for name in comparison_results:
            assert name in result

    def test_contains_metrics(
        self,
        generator: ReportGenerator,
        comparison_results: dict[str, dict[str, object]],
    ) -> None:
        """报告包含指标键名。"""
        result = generator.generate_comparison_report(comparison_results)
        for metrics in comparison_results.values():
            for key in metrics:
                assert key in result

    def test_empty_results(
        self,
        generator: ReportGenerator,
    ) -> None:
        """空结果返回占位文本。"""
        result = generator.generate_comparison_report({})
        assert isinstance(result, str)
        assert "暂无数据" in result


# ---------------------------------------------------------------------------
# TestReportGenerator.generate_evolution_report
# ---------------------------------------------------------------------------


class TestEvolutionReport:
    """generate_evolution_report 测试。"""

    def test_returns_string(
        self,
        generator: ReportGenerator,
        sample_attribution: AttributionReport,
    ) -> None:
        """返回值为字符串。"""
        result = generator.generate_evolution_report(sample_attribution)
        assert isinstance(result, str)

    def test_contains_improvement_count(
        self,
        generator: ReportGenerator,
        sample_attribution: AttributionReport,
    ) -> None:
        """报告包含改进数量。"""
        result = generator.generate_evolution_report(sample_attribution)
        assert str(sample_attribution.improvements) in result

    def test_contains_regression_count(
        self,
        generator: ReportGenerator,
        sample_attribution: AttributionReport,
    ) -> None:
        """报告包含退化数量。"""
        result = generator.generate_evolution_report(sample_attribution)
        assert str(sample_attribution.regressions) in result

    def test_contains_improvement_rate(
        self,
        generator: ReportGenerator,
        sample_attribution: AttributionReport,
    ) -> None:
        """报告包含改进率。"""
        result = generator.generate_evolution_report(sample_attribution)
        assert f"{sample_attribution.improvement_rate:.1%}" in result

    def test_contains_regression_rate(
        self,
        generator: ReportGenerator,
        sample_attribution: AttributionReport,
    ) -> None:
        """报告包含退化率。"""
        result = generator.generate_evolution_report(sample_attribution)
        assert f"{sample_attribution.regression_rate:.1%}" in result

    def test_net_improvement_verdict(
        self,
        generator: ReportGenerator,
    ) -> None:
        """改进 > 退化时结论为'自进化有效'。"""
        attr = AttributionReport(
            improvements=5,
            regressions=1,
            persistent_failures=2,
            stable_successes=2,
            improvement_rate=0.5,
            regression_rate=0.1,
        )
        result = generator.generate_evolution_report(attr)
        assert "自进化有效" in result

    def test_net_regression_verdict(
        self,
        generator: ReportGenerator,
    ) -> None:
        """退化 > 改进时结论为'退化'。"""
        attr = AttributionReport(
            improvements=1,
            regressions=4,
            persistent_failures=3,
            stable_successes=2,
            improvement_rate=0.1,
            regression_rate=0.4,
        )
        result = generator.generate_evolution_report(attr)
        assert "退化" in result

    def test_balanced_verdict(
        self,
        generator: ReportGenerator,
    ) -> None:
        """改进 == 退化时结论为'持平'。"""
        attr = AttributionReport(
            improvements=3,
            regressions=3,
            persistent_failures=2,
            stable_successes=2,
            improvement_rate=0.3,
            regression_rate=0.3,
        )
        result = generator.generate_evolution_report(attr)
        assert "持平" in result
