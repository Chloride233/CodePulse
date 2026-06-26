"""SWE-bench dataset loader.

Parses SWE-bench JSONL files into unified Task objects. Each line is one
problem instance with repo metadata, a problem statement, and the expected
patch plus test patch.

Reference: https://github.com/princeton-nlp/SWE-bench
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from codepulse.data.models import (
    Difficulty,
    Task,
    TaskCategory,
    TaskSource,
)

logger = logging.getLogger(__name__)

# Required SWE-bench fields that must be non-empty strings.
_REQUIRED_FIELDS: tuple[str, ...] = (
    "instance_id",
    "problem_statement",
    "patch",
)

# All fields the loader reads from a JSONL record (required + optional).
_ALL_FIELDS: set[str] = {
    "instance_id",
    "repo",
    "base_commit",
    "problem_statement",
    "patch",
    "test_patch",
    "hints_text",
}


class SweBenchLoader:
    """Load and validate SWE-bench tasks from a JSONL file.

    Implements the :class:`DatasetLoader` protocol defined in
    :mod:`codepulse.data.protocols`.

    Usage::

        loader = SweBenchLoader()
        tasks = loader.load("datasets/swe-bench/verified.jsonl")
        valid = [t for t in tasks if loader.validate(t)]
    """

    def load(self, path: str) -> list[Task]:
        """Parse an SWE-bench JSONL file into a list of Task objects.

        Lines that are empty, not valid JSON, or missing required fields are
        skipped with a warning logged so that a partially-corrupt file does not
        abort the entire load.

        Args:
            path: Path to a ``.jsonl`` file in SWE-bench format.

        Returns:
            List of parsed :class:`Task` objects (may be empty).

        Raises:
            FileNotFoundError: If *path* does not exist.
            ValueError: If *path* is not a file.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset file not found: {path}")
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        tasks: list[Task] = []
        total_lines = 0
        with file_path.open(encoding="utf-8") as fh:
            for line_no, raw_line in enumerate(fh, start=1):
                total_lines = line_no
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    record: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "Skipping line %d: invalid JSON (%s)", line_no, path
                    )
                    continue

                task = self._parse_record(record, path, line_no)
                if task is not None:
                    tasks.append(task)

        logger.info(
            "Loaded %d tasks from %s (%d lines skipped)",
            len(tasks),
            path,
            total_lines - len(tasks),
        )
        return tasks

    def validate(self, task: Task) -> bool:
        """Check whether a task has the minimum fields needed for evaluation.

        Validation rules:
        - ``task_id`` is non-empty.
        - ``task.input["description"]`` is non-empty (maps to problem_statement).
        - ``task.ground_truth["patch"]`` is non-empty.

        Args:
            task: The task to validate.

        Returns:
            ``True`` if the task passes all checks.
        """
        if not task.task_id:
            return False
        if not task.input.get("description"):
            return False
        return bool(task.ground_truth.get("patch"))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_record(
        self,
        record: dict[str, Any],
        path: str,
        line_no: int,
    ) -> Task | None:
        """Convert a single JSONL record to a Task, or None if invalid."""
        missing = [f for f in _REQUIRED_FIELDS if not record.get(f)]
        if missing:
            logger.warning(
                "Skipping line %d: missing fields %s (%s)",
                line_no,
                missing,
                path,
            )
            return None

        return Task(
            task_id=record["instance_id"],
            source=TaskSource.SWE_BENCH,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.MEDIUM,
            language="python",
            input={
                "description": record["problem_statement"],
                "hints": record.get("hints_text", ""),
            },
            ground_truth={
                "patch": record["patch"],
                "test_patch": record.get("test_patch", ""),
            },
            metadata={
                "repo": record.get("repo", ""),
                "base_commit": record.get("base_commit", ""),
            },
        )
