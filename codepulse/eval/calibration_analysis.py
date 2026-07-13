"""Shared numeric metrics for Phase 2 qualitative calibration."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any


def categorical_agreement(
    labels_a: list[str], labels_b: list[str]
) -> dict[str, Any]:
    """Calculate exact agreement and categorical Cohen's kappa."""
    if not labels_a or len(labels_a) != len(labels_b):
        raise ValueError("label lists must have the same non-zero length")
    categories = sorted(set(labels_a) | set(labels_b))
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)
    size = len(labels_a)
    observed = sum(a == b for a, b in zip(labels_a, labels_b, strict=True)) / size
    expected = sum(count_a[label] * count_b[label] for label in categories) / (size * size)
    degenerate = math.isclose(expected, 1.0)
    kappa = None if degenerate else (observed - expected) / (1.0 - expected)
    return {
        "n": size,
        "exact_agreement": round(observed, 4),
        "cohens_kappa": round(kappa, 4) if kappa is not None else None,
        "degenerate": degenerate,
        "distribution_a": dict(sorted(count_a.items())),
        "distribution_b": dict(sorted(count_b.items())),
    }


def score_agreement(scores_a: list[float], scores_b: list[float]) -> dict[str, Any]:
    """Report correlation and absolute agreement for aligned numeric scores."""
    if not scores_a or len(scores_a) != len(scores_b):
        raise ValueError("score lists must have the same non-zero length")
    differences = [
        score_a - score_b
        for score_a, score_b in zip(scores_a, scores_b, strict=True)
    ]
    return {
        "n": len(scores_a),
        "within_one_point": round(
            sum(abs(value) <= 1.0 for value in differences) / len(differences), 4
        ),
        "pearson": _pearson(scores_a, scores_b),
        "mean_signed_error": round(statistics.mean(differences), 4),
        "mean_absolute_error": round(
            statistics.mean(abs(value) for value in differences), 4
        ),
    }


def heldout_bias_correction(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit a mean Judge bias on alternating records and evaluate held-out rows."""
    if len(rows) < 4:
        raise ValueError("at least four rows are required for held-out correction")
    ordered = sorted(rows, key=lambda row: str(row["sample_id"]))
    train = ordered[::2]
    test = ordered[1::2]
    offset = statistics.mean(
        float(row["judge_score"]) - float(row["human_score"]) for row in train
    )
    judge_scores = [float(row["judge_score"]) for row in test]
    human_scores = [float(row["human_score"]) for row in test]
    corrected_scores = [score - offset for score in judge_scores]
    return {
        "split": "sorted_alternating_v1",
        "train_n": len(train),
        "test_n": len(test),
        "bias_offset": round(offset, 4),
        "before": score_agreement(judge_scores, human_scores),
        "after": score_agreement(corrected_scores, human_scores),
    }


def analyze_length_bias(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure score change and length-residual correlation on paired evidence."""
    if not pairs:
        return {"n": 0, "status": "not_identifiable"}
    score_deltas = [
        float(pair["full_score"]) - float(pair["compact_score"]) for pair in pairs
    ]
    lengths: list[float] = []
    residuals: list[float] = []
    for pair in pairs:
        human_score = float(pair["human_score"])
        lengths.extend((float(pair["full_length"]), float(pair["compact_length"])))
        residuals.extend(
            (
                float(pair["full_score"]) - human_score,
                float(pair["compact_score"]) - human_score,
            )
        )
    return {
        "n": len(pairs),
        "status": "estimated",
        "mean_full_minus_compact": round(statistics.mean(score_deltas), 4),
        "length_residual_correlation": _pearson(lengths, residuals),
    }


def _pearson(values_a: list[float], values_b: list[float]) -> float | None:
    if len(values_a) < 2 or len(values_a) != len(values_b):
        return None
    mean_a = statistics.mean(values_a)
    mean_b = statistics.mean(values_b)
    centered_a = [value - mean_a for value in values_a]
    centered_b = [value - mean_b for value in values_b]
    denominator = math.sqrt(
        sum(value * value for value in centered_a)
        * sum(value * value for value in centered_b)
    )
    if math.isclose(denominator, 0.0):
        return None
    numerator = sum(
        value_a * value_b
        for value_a, value_b in zip(centered_a, centered_b, strict=True)
    )
    return round(numerator / denominator, 4)
