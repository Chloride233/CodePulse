"""SkillOpt 主循环 — 评测驱动的自进化引擎。

编排 Forward Pass → Backward Pass → Validation Gate → Edit Buffer，
实现"评测即奖励信号"的核心理念。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codepulse.data.models import Task
    from codepulse.data.protocols import Agent
    from codepulse.eval.harness import EvaluationHarness

from codepulse.evolve.attribution import SampleAttribution
from codepulse.evolve.buffer import EditBuffer
from codepulse.evolve.forward import ForwardPass
from codepulse.evolve.gate import ValidationGate
from codepulse.evolve.prompt_edit import EditType, PromptEdit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvolutionResult:
    """一轮进化的结果。"""

    epoch: int
    baseline_score: float
    candidate_score: float
    improved: bool
    attribution_report: dict[str, Any]
    edits_applied: int
    edits_rejected: int


class SkillOpt:
    """SkillOpt 自进化循环。

    Forward Pass 收集轨迹 → Backward Pass 分析失败生成编辑 →
    Validation Gate 验证 → Edit Buffer 存储负反馈。

    Attributes:
        harness: 评测编排器。
        dataset: 评测数据集。
        buffer: 被拒编辑缓冲区。
        attribution: 样本归因器。
    """

    def __init__(
        self,
        harness: EvaluationHarness,
        dataset: list[Task],
    ) -> None:
        """初始化 SkillOpt。

        Args:
            harness: 评测编排器。
            dataset: 评测数据集。
        """
        self.harness = harness
        self.dataset = dataset
        self.buffer = EditBuffer()
        self.attribution = SampleAttribution()

    def evolve(
        self,
        baseline: Agent,
        candidate: Agent,
        n_epochs: int = 3,
        n_trials: int = 5,
    ) -> list[EvolutionResult]:
        """执行多轮进化。

        Args:
            baseline: 基线 Agent。
            candidate: 候选 Agent（通常是 baseline 的改进版）。
            n_epochs: 进化轮数。
            n_trials: 每任务试运行次数。

        Returns:
            每轮进化结果列表。
        """
        results: list[EvolutionResult] = []

        for epoch in range(n_epochs):
            logger.info("=== 进化轮次 %d/%d ===", epoch + 1, n_epochs)

            result = self._run_epoch(baseline, candidate, epoch, n_trials)
            results.append(result)

            if result.improved:
                logger.info(
                    "轮次 %d: 候选优于基线 (%.2f > %.2f)，进化成功",
                    epoch + 1,
                    result.candidate_score,
                    result.baseline_score,
                )
            else:
                logger.info(
                    "轮次 %d: 候选未优于基线 (%.2f <= %.2f)，保持基线",
                    epoch + 1,
                    result.candidate_score,
                    result.baseline_score,
                )

        return results

    def _run_epoch(
        self,
        baseline: Agent,
        candidate: Agent,
        epoch: int,
        n_trials: int,
    ) -> EvolutionResult:
        """执行一轮进化。

        Args:
            baseline: 基线 Agent。
            candidate: 候选 Agent。
            epoch: 当前轮次。
            n_trials: 每任务试运行次数。

        Returns:
            进化结果。
        """
        # Forward Pass: 收集候选和基线的轨迹
        forward = ForwardPass(self.harness, self.dataset)
        baseline_trajs = forward.run(baseline, n_trials)
        candidate_trajs = forward.run(candidate, n_trials)

        # 归因分析
        old_scores = {
            t.task.task_id: t.avg_scores.get("functional", 0.0)
            for t in baseline_trajs
        }
        new_scores = {
            t.task.task_id: t.avg_scores.get("functional", 0.0)
            for t in candidate_trajs
        }
        attributions = self.attribution.classify_all(old_scores, new_scores)
        report = self.attribution.report(attributions)

        # Validation Gate
        gate = ValidationGate(self.harness, self.dataset)
        gate_result = gate.validate(candidate, baseline, n_trials)

        # 记录编辑（简化版：每轮生成一个示例编辑）
        edits_applied = 0
        edits_rejected = 0

        if gate_result["improved"]:
            edits_applied = 1
        else:
            # 记录被拒编辑
            edit = PromptEdit(
                edit_id=f"edit-{epoch}",
                edit_type=EditType.REPLACE,
                target_section="system_prompt",
                content="candidate prompt",
                reasoning="尝试改进",
                confidence=0.5,
            )
            self.buffer.add_rejected(
                edit,
                gate_result["candidate_score"] - gate_result["baseline_score"],
                "未优于基线",
            )
            edits_rejected = 1

        return EvolutionResult(
            epoch=epoch,
            baseline_score=gate_result["baseline_score"],
            candidate_score=gate_result["candidate_score"],
            improved=gate_result["improved"],
            attribution_report={
                "improvements": report.improvements,
                "regressions": report.regressions,
                "persistent_failures": report.persistent_failures,
                "stable_successes": report.stable_successes,
            },
            edits_applied=edits_applied,
            edits_rejected=edits_rejected,
        )

    def get_buffer_stats(self) -> dict[str, Any]:
        """获取编辑缓冲区统计。

        Returns:
            缓冲区统计信息。
        """
        return self.buffer.get_stats()
