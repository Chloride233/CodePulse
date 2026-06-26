"""Layer 4: 可观测性层 — Trace 采集与分析。

Agent Trace 采集、Token 统计、黑洞模式检测、pass@k/pass^k 统计。
"""

from codepulse.observe.trace import TraceEvent, Transcript

__all__ = ["TraceEvent", "Transcript"]
