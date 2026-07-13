"""Tests for the Phase 2 blinded calibration study workflow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from codepulse.eval.calibration_analysis import (
    analyze_calibration_study,
    analyze_length_bias,
    analyze_model_self_preference,
    analyze_position_bias,
    categorical_agreement,
    heldout_bias_correction,
    render_calibration_report,
    score_agreement,
)
from codepulse.eval.calibration_review import (
    build_response_template,
    build_review_packets,
    prepare_review_files,
    run_functional_judge,
    validate_judge_observations,
    validate_review_packets,
    validate_review_responses,
)

ROOT = Path(__file__).parents[1]
FUNCTIONAL_LABELS_FOR_TEST = (
    "supported_pass",
    "supported_fail",
    "insufficient_evidence",
)


def _records() -> list[dict[str, object]]:
    return [
        {
            "sample_id": "cal-v1-001",
            "source_trial_id": "HumanEval/0--r0--agent-secret",
            "task_id": "HumanEval/0",
            "agent_name": "agent-secret",
            "stratum": "success",
            "deterministic_evidence": {
                "success": True,
                "scores": {"functional": 1.0},
                "outcome": {
                    "exit_code": 0,
                    "stdout": "1 passed in 0.01s",
                    "stderr": "",
                    "provider_model_versions": ["model-secret"],
                },
                "metrics": {"output_tokens": 99},
            },
            "artifact_status": "missing_final_code_and_full_transcript",
            "eligible_dimensions": ["functional_evidence"],
            "ineligible_dimensions": ["process_quality", "experience_alignment"],
            "llm_judge": {"model": "judge-secret", "score": None},
            "human_review_round_1": {"reviewer_id": None, "score": None},
        },
        {
            "sample_id": "cal-v1-002",
            "source_trial_id": "HumanEval/1--r0--other-secret",
            "task_id": "HumanEval/1",
            "agent_name": "other-secret",
            "stratum": "failure",
            "deterministic_evidence": {
                "success": False,
                "scores": {"functional": 0.0},
                "outcome": {
                    "exit_code": 1,
                    "stdout": "1 failed in 0.01s",
                    "stderr": "",
                    "provider_model_versions": ["other-model-secret"],
                },
                "metrics": {"output_tokens": 42},
            },
            "artifact_status": "missing_final_code_and_full_transcript",
            "eligible_dimensions": ["functional_evidence"],
            "ineligible_dimensions": ["process_quality", "experience_alignment"],
            "llm_judge": {"model": None, "score": None},
            "human_review_round_1": {"reviewer_id": None, "score": None},
        },
    ]


def test_calibration_packets_are_deterministic_and_blinded() -> None:
    packets, mapping = build_review_packets(_records(), round_number=1, seed=7)

    assert packets == build_review_packets(_records(), round_number=1, seed=7)[0]
    assert {item["sample_id"] for item in mapping} == {"cal-v1-001", "cal-v1-002"}
    serialized = json.dumps(packets)
    for secret in (
        "agent-secret",
        "other-secret",
        "model-secret",
        "judge-secret",
        '"success"',
        '"scores"',
    ):
        assert secret not in serialized
    assert validate_review_packets(packets) == []


def test_calibration_packet_ids_change_between_rounds() -> None:
    round_1, _ = build_review_packets(_records(), round_number=1, seed=7)
    round_2, _ = build_review_packets(_records(), round_number=2, seed=7)

    assert {packet["packet_id"] for packet in round_1}.isdisjoint(
        {packet["packet_id"] for packet in round_2}
    )


def test_calibration_response_template_validates_when_completed() -> None:
    packets, _ = build_review_packets(_records(), round_number=1, seed=7)
    responses = build_response_template(packets, reviewer_id="human-a")
    for response, label in zip(
        responses, ("supported_pass", "supported_fail"), strict=True
    ):
        response["label"] = label
        response["rationale"] = "Official verification output supports this label."
        response["reviewed_at"] = "2026-07-13T00:00:00Z"

    assert validate_review_responses(packets, responses) == []


def test_calibration_response_validation_rejects_missing_and_hash_drift() -> None:
    packets, _ = build_review_packets(_records(), round_number=1, seed=7)
    responses = build_response_template(packets, reviewer_id="human-a")[:1]
    responses[0]["label"] = "invalid-label"
    responses[0]["rationale"] = ""
    responses[0]["packet_sha256"] = "0" * 64

    errors = validate_review_responses(packets, responses)

    assert any("coverage" in error for error in errors)
    assert any("label" in error for error in errors)
    assert any("rationale" in error for error in errors)
    assert any("hash" in error for error in errors)


def test_calibration_packet_validation_detects_identity_leakage() -> None:
    packets, _ = build_review_packets(_records(), round_number=1, seed=7)
    packets[0]["evidence"]["agent_name"] = "leaked"

    assert any("forbidden" in error for error in validate_review_packets(packets))


def test_calibration_judge_observations_keep_failures_missing() -> None:
    packets, _ = build_review_packets(_records(), round_number=1, seed=7)
    observations = [
        {
            "packet_id": packets[0]["packet_id"],
            "packet_sha256": packets[0]["packet_sha256"],
            "judge_model": "judge-a",
            "variant": "identity_blind",
            "status": "ok",
            "label": "supported_pass",
            "score": None,
            "reasoning": "The official verification passed.",
            "raw_response": '{"label":"supported_pass"}',
            "error": None,
        },
        {
            "packet_id": packets[1]["packet_id"],
            "packet_sha256": packets[1]["packet_sha256"],
            "judge_model": "judge-a",
            "variant": "identity_blind",
            "status": "missing",
            "label": None,
            "score": None,
            "reasoning": None,
            "raw_response": None,
            "error": "provider timeout",
        },
    ]

    assert validate_judge_observations(packets, observations) == []
    observations[1]["score"] = 0
    assert any(
        "missing observation" in error
        for error in validate_judge_observations(packets, observations)
    )


def test_calibration_categorical_agreement_reports_kappa_and_distribution() -> None:
    result = categorical_agreement(
        ["pass", "pass", "fail", "fail"],
        ["pass", "pass", "fail", "pass"],
    )

    assert result["n"] == 4
    assert result["exact_agreement"] == 0.75
    assert result["cohens_kappa"] == 0.5
    assert result["distribution_a"] == {"fail": 2, "pass": 2}


def test_calibration_score_agreement_separates_correlation_and_error() -> None:
    result = score_agreement([1.0, 2.0, 3.0], [2.0, 4.0, 6.0])

    assert result["pearson"] == 1.0
    assert result["mean_signed_error"] == -2.0
    assert result["mean_absolute_error"] == 2.0
    assert score_agreement([1.0, 1.0], [2.0, 3.0])["pearson"] is None


def test_calibration_bias_correction_is_evaluated_on_heldout_records() -> None:
    rows = [
        {"sample_id": f"s{i}", "judge_score": human + 0.2, "human_score": human}
        for i, human in enumerate((0.1, 0.3, 0.5, 0.7, 0.2, 0.6))
    ]

    result = heldout_bias_correction(rows)

    assert result["train_n"] == 3
    assert result["test_n"] == 3
    assert result["bias_offset"] == 0.2
    assert result["after"]["mean_absolute_error"] < result["before"]["mean_absolute_error"]


def test_calibration_position_bias_uses_swapped_pairs() -> None:
    result = analyze_position_bias(
        [
            {
                "comparison_id": "c1",
                "ab_winner": "candidate_a",
                "ba_winner": "candidate_b",
                "ab_first_minus_second": 0.4,
                "ba_first_minus_second": 0.2,
            },
            {
                "comparison_id": "c2",
                "ab_winner": "candidate_a",
                "ba_winner": "candidate_a",
                "ab_first_minus_second": 0.1,
                "ba_first_minus_second": -0.1,
            },
        ]
    )

    assert result["n"] == 2
    assert result["preference_flip_rate"] == 0.5
    assert result["mean_first_position_advantage"] == 0.15


def test_calibration_length_bias_uses_paired_variants() -> None:
    result = analyze_length_bias(
        [
            {
                "sample_id": "s1",
                "full_score": 5.0,
                "compact_score": 4.0,
                "full_length": 1000,
                "compact_length": 200,
                "human_score": 4.0,
            },
            {
                "sample_id": "s2",
                "full_score": 4.0,
                "compact_score": 3.0,
                "full_length": 800,
                "compact_length": 100,
                "human_score": 3.0,
            },
        ]
    )

    assert result["n"] == 2
    assert result["mean_full_minus_compact"] == 1.0
    assert result["length_residual_correlation"] > 0


def test_calibration_self_preference_uses_crossed_human_residuals() -> None:
    result = analyze_model_self_preference(
        [
            {"judge_family": "a", "candidate_family": "a", "judge_score": 4.2, "human_score": 4.0},
            {"judge_family": "b", "candidate_family": "b", "judge_score": 3.1, "human_score": 3.0},
            {"judge_family": "a", "candidate_family": "b", "judge_score": 2.9, "human_score": 3.0},
            {"judge_family": "b", "candidate_family": "a", "judge_score": 4.0, "human_score": 4.0},
        ]
    )

    assert result["status"] == "estimated"
    assert result["own_family_n"] == 2
    assert result["other_family_n"] == 2
    assert result["self_preference_effect"] == 0.2
    assert analyze_model_self_preference(
        [{"judge_family": "a", "candidate_family": "a", "judge_score": 4.0, "human_score": 4.0}]
    )["status"] == "not_identifiable"


def test_calibration_report_states_usage_boundaries() -> None:
    report = render_calibration_report(
        {
            "status": "complete",
            "sample_size": 100,
            "human_agreement": {"exact_agreement": 0.9, "cohens_kappa": 0.8},
            "judge_agreement": {"exact_agreement": 0.85, "cohens_kappa": 0.7},
            "position_bias": {"preference_flip_rate": 0.1},
            "length_bias": {"mean_full_minus_compact": 0.2},
            "model_self_preference": {"status": "not_identifiable"},
            "hard_cases": ["sample-1"],
            "calibration": {
                "before": {"mean_absolute_error": 0.3},
                "after": {"mean_absolute_error": 0.2},
            },
        }
    )

    assert "Deterministic Grader" in report
    assert "LLM Judge" in report
    assert "Human calibration" in report
    assert "not_identifiable" in report


def test_calibration_rubric_and_runbook_publish_required_boundaries() -> None:
    rubric = (ROOT / "docs" / "phase2-human-rubric.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "phase2-calibration-runbook.md").read_text(
        encoding="utf-8"
    )

    assert all(label in rubric for label in FUNCTIONAL_LABELS_FOR_TEST)
    assert "does not contain final code or a full Trace" in rubric
    assert "process quality" in rubric
    assert "calibration_study prepare" in runbook
    assert "calibration_study judge" in runbook
    assert "calibration_study analyze" in runbook
    assert "not completed" in runbook


def test_calibration_prepare_writes_two_blind_rounds_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "sample.jsonl"
    source.write_text(
        "\n".join(json.dumps(record) for record in _records()) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "study"

    manifest = prepare_review_files(
        source,
        output,
        seed=7,
        reviewer_1="human-a",
        reviewer_2="human-b",
    )

    assert manifest["sample_size"] == 2
    assert manifest["reviewer_mode"] == "inter_rater"
    assert (output / "review-packets-round-1.jsonl").exists()
    assert (output / "review-packets-round-2.jsonl").exists()
    assert (output / "review-mapping-round-1.private.jsonl").exists()
    assert (output / "human-review-round-2.jsonl").exists()
    assert (output / "manifest.json").exists()
    with pytest.raises(FileExistsError):
        prepare_review_files(
            source,
            output,
            seed=7,
            reviewer_1="human-a",
            reviewer_2="human-b",
        )


def test_calibration_functional_judge_persists_malformed_raw_response() -> None:
    packets, _ = build_review_packets(_records(), round_number=1, seed=7)
    with patch(
        "codepulse.eval.calibration_review.call_llm_with_retry",
        side_effect=[
            '{"label":"supported_pass","reasoning":"Tests passed."}',
            "not json",
        ],
    ) as mock_call:
        observations = run_functional_judge(packets, model="judge-a")

    assert observations[0]["status"] == "ok"
    assert observations[0]["prompt_version"] == "functional-evidence-judge-v2"
    assert observations[1]["status"] == "missing"
    assert observations[1]["raw_response"] == "not json"
    system_prompt = mock_call.call_args_list[0].kwargs["messages"][0]["content"]
    assert "not contradict an otherwise complete official verification result" in system_prompt
    assert validate_judge_observations(packets, observations) == []


def test_calibration_analysis_aligns_blind_rounds_through_private_mapping() -> None:
    packets_1, mapping_1 = build_review_packets(_records(), round_number=1, seed=7)
    packets_2, mapping_2 = build_review_packets(_records(), round_number=2, seed=7)
    responses_1 = _completed_responses(packets_1, "human-a")
    responses_2 = _completed_responses(packets_2, "human-b")
    judge = _judge_observations_from_packets(packets_1)

    analysis = analyze_calibration_study(
        packets_1=packets_1,
        mapping_1=mapping_1,
        responses_1=responses_1,
        packets_2=packets_2,
        mapping_2=mapping_2,
        responses_2=responses_2,
        judge_observations=judge,
    )

    assert analysis["sample_size"] == 2
    assert analysis["human_agreement"]["exact_agreement"] == 1.0
    assert analysis["judge_agreement"]["exact_agreement"] == 1.0
    assert analysis["hard_cases"] == []
    assert analysis["status"] == "incomplete"


def test_calibration_analysis_requires_adjudication_for_human_disagreement() -> None:
    packets_1, mapping_1 = build_review_packets(_records(), round_number=1, seed=7)
    packets_2, mapping_2 = build_review_packets(_records(), round_number=2, seed=7)
    responses_1 = _completed_responses(packets_1, "human-a")
    responses_2 = _completed_responses(packets_2, "human-b")
    responses_2[0]["label"] = (
        "supported_fail"
        if responses_2[0]["label"] == "supported_pass"
        else "supported_pass"
    )

    analysis = analyze_calibration_study(
        packets_1=packets_1,
        mapping_1=mapping_1,
        responses_1=responses_1,
        packets_2=packets_2,
        mapping_2=mapping_2,
        responses_2=responses_2,
        judge_observations=[],
    )

    assert analysis["unresolved_human_disagreements"] == 1
    assert any(case["kind"] == "human_disagreement" for case in analysis["hard_cases"])


def _completed_responses(
    packets: list[dict[str, object]], reviewer_id: str
) -> list[dict[str, object]]:
    responses = build_response_template(packets, reviewer_id)
    for packet, response in zip(packets, responses, strict=True):
        stdout = packet["evidence"]["verification"].get("stdout", "")
        response["label"] = (
            "supported_fail" if "failed" in stdout else "supported_pass"
        )
        response["rationale"] = "Official verification output supports this label."
        response["reviewed_at"] = "2026-07-13T00:00:00Z"
    return responses


def _judge_observations_from_packets(
    packets: list[dict[str, object]],
) -> list[dict[str, object]]:
    observations = []
    for packet in packets:
        stdout = packet["evidence"]["verification"].get("stdout", "")
        label = "supported_fail" if "failed" in stdout else "supported_pass"
        observations.append(
            {
                "packet_id": packet["packet_id"],
                "packet_sha256": packet["packet_sha256"],
                "judge_model": "judge-a",
                "variant": "identity_blind",
                "status": "ok",
                "label": label,
                "score": None,
                "reasoning": "Official verification output supports this label.",
                "raw_response": json.dumps({"label": label}),
                "error": None,
            }
        )
    return observations
