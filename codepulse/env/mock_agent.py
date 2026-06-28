"""MockAgent — 确定性 Agent，用于评测 Harness 零 LLM 开销的集成测试。

不调用任何真实模型，返回固定结构的 Transcript，
确保评测管线（Trace → Grader → Score → Report）可独立于 LLM 运行。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from codepulse.shared.trace_types import EventType, TraceEvent, Transcript

if TYPE_CHECKING:
    from codepulse.data.models import Task
    from codepulse.env.sandbox import SandboxManager


class MockAgent:
    """确定性 Agent，满足 :class:`Agent` Protocol。

    每次 ``run()`` 返回固定结构的 Transcript：一条 LLM_CALL 事件 + 一条
    TOOL_CALL 事件。不调用真实 LLM，不依赖 Docker，用于验证评测管线。

    Attributes:
        name: 人类可读的 Agent 名称。
        model: 传给 LiteLLM 的模型标识（MockAgent 中为占位符）。
    """

    def __init__(
        self,
        name: str = "mock",
        model: str = "mock-model",
    ) -> None:
        self._name = name
        self._model = model

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    def run(self, task: Task, sandbox: SandboxManager) -> Transcript:
        """执行任务并返回合成 Transcript。

        Args:
            task: 评测任务。
            sandbox: 沙箱管理器（MockAgent 不实际使用）。

        Returns:
            包含两条合成事件的 Transcript。
        """
        transcript = Transcript(
            session_id=task.task_id,
            agent_config={"name": self._name, "model": self._model},
        )

        now = time.time()

        # 合成 LLM_CALL 事件
        llm_event = TraceEvent(
            timestamp=now,
            event_type=EventType.LLM_CALL,
            content={"prompt": task.input.get("prompt", ""), "response": "mock response"},
            token_usage={"input": 100, "output": 50},
            duration=0.1,
        )
        transcript.add_event(llm_event)

        # 合成 TOOL_CALL 事件
        tool_event = TraceEvent(
            timestamp=now + 0.1,
            event_type=EventType.TOOL_CALL,
            content={"tool": "echo", "command": "hello"},
            duration=0.0,
        )
        transcript.add_event(tool_event)

        return transcript
