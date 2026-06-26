"""评测编排器 — 协调评测流程。

编排 Grader 执行、结果收集、分数聚合。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codepulse.data.models import AgentConfig, Task, Trial
from codepulse.eval.scoring import ScoreDimension, aggregate_scores


@dataclass(frozen=True)
class GraderResult:
    """单个 Grader 的评分结果。"""

    dimension: ScoreDimension
    score: float  # 0-1 之间的比例
    details: dict[str, Any] = field(default_factory=dict)


class EvaluationHarness:
    """评测编排器。

    协调 Grader 执行，收集结果，聚合分数。
    """

    def run_task(
        self,
        task: Task,
        agent_config: AgentConfig,
        n_trials: int = 5,
    ) -> list[Trial]:
        """运行一个任务的多次试运行。

        Args:
            task: 评测任务。
            agent_config: Agent 配置。
            n_trials: 试运行次数。

        Returns:
            试运行结果列表。
        """
        # TODO: 实际评测流程
        raise NotImplementedError

    def grade(self, task: Task, trial: Trial) -> dict[ScoreDimension, float]:
        """对一次试运行进行多维度评分。

        Args:
            task: 评测任务。
            trial: 试运行记录。

        Returns:
            各维度得分（0-1 之间的比例）。
        """
        # TODO: 调用各类 Grader
        raise NotImplementedError

    def compute_total_score(self, dimension_scores: dict[ScoreDimension, float]) -> float:
        """聚合各维度分数为总分。

        Args:
            dimension_scores: 各维度得分。

        Returns:
            总分（0-100）。
        """
        return aggregate_scores(dimension_scores)
