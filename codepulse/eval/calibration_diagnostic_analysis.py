"""Numeric agreement and bias analysis for Phase 2 diagnostic reviews."""

from __future__ import annotations

from collections import Counter
from typing import Any

from codepulse.eval.calibration_analysis import (
    analyze_length_bias,
    categorical_agreement,
    heldout_bias_correction,
    score_agreement,
)
from codepulse.eval.calibration_diagnostic import (
    validate_diagnostic_responses,
)
from codepulse.eval.calibration_diagnostic_judge import (
    DIAGNOSTIC_JUDGE_VARIANTS,
    validate_diagnostic_judge_observations,
)


def analyze_diagnostic_study(
    *,
    functional_result: dict[str, Any],
    packets_1: list[dict[str, Any]],
    mapping_1: list[dict[str, Any]],
    responses_1: list[dict[str, Any]],
    packets_2: list[dict[str, Any]],
    mapping_2: list[dict[str, Any]],
    responses_2: list[dict[str, Any]],
    judge_observations: list[dict[str, Any]],
    adjudications: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Align two blind review rounds with full/compact Judge observations."""
    _validate_functional_result(functional_result)
    validation_errors = [
        *validate_diagnostic_responses(packets_1, responses_1),
        *validate_diagnostic_responses(packets_2, responses_2),
        *validate_diagnostic_judge_observations(packets_1, judge_observations),
    ]
    if validation_errors:
        raise ValueError("invalid diagnostic study inputs: " + "; ".join(validation_errors))

    packet_to_trial_1 = _packet_to_trial(mapping_1, packets_1)
    packet_to_trial_2 = _packet_to_trial(mapping_2, packets_2)
    scores_1 = _scores_by_trial(responses_1, packet_to_trial_1)
    scores_2 = _scores_by_trial(responses_2, packet_to_trial_2)
    if set(scores_1) != set(scores_2):
        raise ValueError("diagnostic review rounds do not cover the same trials")

    trial_ids = sorted(scores_1)
    human_agreement = _combined_score_agreement(
        [scores_1[trial_id] for trial_id in trial_ids],
        [scores_2[trial_id] for trial_id in trial_ids],
    )
    packet_by_id = {str(packet["packet_id"]): packet for packet in packets_1}
    packet_id_by_trial = {
        trial_id: packet_id for packet_id, trial_id in packet_to_trial_1.items()
    }
    adjudicated = _validate_adjudications(
        adjudications or [], scores_1, scores_2, packet_id_by_trial
    )

    consensus: dict[str, int] = {}
    hard_cases: list[dict[str, Any]] = []
    for trial_id in trial_ids:
        packet_id = packet_id_by_trial[trial_id]
        packet = packet_by_id[packet_id]
        if scores_1[trial_id] == scores_2[trial_id]:
            consensus[trial_id] = scores_1[trial_id]
        else:
            hard_cases.append(_hard_case("human_disagreement", packet))
            if trial_id in adjudicated:
                consensus[trial_id] = adjudicated[trial_id]
        verification = packet["evidence"]["verification"]
        if (
            verification["exit_code"] != 0
            or verification["pytest_passed"] != verification["pytest_total"]
        ):
            hard_cases.append(_hard_case("official_failure", packet))

    observations_by_trial: dict[str, dict[str, dict[str, Any]]] = {
        trial_id: {} for trial_id in trial_ids
    }
    missing_judge = 0
    for observation in judge_observations:
        packet_id = str(observation["packet_id"])
        mapped_trial_id = packet_to_trial_1.get(packet_id)
        if mapped_trial_id is None:
            raise ValueError(f"Judge observation has no private mapping: {packet_id}")
        variant = str(observation["variant"])
        observations_by_trial[mapped_trial_id][variant] = observation
        if observation["status"] == "missing":
            missing_judge += 1
            hard_cases.append(_hard_case("judge_missing", packet_by_id[packet_id], variant))

    agreement_by_variant: dict[str, dict[str, Any]] = {}
    aligned_by_variant: dict[str, list[tuple[str, float, float]]] = {}
    for variant in DIAGNOSTIC_JUDGE_VARIANTS:
        aligned: list[tuple[str, float, float]] = []
        for trial_id in trial_ids:
            observation = observations_by_trial[trial_id][variant]
            if observation["status"] != "ok" or trial_id not in consensus:
                continue
            judge_score = float(observation["score"])
            human_score = float(consensus[trial_id])
            aligned.append((trial_id, judge_score, human_score))
            if judge_score != human_score:
                packet = packet_by_id[packet_id_by_trial[trial_id]]
                hard_cases.append(_hard_case("judge_human_disagreement", packet, variant))
        aligned_by_variant[variant] = aligned
        agreement_by_variant[variant] = (
            _combined_score_agreement(
                [judge for _, judge, _ in aligned],
                [human for _, _, human in aligned],
            )
            if aligned
            else _empty_score_agreement()
        )

    length_pairs: list[dict[str, Any]] = []
    for trial_id in trial_ids:
        full = observations_by_trial[trial_id]["length_full"]
        compact = observations_by_trial[trial_id]["length_compact"]
        if full["status"] != "ok" or compact["status"] != "ok" or trial_id not in consensus:
            continue
        packet = packet_by_id[packet_id_by_trial[trial_id]]
        if full["score"] != compact["score"]:
            hard_cases.append(_hard_case("length_sensitive", packet))
        length_pairs.append(
            {
                "sample_id": packet["packet_id"],
                "full_score": full["score"],
                "compact_score": compact["score"],
                "full_length": full["evidence_chars"],
                "compact_length": compact["evidence_chars"],
                "human_score": consensus[trial_id],
            }
        )

    full_rows = [
        {
            "sample_id": packet_id_by_trial[trial_id],
            "judge_score": judge,
            "human_score": human,
        }
        for trial_id, judge, human in aligned_by_variant["length_full"]
    ]
    calibration = _calibration(full_rows)
    unresolved = sum(
        scores_1[trial_id] != scores_2[trial_id] and trial_id not in adjudicated
        for trial_id in trial_ids
    )
    length_bias = analyze_length_bias(length_pairs)
    complete = (
        len(trial_ids) >= 10
        and unresolved == 0
        and missing_judge == 0
        and all(
            agreement_by_variant[variant]["n"] == len(trial_ids)
            for variant in DIAGNOSTIC_JUDGE_VARIANTS
        )
        and length_bias["n"] == len(trial_ids)
        and calibration["status"] == "estimated"
    )
    return {
        "status": "complete" if complete else "incomplete",
        "functional_calibration": functional_result,
        "sample_size": len(trial_ids),
        "reviewer_mode": (
            "inter_rater"
            if {str(row["reviewer_id"]) for row in responses_1}
            != {str(row["reviewer_id"]) for row in responses_2}
            else "intra_rater"
        ),
        "human_agreement": human_agreement,
        "unresolved_human_disagreements": unresolved,
        "judge_human_agreement": agreement_by_variant,
        "missing_judge_observations": missing_judge,
        "calibration": calibration,
        "position_bias": {
            "n": 0,
            "status": "not_identifiable",
            "reason": "a single candidate provides no order-swapped A/B comparison",
        },
        "length_bias": length_bias,
        "model_self_preference": {
            "status": "not_identifiable",
            "reason": "crossed candidate and Judge model families are unavailable",
        },
        "hard_cases": _deduplicate_cases(hard_cases),
        "usage_boundaries": {
            "deterministic_grader": "authoritative for executable official tests and static checks",
            "llm_judge": "limited to evidence-complete qualitative dimensions with raw-response retention",
            "human_calibration": "required for qualitative agreement and hard-case adjudication",
        },
    }


def render_diagnostic_report(analysis: dict[str, Any]) -> str:
    """Render the qualitative diagnostic analysis as a concise Markdown report."""
    functional = analysis.get("functional_calibration", {})
    functional_before = functional.get("before", {})
    functional_after = functional.get("after", {})
    human = analysis.get("human_agreement", {})
    judge = analysis.get("judge_human_agreement", {})
    full = judge.get("length_full", {})
    compact = judge.get("length_compact", {})
    length = analysis.get("length_bias", {})
    calibration = analysis.get("calibration", {})
    before = calibration.get("before", {})
    after = calibration.get("after", {})
    hard_cases = analysis.get("hard_cases", [])
    reviewer_mode = str(analysis.get("reviewer_mode", "unknown")).replace("_", "-")
    repeatability_label = (
        "Intra-rater repeatability"
        if reviewer_mode == "intra-rater"
        else "Inter-rater agreement"
    )
    hard_case_counts = Counter(str(case.get("kind", "unknown")) for case in hard_cases)
    hard_case_lines = [
        f"- {kind.replace('_', ' ')}: {count}"
        for kind, count in sorted(hard_case_counts.items())
    ] or ["- None."]
    lines = [
        "# Phase 2 LLM-as-Judge Calibration Report",
        "",
        f"Status: **{analysis.get('status', 'incomplete')}**",
        "",
        "## Functional Oracle Calibration",
        "",
        f"- Sample size: {functional.get('sample_size', 0)}",
        f"- Exact agreement before: {_percentage(functional_before.get('exact_agreement'))}",
        f"- Exact agreement after: {_percentage(functional_after.get('exact_agreement'))}",
        f"- Cohen's kappa before: {_display(functional_before.get('cohens_kappa'))}",
        f"- Cohen's kappa after: {_display(functional_after.get('cohens_kappa'))}",
        "- Reference: deterministic official functional verification, not human annotation.",
        "",
        "## Qualitative Diagnostic Study",
        "",
        f"Sample size: **{analysis.get('sample_size', 0)}**",
        f"Reviewer mode: **{reviewer_mode}**",
        "",
        "## Agreement",
        "",
        f"- {repeatability_label} sample count: {_display(human.get('n'))}",
        f"- {repeatability_label} exact agreement: {_display(human.get('exact_agreement'))}",
        f"- {repeatability_label} within one point: {_display(human.get('within_one_point'))}",
        f"- {repeatability_label} Cohen's kappa: {_display(human.get('cohens_kappa'))}",
        f"- {repeatability_label} Pearson: {_display(human.get('pearson'))}",
        f"- {repeatability_label} mean absolute error: {_display(human.get('mean_absolute_error'))}",
        f"- Full Judge-human sample count: {_display(full.get('n'))}",
        f"- Full Judge-human exact agreement: {_display(full.get('exact_agreement'))}",
        f"- Full Judge-human within one point: {_display(full.get('within_one_point'))}",
        f"- Full Judge-human Cohen's kappa: {_display(full.get('cohens_kappa'))}",
        f"- Full Judge-human Pearson: {_display(full.get('pearson'))}",
        f"- Full Judge-human mean absolute error: {_display(full.get('mean_absolute_error'))}",
        f"- Compact Judge-human sample count: {_display(compact.get('n'))}",
        f"- Compact Judge-human exact agreement: {_display(compact.get('exact_agreement'))}",
        f"- Compact Judge-human within one point: {_display(compact.get('within_one_point'))}",
        f"- Compact Judge-human Cohen's kappa: {_display(compact.get('cohens_kappa'))}",
        f"- Compact Judge-human Pearson: {_display(compact.get('pearson'))}",
        f"- Compact Judge-human mean absolute error: {_display(compact.get('mean_absolute_error'))}",
        f"- Missing Judge observations: {analysis.get('missing_judge_observations', 0)}",
        "",
        "## Bias Diagnostics",
        "",
        f"- Position bias: {_display(analysis.get('position_bias', {}).get('status'))}",
        f"- Position bias reason: {_display(analysis.get('position_bias', {}).get('reason'))}",
        f"- Length full-minus-compact delta: {_display(length.get('mean_full_minus_compact'))}",
        f"- Length/residual Pearson: {_display(length.get('length_residual_correlation'))}",
        f"- Model self-preference: {_display(analysis.get('model_self_preference', {}).get('status'))}",
        f"- Model self-preference reason: {_display(analysis.get('model_self_preference', {}).get('reason'))}",
        "",
        "No significance claim is made from this small diagnostic batch.",
        "",
        "## Hard Cases",
        "",
        f"Total: **{len(hard_cases)}**",
        "",
        *hard_case_lines,
        "",
        "## Held-out Calibration",
        "",
        f"- Mean absolute error before: {_display(before.get('mean_absolute_error'))}",
        f"- Mean absolute error after: {_display(after.get('mean_absolute_error'))}",
        "",
        "## Usage Boundaries",
        "",
        "- **Deterministic Grader:** authoritative for executable official tests and static checks.",
        "- **LLM Judge:** limited to evidence-complete qualitative dimensions; raw responses and missing calls remain visible.",
        "- **Human calibration:** required for qualitative agreement and hard-case adjudication; it cannot override deterministic ground truth.",
    ]
    return "\n".join(lines) + "\n"


def _packet_to_trial(
    mapping: list[dict[str, Any]], packets: list[dict[str, Any]]
) -> dict[str, str]:
    packet_ids = {str(packet["packet_id"]) for packet in packets}
    mapped_ids = [str(row.get("packet_id", "")) for row in mapping]
    if Counter(mapped_ids) != Counter(packet_ids):
        raise ValueError("private diagnostic mapping does not match packet coverage")
    result: dict[str, str] = {}
    trial_ids: list[str] = []
    for row in mapping:
        packet_id = str(row.get("packet_id", ""))
        trial_id = str(row.get("trial_id", ""))
        if not trial_id:
            raise ValueError(f"private diagnostic mapping {packet_id} requires trial_id")
        result[packet_id] = trial_id
        trial_ids.append(trial_id)
    duplicates = [trial_id for trial_id, count in Counter(trial_ids).items() if count > 1]
    if duplicates:
        raise ValueError("private diagnostic mapping contains duplicate trials")
    return result


def _validate_functional_result(result: dict[str, Any]) -> None:
    sample_size = result.get("sample_size")
    if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 100:
        raise ValueError("functional calibration requires at least 100 samples")
    if not _nonempty_string(result.get("comparison_reference")):
        raise ValueError("functional calibration requires its deterministic reference")
    for phase in ("before", "after"):
        metrics = result.get(phase)
        if not isinstance(metrics, dict):
            raise ValueError(f"functional calibration requires {phase} metrics")
        observations = metrics.get("observations")
        missing = metrics.get("missing")
        agreement = metrics.get("exact_agreement")
        if (
            not isinstance(observations, int)
            or isinstance(observations, bool)
            or observations < 100
            or missing != 0
            or not isinstance(agreement, (int, float))
            or isinstance(agreement, bool)
            or not 0 <= float(agreement) <= 1
        ):
            raise ValueError(f"functional calibration has invalid {phase} metrics")


def _scores_by_trial(
    responses: list[dict[str, Any]], packet_to_trial: dict[str, str]
) -> dict[str, int]:
    return {
        packet_to_trial[str(response["packet_id"])]: int(response["score"])
        for response in responses
    }


def _validate_adjudications(
    rows: list[dict[str, Any]],
    scores_1: dict[str, int],
    scores_2: dict[str, int],
    packet_id_by_trial: dict[str, str],
) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        trial_id = str(row.get("trial_id", ""))
        if trial_id not in scores_1:
            raise ValueError(f"adjudication references unknown trial: {trial_id}")
        if trial_id in result:
            raise ValueError(f"duplicate adjudication for trial: {trial_id}")
        if scores_1[trial_id] == scores_2[trial_id]:
            raise ValueError(f"adjudication is not required for trial: {trial_id}")
        score = row.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            raise ValueError(f"adjudication {trial_id} has invalid score")
        if row.get("packet_id") != packet_id_by_trial[trial_id]:
            raise ValueError(f"adjudication {trial_id} packet_id mismatch")
        if not _nonempty_string(row.get("rationale")) or not _nonempty_string(
            row.get("adjudicated_at")
        ):
            raise ValueError(f"adjudication {trial_id} requires rationale and adjudicated_at")
        result[trial_id] = score
    return result


def _combined_score_agreement(
    scores_a: list[float | int], scores_b: list[float | int]
) -> dict[str, Any]:
    numeric = score_agreement(
        [float(score) for score in scores_a], [float(score) for score in scores_b]
    )
    categorical = categorical_agreement(
        [str(score) for score in scores_a], [str(score) for score in scores_b]
    )
    return {
        **numeric,
        "exact_agreement": categorical["exact_agreement"],
        "cohens_kappa": categorical["cohens_kappa"],
        "degenerate": categorical["degenerate"],
        "distribution_a": categorical["distribution_a"],
        "distribution_b": categorical["distribution_b"],
    }


def _empty_score_agreement() -> dict[str, Any]:
    return {
        "n": 0,
        "exact_agreement": None,
        "within_one_point": None,
        "pearson": None,
        "mean_signed_error": None,
        "mean_absolute_error": None,
        "cohens_kappa": None,
        "degenerate": True,
        "distribution_a": {},
        "distribution_b": {},
    }


def _calibration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 4:
        return {
            "status": "not_available",
            "reason": "at least four aligned full Judge-human scores are required",
        }
    result = heldout_bias_correction(rows)
    offset = float(result["bias_offset"])
    judge_scores = [float(row["judge_score"]) for row in rows]
    human_scores = [float(row["human_score"]) for row in rows]
    return {
        "status": "estimated",
        **result,
        "score_distributions": {
            "judge_before": _score_distribution(judge_scores),
            "judge_after": _score_distribution([score - offset for score in judge_scores]),
            "human": _score_distribution(human_scores),
        },
    }


def _score_distribution(scores: list[float]) -> dict[str, int]:
    return dict(sorted(Counter(f"{score:.4g}" for score in scores).items()))


def _hard_case(
    kind: str, packet: dict[str, Any], variant: str | None = None
) -> dict[str, Any]:
    result = {
        "kind": kind,
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
    }
    if variant is not None:
        result["variant"] = variant
    return result


def _deduplicate_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {
        (str(case["kind"]), str(case["packet_id"]), str(case.get("variant", ""))): case
        for case in cases
    }
    return [unique[key] for key in sorted(unique)]


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _display(value: object) -> str:
    return "not_available" if value is None else str(value)


def _percentage(value: object) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "not_available"
    return f"{float(value) * 100:.1f}%"
