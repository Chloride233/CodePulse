"""Tests for codepulse.agent.tools module."""

from __future__ import annotations

from unittest.mock import MagicMock

from codepulse.agent.tools import (
    ExecuteTool,
    ReadFileTool,
    ToolCallResult,
    ToolRegistry,
    WriteFileTool,
    get_default_registry,
    parse_tool_arguments,
)


class TestToolCallResult:
    """Tests for ToolCallResult."""

    def test_success_result(self) -> None:
        result = ToolCallResult(output="file content")
        assert result.success is True
        assert result.error == ""
        assert result.to_content() == "file content"

    def test_error_result(self) -> None:
        result = ToolCallResult(output="", error="not found", success=False)
        assert result.success is False
        assert result.to_content() == "Error: not found"


class TestParseToolArguments:
    """Tests for parse_tool_arguments."""

    def test_dict_input(self) -> None:
        assert parse_tool_arguments({"path": "test.py"}) == {"path": "test.py"}

    def test_json_string(self) -> None:
        assert parse_tool_arguments('{"path": "test.py"}') == {"path": "test.py"}

    def test_invalid_json(self) -> None:
        assert parse_tool_arguments("not json") == {}

    def test_none_input(self) -> None:
        assert parse_tool_arguments(None) == {}

    def test_json_array(self) -> None:
        # JSON array is not a dict
        assert parse_tool_arguments("[1, 2, 3]") == {}


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        sandbox = MagicMock()
        tool = ReadFileTool(sandbox)
        registry.register(tool)

        assert registry.get("read_file") is tool
        assert registry.get("nonexistent") is None

    def test_schemas(self) -> None:
        registry = ToolRegistry()
        sandbox = MagicMock()
        registry.register(ReadFileTool(sandbox))
        registry.register(ExecuteTool(sandbox))

        schemas = registry.schemas()
        assert len(schemas) == 2
        names = {s["function"]["name"] for s in schemas}
        assert "read_file" in names
        assert "execute" in names

    def test_names(self) -> None:
        registry = ToolRegistry()
        sandbox = MagicMock()
        registry.register(ReadFileTool(sandbox))
        registry.register(WriteFileTool(sandbox))
        registry.register(ExecuteTool(sandbox))

        assert set(registry.names) == {"read_file", "write_file", "execute"}


class TestGetDefaultRegistry:
    """Tests for get_default_registry."""

    def test_returns_all_tools(self) -> None:
        sandbox = MagicMock()
        registry = get_default_registry(sandbox)
        assert set(registry.names) == {"read_file", "write_file", "execute"}


class TestReadFileTool:
    """Tests for ReadFileTool."""

    def test_schema(self) -> None:
        sandbox = MagicMock()
        tool = ReadFileTool(sandbox)
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "read_file"
        assert "path" in schema["function"]["parameters"]["properties"]

    def test_missing_path(self) -> None:
        sandbox = MagicMock()
        tool = ReadFileTool(sandbox)
        result = tool.execute()
        assert result.success is False
        assert "path" in result.error

    def test_successful_read(self) -> None:
        sandbox = MagicMock()
        exec_result = MagicMock()
        exec_result.exit_code = 0
        exec_result.stdout = "file content here"
        exec_result.stderr = ""
        sandbox.execute.return_value = exec_result

        tool = ReadFileTool(sandbox)
        result = tool.execute(path="test.py")
        assert result.success is True
        assert result.output == "file content here"

    def test_file_not_found(self) -> None:
        sandbox = MagicMock()
        exec_result = MagicMock()
        exec_result.exit_code = 1
        exec_result.stdout = ""
        exec_result.stderr = "cat: nonexistent.py: No such file"
        sandbox.execute.return_value = exec_result

        tool = ReadFileTool(sandbox)
        result = tool.execute(path="nonexistent.py")
        assert result.success is False


class TestExecuteTool:
    """Tests for ExecuteTool."""

    def test_schema(self) -> None:
        sandbox = MagicMock()
        tool = ExecuteTool(sandbox)
        schema = tool.to_schema()
        assert schema["function"]["name"] == "execute"
        assert "command" in schema["function"]["parameters"]["properties"]

    def test_missing_command(self) -> None:
        sandbox = MagicMock()
        tool = ExecuteTool(sandbox)
        result = tool.execute()
        assert result.success is False

    def test_successful_command(self) -> None:
        sandbox = MagicMock()
        exec_result = MagicMock()
        exec_result.exit_code = 0
        exec_result.stdout = "hello world"
        exec_result.stderr = ""
        sandbox.execute.return_value = exec_result

        tool = ExecuteTool(sandbox)
        result = tool.execute(command="echo hello world")
        assert result.success is True
        assert "hello world" in result.output

    def test_failed_command(self) -> None:
        sandbox = MagicMock()
        exec_result = MagicMock()
        exec_result.exit_code = 1
        exec_result.stdout = ""
        exec_result.stderr = "command not found"
        sandbox.execute.return_value = exec_result

        tool = ExecuteTool(sandbox)
        result = tool.execute(command="badcmd")
        assert result.success is False
        assert "Exit code: 1" in result.error


class TestWriteFileTool:
    """Tests for WriteFileTool."""

    def test_schema(self) -> None:
        sandbox = MagicMock()
        tool = WriteFileTool(sandbox)
        schema = tool.to_schema()
        assert schema["function"]["name"] == "write_file"
        props = schema["function"]["parameters"]["properties"]
        assert "path" in props
        assert "content" in props

    def test_missing_path(self) -> None:
        sandbox = MagicMock()
        tool = WriteFileTool(sandbox)
        result = tool.execute(content="hello")
        assert result.success is False
