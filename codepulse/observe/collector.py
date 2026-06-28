"""Trace 采集器 — 会话管理与持久化。

管理 Agent 会话生命周期，将 Trace 写入 JSONL 文件。
"""

from __future__ import annotations

import json
from pathlib import Path

from codepulse.observe.trace import TraceEvent, Transcript


class TraceCollector:
    """Trace 采集器。

    负责会话创建、事件记录、会话结束和 Trace 持久化。

    Args:
        output_dir: Trace 文件输出根目录。
    """

    def __init__(self, output_dir: str = "results") -> None:
        self._output_dir = Path(output_dir)

    def start_session(self, session_id: str) -> Transcript:
        """创建新的会话。

        Args:
            session_id: 会话唯一标识。

        Returns:
            新建的 Transcript 对象。
        """
        return Transcript(session_id=session_id)

    def record_event(self, transcript: Transcript, event: TraceEvent) -> None:
        """向会话追加事件并更新指标。

        Args:
            transcript: 当前会话的 Transcript。
            event: 待记录的 Trace 事件。
        """
        transcript.add_event(event)

    def end_session(self, transcript: Transcript) -> None:
        """结束会话，汇总最终指标。

        当前会重算 total_duration 确保一致性。
        后续可扩展校验、摘要生成等逻辑。

        Args:
            transcript: 待结束的 Transcript。
        """
        # 重算总耗时，避免浮点累加误差
        transcript.total_duration = sum(e.duration for e in transcript.events)

    def save_trace(self, transcript: Transcript, task_id: str, trial_id: str) -> Path:
        """将 Transcript 事件写入 JSONL 文件。

        文件路径: output_dir / task_id / "{trial_id}-trace.jsonl"
        每行一个 JSON 对象，对应一个 TraceEvent。

        Args:
            transcript: 已结束的 Transcript。
            task_id: 任务标识。
            trial_id: 试验标识。

        Returns:
            写入的文件路径。
        """
        trace_dir = self._output_dir / task_id
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_path = trace_dir / f"{trial_id}-trace.jsonl"

        with trace_path.open("w", encoding="utf-8") as f:
            for event in transcript.events:
                record = {
                    "timestamp": event.timestamp,
                    "event_type": event.event_type.value,
                    "content": event.content,
                    "token_usage": event.token_usage,
                    "duration": event.duration,
                    "span_kind": event.span_kind.value if event.span_kind is not None else None,
                    "parent_id": event.parent_id,
                    "span_id": event.span_id,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return trace_path
