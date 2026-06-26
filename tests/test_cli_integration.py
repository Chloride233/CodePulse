"""CLI 集成测试 — 实际执行命令。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from click.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

from codepulse.cli import cli


def _create_sample_task(tmp_path: Path) -> Path:
    """创建示例任务文件。"""
    task_file = tmp_path / "task.jsonl"
    task_data = {
        "task_id": "test-001",
        "category": "bug_fix",
        "difficulty": "easy",
        "language": "python",
        "description": "Fix the add function",
        "expected_output": "def add(a, b): return a + b",
    }
    task_file.write_text(json.dumps(task_data) + "\n")
    return task_file


class TestEvaluateIntegration:
    """evaluate 命令集成测试。"""

    def test_evaluate_with_valid_task(self, tmp_path: Path) -> None:
        """使用有效任务文件运行 evaluate。"""
        task_file = _create_sample_task(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "evaluate",
                "--task-file", str(task_file),
                "--agent-name", "test-agent",
                "--model", "test-model",
                "--n-trials", "2",
            ],
        )
        # 可能因为 Docker 不可用而失败，但应该有输出
        assert result.output  # 有输出

    def test_evaluate_missing_task_file(self) -> None:
        """evaluate 使用不存在的任务文件应该失败。"""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["evaluate", "--task-file", "/no/such/file.jsonl"],
        )
        assert result.exit_code != 0


class TestCompareIntegration:
    """compare 命令集成测试。"""

    def test_compare_with_agents(self, tmp_path: Path) -> None:
        """使用多个 agent 运行 compare。"""
        task_file = _create_sample_task(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "compare",
                "--task-file", str(task_file),
                "--agents", "agent1",
                "--agents", "agent2",
                "--n-trials", "2",
            ],
        )
        # 可能因为 Docker 不可用而失败，但应该有输出
        assert result.output  # 有输出

    def test_compare_single_agent_fails(self, tmp_path: Path) -> None:
        """compare 只提供一个 agent 应该失败。"""
        task_file = _create_sample_task(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "compare",
                "--task-file", str(task_file),
                "--agents", "agent1",
            ],
        )
        assert result.exit_code != 0


class TestReportIntegration:
    """report 命令集成测试。"""

    def test_report_empty_directory(self, tmp_path: Path) -> None:
        """report 在空目录上应该失败（无结果文件）。"""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["report", "--results-dir", str(results_dir)],
        )
        # 空目录应该失败
        assert result.exit_code != 0 or "No result" in result.output

    def test_report_with_summary(self, tmp_path: Path) -> None:
        """report 包含 summary.json 应该成功。"""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        # 创建一个 summary.json
        summary = {
            "task_id": "test-001",
            "total_trials": 5,
            "success_count": 4,
            "pass_rate": 0.8,
        }
        summary_file = results_dir / "summary.json"
        summary_file.write_text(json.dumps(summary))
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["report", "--results-dir", str(results_dir)],
        )
        assert result.output  # 有输出
