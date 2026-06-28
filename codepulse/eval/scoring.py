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


def weighted_total(str_scores: dict[str, float]) -> float:
    """从字符串键的分数字典计算加权重总分。

    Args:
        str_scores: 维度名 → 比率（0-1）的映射。

    Returns:
        总分（0-100）。无法识别的维度名将被忽略。
    """
    dim_scores: dict[ScoreDimension, float] = {}
    for dim_name, ratio in str_scores.items():
        try:
            dim = ScoreDimension(dim_name)
            dim_scores[dim] = ratio
        except ValueError:
            continue
    return aggregate_scores(dim_scores)


def is_passed(total_score: float, threshold: int = PASS_THRESHOLD) -> bool:
    """判断是否通过。

    Args:
        total_score: 总分。
        threshold: 通过阈值。

    Returns:
        是否通过。
    """
    return total_score >= threshold


# 稳定性容忍阈值配置
# 关键决策类: 0% 容忍 — 一次失败即失败
# 辅助分析类: ≤10% 容忍 — 90% 通过即可
# 创意生成类: ≤40% 容忍 — 60% 通过即算成功
STABILITY_TOLERANCE: dict[str, float] = {
    "critical": 1.0,    # 必须 100% pass
    "normal": 0.8,      # 80% pass
    "tolerant": 0.6,    # 60% pass
}


def is_stable_pass(pass_rate: float, tolerance: str = "normal") -> bool:
    """Check if pass rate meets stability tolerance threshold.

    Args:
        pass_rate: Fraction of trials that passed (0.0 to 1.0).
        tolerance: Stability tier — "critical", "normal", or "tolerant".

    Returns:
        True if pass_rate meets the tolerance requirement.
    """
    threshold = STABILITY_TOLERANCE.get(tolerance, 0.8)
    return pass_rate >= threshold


def sequence_similarity(seq_a: list[str], seq_b: list[str]) -> float:
    """计算两个序列的 LCS 相似度。

    基于最长公共子序列（LCS）算法，衡量两个工具调用序列的匹配程度。
    结果 ∈ [0, 1]，1 表示完全一致。

    Args:
        seq_a: 第一个序列（如基线工具调用行为）。
        seq_b: 第二个序列（如当前 Trial 工具调用行为）。

    Returns:
        相似度得分（0-1）。
    """
    n, m = len(seq_a), len(seq_b)
    if not n and not m:
        return 1.0
    if not n or not m:
        return 0.0

    # DP 表: dp[i][j] = LCS 长度 for seq_a[:i] and seq_b[:j]
    dp: list[list[int]] = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs_len = dp[n][m]
    return round(2.0 * lcs_len / (n + m), 4)
