"""Tests for codepulse.commands.baseline_cli — baseline management."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from codepulse.cli import cli


class TestBaselineSave:
    """Tests for `codepulse baseline save`."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_save_requires_results_dir(self) -> None:
        result = self.runner.invoke(cli, ["baseline", "save", "--name", "test-base"])
        assert result.exit_code != 0
        assert "Results directory" in result.output or "--results-dir" in result.output

    def test_save_with_missing_results_dir(self, tmp_path: Path) -> None:
        fake_dir = str(tmp_path / "nonexistent")
        result = self.runner.invoke(cli, [
            "baseline", "save",
            "--name", "test-base",
            "--results-dir", fake_dir,
        ])
        # Click's Path(exists=True) validation catches this before our logic
        assert result.exit_code != 0
        assert "does not exist" in result.output or "not found" in result.output

    def test_save_creates_baseline_manifest(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        task_dir = results_dir / "task-001"
        task_dir.mkdir(parents=True)
        summary = {
            "task_id": "task-001",
            "agent_name": "test-agent",
            "pass_rate": 0.8,
            "avg_score": 85.0,
            "avg_scores": {"functional": 0.9},
        }
        (task_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

        with self.runner.isolated_filesystem() as fs:
            fs_path = Path(fs)
            # Copy the results dir into the isolated filesystem
            import shutil
            shutil.copytree(str(results_dir), str(fs_path / "results"))

            result = self.runner.invoke(cli, [
                "baseline", "save",
                "--name", "v1",
                "--results-dir", str(fs_path / "results"),
            ])
            assert result.exit_code == 0, result.output
            assert "Baseline" in result.output or "saved" in result.output

    def test_save_with_existing_name_fails(self, tmp_path: Path) -> None:
        """Saving with a name that already exists should fail."""
        results_dir = tmp_path / "results"
        task_dir = results_dir / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "summary.json").write_text(
            json.dumps({"task_id": "task-001", "pass_rate": 0.8}),
            encoding="utf-8",
        )

        with self.runner.isolated_filesystem() as fs:
            fs_path = Path(fs)
            import shutil
            shutil.copytree(str(results_dir), str(fs_path / "results"))

            # First save
            self.runner.invoke(cli, [
                "baseline", "save",
                "--name", "dup",
                "--results-dir", str(fs_path / "results"),
            ])
            # Second save with same name should fail
            result = self.runner.invoke(cli, [
                "baseline", "save",
                "--name", "dup",
                "--results-dir", str(fs_path / "results"),
            ])
            assert result.exit_code != 0
            assert "already exists" in result.output


class TestBaselineList:
    """Tests for `codepulse baseline list`."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_list_with_no_baselines(self) -> None:
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ["baseline", "list"])
            assert result.exit_code == 0
            assert "No baselines found" in result.output

    def test_list_with_baselines(self, tmp_path: Path) -> None:
        # Create a baseline and then list
        results_dir = tmp_path / "results"
        task_dir = results_dir / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "summary.json").write_text(
            json.dumps({"task_id": "task-001", "pass_rate": 0.9, "avg_score": 90.0}),
            encoding="utf-8",
        )

        with self.runner.isolated_filesystem() as fs:
            fs_path = Path(fs)
            import shutil
            shutil.copytree(str(results_dir), str(fs_path / "results"))

            self.runner.invoke(cli, [
                "baseline", "save",
                "--name", "test-v1",
                "--results-dir", str(fs_path / "results"),
            ])
            result = self.runner.invoke(cli, ["baseline", "list"])
            assert result.exit_code == 0
            assert "test-v1" in result.output


class TestBaselineDelete:
    """Tests for `codepulse baseline delete`."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_delete_nonexistent_baseline(self) -> None:
        result = self.runner.invoke(cli, ["baseline", "delete", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_delete_with_confirmation(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        task_dir = results_dir / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "summary.json").write_text(
            json.dumps({"task_id": "task-001", "pass_rate": 0.8}),
            encoding="utf-8",
        )

        with self.runner.isolated_filesystem() as fs:
            fs_path = Path(fs)
            import shutil
            shutil.copytree(str(results_dir), str(fs_path / "results"))

            self.runner.invoke(cli, [
                "baseline", "save",
                "--name", "delete-me",
                "--results-dir", str(fs_path / "results"),
            ])
            result = self.runner.invoke(cli, [
                "baseline", "delete",
                "delete-me",
                "--yes",
            ])
            assert result.exit_code == 0
            assert "deleted" in result.output


class TestBaselineCompare:
    """Tests for `codepulse baseline compare` with LCS alignment."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def _make_results(self, base_path, task_id, score, seq=None):
        """Helper: create a result dir with summary.json and trial files."""
        task_dir = base_path / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "summary.json").write_text(json.dumps({
            "task_id": task_id, "pass_rate": 1.0 if score >= 80 else 0.0,
            "avg_score": score, "avg_scores": {"functional": score / 100},
        }, ensure_ascii=False), encoding="utf-8")
        if seq:
            (task_dir / "trial-0.json").write_text(json.dumps({
                "tool_call_sequence": seq, "metrics": {"total_tokens": 100},
            }, ensure_ascii=False), encoding="utf-8")

    def test_compare_identical(self, tmp_path: Path) -> None:
        with self.runner.isolated_filesystem() as fs:
            fs_path = Path(fs)
            # Create baseline
            self._make_results(fs_path / "base", "task-001", 85.0, ["read", "write"])
            self.runner.invoke(cli, ["baseline", "save", "--name", "v1",
                                      "--results-dir", str(fs_path / "base")])
            # Current = same as baseline
            self._make_results(fs_path / "curr", "task-001", 85.0, ["read", "write"])
            result = self.runner.invoke(cli, ["baseline", "compare", "--against", "v1",
                                               "--results-dir", str(fs_path / "curr")])
            assert result.exit_code == 0

    def test_compare_with_improvement(self, tmp_path: Path) -> None:
        with self.runner.isolated_filesystem() as fs:
            fs_path = Path(fs)
            self._make_results(fs_path / "base", "task-001", 75.0)
            self.runner.invoke(cli, ["baseline", "save", "--name", "v2",
                                      "--results-dir", str(fs_path / "base")])
            self._make_results(fs_path / "curr", "task-001", 90.0)
            result = self.runner.invoke(cli, ["baseline", "compare", "--against", "v2",
                                               "--results-dir", str(fs_path / "curr")])
            assert result.exit_code == 0


class TestBaselineCaptureFailures:
    """Tests for `codepulse baseline capture-failures`."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_capture_failures_creates_file(self, tmp_path: Path) -> None:
        with self.runner.isolated_filesystem() as fs:
            fs_path = Path(fs)
            # Create a failed result
            task_dir = fs_path / "results" / "failed-task"
            task_dir.mkdir(parents=True)
            (task_dir / "summary.json").write_text(json.dumps({
                "task_id": "failed-task", "avg_score": 50.0, "pass_rate": 0.0,
            }), encoding="utf-8")
            out_path = fs_path / "regression.jsonl"
            result = self.runner.invoke(cli, [
                "baseline", "capture-failures",
                "--results-dir", str(fs_path / "results"),
                "--output", str(out_path),
            ])
            assert result.exit_code == 0
            assert out_path.exists()
            captured = json.loads(out_path.read_text(encoding="utf-8"))
            assert captured.get("task_id") == "regression/failed-task"

    def test_capture_no_failures_above_threshold(self, tmp_path: Path) -> None:
        with self.runner.isolated_filesystem() as fs:
            fs_path = Path(fs)
            task_dir = fs_path / "results" / "pass-task"
            task_dir.mkdir(parents=True)
            (task_dir / "summary.json").write_text(json.dumps({
                "task_id": "pass-task", "avg_score": 95.0, "pass_rate": 1.0,
            }), encoding="utf-8")
            out_path = fs_path / "regression.jsonl"
            result = self.runner.invoke(cli, [
                "baseline", "capture-failures",
                "--results-dir", str(fs_path / "results"),
                "--output", str(out_path), "--threshold", "80",
            ])
            assert result.exit_code == 0
            assert "No failures found" in result.output
