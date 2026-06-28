"""共享 Trace 类型 — EventType / TraceEvent / Transcript。

从 observe 层提取到共享层，消除 env/mock_agent（Layer 1）
和 agent/real_agent 对 observe（Layer 4）的向上依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """事件类型。"""

    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    REFLECTION = "reflection"
    ERROR = "error"


@dataclass(frozen=True)
class TraceEvent:
    """单个 Trace 事件。"""

    timestamp: float
    event_type: EventType
    content: dict[str, Any]
    token_usage: dict[str, int] = field(default_factory=dict)
    duration: float = 0.0


@dataclass
class Transcript:
    """完整的 Agent 执行轨迹。"""

    session_id: str
    agent_config: dict[str, Any] = field(default_factory=dict)
    events: list[TraceEvent] = field(default_factory=list)
    total_tokens: int = 0
    total_duration: float = 0.0
    tool_call_count: int = 0

    def add_event(self, event: TraceEvent) -> None:
        """添加事件。"""
        self.events.append(event)
        self._update_metrics(event)

    def _update_metrics(self, event: TraceEvent) -> None:
        """更新指标。"""
        self.total_tokens += sum(event.token_usage.values())
        self.total_duration += event.duration
        if event.event_type == EventType.TOOL_CALL:
            self.tool_call_count += 1

    def token_breakdown(self) -> list[dict[str, str | int]]:
        """获取逐 token 消耗明细（按事件）。"""
        steps: list[dict[str, str | int]] = []
        for i, ev in enumerate(self.events):
            total = sum(ev.token_usage.values())
            steps.append({
                "step": i,
                "event_type": ev.event_type.value,
                "tokens": total,
                "duration_ms": int(ev.duration * 1000),
            })
        return steps
