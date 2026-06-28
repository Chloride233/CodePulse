"""四类样本归因。

将样本分为四类：
- 改进（improvement）：未通过 → 通过
- 退化（regression）：通过 → 未通过
- 持续失败（persistent_failure）：未通过 → 未通过
- 稳定成功（stable_success）：通过 → 通过
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from codepulse.eval.scoring import PASS_THRESHOLD


class AttributionType(StrEnum):
    """归因类型。"""

    IMPROVEMENT = "improvement"
    REGRESSION = "regression"
    PERSISTENT_FAILURE = "persistent_failure"
    STABLE_SUCCESS = "stable_success"


@dataclass(frozen=True)
class AttributionReport:
    """归因报告。"""

    improvements: int = 0
    regressions: int = 0
    persistent_failures: int = 0
    stable_successes: int = 0
    improvement_rate: float = 0.0
    regression_rate: float = 0.0

    @property
    def total(self) -> int:
        """总样本数。"""
        return self.improvements + self.regressions + self.persistent_failures + self.stable_successes


class SampleAttribution:
    """样本归因器。"""

    def __init__(self, pass_threshold: float = PASS_THRESHOLD) -> None:
        self.pass_threshold = pass_threshold

    def classify(self, old_score: float, new_score: float) -> AttributionType:
        """分类单个样本。

        Args:
            old_score: 旧分数。
            new_score: 新分数。

        Returns:
            归因类型。
        """
        old_pass = old_score >= self.pass_threshold
        new_pass = new_score >= self.pass_threshold

        if not old_pass and new_pass:
            return AttributionType.IMPROVEMENT
        elif old_pass and not new_pass:
            return AttributionType.REGRESSION
        elif not old_pass and not new_pass:
            return AttributionType.PERSISTENT_FAILURE
        else:
            return AttributionType.STABLE_SUCCESS

    def classify_all(
        self,
        old_scores: dict[str, float],
        new_scores: dict[str, float],
    ) -> dict[str, AttributionType]:
        """分类所有样本。

        Args:
            old_scores: 旧分数字典，key 为 task_id。
            new_scores: 新分数字典，key 为 task_id。

        Returns:
            归因字典，key 为 task_id。
        """
        attributions: dict[str, AttributionType] = {}
        for task_id in set(old_scores) | set(new_scores):
            old = old_scores.get(task_id, 0.0)
            new = new_scores.get(task_id, 0.0)
            attributions[task_id] = self.classify(old, new)
        return attributions

    def report(self, attributions: dict[str, AttributionType]) -> AttributionReport:
        """生成归因报告。

        Args:
            attributions: 归因字典。

        Returns:
            归因报告。
        """
        counts = Counter(attributions.values())
        total = len(attributions)

        return AttributionReport(
            improvements=counts.get(AttributionType.IMPROVEMENT, 0),
            regressions=counts.get(AttributionType.REGRESSION, 0),
            persistent_failures=counts.get(AttributionType.PERSISTENT_FAILURE, 0),
            stable_successes=counts.get(AttributionType.STABLE_SUCCESS, 0),
            improvement_rate=counts.get(AttributionType.IMPROVEMENT, 0) / max(total, 1),
            regression_rate=counts.get(AttributionType.REGRESSION, 0) / max(total, 1),
        )
