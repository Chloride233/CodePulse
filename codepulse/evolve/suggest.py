"""Suggestion engine — 基于评测分数的优化建议。

Analyzes score patterns across dimensions and produces human-readable,
actionable suggestions for improving agent performance.

Usage::

    from codepulse.evolve.suggest import SuggestionEngine

    engine = SuggestionEngine()
    suggestions = engine.analyze(scores_dict)
    for s in suggestions:
        print(s.title, s.priority, s.action)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codepulse.eval.scoring import MAX_SCORES, ScoreDimension

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class SuggestionPriority:
    """Priority levels for suggestions."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Suggestion:
    """An actionable improvement suggestion derived from evaluation scores.

    Attributes:
        title: Short headline (e.g. ``"Functional correctness needs attention"``).
        priority: One of ``SuggestionPriority.*``.
        dimension: The :class:`ScoreDimension` this relates to.
        score: The current score ratio (0-1).
        threshold: The recommended minimum.
        action: Human-readable action description in Chinese.
        details: Optional additional context or metrics.
    """

    title: str
    priority: str
    dimension: str
    score: float
    threshold: float
    action: str
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Built-in suggestion rules
# ---------------------------------------------------------------------------

_SUGGESTION_RULES: list[dict[str, Any]] = [
    {
        "dimension": ScoreDimension.FUNCTIONAL,
        "threshold": 0.8,
        "title": "功能正确性不足",
        "action": (
            "检查 Agent 是否准确理解了任务需求；增加系统提示中的格式约束；"
            "考虑使用 few-shot 示例引导输出；验证测试用例是否完整覆盖了需求。"
        ),
        "priority": SuggestionPriority.CRITICAL,
    },
    {
        "dimension": ScoreDimension.ROBUSTNESS,
        "threshold": 0.7,
        "title": "代码质量有待提升",
        "action": (
            "在系统提示中加入代码规范要求（ruff/mypy/bandit）；"
            "增加自检步骤让 Agent 在提交前审查自己的代码；"
            "考虑使用更严格的 lint 配置。"
        ),
        "priority": SuggestionPriority.HIGH,
    },
    {
        "dimension": ScoreDimension.EFFICIENCY,
        "threshold": 0.7,
        "title": "Token 或耗时偏高",
        "action": (
            "检查 Agent 是否进行了不必要的循环或重复调用；"
            "精简系统提示模板；考虑使用更长上下文的模型减少重试；"
            "增加 max_iterations 限制或实施 early-stop 策略。"
        ),
        "priority": SuggestionPriority.MEDIUM,
    },
    {
        "dimension": ScoreDimension.PROCESS,
        "threshold": 0.7,
        "title": "过程质量有待优化",
        "action": (
            "检查 Agent 是否规划了足够的中间步骤；"
            "引导 Agent 采用「分析-实施-验证」的循环；"
            "增加 self-correction 机制。"
        ),
        "priority": SuggestionPriority.MEDIUM,
    },
    {
        "dimension": ScoreDimension.ALIGNMENT,
        "threshold": 0.6,
        "title": "体验对齐度不足",
        "action": (
            "检查 Agent 的输出格式是否符合用户预期；"
            "在系统提示中加入输出格式示例；"
            "考虑使用 Chain-of-Thought 提升输出质量。"
        ),
        "priority": SuggestionPriority.LOW,
    },
]

# Cross-dimension patterns — when multiple dimensions are weak
_CROSS_PATTERNS: list[dict[str, Any]] = [
    {
        "dims": [ScoreDimension.FUNCTIONAL, ScoreDimension.PROCESS],
        "threshold": 0.6,
        "title": "基础能力薄弱",
        "action": (
            "功能正确性和过程质量同时偏低，说明 Agent 可能缺乏基础编程能力。"
            "建议：选择更强的基座模型；增加领域相关的 few-shot 示例；"
            "考虑使用 Agent 框架（如 LangChain）提供的规划能力。"
        ),
        "priority": SuggestionPriority.CRITICAL,
    },
    {
        "dims": [ScoreDimension.EFFICIENCY, ScoreDimension.ROBUSTNESS],
        "threshold": 0.6,
        "title": "代码质量与效率双低",
        "action": (
            "Agent 生成的代码既低效又不符合规范。"
            "建议：在提示中加入明确的「先设计再编码」指令；"
            "使用更强的模型；考虑使用代码优化工具作为后处理步骤。"
        ),
        "priority": SuggestionPriority.HIGH,
    },
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SuggestionEngine:
    """Analyzes evaluation scores and generates improvement suggestions.

    Usage::

        engine = SuggestionEngine()
        suggestions = engine.analyze(scores)
    """

    def analyze(
        self,
        scores: dict[str, float] | dict[ScoreDimension, float],
    ) -> list[Suggestion]:
        """Analyze scores and produce improvement suggestions.

        Args:
            scores: Mapping of dimension → ratio score (0-1).
                    Keys can be ``ScoreDimension`` enum or string names.

        Returns:
            List of :class:`Suggestion` objects, sorted by priority.
        """
        normalized: dict[str, float] = {}
        for key, val in scores.items():
            if isinstance(key, ScoreDimension):
                normalized[key.value] = val
            else:
                normalized[key] = val

        suggestions: list[Suggestion] = []

        # Per-dimension rules
        for rule in _SUGGESTION_RULES:
            dim = rule["dimension"]
            score = normalized.get(dim.value, 1.0)
            if score < rule["threshold"]:
                suggestions.append(
                    Suggestion(
                        title=rule["title"],
                        priority=rule["priority"],
                        dimension=dim.value,
                        score=score,
                        threshold=rule["threshold"],
                        action=rule["action"],
                        details={
                            "max_score": MAX_SCORES.get(dim, 0),
                            "weighted_score": score * MAX_SCORES.get(dim, 0),
                        },
                    )
                )

        # Cross-dimension patterns
        for pattern in _CROSS_PATTERNS:
            dims = pattern["dims"]
            all_below = all(
                normalized.get(d.value, 1.0) < pattern["threshold"]
                for d in dims
            )
            if all_below:
                dim_values = {d.value: normalized.get(d.value, 0) for d in dims}
                suggestions.append(
                    Suggestion(
                        title=pattern["title"],
                        priority=pattern["priority"],
                        dimension="+".join(d.value for d in dims),
                        score=0.0,
                        threshold=pattern["threshold"],
                        action=pattern["action"],
                        details=dim_values,
                    )
                )

        # Sort by priority
        priority_order = {
            SuggestionPriority.CRITICAL: 0,
            SuggestionPriority.HIGH: 1,
            SuggestionPriority.MEDIUM: 2,
            SuggestionPriority.LOW: 3,
        }
        suggestions.sort(key=lambda s: priority_order.get(s.priority, 99))

        return suggestions

    def summarize(self, suggestions: list[Suggestion]) -> str:
        """Format suggestions as a Markdown summary.

        Args:
            suggestions: Output from :meth:`analyze`.

        Returns:
            Markdown string.
        """
        if not suggestions:
            return "✅ 所有维度得分均在阈值以上，无需优化建议。"

        parts = ["## 优化建议\n"]
        for s in suggestions:
            emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                s.priority, "⚪"
            )
            parts.append(f"### {emoji} [{s.priority.upper()}] {s.title}")
            parts.append(f"- **维度**: {s.dimension}")
            parts.append(f"- **当前得分**: {s.score:.2f} / {s.threshold:.2f}（阈值）")
            parts.append(f"- **建议**: {s.action}")
            parts.append("")

        return "\n".join(parts)

    def analyze_benchmark(
        self, benchmark_results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze a full benchmark run across all tasks.

        Args:
            benchmark_results: List of per-task result dicts.

        Returns:
            Aggregated analysis with average scores and suggestions.
        """
        if not benchmark_results:
            return {"avg_scores": {}, "suggestions": [], "pass_rate": 0.0}

        # Aggregate scores
        dim_scores: dict[str, float] = {}
        dim_counts: dict[str, int] = {}
        n_passed = 0

        for task_result in benchmark_results:
            if task_result.get("pass_rate", 0) >= 0.8:
                n_passed += 1
            for dim, score in task_result.get("avg_scores", {}).items():
                dim_scores[dim] = dim_scores.get(dim, 0) + score
                dim_counts[dim] = dim_counts.get(dim, 0) + 1

        avg_scores: dict[str, float] = {}
        for dim in dim_scores:
            avg_scores[dim] = dim_scores[dim] / dim_counts[dim]

        suggestions = self.analyze(avg_scores)
        pass_rate = n_passed / len(benchmark_results)

        return {
            "avg_scores": avg_scores,
            "suggestions": suggestions,
            "pass_rate": pass_rate,
            "n_total": len(benchmark_results),
            "n_passed": n_passed,
        }
