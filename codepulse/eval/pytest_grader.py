"""Pytest execution grader — functional correctness via exit code.

Evaluates whether an agent's patch passes the task's test suite by inspecting
the pytest process exit code.  This is the MVP heuristic; a future iteration
will parse pytest's structured output (JSON report) for per-test granularity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codepulse.eval.scoring import ScoreDimension

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.data.protocols import GraderResult


class PytestGrader:
    """Grade functional correctness by checking the pytest exit code.

    Attributes:
        name: Identifier used in scoring reports.
    """

    name: str = "pytest"

    def grade(self, task: Task, trial: Trial) -> GraderResult:
        """Evaluate a trial based on pytest execution outcome.

        Scoring heuristic (MVP):
        - ``exit_code == 0`` means all tests passed → score 1.0
        - Any other value (or missing) → score 0.0

        Future work will parse ``pytest --json-report`` output to compute the
        ratio of passed-to-total tests, giving partial credit.

        Args:
            task: The original task definition, including ``ground_truth``.
            trial: The agent's execution trial containing ``outcome``.

        Returns:
            :class:`GraderResult` with dimension ``FUNCTIONAL`` and a details
            dict carrying raw execution diagnostics.
        """
        # Deferred import avoids circular dependency at module level.
        from codepulse.data.protocols import GraderResult

        outcome: dict[str, object] = trial.outcome or {}

        exit_code_raw = outcome.get("exit_code")
        exit_code: int = int(exit_code_raw) if exit_code_raw is not None and isinstance(exit_code_raw, (int, str)) else -1
        score = 1.0 if exit_code == 0 else 0.0

        # Extract optional diagnostics for downstream observability.
        stdout = str(outcome.get("stdout", ""))
        stderr = str(outcome.get("stderr", ""))
        test_patch = task.ground_truth.get("test_patch", "")

        details: dict[str, float | int | str | bool] = {
            "exit_code": exit_code,
            "stdout": stdout[:4096],  # truncate to avoid memory bloat
            "stderr": stderr[:4096],
            "has_test_patch": bool(test_patch),
        }

        return GraderResult(
            dimension=ScoreDimension.FUNCTIONAL,
            score=score,
            details=details,
        )
