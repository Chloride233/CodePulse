"""评测编排器 — 协调评测流程。

编排 Grader 执行、结果收集、分数聚合。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codepulse.data.models import AgentConfig, Task
    from codepulse.data.protocols import Grader
    from codepulse.env.sandbox import SandboxManager

from codepulse.data.models import Trial
from codepulse.env.mock_agent import MockAgent
from codepulse.eval.scoring import PASS_THRESHOLD, ScoreDimension, aggregate_scores

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraderResult:
    """单个 Grader 的评分结果。"""

    dimension: ScoreDimension
    score: float  # 0-1 之间的比例
    details: dict[str, Any] = field(default_factory=dict)


class EvaluationHarness:
    """评测编排器。

    协调 Grader 执行，收集结果，聚合分数。使用 MockAgent 生成合成
    Transcript，避免真实 LLM 调用，确保评测管线可独立运行。

    Attributes:
        sandbox: Docker 沙箱管理器。
        graders: Grader 列表，每个 Grader 负责一个评分维度。
    """

    def __init__(
        self,
        sandbox: SandboxManager,
        graders: list[Grader] | None = None,
    ) -> None:
        """初始化评测编排器。

        Args:
            sandbox: Docker 沙箱管理器。
            graders: Grader 列表，默认使用空列表。
        """
        self.sandbox = sandbox
        self.graders: list[Grader] = graders if graders is not None else []

    def run_task(
        self,
        task: Task,
        agent_config: AgentConfig,
        n_trials: int = 5,
    ) -> list[Trial]:
        """运行一个任务的多次试运行。

        使用 MockAgent 生成合成 Transcript，对每次试运行进行评分，
        并根据通过阈值判断成功与否。

        Args:
            task: 评测任务。
            agent_config: Agent 配置。
            n_trials: 试运行次数。

        Returns:
            试运行结果列表。
        """
        agent = MockAgent()
        trials: list[Trial] = []

        for i in range(n_trials):
            trial_id = f"{task.task_id}-trial-{i}"

            # 使用 MockAgent 生成合成 Transcript
            transcript = agent.run(task, self.sandbox)

            # 构建 Trial 对象
            trial = Trial(
                trial_id=trial_id,
                task_id=task.task_id,
                agent_config=agent_config,
                outcome={
                    "transcript_events": len(transcript.events),
                    "total_tokens": transcript.total_tokens,
                    "total_duration": transcript.total_duration,
                    "tool_call_count": transcript.tool_call_count,
                },
            )

            # 评分
            dimension_scores = self.grade(task, trial)
            total_score = self.compute_total_score(dimension_scores)

            # 更新 Trial 的分数和成功状态
            trial.scores = {dim.value: score for dim, score in dimension_scores.items()}
            trial.success = total_score >= PASS_THRESHOLD

            logger.debug(
                "试运行 %s: 总分=%.2f, 成功=%s",
                trial_id,
                total_score,
                trial.success,
            )

            trials.append(trial)

        return trials

    def grade(self, task: Task, trial: Trial) -> dict[ScoreDimension, float]:
        """对一次试运行进行多维度评分。

        调用每个 Grader 的 grade() 方法，收集各维度得分。

        Args:
            task: 评测任务。
            trial: 试运行记录。

        Returns:
            各维度得分（0-1 之间的比例）。
        """
        dimension_scores: dict[ScoreDimension, float] = {}

        for grader in self.graders:
            try:
                result = grader.grade(task, trial)
                dimension_scores[result.dimension] = result.score
            except Exception:
                logger.exception(
                    "Grader '%s' 评分失败，跳过该维度",
                    grader.name,
                )

        return dimension_scores

    def compute_total_score(self, dimension_scores: dict[ScoreDimension, float]) -> float:
        """聚合各维度分数为总分。

        Args:
            dimension_scores: 各维度得分。

        Returns:
            总分（0-100）。
        """
        return aggregate_scores(dimension_scores)
