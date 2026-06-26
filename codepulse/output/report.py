"""报告生成器。

生成 Markdown 格式的评测报告，包括：
- 单次试运行报告
- 多 Agent 对比报告
- 自进化归因报告
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.evolve.attribution import AttributionReport

# 维度显示名称映射
_DIMENSION_LABELS: dict[str, str] = {
    "correctness": "功能正确性",
    "process_quality": "过程质量",
    "efficiency": "效率成本",
    "robustness": "鲁棒安全",
    "alignment": "体验对齐",
}

# 维度权重
_DIMENSION_WEIGHTS: dict[str, float] = {
    "correctness": 30,
    "process_quality": 25,
    "efficiency": 15,
    "robustness": 20,
    "alignment": 10,
}

_PASS_THRESHOLD = 80


class ReportGenerator:
    """Markdown 报告生成器。

    Args:
        template_dir: Jinja2 模板目录（保留扩展用，当前未使用）。
    """

    def __init__(self, template_dir: str | None = None) -> None:
        self.template_dir = template_dir

    # ------------------------------------------------------------------
    # 单次试运行报告
    # ------------------------------------------------------------------

    def generate_trial_report(self, trial: Trial, task: Task) -> str:
        """生成单次试运行的 Markdown 报告。

        Args:
            trial: 试运行记录。
            task: 对应的评测任务。

        Returns:
            Markdown 格式报告字符串。
        """
        sections: list[str] = []

        # 标题
        sections.append(f"# 试运行报告 — {trial.trial_id}\n")

        # 任务信息
        sections.append("## 任务信息\n")
        sections.append("| 属性 | 值 |")
        sections.append("|------|-----|")
        sections.append(f"| 任务 ID | `{task.task_id}` |")
        sections.append(f"| 类别 | {task.category.value} |")
        sections.append(f"| 难度 | {task.difficulty.value} |")
        sections.append(f"| 语言 | {task.language} |")
        sections.append("")

        # 结果状态
        status = "通过" if trial.success else "未通过"
        sections.append(f"## 结果：{status}\n")

        # 总分
        total = sum(trial.scores.values())
        sections.append(f"**总分：{total:.1f} / 100**（通过阈值 {_PASS_THRESHOLD}）\n")

        # 各维度得分
        sections.append("## 维度得分\n")
        sections.append("| 维度 | 权重 | 得分 |")
        sections.append("|------|------|------|")
        for key, label in _DIMENSION_LABELS.items():
            weight = _DIMENSION_WEIGHTS.get(key, 0)
            score = trial.scores.get(key, 0.0)
            sections.append(f"| {label} | {weight:.0f} | {score:.1f} |")
        sections.append("")

        # 关键指标
        m = trial.metrics
        sections.append("## 关键指标\n")
        sections.append("| 指标 | 值 |")
        sections.append("|------|-----|")
        sections.append(f"| 总 Token | {m.total_tokens:,} |")
        sections.append(f"| 输入 Token | {m.input_tokens:,} |")
        sections.append(f"| 输出 Token | {m.output_tokens:,} |")
        sections.append(f"| 耗时 | {m.total_duration:.1f}s |")
        sections.append(f"| 工具调用次数 | {m.tool_call_count} |")
        sections.append(f"| 自纠正次数 | {m.self_correction_count} |")
        sections.append(f"| 费用 (USD) | ${m.cost_usd:.4f} |")
        sections.append("")

        # Agent 配置
        sections.append("## Agent 配置\n")
        ac = trial.agent_config
        sections.append(f"- **名称**: {ac.name}")
        sections.append(f"- **模型**: {ac.model}")
        sections.append(f"- **温度**: {ac.temperature}")
        sections.append(f"- **最大 Token**: {ac.max_tokens}")
        sections.append("")

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # 多 Agent 对比报告
    # ------------------------------------------------------------------

    def generate_comparison_report(self, results: dict[str, dict[str, Any]]) -> str:
        """生成多 Agent 对比的 Markdown 报告。

        Args:
            results: 映射 agent_name -> metrics 的字典。
                     每个 metrics 字典包含任意指标键值对。

        Returns:
            Markdown 格式对比表格字符串。
        """
        if not results:
            return "# 对比报告\n\n暂无数据。\n"

        sections: list[str] = []
        sections.append("# Agent 对比报告\n")

        # 收集所有指标键，保持稳定顺序
        all_keys: list[str] = []
        seen: set[str] = set()
        for metrics in results.values():
            for k in metrics:
                if k not in seen:
                    all_keys.append(k)
                    seen.add(k)

        # 表头
        header = "| Agent | " + " | ".join(all_keys) + " |"
        sep = "|-------|" + "|".join("------" for _ in all_keys) + "|"
        sections.append(header)
        sections.append(sep)

        # 数据行
        for agent_name, metrics in results.items():
            cells = [f"**{agent_name}**"]
            for k in all_keys:
                v = metrics.get(k, "—")
                cells.append(self._format_cell(v))
            sections.append("| " + " | ".join(cells) + " |")

        sections.append("")
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # 自进化归因报告
    # ------------------------------------------------------------------

    def generate_evolution_report(self, attribution: AttributionReport) -> str:
        """生成自进化归因的 Markdown 报告。

        Args:
            attribution: 归因报告。

        Returns:
            Markdown 格式归因分析字符串。
        """
        sections: list[str] = []
        sections.append("# 自进化归因报告\n")

        total = attribution.total

        sections.append("## 总览\n")
        sections.append("| 指标 | 值 |")
        sections.append("|------|-----|")
        sections.append(f"| 总样本数 | {total} |")
        sections.append(f"| 改进率 | {attribution.improvement_rate:.1%} |")
        sections.append(f"| 退化率 | {attribution.regression_rate:.1%} |")
        sections.append("")

        sections.append("## 四类归因\n")
        sections.append("| 归因类型 | 数量 | 占比 |")
        sections.append("|----------|------|------|")
        for label, count in [
            ("改进", attribution.improvements),
            ("退化", attribution.regressions),
            ("持续失败", attribution.persistent_failures),
            ("稳定成功", attribution.stable_successes),
        ]:
            pct = f"{count / total:.1%}" if total > 0 else "—"
            sections.append(f"| {label} | {count} | {pct} |")
        sections.append("")

        # 净变化判定
        net = attribution.improvements - attribution.regressions
        if net > 0:
            verdict = f"净改进 **+{net}**，自进化有效。"
        elif net < 0:
            verdict = f"净退化 **{net}**，需要排查退化原因。"
        else:
            verdict = "改进与退化持平，无净变化。"

        sections.append(f"## 结论\n\n{verdict}\n")

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _format_cell(value: Any) -> str:
        """格式化表格单元格值。"""
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)
