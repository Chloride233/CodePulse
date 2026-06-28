"""Human calibration tool for LLM-as-Judge graders.

Records human review scores alongside LLM grader outputs, computes
agreement metrics (simple agreement, Cohen's Kappa), and produces a
calibration-corrected grader that adjusts LLM scores based on
historical calibration bias.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.data.protocols import Grader, GraderResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalibrationSample:
    """A single human-LLM calibration record.

    Attributes:
        grader: Name of the LLM grader.
        task_id: The task that was graded.
        dimension: The evaluation dimension.
        llm_score: Raw LLM score in [0, 1].
        human_score: Human-assigned score in [0, 1].
        llm_reasoning: LLM's reasoning text (optional).
        human_note: Human reviewer's note (optional).
        timestamp: ISO-format timestamp.
    """

    grader: str
    task_id: str
    dimension: str
    llm_score: float
    human_score: float
    llm_reasoning: str = ""
    human_note: str = ""
    timestamp: str = ""


@dataclass
class CalibrationDataset:
    """Collection of calibration samples with analysis methods.

    Attributes:
        samples: All recorded calibration samples.
    """

    samples: list[CalibrationSample] = field(default_factory=list)

    def add(
        self,
        grader: str,
        task_id: str,
        dimension: str,
        llm_score: float,
        human_score: float,
        llm_reasoning: str = "",
        human_note: str = "",
    ) -> None:
        self.samples.append(
            CalibrationSample(
                grader=grader,
                task_id=task_id,
                dimension=dimension,
                llm_score=round(llm_score, 4),
                human_score=round(human_score, 4),
                llm_reasoning=llm_reasoning,
                human_note=human_note,
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

    @property
    def size(self) -> int:
        return len(self.samples)

    def agreement_rate(self) -> float:
        """Proportion of samples where human and LLM scores are within 0.2."""
        if not self.samples:
            return 0.0
        aligned = sum(
            1 for s in self.samples if abs(s.llm_score - s.human_score) <= 0.2
        )
        return aligned / len(self.samples)

    def mean_bias(self) -> float:
        """Mean signed difference (LLM - human). Positive = LLM over-scores."""
        if not self.samples:
            return 0.0
        return statistics.mean(s.llm_score - s.human_score for s in self.samples)

    def filter_by_grader(self, grader_name: str) -> CalibrationDataset:
        return CalibrationDataset(
            [s for s in self.samples if s.grader == grader_name]
        )

    def filter_by_dimension(self, dimension: str) -> CalibrationDataset:
        return CalibrationDataset(
            [s for s in self.samples if s.dimension == dimension]
        )

    def to_jsonl(self, path: str | Path) -> None:
        data = [
            {
                "grader": s.grader,
                "task_id": s.task_id,
                "dimension": s.dimension,
                "llm_score": s.llm_score,
                "human_score": s.human_score,
                "llm_reasoning": s.llm_reasoning,
                "human_note": s.human_note,
                "timestamp": s.timestamp,
            }
            for s in self.samples
        ]
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(
            "\n".join(json.dumps(d, ensure_ascii=False) for d in data),
            encoding="utf-8",
        )

    @classmethod
    def from_jsonl(cls, path: str | Path) -> CalibrationDataset:
        path_obj = Path(path)
        if not path_obj.exists():
            return cls()
        samples: list[CalibrationSample] = []
        for line in path_obj.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            record = json.loads(line)
            samples.append(
                CalibrationSample(
                    grader=record["grader"],
                    task_id=record["task_id"],
                    dimension=record["dimension"],
                    llm_score=record["llm_score"],
                    human_score=record["human_score"],
                    llm_reasoning=record.get("llm_reasoning", ""),
                    human_note=record.get("human_note", ""),
                    timestamp=record.get("timestamp", ""),
                )
            )
        return cls(samples=samples)


class Calibrator:
    """Calibration tool that produces corrected grader scores.

    Uses a calibration dataset to compute bias correction offsets per grader
    and dimension. The resulting :class:`CalibratedGrader` wrapper adjusts
    raw LLM scores before returning them.

    Attributes:
        dataset: The calibration dataset.
    """

    def __init__(self, dataset: CalibrationDataset | None = None) -> None:
        self.dataset = dataset or CalibrationDataset()

    @staticmethod
    def cohens_kappa(
        scores_a: list[float],
        scores_b: list[float],
        bins: int = 5,
    ) -> float:
        """Compute Cohen's Kappa between two sets of discretised scores.

        Args:
            scores_a: First set of scores.
            scores_b: Second set of scores.
            bins: Number of equal-width bins to discretise into.

        Returns:
            Kappa value in [-1, 1]. 1 = perfect agreement.
        """
        if len(scores_a) != len(scores_b) or len(scores_a) == 0:
            return 0.0

        def _discretise(scores: list[float], n: int) -> list[int]:
            return [min(int(s * n), n - 1) for s in scores]

        labels_a = _discretise(scores_a, bins)
        labels_b = _discretise(scores_b, bins)

        n = len(labels_a)
        # Confusion matrix
        matrix = Counter((labels_a[i], labels_b[i]) for i in range(n))
        categories = list(range(bins))

        # Observed agreement
        observed = sum(matrix[(c, c)] for c in categories) / n

        # Expected agreement (marginal independence)
        row_marg = {c: sum(matrix[(c, j)] for j in categories) / n for c in categories}
        col_marg = {c: sum(matrix[(i, c)] for i in categories) / n for c in categories}
        expected = sum(row_marg[c] * col_marg[c] for c in categories)

        if expected == 1.0:
            return 1.0

        return round((observed - expected) / (1.0 - expected), 4)

    def analyze(self, grader_name: str | None = None) -> dict[str, Any]:
        """Run calibration analysis for an optional specific grader.

        Args:
            grader_name: If provided, only analyse this grader's samples.

        Returns:
            Dictionary with agreement metrics and drift indicators.
        """
        subset = (
            self.dataset
            if grader_name is None
            else self.dataset.filter_by_grader(grader_name)
        )

        if subset.size < 2:
            return {"error": "insufficient samples", "size": subset.size}

        llm_scores = [s.llm_score for s in subset.samples]
        human_scores = [s.human_score for s in subset.samples]

        return {
            "grader": grader_name or "all",
            "size": subset.size,
            "agreement_rate": round(subset.agreement_rate(), 4),
            "mean_bias": round(subset.mean_bias(), 4),
            "kappa": self.cohens_kappa(llm_scores, human_scores),
            "llm_mean": round(statistics.mean(llm_scores), 4),
            "human_mean": round(statistics.mean(human_scores), 4),
            "llm_stddev": round(statistics.stdev(llm_scores), 4) if subset.size >= 2 else 0.0,
            "human_stddev": round(statistics.stdev(human_scores), 4) if subset.size >= 2 else 0.0,
        }

    def bias_offset(
        self,
        grader_name: str,
        dimension: str | None = None,
    ) -> float:
        """Compute the expected bias correction offset for a grader.

        The offset is the mean (LLM - human) difference over calibration
        samples. A positive offset means the LLM tends to over-score, so
        subtract it from future LLM scores.

        Args:
            grader_name: Name of the LLM grader.
            dimension: Optional dimension filter.

        Returns:
            Bias offset to subtract from LLM scores.
        """
        subset = self.dataset.filter_by_grader(grader_name)
        if dimension is not None:
            subset = subset.filter_by_dimension(dimension)

        if subset.size < 1:
            return 0.0
        return round(subset.mean_bias(), 4)

    def calibrate(self, grader: Grader) -> CalibratedGrader:
        """Wrap an existing Grader with calibration correction.

        Args:
            grader: The raw LLM grader to calibrate.

        Returns:
            A :class:`CalibratedGrader` that applies bias correction.
        """
        return CalibratedGrader(
            inner=grader,
            calibrator=self,
        )


class CalibratedGrader:
    """Grader wrapper that applies calibration bias correction.

    Delegates grading to the inner grader, then adjusts the returned
    score using the bias offset computed from calibration data.
    """

    def __init__(self, inner: Grader, calibrator: Calibrator) -> None:
        self._inner = inner
        self._calibrator = calibrator

    @property
    def name(self) -> str:
        return f"{self._inner.name}_calibrated"

    def grade(self, task: Task, trial: Trial) -> GraderResult:
        from codepulse.data.protocols import GraderResult
        from codepulse.eval.scoring import ScoreDimension

        result = self._inner.grade(task, trial)

        offset = self._calibrator.bias_offset(
            grader_name=self._inner.name,
            dimension=result.dimension.value if isinstance(result.dimension, ScoreDimension) else str(result.dimension),
        )

        adjusted = max(0.0, min(1.0, result.score - offset))

        return GraderResult(
            dimension=result.dimension,
            score=round(adjusted, 4),
            details={
                **result.details,
                "original_score": result.score,
                "bias_offset": offset,
                "calibrated": True,
            },
        )
