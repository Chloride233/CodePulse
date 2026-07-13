"""Agreement, calibration, and bias analysis for Phase 2 Judge studies."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any

from codepulse.eval.calibration_review import (
    FUNCTIONAL_LABELS,
    validate_judge_observations,
    validate_review_responses,
)


def analyze_calibration_study(
    *,
    packets_1: list[dict[str, Any]],
    mapping_1: list[dict[str, Any]],
    responses_1: list[dict[str, Any]],
    packets_2: list[dict[str, Any]],
    mapping_2: list[dict[str, Any]],
    responses_2: list[dict[str, Any]],
    judge_observations: list[dict[str, Any]],
    adjudications: list[dict[str, Any]] | None = None,
    score_rows: list[dict[str, Any]] | None = None,
    position_pairs: list[dict[str, Any]] | None = None,
    length_pairs: list[dict[str, Any]] | None = None,
    self_preference_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Align blinded artifacts and build the authoritative study analysis."""
    validation_errors = [
        *validate_review_responses(packets_1, responses_1),
        *validate_review_responses(packets_2, responses_2),
        *validate_judge_observations(packets_1, judge_observations),
    ]
    if validation_errors:
        raise ValueError("invalid study inputs: " + "; ".join(validation_errors))

    packet_to_sample_1 = _packet_to_sample(mapping_1)
    packet_to_sample_2 = _packet_to_sample(mapping_2)
    labels_1 = _labels_by_sample(responses_1, packet_to_sample_1)
    labels_2 = _labels_by_sample(responses_2, packet_to_sample_2)
    if set(labels_1) != set(labels_2):
        raise ValueError("review rounds do not cover the same source samples")

    sample_ids = sorted(labels_1)
    human_agreement = categorical_agreement(
        [labels_1[sample_id] for sample_id in sample_ids],
        [labels_2[sample_id] for sample_id in sample_ids],
    )
    adjudicated = {
        str(row["sample_id"]): str(row["label"])
        for row in (adjudications or [])
        if row.get("label") in FUNCTIONAL_LABELS
    }
    consensus: dict[str, str] = {}
    hard_cases: list[dict[str, str]] = []
    for sample_id in sample_ids:
        if labels_1[sample_id] == labels_2[sample_id]:
            consensus[sample_id] = labels_1[sample_id]
        elif sample_id in adjudicated:
            consensus[sample_id] = adjudicated[sample_id]
            hard_cases.append({"kind": "human_disagreement", "sample_id": sample_id})
        else:
            hard_cases.append({"kind": "human_disagreement", "sample_id": sample_id})

    judge_labels: list[str] = []
    human_labels: list[str] = []
    by_model_pairs: dict[str, tuple[list[str], list[str]]] = {}
    missing_judge = 0
    for observation in judge_observations:
        packet_id = str(observation["packet_id"])
        mapped_sample_id = packet_to_sample_1.get(packet_id)
        if mapped_sample_id is None:
            raise ValueError(f"Judge observation has no private mapping: {packet_id}")
        if observation["status"] == "missing":
            missing_judge += 1
            hard_cases.append({"kind": "judge_missing", "sample_id": mapped_sample_id})
            continue
        if mapped_sample_id not in consensus:
            continue
        judge_label = str(observation["label"])
        human_label = consensus[mapped_sample_id]
        judge_labels.append(judge_label)
        human_labels.append(human_label)
        model = str(observation["judge_model"])
        model_judge, model_human = by_model_pairs.setdefault(model, ([], []))
        model_judge.append(judge_label)
        model_human.append(human_label)
        if judge_label != human_label:
            hard_cases.append(
                {"kind": "judge_human_disagreement", "sample_id": mapped_sample_id}
            )

    judge_agreement = (
        categorical_agreement(judge_labels, human_labels)
        if judge_labels
        else _empty_agreement()
    )
    judge_agreement_by_model = {
        model: categorical_agreement(model_labels, model_human)
        for model, (model_labels, model_human) in sorted(by_model_pairs.items())
    }
    calibration = (
        {"status": "estimated", **heldout_bias_correction(score_rows)}
        if score_rows is not None and len(score_rows) >= 4
        else {
            "status": "not_available",
            "reason": "at least four aligned numeric Judge-human scores are required",
        }
    )
    position = analyze_position_bias(position_pairs or [])
    length = analyze_length_bias(length_pairs or [])
    self_preference = analyze_model_self_preference(self_preference_rows or [])
    unresolved = sum(
        labels_1[sample_id] != labels_2[sample_id] and sample_id not in adjudicated
        for sample_id in sample_ids
    )
    diagnostics_complete = (
        position.get("status") == "estimated"
        and length.get("status") == "estimated"
        and self_preference.get("status") in {"estimated", "not_identifiable"}
    )
    complete = (
        len(sample_ids) >= 100
        and unresolved == 0
        and missing_judge == 0
        and judge_agreement["n"] >= len(sample_ids)
        and calibration.get("status") == "estimated"
        and diagnostics_complete
    )
    return {
        "status": "complete" if complete else "incomplete",
        "sample_size": len(sample_ids),
        "reviewer_mode": (
            "inter_rater"
            if {str(row["reviewer_id"]) for row in responses_1}
            != {str(row["reviewer_id"]) for row in responses_2}
            else "intra_rater"
        ),
        "human_agreement": human_agreement,
        "unresolved_human_disagreements": unresolved,
        "judge_agreement": judge_agreement,
        "judge_agreement_by_model": judge_agreement_by_model,
        "missing_judge_observations": missing_judge,
        "calibration": calibration,
        "position_bias": position,
        "length_bias": length,
        "model_self_preference": self_preference,
        "hard_cases": _deduplicate_cases(hard_cases),
    }


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


def analyze_position_bias(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure preference flips and first-position advantage after A/B swaps."""
    if not pairs:
        return {"n": 0, "status": "not_identifiable"}
    flips = sum(pair["ab_winner"] != pair["ba_winner"] for pair in pairs)
    position_deltas = [
        float(pair[key])
        for pair in pairs
        for key in ("ab_first_minus_second", "ba_first_minus_second")
    ]
    return {
        "n": len(pairs),
        "status": "estimated",
        "preference_flip_rate": round(flips / len(pairs), 4),
        "mean_first_position_advantage": round(statistics.mean(position_deltas), 4),
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


def analyze_model_self_preference(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare own-family and other-family Judge-minus-human residuals."""
    families = {
        str(row[key])
        for row in rows
        for key in ("judge_family", "candidate_family")
    }
    own = [
        float(row["judge_score"]) - float(row["human_score"])
        for row in rows
        if row["judge_family"] == row["candidate_family"]
    ]
    other = [
        float(row["judge_score"]) - float(row["human_score"])
        for row in rows
        if row["judge_family"] != row["candidate_family"]
    ]
    if len(families) < 2 or not own or not other:
        return {
            "status": "not_identifiable",
            "reason": "crossed candidate and Judge model families are required",
            "own_family_n": len(own),
            "other_family_n": len(other),
        }
    own_mean = statistics.mean(own)
    other_mean = statistics.mean(other)
    return {
        "status": "estimated",
        "own_family_n": len(own),
        "other_family_n": len(other),
        "own_family_mean_residual": round(own_mean, 4),
        "other_family_mean_residual": round(other_mean, 4),
        "self_preference_effect": round(own_mean - other_mean, 4),
    }


def render_calibration_report(analysis: dict[str, Any]) -> str:
    """Render a concise evidence report from authoritative analysis JSON."""
    human = analysis.get("human_agreement", {})
    judge = analysis.get("judge_agreement", {})
    position = analysis.get("position_bias", {})
    length = analysis.get("length_bias", {})
    self_preference = analysis.get("model_self_preference", {})
    calibration = analysis.get("calibration", {})
    before = calibration.get("before", {})
    after = calibration.get("after", {})
    hard_cases = analysis.get("hard_cases", [])
    lines = [
        "# Phase 2 LLM-as-Judge Calibration Report",
        "",
        f"Status: **{analysis.get('status', 'incomplete')}**",
        f"Sample size: **{analysis.get('sample_size', 0)}**",
        "",
        "## Agreement",
        "",
        f"- Human exact agreement: {_display(human.get('exact_agreement'))}",
        f"- Human Cohen's kappa: {_display(human.get('cohens_kappa'))}",
        f"- Judge-human exact agreement: {_display(judge.get('exact_agreement'))}",
        f"- Judge-human Cohen's kappa: {_display(judge.get('cohens_kappa'))}",
        "",
        "## Bias Diagnostics",
        "",
        f"- Position preference flip rate: {_display(position.get('preference_flip_rate'))}",
        f"- Length full-minus-compact delta: {_display(length.get('mean_full_minus_compact'))}",
        f"- Model self-preference: {_display(self_preference.get('status'))}",
        f"- Hard cases: {len(hard_cases)}",
        "",
        "## Held-out Calibration",
        "",
        f"- Mean absolute error before: {_display(before.get('mean_absolute_error'))}",
        f"- Mean absolute error after: {_display(after.get('mean_absolute_error'))}",
        "",
        "## Usage Boundaries",
        "",
        "- **Deterministic Grader:** authoritative whenever executable official tests or static checks directly measure the requirement.",
        "- **LLM Judge:** limited to evidence-complete qualitative dimensions; retain raw reasoning and treat malformed calls as missing.",
        "- **Human calibration:** required to establish Judge agreement and adjudicate hard cases; it does not override deterministic ground truth.",
    ]
    return "\n".join(lines) + "\n"


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


def _packet_to_sample(mapping: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in mapping:
        packet_id = str(row.get("packet_id", ""))
        sample_id = str(row.get("sample_id", ""))
        if not packet_id or not sample_id:
            raise ValueError("private review mapping requires packet_id and sample_id")
        if packet_id in result:
            raise ValueError(f"duplicate private mapping for packet {packet_id}")
        result[packet_id] = sample_id
    return result


def _labels_by_sample(
    responses: list[dict[str, Any]], packet_to_sample: dict[str, str]
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for response in responses:
        packet_id = str(response["packet_id"])
        sample_id = packet_to_sample.get(packet_id)
        if sample_id is None:
            raise ValueError(f"response has no private mapping: {packet_id}")
        labels[sample_id] = str(response["label"])
    return labels


def _empty_agreement() -> dict[str, Any]:
    return {
        "n": 0,
        "exact_agreement": None,
        "cohens_kappa": None,
        "degenerate": True,
        "distribution_a": {},
        "distribution_b": {},
    }


def _deduplicate_cases(cases: list[dict[str, str]]) -> list[dict[str, str]]:
    unique = {(case["kind"], case["sample_id"]) for case in cases}
    return [
        {"kind": kind, "sample_id": sample_id}
        for kind, sample_id in sorted(unique)
    ]


def _display(value: object) -> str:
    return "not_available" if value is None else str(value)
