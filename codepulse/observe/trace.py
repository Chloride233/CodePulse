"""Trace 采集 — Agent 行为记录。

从 shared/trace_types 导出类型以保持向后兼容。
"""

from codepulse.shared.trace_types import EventType, TraceEvent, Transcript

__all__ = ["EventType", "TraceEvent", "Transcript"]
