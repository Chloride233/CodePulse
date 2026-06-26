"""评分系统 — 100 分扣分制。

五维度评测体系：
- 功能正确性（P0，30 分）
- 过程质量（P1，25 分）
- 效率成本（P1，15 分）
- 鲁棒安全（P0，20 分）
- 体验对齐（P2，10 分）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScoreDimension(StrEnum):
    """评分维度。"""

    FUNCTIONAL = "functional"
    PROCESS = "process"
    EFFICIENCY = "efficiency"
    ROBUSTNESS = "robustness"
    ALIGNMENT = "alignment"


# 各维度满分
MAX_SCORES: dict[ScoreDimension, int] = {
    ScoreDimension.FUNCTIONAL: 30,
    ScoreDimension.PROCESS: 25,
    ScoreDimension.EFFICIENCY: 15,
    ScoreDimension.ROBUSTNESS: 20,
    ScoreDimension.ALIGNMENT: 10,
}

# 通过阈值
PASS_THRESHOLD = 80


@dataclass(frozen=True)
class ScoringConfig:
    """评分配置。"""

    pass_threshold: int = PASS_THRESHOLD
    max_scores: dict[ScoreDimension, int] | None = None

    def __post_init__(self) -> None:
        if self.max_scores is None:
            object.__setattr__(self, "max_scores", MAX_SCORES.copy())


def aggregate_scores(dimension_scores: dict[ScoreDimension, float]) -> float:
    """聚合各维度分数为总分。

    Args:
        dimension_scores: 各维度得分（0-1 之间的比例）。

    Returns:
        总分（0-100）。
    """
    total = 0.0
    for dim, ratio in dimension_scores.items():
        max_score = MAX_SCORES.get(dim, 0)
        total += max_score * max(0.0, min(1.0, ratio))
    return round(total, 2)


def is_passed(total_score: float, threshold: int = PASS_THRESHOLD) -> bool:
    """判断是否通过。

    Args:
        total_score: 总分。
        threshold: 通过阈值。

    Returns:
        是否通过。
    """
    return total_score >= threshold
