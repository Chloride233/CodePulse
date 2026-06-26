"""AACR-Bench dataset loader.

Parses AACR-Bench JSONL files into unified Task objects. Each line is one
code-review instance with PR metadata, review comments, and a ground-truth
expected review.

Reference: AACR-Bench — Automated Code Review Benchmark
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

# Required AACR-Bench fields that must be non-empty strings.
_REQUIRED_FIELDS: tuple[str, ...] = (
    "pr_id",
    "pr_title",
    "expected_review",
)

# File extension to language mapping for language detection fallback.
_EXT_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".cpp": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "shell",
    ".sql": "sql",
    ".r": "r",
    ".m": "objc",
}


class AacrBenchLoader:
    """Load and validate AACR-Bench tasks from a JSONL file.

    Implements the :class:`DatasetLoader` protocol defined in
    :mod:`codepulse.data.protocols`.

    Usage::

        loader = AacrBenchLoader()
        tasks = loader.load("datasets/aacr-bench/data.jsonl")
        valid = [t for t in tasks if loader.validate(t)]
    """

    def load(self, path: str) -> list[Task]:
        """Parse an AACR-Bench JSONL file into a list of Task objects.

        Lines that are empty, not valid JSON, or missing required fields are
        skipped with a warning logged so that a partially-corrupt file does not
        abort the entire load.

        Args:
            path: Path to a ``.jsonl`` file in AACR-Bench format.

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
        - ``task.input["title"]`` is non-empty (maps to pr_title).
        - ``task.ground_truth["expected_review"]`` is non-empty.

        Args:
            task: The task to validate.

        Returns:
            ``True`` if the task passes all checks.
        """
        if not task.task_id:
            return False
        if not task.input.get("title"):
            return False
        return bool(task.ground_truth.get("expected_review"))

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

        language = record.get("language", "").strip()
        if not language:
            language = self._detect_language(record)

        return Task(
            task_id=record["pr_id"],
            source=TaskSource.AACR_BENCH,
            category=TaskCategory.CODE_REVIEW,
            difficulty=Difficulty.MEDIUM,
            language=language,
            input={
                "title": record["pr_title"],
                "body": record.get("pr_body", ""),
                "comments": record.get("review_comments", []),
            },
            ground_truth={
                "expected_review": record["expected_review"],
            },
            metadata={
                "repo": record.get("repo", ""),
            },
        )

    @staticmethod
    def _detect_language(record: dict[str, Any]) -> str:
        """Infer language from file extensions in review_comments.

        Scans all ``file`` fields in ``review_comments`` and returns the
        language corresponding to the most common file extension. Falls
        back to ``"unknown"`` when no recognisable extension is found.
        """
        comments: list[dict[str, Any]] = record.get("review_comments", [])
        counts: dict[str, int] = {}
        for comment in comments:
            file_path = comment.get("file", "")
            if not file_path:
                continue
            suffix = Path(file_path).suffix.lower()
            lang = _EXT_LANG.get(suffix)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1

        if not counts:
            return "unknown"
        return max(counts, key=counts.get)  # type: ignore[arg-type]
