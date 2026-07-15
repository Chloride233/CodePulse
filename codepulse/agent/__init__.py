"""Agent 模块 — 真实 LLM Agent 实现。"""

from typing import Any

from codepulse.agent.adapter import AgentProfile, AgentResult, run_adapter_trials, run_agent
from codepulse.agent.real_agent import RealAgent
from codepulse.agent.tools import (
    EditFileTool,
    ExecuteTool,
    ReadFileTool,
    Tool,
    ToolRegistry,
    WriteFileTool,
    get_default_registry,
)


def create_agent(profile: AgentProfile) -> Any:
    """从 AgentProfile 创建 Agent 实例。"""
    if profile.type == "mock":
        from codepulse.env.mock_agent import MockAgent
        return MockAgent(name=profile.name, model=profile.model or "mock")
    elif profile.type == "protocol":
        return RealAgent(
            name=profile.name,
            model=profile.model or "deepseek-chat",
            max_tokens=profile.max_tokens,
            temperature=profile.temperature,
            max_iterations=profile.max_iterations,
            system_prompt=profile.system_prompt or None,
            tool_names=profile.tools,
        )
    else:
        raise ValueError(f"不支持的 Agent 类型: {profile.type}")


__all__ = [
    "AgentProfile",
    "AgentResult",
    "EditFileTool",
    "ExecuteTool",
    "ReadFileTool",
    "RealAgent",
    "Tool",
    "ToolRegistry",
    "WriteFileTool",
    "create_agent",
    "get_default_registry",
    "run_adapter_trials",
    "run_agent",
]
