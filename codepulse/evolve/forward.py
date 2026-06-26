"""Forward Pass — 在数据集上运行 Skill，收集 Trajectory。

SkillOpt 循环的第一步：给定一个 Agent Skill（prompt 配置），
在数据集上执行多次试运行，收集评测结果用于后续归因和优化。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.data.protocols import Agent
    from codepulse.eval.harness import EvaluationHarness

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Trajectory:
    """一个任务上的完整试运行轨迹。

    Attributes:
        task: 原始评测任务。
        trials: 多次试运行结果。
        success: 是否所有试运行均通过。
        avg_scores: 各维度平均分（0-1 比例）。
    """

    task: Task
    trials: list[Trial]
    success: bool
    avg_scores: dict[str, float] = field(default_factory=dict)


def _compute_avg_scores(trials: list[Trial]) -> dict[str, float]:
    """计算多次试运行各维度的平均分。

    Args:
        trials: 试运行结果列表。

    Returns:
        维度名 -> 平均分的映射。
    """
    if not trials:
        return {}

    # 收集所有出现过的维度
    all_dimensions: set[str] = set()
    for trial in trials:
        all_dimensions.update(trial.scores.keys())

    # 计算每个维度的平均值
    avg: dict[str, float] = {}
    for dim in all_dimensions:
        values = [trial.scores[dim] for trial in trials if dim in trial.scores]
        avg[dim] = sum(values) / len(values) if values else 0.0

    return avg


class ForwardPass:
    """Forward Pass：在数据集上运行 Agent Skill，收集轨迹。

    遍历数据集中的每个任务，使用评测编排器执行多次试运行，
    汇总为 Trajectory 列表，供 Backward Pass 归因分析。

    Attributes:
        harness: 评测编排器。
        dataset: 待评测任务列表。
    """

    def __init__(
        self,
        harness: EvaluationHarness,
        dataset: list[Task],
    ) -> None:
        """初始化 Forward Pass。

        Args:
            harness: 评测编排器。
            dataset: 待评测任务列表。
        """
        self.harness = harness
        self.dataset = dataset

    def run(self, skill: Agent, n_trials: int = 5) -> list[Trajectory]:
        """在数据集上运行 Agent Skill，收集所有任务的轨迹。

        Args:
            skill: 待评测的 Agent 实现。
            n_trials: 每个任务的试运行次数，默认 5。

        Returns:
            每个任务对应的 Trajectory 列表。
        """
        trajectories: list[Trajectory] = []

        for task in self.dataset:
            logger.info(
                "Forward Pass: 任务 %s (%d 次试运行)",
                task.task_id,
                n_trials,
            )

            trials = self.harness.run_task(task, skill, n_trials)
            success = all(trial.success for trial in trials)
            avg_scores = _compute_avg_scores(trials)

            trajectory = Trajectory(
                task=task,
                trials=trials,
                success=success,
                avg_scores=avg_scores,
            )

            logger.info(
                "任务 %s: success=%s, 维度平均分=%s",
                task.task_id,
                success,
                avg_scores,
            )

            trajectories.append(trajectory)

        return trajectories
