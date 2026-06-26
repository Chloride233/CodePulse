"""Validation Gate — 候选 Agent 与基线的对比回归门控。

SkillOpt 循环的第三步：在 Backward Pass 产出 PromptEdit 后，
用 Validation Gate 验证候选 Agent 是否真正优于基线。
只有 improvement_rate > regression_rate 时才放行。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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
        n_tasks = len(candidate_trajs)
        if n_tasks == 0:
            return {
                "candidate_score": 0.0,
                "baseline_score": 0.0,
                "improved": False,
                "improvement_rate": 0.0,
                "regression_rate": 0.0,
            }

        candidate_total = 0.0
        baseline_total = 0.0
        improved_count = 0
        regressed_count = 0

        for c_traj, b_traj in zip(
            candidate_trajs, baseline_trajs, strict=True
        ):
            c_score = aggregate_scores(_to_dimension_scores(c_traj.avg_scores))
            b_score = aggregate_scores(_to_dimension_scores(b_traj.avg_scores))

            candidate_total += c_score
            baseline_total += b_score

            if c_score > b_score:
                improved_count += 1
            elif c_score < b_score:
                regressed_count += 1

        candidate_score = round(candidate_total / n_tasks, 2)
        baseline_score = round(baseline_total / n_tasks, 2)
        improvement_rate = round(improved_count / n_tasks, 4)
        regression_rate = round(regressed_count / n_tasks, 4)

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
            "improved": candidate_score > baseline_score,
            "improvement_rate": improvement_rate,
            "regression_rate": regression_rate,
        }
