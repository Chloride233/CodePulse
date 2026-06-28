"""评测结果检视模块测试。"""

import json
from pathlib import Path

import pytest

from codepulse.inspect import (
    _get_suggestions,
    inspect_result,
    inspect_task,
)


class TestGetSuggestions:
    def test_all_good_no_suggestions(self) -> None:
        scores = {"functional": 1.0, "process": 1.0, "efficiency": 1.0, "robustness": 1.0}
        assert _get_suggestions(scores) == []

    def test_low_functional(self) -> None:
        suggestions = _get_suggestions({"functional": 0.3})
        assert any("功能正确性低" in s for s in suggestions)

    def test_partial_functional(self) -> None:
        suggestions = _get_suggestions({"functional": 0.7})
        assert any("边界条件遗漏" in s for s in suggestions)

    def test_low_process(self) -> None:
        suggestions = _get_suggestions({"process": 0.3})
        assert any("过程质量差" in s for s in suggestions)

    def test_low_efficiency(self) -> None:
        suggestions = _get_suggestions({"efficiency": 0.3})
        assert any("效率低" in s for s in suggestions)

    def test_low_robustness(self) -> None:
        suggestions = _get_suggestions({"robustness": 0.3})
        assert any("鲁棒性差" in s for s in suggestions)

    def test_multiple_issues(self) -> None:
        suggestions = _get_suggestions({"functional": 0.3, "process": 0.3, "efficiency": 0.3, "robustness": 0.3})
        assert len(suggestions) == 4


class TestInspectResult:
    def test_nonexistent_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        inspect_result("/nonexistent/path/result.json")
        captured = capsys.readouterr()
        assert "文件不存在" in captured.out

    def test_invalid_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not json", encoding="utf-8")
        inspect_result(str(p))
        captured = capsys.readouterr()
        assert "读取失败" in captured.out

    def test_summary_display(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        data = {
            "task_id": "task-001",
            "n_total": 5,
            "n_passed": 4,
            "avg_score": 85.0,
            "avg_scores": {"functional": 0.9, "process": 0.8},
            "pass_metrics": {"pass_at_1": 0.8, "pass_at_k": 0.9, "pass_hat_k": 0.7, "k": 5},
            "trials": [
                {"success": True, "scores": {"functional": 0.9}, "outcome": {"total_duration": 10.0, "total_tokens": 500}},
                {"success": False, "scores": {"functional": 0.4}, "outcome": {"exit_code": 1, "stderr": "error"}},
            ],
        }
        p = tmp_path / "summary.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        inspect_result(str(p))
        captured = capsys.readouterr()
        assert "task-001" in captured.out
        assert "测试" in captured.out or "评测" in captured.out or "PASSED" in captured.out or "FAILED" in captured.out

    def test_trial_display(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        data = {
            "trial_id": "trial-001",
            "task_id": "task-001",
            "success": True,
            "scores": {"functional": 0.95, "process": 0.8},
            "outcome": {"exit_code": 0},
        }
        p = tmp_path / "trial.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        inspect_result(str(p))
        captured = capsys.readouterr()
        assert "trial-001" in captured.out or "Trial" in captured.out


class TestInspectTask:
    def test_nonexistent_task(self, capsys: pytest.CaptureFixture[str]) -> None:
        inspect_task(str(Path.cwd()), "nonexistent-task-xyz")
        captured = capsys.readouterr()
        assert "未找到" in captured.out

    def test_empty_task_dir(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        inspect_task(str(tmp_path), "task-001")
        captured = capsys.readouterr()
        assert "为空" in captured.out

    def test_task_with_trial_files(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        (task_dir / "trial-001.json").write_text("{}", encoding="utf-8")
        (task_dir / "trial-002.json").write_text("{}", encoding="utf-8")
        inspect_task(str(tmp_path), "task-001")
        captured = capsys.readouterr()
        assert "2 个 trial" in captured.out

    def test_task_with_summary(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        summary = {"task_id": "task-001", "n_total": 5, "n_passed": 4, "avg_score": 85.0}
        (task_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        inspect_task(str(tmp_path), "task-001")
        captured = capsys.readouterr()
        assert "task-001" in captured.out
