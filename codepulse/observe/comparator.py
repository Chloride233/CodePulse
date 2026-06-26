"""Agent 对比工具 — 多 Agent 横向评测。

对同一任务运行多个 Agent 配置，对比 pass@k、pass^k、效率指标。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from codepulse.data.models import Task
    from codepulse.data.protocols import Agent
    from codepulse.eval.harness import EvaluationHarness
from codepulse.observe.metrics import compute_pass_metrics

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentMetrics:
    """单个 Agent 在一组试运行上的聚合指标。"""

    agent_name: str
    n_success: int
    n_total: int
    pass_at_1: float
    pass_at_k: float
    pass_hat_k: float
    avg_tokens: float
    avg_duration: float
    avg_cost: float
    self_correction_rate: float


class AgentComparator:
    """多 Agent 横向对比。

    对同一任务运行多个 Agent 配置，收集试运行结果并计算
    pass@k、pass^k、效率等聚合指标。

    Attributes:
        harness: 评测编排器。
    """

    def __init__(self, harness: EvaluationHarness) -> None:
        """初始化 Agent 对比器。

        Args:
            harness: 评测编排器实例。
        """
        self.harness = harness

    def compare(
        self,
        task: Task,
        agents: Sequence[Agent],
        n_trials: int = 5,
    ) -> dict[str, AgentMetrics]:
        """对同一任务横向对比多个 Agent。

        对每个 Agent 调用 harness.run_task()，然后计算 pass@k、pass^k、
        平均 token 消耗、平均耗时、平均成本、自纠正率。

        Args:
            task: 评测任务。
            agents: Agent 实现列表（满足 Agent Protocol）。
            n_trials: 每个 Agent 的试运行次数。

        Returns:
            映射：agent name -> AgentMetrics。
        """
        results: dict[str, AgentMetrics] = {}

        for agent in agents:
            logger.info(
                "运行 Agent '%s' 在任务 '%s'，共 %d 次试运行",
                agent.name,
                task.task_id,
                n_trials,
            )

            trials = self.harness.run_task(task, agent, n_trials=n_trials)

            n_total = len(trials)
            n_success = sum(1 for t in trials if t.success)

            # 计算 pass 指标
            pass_metrics = compute_pass_metrics(n_total, n_success, k=n_trials)

            # 聚合效率指标
            total_tokens = 0
            total_duration = 0.0
            total_cost = 0.0
            total_self_corrections = 0
            total_tool_calls = 0

            for trial in trials:
                total_tokens += trial.metrics.total_tokens
                total_duration += trial.metrics.total_duration
                total_cost += trial.metrics.cost_usd
                total_self_corrections += trial.metrics.self_correction_count
                total_tool_calls += trial.metrics.tool_call_count

            avg_tokens = total_tokens / n_total if n_total > 0 else 0.0
            avg_duration = total_duration / n_total if n_total > 0 else 0.0
            avg_cost = total_cost / n_total if n_total > 0 else 0.0

            # 自纠正率 = 自纠正次数 / 总 tool call 次数
            self_correction_rate = (
                total_self_corrections / total_tool_calls
                if total_tool_calls > 0
                else 0.0
            )

            metrics = AgentMetrics(
                agent_name=agent.name,
                n_success=n_success,
                n_total=n_total,
                pass_at_1=pass_metrics.pass_at_1,
                pass_at_k=pass_metrics.pass_at_k,
                pass_hat_k=pass_metrics.pass_hat_k,
                avg_tokens=avg_tokens,
                avg_duration=avg_duration,
                avg_cost=avg_cost,
                self_correction_rate=self_correction_rate,
            )

            results[agent.name] = metrics

            logger.info(
                "Agent '%s': pass@1=%.2f, pass@%d=%.2f, pass^%d=%.2f",
                agent.name,
                metrics.pass_at_1,
                n_trials,
                metrics.pass_at_k,
                n_trials,
                metrics.pass_hat_k,
            )

        return results

    def generate_report(self, results: dict[str, AgentMetrics]) -> str:
        """生成 Markdown 格式的对比报告。

        Args:
            results: compare() 返回的结果字典。

        Returns:
            Markdown 表格字符串。
        """
        if not results:
            return "# Agent 对比报告\n\n无结果。"

        lines = [
            "# Agent 对比报告",
            "",
            "| Agent | pass@1 | pass@5 | pass^5 | 平均 Tokens | 平均耗时(s) | 平均成本($) | 自纠正率 |",
            "|-------|--------|--------|--------|-------------|-------------|-------------|----------|",
        ]

        for m in results.values():
            lines.append(
                f"| {m.agent_name} "
                f"| {m.pass_at_1:.2f} "
                f"| {m.pass_at_k:.2f} "
                f"| {m.pass_hat_k:.2f} "
                f"| {m.avg_tokens:,.0f} "
                f"| {m.avg_duration:.2f} "
                f"| {m.avg_cost:.4f} "
                f"| {m.self_correction_rate:.2%} |"
            )

        lines.append("")
        return "\n".join(lines)
