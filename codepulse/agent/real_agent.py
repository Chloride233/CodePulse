"""RealAgent — 基于 LiteLLM 的真实 Agent 实现。

实现 Agent Protocol，通过 LiteLLM 调用 LLM，在 Docker 沙箱中执行工具，
产生真实的 Transcript 记录。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from codepulse.agent.tools import (
    ToolCallResult,
    ToolRegistry,
    get_default_registry,
    parse_tool_arguments,
)
from codepulse.config import calc_cost
from codepulse.shared.trace_types import EventType, TraceEvent, Transcript

if TYPE_CHECKING:
    from codepulse.data.models import Task
    from codepulse.env.sandbox import SandboxManager

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a coding agent. You work inside a sandboxed environment to solve coding tasks.

## Available Tools
{tools_desc}

## Rules
1. Read the task description carefully.
2. If there is input code, read it first to understand the context.
3. Write your solution using write_file to **/workspace/solution.py**.
4. If test cases are provided, run them with execute to verify correctness.
5. Fix any failures and iterate until tests pass.
6. When done, output a brief summary of what you did.

Be concise. Focus on correctness. Do not over-engineer.
"""


class RealAgent:
    """基于 LiteLLM 的真实 Agent。

    通过 LLM 的 tool-calling 能力在沙箱中执行文件操作和命令，
    产生完整的执行轨迹（Transcript）。

    Attributes:
        name: Agent 名称。
        model: LiteLLM 模型标识。
    """

    def __init__(
        self,
        name: str = "real-agent",
        model: str = "deepseek-chat",
        *,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        max_iterations: int = 20,
        system_prompt: str | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._name = name
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_iterations = max_iterations
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations
        self._tool_registry = tool_registry  # 延迟初始化，run 时绑定 sandbox

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    def run(self, task: Task, sandbox: SandboxManager) -> Transcript:
        """执行任务并返回 Transcript。

        Args:
            task: 评测任务。
            sandbox: 沙箱管理器。

        Returns:
            完整的执行轨迹。
        """
        import litellm

        session_id = f"{task.task_id}-{uuid.uuid4().hex[:8]}"
        transcript = Transcript(
            session_id=session_id,
            agent_config={"name": self._name, "model": self._model},
        )

        # 绑定工具到 sandbox
        registry = self._tool_registry or get_default_registry(sandbox)
        tools_schema = registry.schemas()
        tools_desc = "\n".join(
            f"- **{t['function']['name']}**: {t['function']['description']}"
            for t in tools_schema
        )

        # 准备初始消息
        system_prompt = self._system_prompt or _SYSTEM_PROMPT.format(tools_desc=tools_desc)
        user_content = self._build_task_message(task)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # 记录累积 token 使用
        total_input = 0
        total_output = 0
        total_cache = 0
        provider_model_versions: set[str] = set()

        start_time = time.time()

        for iteration in range(self._max_iterations):
            # 调用 LLM
            llm_start = time.time()
            try:
                response = litellm.completion(
                    model=self._model,
                    messages=messages,
                    tools=tools_schema if tools_schema else None,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )
            except Exception as exc:
                error_event = TraceEvent(
                    timestamp=time.time(),
                    event_type=EventType.ERROR,
                    content={"error": str(exc), "iteration": iteration},
                )
                transcript.add_event(error_event)
                logger.error("LLM 调用失败 (iteration %d): %s", iteration, exc)
                break

            llm_duration = time.time() - llm_start
            choice = response.choices[0]
            message = choice.message
            provider_model = str(getattr(response, "model", "") or "")
            if provider_model:
                provider_model_versions.add(provider_model)

            # 提取 token 使用
            usage = self._extract_usage(response)
            total_input += usage.get("input", 0)
            total_output += usage.get("output", 0)
            total_cache += usage.get("cache", 0)

            # 记录 LLM 调用事件
            llm_event = TraceEvent(
                timestamp=llm_start,
                event_type=EventType.LLM_CALL,
                content={
                    "iteration": iteration,
                    "model": self._model,
                    "provider_model": provider_model,
                    "content": message.content or "",
                    "has_tool_calls": bool(getattr(message, "tool_calls", None)),
                },
                token_usage={
                    "input": usage.get("input", 0),
                    "output": usage.get("output", 0),
                    "cache": usage.get("cache", 0),
                },
                duration=llm_duration,
            )
            transcript.add_event(llm_event)

            # 检查是否有工具调用
            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                # 无工具调用 → 模型认为任务完成
                break

            # 将 assistant 消息加入对话
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)

            # 执行工具调用
            for tc in tool_calls:
                func_name = tc.function.name
                func_args = parse_tool_arguments(tc.function.arguments)
                tool_call_id = tc.id

                tool_start = time.time()
                tool_result = self._execute_tool(registry, func_name, func_args)
                tool_duration = time.time() - tool_start

                # 记录工具调用事件
                tool_event = TraceEvent(
                    timestamp=tool_start,
                    event_type=EventType.TOOL_CALL,
                    content={
                        "tool": func_name,
                        "arguments": func_args,
                        "success": tool_result.success,
                        "output_length": len(tool_result.output),
                        "error": tool_result.error,
                    },
                    duration=tool_duration,
                )
                transcript.add_event(tool_event)

                # 将工具结果加入对话
                result_content = tool_result.to_content()
                if len(result_content) > 100_000:
                    result_content = result_content[:100_000] + "\n... (truncated)"
                transcript.add_event(
                    TraceEvent(
                        timestamp=time.time(),
                        event_type=EventType.TOOL_RESULT,
                        content={
                            "tool": func_name,
                            "tool_call_id": tool_call_id,
                            "success": tool_result.success,
                            "output": result_content,
                            "error": tool_result.error,
                        },
                    )
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_content,
                })

        total_duration = time.time() - start_time

        # 更新 transcript 的汇总指标
        transcript.total_tokens = total_input + total_output + total_cache
        transcript.total_duration = round(total_duration, 3)

        # 计算成本并存储在 agent_config 中
        cost = calc_cost(self._model, total_input, total_output, total_cache)
        transcript.agent_config["cost_usd"] = cost
        transcript.agent_config["input_tokens"] = total_input
        transcript.agent_config["output_tokens"] = total_output
        transcript.agent_config["cache_tokens"] = total_cache
        transcript.agent_config["provider_model_versions"] = sorted(
            provider_model_versions
        )

        return transcript

    def _build_task_message(self, task: Task) -> str:
        """构建发送给 LLM 的任务消息。"""
        parts: list[str] = []

        description = task.input.get("description", "")
        if description:
            parts.append(f"## Task\n{description}")

        input_code = task.input.get("input_code", "")
        if input_code:
            parts.append(f"## Input Code\n```\n{input_code}\n```")

        test_cases = task.ground_truth.get("test_cases", [])
        if test_cases:
            cases = "\n".join(f"  {i+1}. `{tc}`" for i, tc in enumerate(test_cases))
            parts.append(f"## Test Cases\nRun these to verify your solution:\n{cases}")

        expected_output = task.ground_truth.get("expected_output", "")
        if expected_output:
            parts.append(f"## Expected Behavior\n{expected_output}")

        return "\n\n".join(parts) if parts else "No task description provided."

    def _execute_tool(
        self,
        registry: ToolRegistry,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolCallResult:
        """执行工具调用。"""
        tool = registry.get(name)
        if tool is None:
            return ToolCallResult(
                output="",
                error=f"Unknown tool: {name}. Available: {', '.join(registry.names)}",
                success=False,
            )
        try:
            return tool.execute(**arguments)
        except Exception as exc:
            return ToolCallResult(output="", error=str(exc), success=False)

    def _extract_usage(self, response: Any) -> dict[str, int]:
        """从 LLM 响应中提取 token 使用量。

        处理不同提供商的格式差异。
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return {"input": 0, "output": 0, "cache": 0}

        result: dict[str, int] = {"input": 0, "output": 0, "cache": 0}

        # input tokens
        for attr in ("prompt_tokens", "input_tokens"):
            val = getattr(usage, attr, None)
            if val is not None:
                result["input"] = _safe_int(val)
                break

        # output tokens
        for attr in ("completion_tokens", "output_tokens"):
            val = getattr(usage, attr, None)
            if val is not None:
                result["output"] = _safe_int(val)
                break

        # cache tokens
        cache_info = getattr(usage, "prompt_tokens_details", None)
        if cache_info is not None:
            cached = getattr(cache_info, "cached_tokens", None)
            if cached is not None:
                result["cache"] = _safe_int(cached)
        else:
            # DeepSeek 格式
            for attr in ("cache_hit_input_tokens", "prompt_cache_hit_tokens"):
                val = getattr(usage, attr, None)
                if val is not None:
                    result["cache"] = _safe_int(val)
                    break

        return result


def _safe_int(val: Any) -> int:
    """安全转为 int。"""
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0
