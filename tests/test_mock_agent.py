"""Tests for MockAgent — 确定性 Agent 用于评测 Harness 集成测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codepulse.data.models import (
    Difficulty,
    Task,
    TaskCategory,
    TaskSource,
)
from codepulse.data.protocols import Agent
from codepulse.env.mock_agent import MockAgent
from codepulse.observe.trace import EventType, Transcript


@pytest.fixture
def sample_task(sample_task_data: dict) -> Task:
    """从 sample_task_data fixture 构造 Task 实例。"""
    return Task(
        task_id=sample_task_data["task_id"],
        source=TaskSource(sample_task_data["source"]),
        category=TaskCategory(sample_task_data["category"]),
        difficulty=Difficulty(sample_task_data["difficulty"]),
        language=sample_task_data["language"],
        input=sample_task_data["input"],
        ground_truth=sample_task_data["ground_truth"],
    )


@pytest.fixture
def mock_sandbox() -> MagicMock:
    """Mock SandboxManager，避免调用真实 Docker daemon。"""
    return MagicMock()


class TestMockAgentProtocol:
    """测试 MockAgent 满足 Agent 协议。"""

    def test_mock_agent_satisfies_agent_protocol(self) -> None:
        """MockAgent 必须满足 runtime_checkable 的 Agent Protocol。"""
        agent = MockAgent()
        assert isinstance(agent, Agent)

    def test_mock_agent_has_name_property(self) -> None:
        """MockAgent 必须提供 name 属性。"""
        agent = MockAgent()
        assert hasattr(agent, "name")
        assert isinstance(agent.name, str)

    def test_mock_agent_has_model_property(self) -> None:
        """MockAgent 必须提供 model 属性。"""
        agent = MockAgent()
        assert hasattr(agent, "model")
        assert isinstance(agent.model, str)

    def test_mock_agent_has_run_method(self) -> None:
        """MockAgent 必须提供 run 方法。"""
        agent = MockAgent()
        assert callable(getattr(agent, "run", None))


class TestMockAgentDefaults:
    """测试 MockAgent 默认值。"""

    def test_default_name(self) -> None:
        """默认 name 应为 'mock'。"""
        agent = MockAgent()
        assert agent.name == "mock"

    def test_default_model(self) -> None:
        """默认 model 应为 'mock-model'。"""
        agent = MockAgent()
        assert agent.model == "mock-model"


class TestMockAgentCustomConfig:
    """测试 MockAgent 自定义配置。"""

    def test_custom_name(self) -> None:
        """应支持自定义 name。"""
        agent = MockAgent(name="my-agent")
        assert agent.name == "my-agent"

    def test_custom_model(self) -> None:
        """应支持自定义 model。"""
        agent = MockAgent(model="deepseek-chat")
        assert agent.model == "deepseek-chat"

    def test_custom_name_and_model(self) -> None:
        """应同时支持自定义 name 和 model。"""
        agent = MockAgent(name="test-agent", model="gpt-4")
        assert agent.name == "test-agent"
        assert agent.model == "gpt-4"


class TestMockAgentRun:
    """测试 MockAgent.run() 行为。"""

    def test_run_returns_transcript(
        self, sample_task: Task, mock_sandbox: MagicMock
    ) -> None:
        """run() 必须返回 Transcript 实例。"""
        agent = MockAgent()
        result = agent.run(sample_task, mock_sandbox)
        assert isinstance(result, Transcript)

    def test_run_transcript_session_id_matches_task_id(
        self, sample_task: Task, mock_sandbox: MagicMock
    ) -> None:
        """Transcript.session_id 必须等于 task.task_id。"""
        agent = MockAgent()
        transcript = agent.run(sample_task, mock_sandbox)
        assert transcript.session_id == sample_task.task_id

    def test_run_transcript_has_events(
        self, sample_task: Task, mock_sandbox: MagicMock
    ) -> None:
        """Transcript 必须包含事件。"""
        agent = MockAgent()
        transcript = agent.run(sample_task, mock_sandbox)
        assert len(transcript.events) > 0

    def test_run_transcript_has_llm_call_event(
        self, sample_task: Task, mock_sandbox: MagicMock
    ) -> None:
        """Transcript 必须包含 LLM_CALL 事件。"""
        agent = MockAgent()
        transcript = agent.run(sample_task, mock_sandbox)
        event_types = {e.event_type for e in transcript.events}
        assert EventType.LLM_CALL in event_types

    def test_run_transcript_has_tool_call_event(
        self, sample_task: Task, mock_sandbox: MagicMock
    ) -> None:
        """Transcript 必须包含 TOOL_CALL 事件。"""
        agent = MockAgent()
        transcript = agent.run(sample_task, mock_sandbox)
        event_types = {e.event_type for e in transcript.events}
        assert EventType.TOOL_CALL in event_types

    def test_run_transcript_has_both_event_types(
        self, sample_task: Task, mock_sandbox: MagicMock
    ) -> None:
        """Transcript 必须同时包含 LLM_CALL 和 TOOL_CALL 事件。"""
        agent = MockAgent()
        transcript = agent.run(sample_task, mock_sandbox)
        event_types = {e.event_type for e in transcript.events}
        assert event_types == {EventType.LLM_CALL, EventType.TOOL_CALL}

    def test_run_transcript_agent_config_contains_name(
        self, sample_task: Task, mock_sandbox: MagicMock
    ) -> None:
        """Transcript.agent_config 必须包含 agent 的 name。"""
        agent = MockAgent(name="test-agent", model="test-model")
        transcript = agent.run(sample_task, mock_sandbox)
        assert transcript.agent_config["name"] == "test-agent"
        assert transcript.agent_config["model"] == "test-model"
