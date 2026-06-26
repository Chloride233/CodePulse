"""Code quality grader — static analysis violations as robustness signal.

Evaluates code quality by aggregating violations from ruff, mypy, and bandit
(static analysis tools mandated by the project's engineering standards).
Each violation deducts 0.1 from a perfect 1.0 score, clamped to [0, 1].
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codepulse.eval.scoring import ScoreDimension

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.data.protocols import GraderResult

# Penalty per violation (summed across all tools).
_VIOLATION_PENALTY: float = 0.1


class CodeQualityGrader:
    """Grade robustness/safety by counting static analysis violations.

    Expects the trial's ``outcome`` dict to carry pre-computed violation
    counts produced by the sandbox execution layer (ruff, mypy, bandit).

    Attributes:
        name: Identifier used in scoring reports.
    """

    name: str = "code_quality"

    def grade(self, task: Task, trial: Trial) -> GraderResult:
        """Evaluate a trial based on static analysis violation counts.

        Scoring formula::

            total_violations = ruff + mypy + bandit_high
            score = max(0.0, 1.0 - total_violations * 0.1)

        Args:
            task: The original task definition.
            trial: The agent's execution trial containing ``outcome``.

        Returns:
            :class:`GraderResult` with dimension ``ROBUSTNESS`` and a details
            dict carrying per-tool violation counts and the total.
        """
        from codepulse.data.protocols import GraderResult

        outcome: dict[str, object] = trial.outcome or {}

        ruff_raw = outcome.get("ruff_violations", 0)
        mypy_raw = outcome.get("mypy_errors", 0)
        bandit_raw = outcome.get("bandit_high", 0)
        ruff_violations: int = int(ruff_raw) if isinstance(ruff_raw, (int, str)) else 0
        mypy_errors: int = int(mypy_raw) if isinstance(mypy_raw, (int, str)) else 0
        bandit_high: int = int(bandit_raw) if isinstance(bandit_raw, (int, str)) else 0

        total_violations = ruff_violations + mypy_errors + bandit_high
        score = max(0.0, 1.0 - total_violations * _VIOLATION_PENALTY)

        details: dict[str, float | int | str | bool] = {
            "ruff_violations": ruff_violations,
            "mypy_errors": mypy_errors,
            "bandit_high": bandit_high,
            "total_violations": total_violations,
            "penalty_per_violation": _VIOLATION_PENALTY,
        }

        return GraderResult(
            dimension=ScoreDimension.ROBUSTNESS,
            score=score,
            details=details,
        )
