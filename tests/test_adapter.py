"""测试 adapter 模块 — AgentProfile, _guess_filename, 运行模式。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from codepulse.agent.adapter import (
    AgentProfile,
    _guess_filename,
    _inject_task_files,
    _load_agent_class,
    _run_cli_agent,
    _run_mock_agent,
    _run_protocol_agent,
    _run_verification,
    run_agent,
)
from codepulse.data.models import AgentConfig, Difficulty, Task, TaskCategory, TaskSource, Trial

# ======================================================================
# AgentProfile
# ======================================================================


class TestAgentProfile:
    def test_from_yaml_full(self):
        data = {
            "name": "test-agent",
            "type": "protocol",
            "model": "deepseek-chat",
            "command": "python agent.py",
            "workdir": "/workspace",
            "agent_class": "codepulse.env.mock_agent.MockAgent",
            "system_prompt": "You are a coding agent.",
            "tools": ["read_file", "write_file"],
            "max_iterations": 10,
            "temperature": 0.2,
            "max_tokens": 2048,
            "description": "Test agent",
            "version": "2.0",
            "author": "test",
            "metadata": {"key": "value"},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(data, f)
            path = f.name
        try:
            profile = AgentProfile.from_yaml(path)
            assert profile.name == "test-agent"
            assert profile.type == "protocol"
            assert profile.model == "deepseek-chat"
            assert profile.agent_class == "codepulse.env.mock_agent.MockAgent"
            assert profile.system_prompt == "You are a coding agent."
            assert profile.max_iterations == 10
            assert profile.temperature == 0.2
            assert profile.metadata == {"key": "value"}
        finally:
            Path(path).unlink(missing_ok=True)

    def test_from_yaml_minimal(self):
        data = {"name": "minimal"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(data, f)
            path = f.name
        try:
            profile = AgentProfile.from_yaml(path)
            assert profile.name == "minimal"
            assert profile.type == "protocol"
            assert profile.model == ""
        finally:
            Path(path).unlink(missing_ok=True)

    def test_from_yaml_missing_file(self):
        with pytest.raises(FileNotFoundError):
            AgentProfile.from_yaml("/nonexistent/path.yaml")

    def test_to_yaml_roundtrip(self):
        profile = AgentProfile(
            name="roundtrip",
            type="cli",
            model="deepseek-chat",
            command="python solve.py",
            workdir="/custom",
            timeout=600,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            path = f.name
        try:
            profile.to_yaml(path)
            loaded = AgentProfile.from_yaml(path)
            assert loaded.name == "roundtrip"
            assert loaded.type == "cli"
            assert loaded.command == "python solve.py"
            assert loaded.workdir == "/custom"
            assert loaded.timeout == 600
        finally:
            Path(path).unlink(missing_ok=True)

    def test_to_yaml_protocol(self):
        profile = AgentProfile(
            name="proto-agent",
            type="protocol",
            agent_class="my.module.MyAgent",
            system_prompt="Be helpful.",
            tools=["read_file", "write_file"],
            max_iterations=30,
            temperature=0.5,
            max_tokens=8192,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            path = f.name
        try:
            profile.to_yaml(path)
            loaded = AgentProfile.from_yaml(path)
            assert loaded.type == "protocol"
            assert loaded.agent_class == "my.module.MyAgent"
            assert loaded.max_iterations == 30
        finally:
            Path(path).unlink(missing_ok=True)


# ======================================================================
# _guess_filename
# ======================================================================


class TestGuessFilename:
    def test_python(self):
        assert _guess_filename("python", "solution") == "solution.py"
        assert _guess_filename("py", "input") == "input.py"

    def test_javascript(self):
        assert _guess_filename("javascript", "output") == "output.js"
        assert _guess_filename("js", "test") == "test.js"

    def test_other_languages(self):
        assert _guess_filename("go", "main") == "main.go"
        assert _guess_filename("rust", "lib") == "lib.rs"
        assert _guess_filename("java", "Main") == "Main.java"

    def test_unknown_fallback(self):
        assert _guess_filename("ruby", "app") == "app.txt"
        assert _guess_filename("", "data") == "data.txt"


# ======================================================================
# _load_agent_class
# ======================================================================


class TestLoadAgentClass:
    def test_load_mock_agent(self):
        profile = AgentProfile(
            name="mock-loader",
            type="protocol",
            model="",
            max_iterations=0,
            agent_class="codepulse.env.mock_agent.MockAgent",
        )
        agent = _load_agent_class(profile)
        assert agent is not None
        assert agent.model == "mock-model"

    def test_load_with_model_override(self):
        profile = AgentProfile(
            name="custom",
            type="protocol",
            model="my-model",
            max_iterations=0,
            agent_class="codepulse.env.mock_agent.MockAgent",
        )
        agent = _load_agent_class(profile)
        assert agent.model == "my-model"

    def test_missing_agent_class(self):
        profile = AgentProfile(name="bad", type="protocol", agent_class="")
        with pytest.raises(ValueError, match="agent_class"):
            _load_agent_class(profile)

    def test_invalid_format(self):
        profile = AgentProfile(name="bad", type="protocol", agent_class="no_dots")
        with pytest.raises(ValueError, match="agent_class.*格式"):
            _load_agent_class(profile)


# ======================================================================
# run_agent dispatcher
# ======================================================================


class TestRunAgent:
    def test_mock_type(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("test-dispatch")
        profile = AgentProfile(name="mock-dispatch", type="mock")
        result = run_agent(profile, task, sandbox, container)
        assert result.task_id == "test-dispatch"
        assert result.exit_code == 0

    def test_unknown_type(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("test-unknown")
        profile = AgentProfile(name="unknown", type="nonexistent")
        result = run_agent(profile, task, sandbox, container)
        assert result.exit_code == -1
        assert "未知" in result.stderr


# ======================================================================
# _run_mock_agent
# ======================================================================


class TestRunMockAgent:
    def test_basic_run(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("mock-run")
        profile = AgentProfile(name="mock-tester", type="mock")
        result = _run_mock_agent(profile, task, sandbox, container)
        assert result.exit_code == 0
        assert result.transcript is not None


# ======================================================================
# _run_cli_agent
# ======================================================================


class TestRunCliAgent:
    def test_successful_run(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("cli-test")
        profile = AgentProfile(name="cli-agent", type="cli", command="python script.py")
        sandbox.execute.return_value = MagicMock(exit_code=0, stdout="done", stderr="")
        result = _run_cli_agent(profile, task, sandbox, container)
        assert result.task_id == "cli-test"
        assert result.exit_code == 0

    def test_command_failure(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("cli-fail")
        profile = AgentProfile(name="cli-agent", type="cli", command="python script.py")
        sandbox.execute.return_value = MagicMock(exit_code=1, stdout="", stderr="error!")
        result = _run_cli_agent(profile, task, sandbox, container)
        assert result.exit_code == 1
        assert result.stderr == "error!"

    def test_inject_failure_returns_early(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("cli-inject-fail")
        profile = AgentProfile(name="cli-agent", type="cli", command="python script.py")
        sandbox.execute.side_effect = Exception("inject failed")
        result = _run_cli_agent(profile, task, sandbox, container)
        assert result.exit_code == -1

    def test_empty_command_falls_back(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("cli-no-cmd")
        profile = AgentProfile(name="cli-agent", type="cli", command="")
        sandbox.execute.return_value = MagicMock(exit_code=1, stdout="", stderr="No command")
        result = _run_cli_agent(profile, task, sandbox, container)
        assert result.exit_code == 1


# ======================================================================
# _run_protocol_agent
# ======================================================================


class TestRunProtocolAgent:
    def test_missing_agent_class(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("proto-no-class")
        profile = AgentProfile(name="proto", type="protocol", agent_class="")
        result = _run_protocol_agent(profile, task, sandbox, container)
        assert result.exit_code == -1
        assert "未指定 agent_class" in result.stderr


# ======================================================================
# _inject_task_files
# ======================================================================


class TestInjectTaskFiles:
    def test_inject_with_input_code(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("inject-test", input_code="print('hello')")
        _inject_task_files(task, sandbox, container)
        sandbox.execute.assert_any_call(container, "mkdir -p /workspace")

    def test_inject_without_input_code(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("inject-no-input")
        _inject_task_files(task, sandbox, container)
        sandbox.execute.assert_any_call(container, "mkdir -p /workspace")


# ======================================================================
# _run_verification
# ======================================================================


class TestRunVerification:
    def test_no_test_cases(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("verify-no-tests")
        trial = Trial(trial_id="t1", task_id="verify-no-tests", agent_config=_agent_cfg())
        _run_verification(task, sandbox, container, trial)
        assert "exit_code" not in trial.outcome

    def test_non_python_skips(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("verify-js", language="javascript", test_cases=["assert(1+1==2)"])
        trial = Trial(trial_id="t1", task_id="verify-js", agent_config=_agent_cfg())
        _run_verification(task, sandbox, container, trial)
        assert "exit_code" not in trial.outcome

    def test_pytest_success(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("verify-py", test_cases=["assert 1+1==2"])
        trial = Trial(trial_id="t1", task_id="verify-py", agent_config=_agent_cfg())
        # Mock: pytest succeeds, JSON report has summary
        report = json.dumps({"summary": {"total": 1, "passed": 1}})
        sandbox.execute.side_effect = [
            MagicMock(exit_code=0),  # write_file
            MagicMock(exit_code=0),  # pip install
            MagicMock(exit_code=0, stdout="passed 1"),  # pytest
            MagicMock(exit_code=0, stdout=report),  # cat report
        ]
        _run_verification(task, sandbox, container, trial)
        assert trial.outcome.get("pytest_total") == 1
        assert trial.outcome.get("pytest_passed") == 1

    def test_pytest_no_report(self):
        sandbox = MagicMock()
        container = MagicMock()
        task = _make_task("verify-no-report", test_cases=["assert 1+1==2"])
        trial = Trial(trial_id="t1", task_id="verify-no-report", agent_config=_agent_cfg())
        sandbox.execute.side_effect = [
            MagicMock(exit_code=0),  # write_file
            MagicMock(exit_code=0),  # pip install
            MagicMock(exit_code=1, stdout="failure"),  # pytest fails
            MagicMock(exit_code=1, stdout=""),  # no report
        ]
        _run_verification(task, sandbox, container, trial)
        assert trial.outcome.get("exit_code") == 1


# ======================================================================
# Helpers
# ======================================================================


def _agent_cfg(**kwargs: object) -> AgentConfig:
    return AgentConfig(name=kwargs.get("name", "test"), model=kwargs.get("model", "test"))


def _make_task(task_id: str, **overrides: object) -> Task:
    return Task(
        task_id=task_id,
        source=TaskSource.CUSTOM,
        category=TaskCategory.BUG_FIX,
        difficulty=Difficulty.EASY,
        language=overrides.get("language", "python"),
        input={"description": "test task", **({"input_code": overrides["input_code"]} if "input_code" in overrides else {})},
        ground_truth={
            "expected_output": "pass",
            **({"test_cases": overrides["test_cases"]} if "test_cases" in overrides else {}),
        },
    )
