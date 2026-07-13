"""Tests for functional Judge calibration and shared calibration metrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from codepulse.eval.calibration_analysis import (
    analyze_length_bias,
    categorical_agreement,
    heldout_bias_correction,
    score_agreement,
)
from codepulse.eval.calibration_review import (
    build_review_packets,
    prepare_functional_judge_files,
    run_functional_judge,
    validate_judge_observations,
    validate_review_packets,
)
from codepulse.eval.calibration_study import main

ROOT = Path(__file__).parents[1]


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


def test_calibration_functional_packets_are_deterministic_and_blinded() -> None:
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


def test_calibration_functional_packet_ids_change_with_round() -> None:
    round_1, _ = build_review_packets(_records(), round_number=1, seed=7)
    round_2, _ = build_review_packets(_records(), round_number=2, seed=7)

    assert {packet["packet_id"] for packet in round_1}.isdisjoint(
        {packet["packet_id"] for packet in round_2}
    )


def test_calibration_functional_packet_validation_detects_identity_leakage() -> None:
    packets, _ = build_review_packets(_records(), round_number=1, seed=7)
    packets[0]["evidence"]["agent_name"] = "leaked"

    assert any("forbidden" in error for error in validate_review_packets(packets))


def test_calibration_functional_judge_observations_keep_failures_missing() -> None:
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


def test_calibration_functional_prepare_writes_no_human_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.jsonl"
    source.write_text(
        "\n".join(json.dumps(record) for record in _records()) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "study"

    manifest = prepare_functional_judge_files(source, output, seed=7)

    assert manifest["sample_size"] == 2
    assert manifest["status"] == "judge_prepared"
    assert (output / "functional-packets.jsonl").exists()
    assert (output / "functional-mapping.private.jsonl").exists()
    assert not list(output.glob("human-review*.jsonl"))
    with pytest.raises(FileExistsError):
        prepare_functional_judge_files(source, output, seed=7)


def test_calibration_functional_prepare_cli_uses_no_reviewer_ids() -> None:
    argv = [
        "calibration_study",
        "prepare-functional",
        "--input",
        "sample.jsonl",
        "--output-dir",
        "study",
    ]
    with (
        patch.object(sys, "argv", argv),
        patch(
            "codepulse.eval.calibration_study.prepare_functional_judge_files",
            return_value={"sample_size": 100},
        ) as prepare,
    ):
        main()

    prepare.assert_called_once_with(
        "sample.jsonl",
        "study",
        seed=20260713,
        force=False,
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


def test_calibration_runbook_checks_cohort_before_human_review() -> None:
    rubric = (ROOT / "docs" / "phase2-human-rubric.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "phase2-calibration-runbook.md").read_text(
        encoding="utf-8"
    )

    assert "diagnostic-process-v1" in rubric
    assert "100-record functional sample is not a human task" in rubric
    assert "profile-diagnostic" in runbook
    assert "not_ready" in runbook
    assert runbook.index("profile-diagnostic") < runbook.index("prepare-diagnostic")
