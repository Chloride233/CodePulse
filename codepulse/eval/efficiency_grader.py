"""Efficiency grader — token usage and duration as cost-efficiency signal.

Evaluates how efficiently an agent completes a task by comparing token
consumption and wall-clock duration against configurable baselines.
Each metric is scored independently as a ratio of deviation from baseline,
then averaged for the final score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codepulse.eval.scoring import ScoreDimension

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.data.protocols import GraderResult


@dataclass
class EfficiencyGrader:
    """Grade efficiency cost by comparing tokens and duration to baselines.

    Attributes:
        name: Identifier used in scoring reports.
        baseline_tokens: Expected token count for a competent solution.
        baseline_duration: Expected wall-clock seconds for a competent solution.
    """

    name: str = "efficiency"
    baseline_tokens: int = 1000
    baseline_duration: float = 60.0

    def grade(self, task: Task, trial: Trial) -> GraderResult:
        """Evaluate a trial based on token and duration efficiency.

        Scoring formula::

            token_score    = max(0, 1 - (tokens - baseline) / baseline * 0.1)
            duration_score = max(0, 1 - (duration - baseline) / baseline * 0.1)
            score          = (token_score + duration_score) / 2

        When usage is at or below baseline the sub-score clamps to 1.0.
        Each 10 % over baseline costs 0.1 from the sub-score, clamped at 0.

        Args:
            task: The original task definition.
            trial: The agent's execution trial containing ``metrics``.

        Returns:
            :class:`GraderResult` with dimension ``EFFICIENCY`` and a details
            dict carrying raw metrics and per-metric sub-scores.
        """
        from codepulse.data.protocols import GraderResult

        tokens: int = trial.metrics.total_tokens
        duration: float = trial.metrics.total_duration

        token_score = max(
            0.0,
            min(1.0, 1.0 - (tokens - self.baseline_tokens) / self.baseline_tokens * 0.1),
        )
        duration_score = max(
            0.0,
            min(1.0, 1.0 - (duration - self.baseline_duration) / self.baseline_duration * 0.1),
        )
        score = (token_score + duration_score) / 2

        details: dict[str, float | int | str | bool] = {
            "total_tokens": tokens,
            "baseline_tokens": self.baseline_tokens,
            "token_score": round(token_score, 4),
            "total_duration": round(duration, 4),
            "baseline_duration": self.baseline_duration,
            "duration_score": round(duration_score, 4),
        }

        return GraderResult(
            dimension=ScoreDimension.EFFICIENCY,
            score=round(score, 4),
            details=details,
            evidence=[
                {"kind": "total_tokens", "value": tokens},
                {"kind": "total_duration", "value": round(duration, 4)},
                {"kind": "baseline_tokens", "value": self.baseline_tokens},
            ],
            diagnosis=(
                "成本或时延高于基线，建议先压缩上下文和工具往返。"
                if score < 1.0
                else "效率维度达到基线。"
            ),
        )
