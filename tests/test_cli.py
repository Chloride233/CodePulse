"""Tests for codepulse.cli module.

Uses click.testing.CliRunner to exercise the CLI commands without
spawning a subprocess, covering imports, command registration, and
--help output for every subcommand.
"""

from __future__ import annotations

import click
from click.testing import CliRunner

from codepulse.cli import cli

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _assert_is_click_group(obj: object) -> None:
    """Assert that *obj* is a click.Group (or a subclass thereof)."""
    assert isinstance(obj, click.Group), f"Expected click.Group, got {type(obj)}"


def _assert_command_registered(group: click.Group, name: str) -> None:
    """Assert that a subcommand *name* is registered on *group*."""
    assert name in group.commands, (
        f"Command '{name}' not found. Registered commands: {list(group.commands)}"
    )


def _assert_help_contains(result: click.testing.Result, *substrings: str) -> None:
    """Assert that the CLI output contains every given substring."""
    output = result.output
    for s in substrings:
        assert s in output, f"Expected '{s}' in help output.\nFull output:\n{output}"


# ------------------------------------------------------------------
# 1. Import tests
# ------------------------------------------------------------------

class TestCLIImports:
    """Verify that the CLI module can be imported and exposes the expected objects."""

    def test_import_cli_module(self) -> None:
        """codepulse.cli should be importable."""
        import codepulse.cli  # noqa: F401

    def test_cli_object_is_click_group(self) -> None:
        """The exported ``cli`` should be a click.Group instance."""
        _assert_is_click_group(cli)


# ------------------------------------------------------------------
# 2. Main command group
# ------------------------------------------------------------------

class TestMainGroup:
    """Tests for the top-level ``codepulse`` command group."""

    def test_main_help(self) -> None:
        """``codepulse --help`` should succeed and mention key info."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0, result.output
        _assert_help_contains(result, "CodePulse", "evaluate", "compare", "report")

    def test_main_is_group(self) -> None:
        """``cli`` should be a group with subcommands."""
        _assert_is_click_group(cli)

    def test_main_version_option(self) -> None:
        """``codepulse --version`` should succeed."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0, result.output


# ------------------------------------------------------------------
# 3. evaluate command
# ------------------------------------------------------------------

class TestEvaluateCommand:
    """Tests for the ``evaluate`` subcommand."""

    def test_evaluate_registered(self) -> None:
        """The ``evaluate`` command should be registered on the CLI group."""
        _assert_command_registered(cli, "evaluate")

    def test_evaluate_help(self) -> None:
        """``codepulse evaluate --help`` should show usage details."""
        runner = CliRunner()
        result = runner.invoke(cli, ["evaluate", "--help"])
        assert result.exit_code == 0, result.output
        _assert_help_contains(
            result,
            "--task-file",
            "--agent-name",
            "--model",
            "--n-trials",
        )

    def test_evaluate_requires_task_file(self) -> None:
        """Running ``evaluate`` without ``--task-file`` should fail."""
        runner = CliRunner()
        result = runner.invoke(cli, ["evaluate"])
        assert result.exit_code != 0


# ------------------------------------------------------------------
# 4. compare command
# ------------------------------------------------------------------

class TestCompareCommand:
    """Tests for the ``compare`` subcommand."""

    def test_compare_registered(self) -> None:
        """The ``compare`` command should be registered on the CLI group."""
        _assert_command_registered(cli, "compare")

    def test_compare_help(self) -> None:
        """``codepulse compare --help`` should show usage details."""
        runner = CliRunner()
        result = runner.invoke(cli, ["compare", "--help"])
        assert result.exit_code == 0, result.output
        _assert_help_contains(
            result,
            "--task-file",
            "--agents",
            "--n-trials",
        )

    def test_compare_requires_agents(self) -> None:
        """Running ``compare`` without ``--agents`` should fail."""
        runner = CliRunner()
        result = runner.invoke(cli, ["compare", "--task-file", "dummy.jsonl"])
        assert result.exit_code != 0


# ------------------------------------------------------------------
# 5. report command
# ------------------------------------------------------------------

class TestReportCommand:
    """Tests for the ``report`` subcommand."""

    def test_report_registered(self) -> None:
        """The ``report`` command should be registered on the CLI group."""
        _assert_command_registered(cli, "report")

    def test_report_help(self) -> None:
        """``codepulse report --help`` should show usage details."""
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--help"])
        assert result.exit_code == 0, result.output
        _assert_help_contains(
            result,
            "--results-dir",
            "--format",
        )

    def test_report_requires_results_dir(self) -> None:
        """Running ``report`` without ``--results-dir`` should fail."""
        runner = CliRunner()
        result = runner.invoke(cli, ["report"])
        assert result.exit_code != 0


# ------------------------------------------------------------------
# 6. CliRunner integration smoke tests
# ------------------------------------------------------------------

class TestCliRunnerIntegration:
    """Smoke tests exercising the runner across all subcommands."""

    def test_runner_invokes_cli_without_error(self) -> None:
        """CliRunner should be able to invoke the root group."""
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code == 0

    def test_unknown_subcommand_fails(self) -> None:
        """An unrecognised subcommand should exit with a non-zero code."""
        runner = CliRunner()
        result = runner.invoke(cli, ["nonexistent-command"])
        assert result.exit_code != 0

    def test_evaluate_task_file_not_found(self, tmp_path: object) -> None:
        """``evaluate`` with a non-existent file should fail gracefully."""
        runner = CliRunner()
        result = runner.invoke(cli, ["evaluate", "--task-file", "/no/such/file.jsonl"])
        assert result.exit_code != 0

    def test_report_results_dir_not_found(self) -> None:
        """``report`` with a non-existent directory should fail gracefully."""
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--results-dir", "/no/such/dir"])
        assert result.exit_code != 0
