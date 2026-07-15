"""Agent 工具定义 — 沙箱内的文件操作和命令执行。

工具遵循 OpenAI Function Calling 格式，可直接用于 LiteLLM 的 tool 参数。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from codepulse.env.sandbox import SandboxManager

logger = logging.getLogger(__name__)


class ToolCallResult:
    """工具调用结果。"""

    __slots__ = ("output", "error", "success")

    def __init__(self, output: str, error: str = "", success: bool = True) -> None:
        self.output = output
        self.error = error
        self.success = success

    def to_content(self) -> str:
        """转为传回 LLM 的文本。"""
        if self.error:
            return f"Error: {self.error}"
        return self.output


class Tool:
    """工具基类。

    子类必须定义类变量 ``name``、``description``、``parameters``，
    并实现 ``execute`` 方法。
    """

    name: ClassVar[str]
    description: ClassVar[str]
    parameters: ClassVar[dict[str, Any]]

    def __init__(self, sandbox: SandboxManager) -> None:
        self._sandbox = sandbox

    def execute(self, **kwargs: Any) -> ToolCallResult:
        raise NotImplementedError

    def to_schema(self) -> dict[str, Any]:
        """转为 OpenAI Function Calling schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ReadFileTool(Tool):
    """读取沙箱内的文件内容。"""

    name = "read_file"
    description = "Read the contents of a file in the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to the workspace root.",
            },
            "offset": {
                "type": "integer",
                "minimum": 1,
                "description": "Optional one-based starting line.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "description": "Optional number of lines to return.",
            },
        },
        "required": ["path"],
    }

    def execute(
        self,
        *,
        path: str = "",
        offset: int | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> ToolCallResult:
        if not path:
            return ToolCallResult(output="", error="path is required", success=False)
        for name, value in (("offset", offset), ("limit", limit)):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 1
            ):
                return ToolCallResult(
                    output="", error=f"{name} must be a positive integer", success=False
                )

        from codepulse.env.sandbox_utils import SandboxUtils

        utils = SandboxUtils(self._sandbox)
        container = self._sandbox.get_active_container()
        try:
            content = utils.read_file(container, path)
        except Exception as exc:
            return ToolCallResult(
                output="",
                error=str(exc),
                success=False,
            )

        if offset is not None or limit is not None:
            lines = content.splitlines(keepends=True)
            start = (offset or 1) - 1
            end = start + limit if limit is not None else None
            content = "".join(lines[start:end])
        if len(content) > 200_000:
            content = content[:200_000] + "\n... (truncated)"
        return ToolCallResult(output=content)


class EditFileTool(Tool):
    """Replace one exact string in a workspace text file."""

    name = "edit_file"
    description = "Replace exactly one occurrence of text in a workspace file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to the workspace root.",
            },
            "old_string": {
                "type": "string",
                "description": "Exact existing text to replace.",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text.",
            },
        },
        "required": ["path", "old_string", "new_string"],
    }

    def execute(
        self,
        *,
        path: str = "",
        old_string: str = "",
        new_string: str = "",
        **kwargs: Any,
    ) -> ToolCallResult:
        if not path:
            return ToolCallResult(output="", error="path is required", success=False)
        if not old_string:
            return ToolCallResult(
                output="", error="old_string is required", success=False
            )

        from codepulse.env.sandbox_utils import SandboxUtils

        utils = SandboxUtils(self._sandbox)
        container = self._sandbox.get_active_container()
        try:
            content = utils.read_file(container, path)
        except Exception as exc:
            return ToolCallResult(output="", error=str(exc), success=False)

        matches = content.count(old_string)
        if matches == 0:
            return ToolCallResult(
                output="", error="old_string was not found", success=False
            )
        if matches > 1:
            return ToolCallResult(
                output="",
                error=f"old_string matched {matches} occurrences; make it unique",
                success=False,
            )

        try:
            utils.write_file(container, path, content.replace(old_string, new_string, 1))
        except Exception as exc:
            return ToolCallResult(output="", error=str(exc), success=False)
        return ToolCallResult(output=f"File edited: {path}")


class WriteFileTool(Tool):
    """写入文件到沙箱。"""

    name = "write_file"
    description = "Write content to a file in the workspace. Creates parent directories automatically."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to the workspace root.",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file.",
            },
        },
        "required": ["path", "content"],
    }

    def execute(self, *, path: str = "", content: str = "", **kwargs: Any) -> ToolCallResult:
        if not path:
            return ToolCallResult(output="", error="path is required", success=False)
        from codepulse.env.sandbox_utils import SandboxUtils

        utils = SandboxUtils(self._sandbox)
        container = self._sandbox.get_active_container()
        try:
            utils.write_file(container, path, content)
        except Exception as exc:
            return ToolCallResult(output="", error=str(exc), success=False)
        return ToolCallResult(output=f"File written: {path}")


class ExecuteTool(Tool):
    """在沙箱中执行 shell 命令。"""

    name = "execute"
    description = (
        "Execute a shell command for repository inspection, targeted transformations, "
        "and existing checks."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute.",
            },
        },
        "required": ["command"],
    }

    def execute(self, *, command: str = "", **kwargs: Any) -> ToolCallResult:
        if not command:
            return ToolCallResult(output="", error="command is required", success=False)
        container = self._sandbox.get_active_container()
        result = self._sandbox.execute(container, command)
        output_parts: list[str] = []
        if result.stdout.strip():
            output_parts.append(result.stdout.strip())
        if result.stderr.strip():
            output_parts.append(f"[stderr] {result.stderr.strip()}")
        output = "\n".join(output_parts) if output_parts else "(no output)"
        if len(output) > 100_000:
            output = output[:100_000] + "\n... (truncated)"
        return ToolCallResult(
            output=output,
            error="" if result.exit_code == 0 else f"Exit code: {result.exit_code}",
            success=result.exit_code == 0,
        )


class ToolRegistry:
    """工具注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        """返回所有工具的 OpenAI schema 列表。"""
        return [tool.to_schema() for tool in self._tools.values()]

    @property
    def names(self) -> list[str]:
        return list(self._tools.keys())


def get_default_registry(
    sandbox: SandboxManager, tool_names: list[str] | None = None
) -> ToolRegistry:
    """获取默认工具注册表。

    Args:
        sandbox: 沙箱管理器。

    Returns:
        包含 read_file、write_file、execute 的注册表。
    """
    tool_types: dict[str, type[Tool]] = {
        "read_file": ReadFileTool,
        "edit_file": EditFileTool,
        "write_file": WriteFileTool,
        "execute": ExecuteTool,
    }
    selected_names = (
        tool_names if tool_names is not None else ["read_file", "write_file", "execute"]
    )
    unknown_names = [name for name in selected_names if name not in tool_types]
    if unknown_names:
        raise ValueError(f"Unsupported tool names: {', '.join(unknown_names)}")

    registry = ToolRegistry()
    for name in selected_names:
        registry.register(tool_types[name](sandbox))
    return registry


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    """解析工具调用参数。

    处理 LLM 返回的参数格式差异（dict / JSON string / None）。

    Args:
        raw: 原始参数。

    Returns:
        解析后的参数字典。
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
