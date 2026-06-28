"""Pytest execution grader — functional correctness via exit code and partial scoring.

Evaluates whether an agent's solution passes the task's test suite.
Supports two scoring modes:

1. **Exit code mode** (default): pass/fail based on pytest exit code.
2. **Partial scoring mode**: when pytest JSON report data is available,
   computes pass rate as ratio of passed-to-total tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codepulse.eval.scoring import ScoreDimension

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.data.protocols import GraderResult


class PytestGrader:
    """Grade functional correctness by checking pytest results.

    Attributes:
        name: Identifier used in scoring reports.
        use_partial_scoring: Whether to use partial scoring when JSON
            report data is available. If False, always uses exit code.
    """

    name: str = "pytest"

    def __init__(self, use_partial_scoring: bool = True) -> None:
        self.use_partial_scoring = use_partial_scoring

    def grade(self, task: Task, trial: Trial) -> GraderResult:
        """Evaluate a trial based on pytest execution outcome.

        Scoring:
        - Positive tests (pytest): ``score = pytest_passed / pytest_total`` (partial)
          or ``1.0 if exit_code == 0`` (exit-code mode)
        - Negative tests (negative_test_failures): If negative tests passed
          incorrectly (false positive), score is penalized.
        """
        from codepulse.data.protocols import GraderResult

        outcome: dict[str, object] = trial.outcome or {}

        exit_code_raw = outcome.get("exit_code")
        exit_code: int = (
            int(exit_code_raw)
            if exit_code_raw is not None and isinstance(exit_code_raw, (int, str))
            else -1
        )

        # Positive tests score
        pytest_total_raw = outcome.get("pytest_total", 0)
        pytest_passed_raw = outcome.get("pytest_passed", 0)
        pytest_total = int(pytest_total_raw) if isinstance(pytest_total_raw, (int, str)) else 0
        pytest_passed = int(pytest_passed_raw) if isinstance(pytest_passed_raw, (int, str)) else 0

        if self.use_partial_scoring and pytest_total > 0:
            base_score = round(pytest_passed / pytest_total, 4)
        else:
            base_score = 1.0 if exit_code == 0 else 0.0

        # Negative tests penalty
        neg_raw = outcome.get("negative_test_failures", 1)
        neg_failures = int(neg_raw) if isinstance(neg_raw, (int, str)) else 1
        # neg_failures = 0 means at least one negative test passed (false positive)
        # Penalty: 0.3 per missed negative test
        neg_penalty = 0.0
        if neg_failures == 0:
            neg_penalty = 0.3

        score = max(0.0, base_score - neg_penalty)

        stdout = str(outcome.get("stdout", ""))
        stderr = str(outcome.get("stderr", ""))

        details: dict[str, float | int | str | bool] = {
            "exit_code": exit_code,
            "stdout": stdout[:4096],
            "stderr": stderr[:4096],
            "pytest_total": pytest_total,
            "pytest_passed": pytest_passed,
            "scoring_mode": "partial" if (self.use_partial_scoring and pytest_total > 0) else "exit_code",
            "negative_test_failures": neg_failures,
            "neg_penalty": neg_penalty,
        }

        return GraderResult(
            dimension=ScoreDimension.FUNCTIONAL,
            score=score,
            details=details,
        )
