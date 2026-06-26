"""Storage path utilities for result files.

Defines the on-disk layout: results/{task_id}/trial-{id}.jsonl + trial-{id}-trace.jsonl
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ResultPath:
    """Manages paths for task result files under a base directory.

    File layout:
        base_dir/task_id/summary.json
        base_dir/task_id/trial-{trial_id}.jsonl
        base_dir/task_id/trial-{trial_id}-trace.jsonl
    """

    base_dir: str
    task_id: str
    trial_id: str | None = None

    def task_dir(self) -> Path:
        """Return the directory for this task: base_dir/task_id/"""
        return Path(self.base_dir) / self.task_id

    def trial_path(self) -> Path:
        """Return the path for a trial result file: base_dir/task_id/trial-{trial_id}.jsonl"""
        return self.task_dir() / f"trial-{self.trial_id}.jsonl"

    def trace_path(self) -> Path:
        """Return the path for a trial trace file: base_dir/task_id/trial-{trial_id}-trace.jsonl"""
        return self.task_dir() / f"trial-{self.trial_id}-trace.jsonl"

    def summary_path(self) -> Path:
        """Return the path for the task summary file: base_dir/task_id/summary.json"""
        return self.task_dir() / "summary.json"

    def ensure_dirs(self) -> None:
        """Create all necessary directories for this result path."""
        self.task_dir().mkdir(parents=True, exist_ok=True)
