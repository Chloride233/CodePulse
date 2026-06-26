"""Tests for codepulse.data.storage path utilities."""

from pathlib import Path

from codepulse.data.storage import ResultPath


class TestResultPathTaskDir:
    """ResultPath.task_dir() returns base_dir/task_id."""

    def test_task_dir_returns_correct_path(self, tmp_path: Path) -> None:
        rp = ResultPath(base_dir=str(tmp_path), task_id="bugfix-42")
        assert rp.task_dir() == tmp_path / "bugfix-42"

    def test_task_dir_with_nested_base(self, tmp_path: Path) -> None:
        base = tmp_path / "results" / "v1"
        rp = ResultPath(base_dir=str(base), task_id="t-1")
        assert rp.task_dir() == base / "t-1"


class TestResultPathTrialPath:
    """ResultPath.trial_path() includes trial_id in the filename."""

    def test_trial_path_includes_trial_id(self, tmp_path: Path) -> None:
        rp = ResultPath(
            base_dir=str(tmp_path), task_id="task-1", trial_id="run-3"
        )
        assert rp.trial_path() == tmp_path / "task-1" / "trial-run-3.jsonl"

    def test_trial_path_numeric_id(self, tmp_path: Path) -> None:
        rp = ResultPath(
            base_dir=str(tmp_path), task_id="t", trial_id="0"
        )
        assert rp.trial_path().name == "trial-0.jsonl"


class TestResultPathTracePath:
    """ResultPath.trace_path() includes the -trace suffix."""

    def test_trace_path_has_trace_suffix(self, tmp_path: Path) -> None:
        rp = ResultPath(
            base_dir=str(tmp_path), task_id="t-1", trial_id="r-1"
        )
        assert rp.trace_path() == tmp_path / "t-1" / "trial-r-1-trace.jsonl"

    def test_trace_path_suffix_matches_trial(self, tmp_path: Path) -> None:
        rp = ResultPath(
            base_dir=str(tmp_path), task_id="t", trial_id="7"
        )
        assert rp.trace_path().stem == "trial-7-trace"


class TestResultPathSummaryPath:
    """ResultPath.summary_path() returns summary.json under task dir."""

    def test_summary_path_returns_summary_json(self, tmp_path: Path) -> None:
        rp = ResultPath(base_dir=str(tmp_path), task_id="any-task")
        assert rp.summary_path() == tmp_path / "any-task" / "summary.json"

    def test_summary_path_ignores_trial_id(self, tmp_path: Path) -> None:
        rp = ResultPath(
            base_dir=str(tmp_path), task_id="t", trial_id="x"
        )
        assert rp.summary_path().name == "summary.json"


class TestEnsureDirs:
    """ensure_dirs() creates the task directory on disk."""

    def test_creates_task_directory(self, tmp_path: Path) -> None:
        rp = ResultPath(base_dir=str(tmp_path), task_id="new-task")
        assert not rp.task_dir().exists()
        rp.ensure_dirs()
        assert rp.task_dir().is_dir()

    def test_idempotent(self, tmp_path: Path) -> None:
        rp = ResultPath(base_dir=str(tmp_path), task_id="dup")
        rp.ensure_dirs()
        rp.ensure_dirs()
        assert rp.task_dir().is_dir()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        base = tmp_path / "a" / "b" / "c"
        rp = ResultPath(base_dir=str(base), task_id="deep")
        rp.ensure_dirs()
        assert rp.task_dir().is_dir()
