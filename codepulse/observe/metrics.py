"""指标计算 — pass@k、pass^k、效率指标。

基于多次试运行结果计算统计指标。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PassMetrics:
    """Pass 指标。"""

    pass_at_1: float  # 1 次至少成功 1 次的概率
    pass_at_k: float  # k 次至少成功 1 次的概率
    pass_hat_k: float  # k 次全部成功的概率
    k: int


def calc_pass_at_k(n_total: int, n_success: int, k: int = 1) -> float:
    """计算 pass@k。

    公式：1 - C(n-c, k) / C(n, k)

    Args:
        n_total: 总试运行次数。
        n_success: 成功次数。
        k: k 值。

    Returns:
        pass@k 值。
    """
    if n_total <= 0 or k <= 0:
        return 0.0
    if n_success >= n_total:
        return 1.0
    if n_success == 0:
        return 0.0
    if k > n_total:
        k = n_total
    # 1 - C(n-c, k) / C(n, k)
    return 1.0 - math.comb(n_total - n_success, k) / math.comb(n_total, k)


def calc_pass_hat_k(n_total: int, n_success: int, k: int = 5) -> float:
    """计算 pass^k（稳定性）。

    公式：(n_success / n_total) ^ k

    Args:
        n_total: 总试运行次数。
        n_success: 成功次数。
        k: k 值。

    Returns:
        pass^k 值。
    """
    if n_total <= 0:
        return 0.0
    return (n_success / n_total) ** k


def compute_pass_metrics(n_total: int, n_success: int, k: int = 5) -> PassMetrics:
    """计算完整的 Pass 指标。

    Args:
        n_total: 总试运行次数。
        n_success: 成功次数。
        k: k 值。

    Returns:
        PassMetrics。
    """
    return PassMetrics(
        pass_at_1=calc_pass_at_k(n_total, n_success, 1),
        pass_at_k=calc_pass_at_k(n_total, n_success, k),
        pass_hat_k=calc_pass_hat_k(n_total, n_success, k),
        k=k,
    )
