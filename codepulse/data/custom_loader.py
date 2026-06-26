"""Custom dataset loader.

Parses custom JSONL files into unified Task objects. Each line is one task
with a flexible schema covering bug-fix, feature, refactor, and code-review
categories.

Expected JSONL fields per line:

- task_id (str, required): Unique identifier.
- category (str, required): One of bug_fix, feature, refactor, code_review.
- difficulty (str, required): One of easy, medium, hard.
- language (str, required): Programming language (e.g. "python", "rust").
- description (str, required): Human-readable task description.
- input_code (str, optional): Starting code the agent receives.
- expected_output (str, required): Expected result or code.
- test_cases (list[str], optional): Commands to verify correctness.
- metadata (dict, optional): Arbitrary extra information.
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

# Required fields that must be present and non-empty.
_REQUIRED_FIELDS: tuple[str, ...] = (
    "task_id",
    "description",
    "expected_output",
)

# Build reverse-lookups for string-to-enum conversion.
_CATEGORY_MAP: dict[str, TaskCategory] = {v.value: v for v in TaskCategory}
_DIFFICULTY_MAP: dict[str, Difficulty] = {v.value: v for v in Difficulty}


def _resolve_category(raw: str) -> TaskCategory:
    """Convert a category string to a TaskCategory enum member.

    Falls back to ``TaskCategory.FEATURE`` for unrecognised values so that a
    single bad entry does not block loading.
    """
    return _CATEGORY_MAP.get(raw, TaskCategory.FEATURE)


def _resolve_difficulty(raw: str) -> Difficulty:
    """Convert a difficulty string to a Difficulty enum member.

    Falls back to ``Difficulty.MEDIUM`` for unrecognised values.
    """
    return _DIFFICULTY_MAP.get(raw, Difficulty.MEDIUM)


class CustomDatasetLoader:
    """Load and validate custom-format tasks from a JSONL file.

    Implements the :class:`DatasetLoader` protocol defined in
    :mod:`codepulse.data.protocols`.

    Usage::

        loader = CustomDatasetLoader()
        tasks = loader.load("datasets/custom/tasks.jsonl")
        valid = [t for t in tasks if loader.validate(t)]
    """

    def load(self, path: str) -> list[Task]:
        """Parse a custom JSONL file into a list of Task objects.

        Lines that are empty, not valid JSON, or missing required fields are
        skipped with a warning so that a partially-corrupt file does not abort
        the entire load.

        Args:
            path: Path to a ``.jsonl`` file in the custom format.

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
        - ``task.task_id`` is non-empty.
        - ``task.input["description"]`` is non-empty.
        - ``task.ground_truth["expected_output"]`` is non-empty.

        Args:
            task: The task to validate.

        Returns:
            ``True`` if the task passes all checks.
        """
        if not task.task_id:
            return False
        if not task.input.get("description"):
            return False
        return bool(task.ground_truth.get("expected_output"))

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

        category = _resolve_category(record.get("category", ""))
        difficulty = _resolve_difficulty(record.get("difficulty", ""))

        return Task(
            task_id=record["task_id"],
            source=TaskSource.CUSTOM,
            category=category,
            difficulty=difficulty,
            language=record.get("language", "unknown"),
            input={
                "description": record["description"],
                "input_code": record.get("input_code", ""),
            },
            ground_truth={
                "expected_output": record["expected_output"],
                "test_cases": record.get("test_cases", []),
            },
            metadata=record.get("metadata", {}),
        )
