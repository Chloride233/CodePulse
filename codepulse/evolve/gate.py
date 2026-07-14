"""Validation Gate — 候选 Agent 与基线的对比回归门控。

SkillOpt 循环的第三步：在 Backward Pass 产出 PromptEdit 后，
用 Validation Gate 验证候选 Agent 是否真正优于基线。
只有 improvement_rate > regression_rate 时才放行。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from codepulse.eval.comparison import align_exact
from codepulse.eval.scoring import ScoreDimension, aggregate_scores
from codepulse.evolve.forward import ForwardPass, Trajectory

if TYPE_CHECKING:
    from codepulse.data.models import Task
    from codepulse.data.protocols import Agent
    from codepulse.eval.harness import EvaluationHarness

logger = logging.getLogger(__name__)


def _to_dimension_scores(
    avg_scores: dict[str, float],
) -> dict[ScoreDimension, float]:
    """将字符串键的平均分转换为 ScoreDimension 键。

    ForwardPass 产生的 avg_scores 使用字符串键，需要转换为
    ScoreDimension 枚举键后才能传给 aggregate_scores。

    Args:
        avg_scores: 维度名（字符串）到分数的映射。

    Returns:
        ScoreDimension 到分数的映射。无法识别的键将被跳过。
    """
    result: dict[ScoreDimension, float] = {}
    for key, value in avg_scores.items():
        try:
            dim = ScoreDimension(key)
            result[dim] = value
        except ValueError:
            logger.warning("跳过未知维度: %s", key)
    return result


class ValidationGate:
    """验证门控：对比候选 Agent 与基线的评测表现。

    在数据集上分别运行候选和基线的 Forward Pass，
    计算改进率和回归率，决定候选是否放行。

    Attributes:
        harness: 评测编排器。
        dataset: 待评测任务列表。
    """

    def __init__(
        self,
        harness: EvaluationHarness,
        dataset: list[Task],
    ) -> None:
        """初始化验证门控。

        Args:
            harness: 评测编排器。
            dataset: 待评测任务列表。
        """
        self.harness = harness
        self.dataset = dataset

    def validate(
        self,
        candidate: Agent,
        baseline: Agent,
        n_trials: int = 5,
    ) -> dict[str, Any]:
        """验证候选 Agent 是否优于基线。

        分别对候选和基线执行 Forward Pass，逐任务对比聚合分数，
        计算改进率和回归率。

        Args:
            candidate: 候选 Agent 实现。
            baseline: 基线 Agent 实现。
            n_trials: 每个任务的试运行次数，默认 5。

        Returns:
            包含以下字段的字典：
            - candidate_score: 候选 Agent 平均总分。
            - baseline_score: 基线 Agent 平均总分。
            - improved: 候选是否优于基线。
            - improvement_rate: 改进任务占比。
            - regression_rate: 退化任务占比。
        """
        forward = ForwardPass(self.harness, self.dataset)

        logger.info(
            "Validation Gate: 候选 '%s' vs 基线 '%s', 每任务 %d 次试运行",
            candidate.name,
            baseline.name,
            n_trials,
        )

        candidate_trajectories = forward.run(candidate, n_trials)
        baseline_trajectories = forward.run(baseline, n_trials)

        return self._compare(candidate_trajectories, baseline_trajectories)

    @staticmethod
    def validate_phase3(
        comparison: dict[str, Any],
        attribution: dict[str, Any],
        candidate_peak_costs: list[float],
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        """Accept a frozen Phase 3 candidate only when it is stably safer and in budget."""
        candidate = comparison["candidate"]
        deltas = comparison["deltas"]
        summary = attribution["summary"]
        per_trial_limit = float(budget["per_trial_cny"])
        per_agent_limit = float(budget["per_agent_cny"])
        rejection_reasons: list[str] = []

        if any(cost < 0 for cost in candidate_peak_costs):
            rejection_reasons.append("invalid_cost_metrics")
        if any(cost > per_trial_limit for cost in candidate_peak_costs):
            rejection_reasons.append("per_trial_budget_exceeded")
        if float(candidate["cost_cny_peak"]) > per_agent_limit:
            rejection_reasons.append("per_agent_budget_exceeded")
        if int(summary["regressions"]) > 0:
            rejection_reasons.append("regression_detected")
        if float(deltas["success_rate"]) < 0:
            rejection_reasons.append("success_rate_regression")
        if float(deltas["pass_hat_k"]) <= 0:
            rejection_reasons.append("no_stable_improvement")

        return {
            "accepted": not rejection_reasons,
            "rejection_reasons": rejection_reasons,
            "stable_pass_gain": float(deltas["pass_hat_k"]),
            "success_rate_delta": float(deltas["success_rate"]),
            "regressions": int(summary["regressions"]),
            "candidate_peak_cost_cny": float(candidate["cost_cny_peak"]),
        }

    def _compare(
        self,
        candidate_trajs: list[Trajectory],
        baseline_trajs: list[Trajectory],
    ) -> dict[str, Any]:
        """对比候选与基线的轨迹，计算改进率和回归率。

        Args:
            candidate_trajs: 候选 Agent 的轨迹列表。
            baseline_trajs: 基线 Agent 的轨迹列表。

        Returns:
            对比结果字典。
        """
        pairs = align_exact(
            candidate_trajs,
            baseline_trajs,
            left_key=lambda trajectory: trajectory.task.task_id,
            right_key=lambda trajectory: trajectory.task.task_id,
            left_name="candidate",
            right_name="baseline",
        )
        n_tasks = len(pairs)
        if n_tasks == 0:
            return {
                "candidate_score": 0.0,
                "baseline_score": 0.0,
                "improved": False,
                "improvement_rate": 0.0,
                "regression_rate": 0.0,
                "rejection_reason": "empty_dataset",
            }

        candidate_total = 0.0
        baseline_total = 0.0
        improved_count = 0
        regressed_count = 0
        p0_regressions = 0
        cost_violations = 0
        regression_suite_failures = 0

        for c_traj, b_traj in pairs:
            c_score = aggregate_scores(_to_dimension_scores(c_traj.avg_scores))
            b_score = aggregate_scores(_to_dimension_scores(b_traj.avg_scores))

            candidate_total += c_score
            baseline_total += b_score

            if c_score > b_score:
                improved_count += 1
            elif c_score < b_score:
                regressed_count += 1

            c_func = c_traj.avg_scores.get(ScoreDimension.FUNCTIONAL.value, 0.0)
            b_func = b_traj.avg_scores.get(ScoreDimension.FUNCTIONAL.value, 0.0)
            c_robust = c_traj.avg_scores.get(ScoreDimension.ROBUSTNESS.value, 0.0)
            b_robust = b_traj.avg_scores.get(ScoreDimension.ROBUSTNESS.value, 0.0)
            if c_func < b_func or c_robust < b_robust:
                p0_regressions += 1

            c_cost = self._avg_cost(c_traj)
            b_cost = self._avg_cost(b_traj)
            if b_cost > 0 and c_cost > b_cost * 1.1:
                cost_violations += 1

            if c_traj.task.suite_type.value == "regression" and not c_traj.success:
                regression_suite_failures += 1

        candidate_score = round(candidate_total / n_tasks, 2)
        baseline_score = round(baseline_total / n_tasks, 2)
        improvement_rate = round(improved_count / n_tasks, 4)
        regression_rate = round(regressed_count / n_tasks, 4)
        improved = (
            candidate_score > baseline_score
            and p0_regressions == 0
            and cost_violations == 0
            and regression_suite_failures == 0
        )
        rejection_reason = ""
        if not improved:
            if p0_regressions > 0:
                rejection_reason = "p0_regression"
            elif cost_violations > 0:
                rejection_reason = "cost_budget_exceeded"
            elif regression_suite_failures > 0:
                rejection_reason = "regression_suite_failed"
            elif candidate_score < baseline_score:
                rejection_reason = "score_regression"

        logger.info(
            "Validation 结果: 候选=%.2f, 基线=%.2f, "
            "改进率=%.2f%%, 回归率=%.2f%%",
            candidate_score,
            baseline_score,
            improvement_rate * 100,
            regression_rate * 100,
        )

        return {
            "candidate_score": candidate_score,
            "baseline_score": baseline_score,
            "improved": improved,
            "improvement_rate": improvement_rate,
            "regression_rate": regression_rate,
            "p0_regressions": p0_regressions,
            "cost_violations": cost_violations,
            "regression_suite_failures": regression_suite_failures,
            "rejection_reason": rejection_reason,
        }

    def _avg_cost(self, trajectory: Trajectory) -> float:
        if not trajectory.trials:
            return 0.0
        return sum(trial.metrics.cost_usd for trial in trajectory.trials) / len(trajectory.trials)
