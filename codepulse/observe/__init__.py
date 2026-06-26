"""Layer 4: 可观测性层 — Trace 采集与分析。

Agent Trace 采集、Token 统计、黑洞模式检测、pass@k/pass^k 统计。
"""

from codepulse.observe.blackhole import BlackholeDetector
from codepulse.observe.collector import TraceCollector
from codepulse.observe.comparator import AgentComparator
from codepulse.observe.metrics import calc_pass_at_k, calc_pass_hat_k, compute_pass_metrics
from codepulse.observe.trace import EventType, TraceEvent, Transcript

__all__ = [
    "AgentComparator",
    "BlackholeDetector",
    "EventType",
    "TraceCollector",
    "TraceEvent",
    "Transcript",
    "calc_pass_at_k",
    "calc_pass_hat_k",
    "compute_pass_metrics",
]
