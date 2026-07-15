"""Tests for codepulse.agent.real_agent module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from codepulse.agent.real_agent import RealAgent, _safe_int
from codepulse.observe.trace import EventType


def _make_task() -> MagicMock:
    """Create a mock task."""
    task = MagicMock()
    task.task_id = "test-001"
    task.language = "python"
    task.input = {
        "description": "Fix the bug in function add()",
        "input_code": "def add(a, b):\n    return a - b",
    }
    task.ground_truth = {
        "expected_output": "def add(a, b): return a + b",
        "test_cases": ["assert add(1, 2) == 3"],
    }
    return task


def _make_llm_response(
    content: str = "",
    tool_calls: list | None = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> MagicMock:
    """Create a mock LLM response."""
    response = MagicMock()
    choice = MagicMock()
    message = MagicMock()

    message.content = content
    message.tool_calls = tool_calls

    choice.message = message
    choice.finish_reason = "stop" if not tool_calls else "tool_calls"
    response.choices = [choice]
    response.model = "provider-model-v1"

    # Usage
    usage = MagicMock()
    usage.prompt_tokens = input_tokens
    usage.completion_tokens = output_tokens
    usage.prompt_tokens_details = None
    response.usage = usage

    return response


def _make_tool_call(name: str, arguments: dict, call_id: str = "call_1") -> MagicMock:
    """Create a mock tool call."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


class TestSafeInt:
    """Tests for _safe_int helper."""

    def test_int_input(self) -> None:
        assert _safe_int(42) == 42

    def test_string_input(self) -> None:
        assert _safe_int("100") == 100

    def test_none_input(self) -> None:
        assert _safe_int(None) == 0

    def test_invalid_string(self) -> None:
        assert _safe_int("abc") == 0


class TestRealAgentInit:
    """Tests for RealAgent initialization."""

    def test_default_values(self) -> None:
        agent = RealAgent()
        assert agent.name == "real-agent"
        assert agent.model == "deepseek-chat"

    def test_custom_values(self) -> None:
        agent = RealAgent(
            name="my-agent",
            model="gpt-4o",
            max_tokens=8192,
            temperature=0.5,
            max_iterations=10,
        )
        assert agent.name == "my-agent"
        assert agent.model == "gpt-4o"


class TestRealAgentBuildTaskMessage:
    """Tests for _build_task_message."""

    def test_full_task(self) -> None:
        agent = RealAgent()
        task = _make_task()
        msg = agent._build_task_message(task)

        assert "Fix the bug" in msg
        assert "def add(a, b)" in msg
        assert "assert add(1, 2) == 3" in msg

    def test_minimal_task(self) -> None:
        agent = RealAgent()
        task = MagicMock()
        task.input = {"description": "Do something"}
        task.ground_truth = {}

        msg = agent._build_task_message(task)
        assert "Do something" in msg


class TestRealAgentExtractUsage:
    """Tests for _extract_usage."""

    def test_standard_format(self) -> None:
        agent = RealAgent()
        response = MagicMock()
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens"])
        usage.prompt_tokens = 100
        usage.completion_tokens = 50
        response.usage = usage

        result = agent._extract_usage(response)
        assert result["input"] == 100
        assert result["output"] == 50
        assert result["cache"] == 0

    def test_deepseek_cache_format(self) -> None:
        agent = RealAgent()
        response = MagicMock()
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "cache_hit_input_tokens"])
        usage.prompt_tokens = 200
        usage.completion_tokens = 80
        usage.cache_hit_input_tokens = 150
        response.usage = usage

        result = agent._extract_usage(response)
        assert result["cache"] == 150

    def test_no_usage(self) -> None:
        agent = RealAgent()
        response = MagicMock()
        response.usage = None

        result = agent._extract_usage(response)
        assert result == {"input": 0, "output": 0, "cache": 0}


class TestRealAgentExecuteTool:
    """Tests for _execute_tool."""

    def test_known_tool(self) -> None:
        agent = RealAgent()
        registry = MagicMock()
        tool = MagicMock()
        tool.execute.return_value = MagicMock(output="result", error="", success=True)
        registry.get.return_value = tool
        registry.names = ["test_tool"]

        result = agent._execute_tool(registry, "test_tool", {"arg": "val"})
        assert result.success is True

    def test_unknown_tool(self) -> None:
        agent = RealAgent()
        registry = MagicMock()
        registry.get.return_value = None
        registry.names = ["known_tool"]

        result = agent._execute_tool(registry, "unknown", {})
        assert result.success is False
        assert "Unknown tool" in result.error

    def test_tool_exception(self) -> None:
        agent = RealAgent()
        registry = MagicMock()
        tool = MagicMock()
        tool.execute.side_effect = RuntimeError("boom")
        registry.get.return_value = tool
        registry.names = ["crash_tool"]

        result = agent._execute_tool(registry, "crash_tool", {})
        assert result.success is False
        assert "boom" in result.error


class TestRealAgentRun:
    """Tests for RealAgent.run (integration with mocked LLM)."""

    @patch("litellm.completion")
    def test_simple_task_no_tools(self, mock_completion: MagicMock) -> None:
        """Agent stops when LLM returns no tool calls."""
        agent = RealAgent(max_iterations=5)
        task = _make_task()
        sandbox = MagicMock()

        # LLM 直接返回最终答案
        response = _make_llm_response(content="Task completed: fixed add function")
        mock_completion.return_value = response

        transcript = agent.run(task, sandbox)

        assert transcript.session_id.startswith("test-001")
        assert len(transcript.events) == 1  # one LLM call
        assert transcript.events[0].event_type == EventType.LLM_CALL
        assert transcript.agent_config["provider_model_versions"] == [
            "provider-model-v1"
        ]

    @patch("litellm.completion")
    def test_unknown_profile_tool_fails_before_model_call(
        self, mock_completion: MagicMock
    ) -> None:
        agent = RealAgent(tool_names=["read_file", "missing_tool"])

        try:
            agent.run(_make_task(), MagicMock())
        except ValueError as exc:
            assert "missing_tool" in str(exc)
        else:
            raise AssertionError("unknown profile tool should fail before execution")

        mock_completion.assert_not_called()

    @patch("litellm.completion")
    def test_task_with_tool_calls(self, mock_completion: MagicMock) -> None:
        """Agent executes tools and continues conversation."""
        agent = RealAgent(max_iterations=5)
        task = _make_task()
        sandbox = MagicMock()

        # 第一次调用：LLM 返回工具调用
        tool_call = _make_tool_call("execute", {"command": "echo hello"})
        response1 = _make_llm_response(
            content="Let me test",
            tool_calls=[tool_call],
        )

        # 第二次调用：LLM 返回最终答案
        response2 = _make_llm_response(content="Done!")

        mock_completion.side_effect = [response1, response2]

        # Mock sandbox execute for the tool
        sandbox._active_container = MagicMock()
        exec_result = MagicMock()
        exec_result.exit_code = 0
        exec_result.stdout = "hello"
        exec_result.stderr = ""
        sandbox.execute.return_value = exec_result

        transcript = agent.run(task, sandbox)

        # 应该有 2 个 LLM_CALL 事件、1 个 TOOL_CALL 和 1 个 TOOL_RESULT 事件
        llm_events = [e for e in transcript.events if e.event_type == EventType.LLM_CALL]
        tool_events = [e for e in transcript.events if e.event_type == EventType.TOOL_CALL]
        result_events = [e for e in transcript.events if e.event_type == EventType.TOOL_RESULT]
        assert len(llm_events) == 2
        assert len(tool_events) == 1
        assert len(result_events) == 1
        assert result_events[0].content["output"] == "hello"

    @patch("litellm.completion")
    def test_max_iterations_stops(self, mock_completion: MagicMock) -> None:
        """Agent stops at max iterations."""
        agent = RealAgent(max_iterations=3)
        task = _make_task()
        sandbox = MagicMock()
        sandbox._active_container = MagicMock()

        # 每次都返回工具调用
        tool_call = _make_tool_call("execute", {"command": "echo loop"})
        response = _make_llm_response(content="looping", tool_calls=[tool_call])
        mock_completion.return_value = response

        exec_result = MagicMock()
        exec_result.exit_code = 0
        exec_result.stdout = "loop"
        exec_result.stderr = ""
        sandbox.execute.return_value = exec_result

        agent.run(task, sandbox)

        # 应该恰好调用 3 次 LLM
        assert mock_completion.call_count == 3

    @patch("litellm.completion")
    def test_llm_error_recorded(self, mock_completion: MagicMock) -> None:
        """LLM errors are recorded in transcript."""
        agent = RealAgent(max_iterations=5)
        task = _make_task()
        sandbox = MagicMock()

        mock_completion.side_effect = RuntimeError("API error")

        transcript = agent.run(task, sandbox)

        error_events = [e for e in transcript.events if e.event_type == EventType.ERROR]
        assert len(error_events) == 1
        assert "API error" in error_events[0].content["error"]
        assert error_events[0].content["error_type"] == "RuntimeError"

    @patch("litellm.completion")
    def test_transcript_metrics(self, mock_completion: MagicMock) -> None:
        """Transcript accumulates token counts and cost."""
        agent = RealAgent()
        task = _make_task()
        sandbox = MagicMock()

        response = _make_llm_response(
            content="done",
            input_tokens=200,
            output_tokens=100,
        )
        mock_completion.return_value = response

        transcript = agent.run(task, sandbox)

        assert transcript.total_tokens > 0
        assert transcript.total_duration >= 0
        assert "cost_usd" in transcript.agent_config
        assert "input_tokens" in transcript.agent_config
