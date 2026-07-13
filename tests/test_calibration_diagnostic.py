"""Tests for full-evidence qualitative calibration packets."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from codepulse.eval.calibration_diagnostic import (
    build_diagnostic_packets,
    build_diagnostic_response_template,
    prepare_diagnostic_review_files,
    validate_diagnostic_packets,
    validate_diagnostic_responses,
)
from codepulse.eval.calibration_diagnostic_judge import (
    compact_diagnostic_evidence,
    run_diagnostic_judge,
    validate_diagnostic_judge_observations,
)
from codepulse.eval.calibration_study import main

if TYPE_CHECKING:
    from pathlib import Path


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _trial(index: int = 0) -> dict[str, object]:
    evidence = {
        "schema_version": "calibration-evidence-v1",
        "task": {
            "task_id": f"HumanEval/{index}",
            "language": "python",
            "description": "Return the input value.",
            "input_code": "def identity(value):\n    pass",
            "expected_output": "Return value unchanged.",
            "test_cases": ["assert identity(1) == 1"],
        },
        "output_files": {
            "solution.py": "def identity(value):\n    return value\n",
            "test_solution.py": "assert identity(1) == 1",
        },
        "transcript": {
            "session_id": f"private-session-{index}",
            "agent_config": {
                "name": "private-agent",
                "model": "private-model",
            },
            "events": [
                {
                    "timestamp": 1.0,
                    "event_type": "llm_call",
                    "content": {
                        "model": "private-model",
                        "provider_model": "private-version",
                        "content": "I will implement the function.",
                    },
                    "token_usage": {"input": 100, "output": 20},
                    "duration": 0.5,
                    "span_kind": None,
                    "parent_id": None,
                    "span_id": None,
                },
                {
                    "timestamp": 2.0,
                    "event_type": "tool_result",
                    "content": {
                        "tool": "execute",
                        "success": True,
                        "output": "1 passed",
                    },
                    "token_usage": {},
                    "duration": 0.1,
                    "span_kind": None,
                    "parent_id": None,
                    "span_id": None,
                },
            ],
            "total_tokens": 120,
            "total_duration": 0.6,
            "tool_call_count": 1,
        },
        "verification": {
            "exit_code": 0,
            "stdout": "1 passed in 0.01s",
            "stderr": "",
            "pytest_total": 1,
            "pytest_passed": 1,
        },
    }
    evidence["sha256"] = _canonical_sha256(evidence)
    return {
        "trial_id": f"HumanEval/{index}--r0--private-agent",
        "task_id": f"HumanEval/{index}",
        "agent_name": "private-agent",
        "provider_model_versions": ["private-version"],
        "success": True,
        "outcome": {"evidence": evidence, "failure_type": None},
        "metrics": {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_tokens": 0,
            "total_tokens": 120,
            "duration_seconds": 0.6,
        },
    }


def _trials() -> list[dict[str, object]]:
    return [_trial(index) for index in range(10)]


def test_diagnostic_packets_are_complete_blinded_and_hashed() -> None:
    packets, mapping = build_diagnostic_packets(_trials(), round_number=1, seed=7)

    serialized = json.dumps(packets)
    assert len(packets) == 10
    assert len(mapping) == 10
    assert "private-agent" not in serialized
    assert "private-model" not in serialized
    assert "private-version" not in serialized
    assert "private-session" not in serialized
    assert packets[0]["evidence"]["final_code"].startswith("def identity")
    assert validate_diagnostic_packets(packets) == []


def test_diagnostic_packet_ids_change_between_rounds() -> None:
    round_1, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)
    round_2, _ = build_diagnostic_packets(_trials(), round_number=2, seed=7)

    assert {row["packet_id"] for row in round_1}.isdisjoint(
        {row["packet_id"] for row in round_2}
    )


def test_diagnostic_response_template_requires_reviewer() -> None:
    packets, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)

    with pytest.raises(ValueError, match="reviewer_id"):
        build_diagnostic_response_template(packets, " ")


def test_diagnostic_packets_reject_invalid_round_size_and_duplicates() -> None:
    with pytest.raises(ValueError, match="round_number"):
        build_diagnostic_packets(_trials(), round_number=0, seed=7)
    with pytest.raises(ValueError, match="at least 10"):
        build_diagnostic_packets(_trials()[:9], round_number=1, seed=7)
    trials = _trials()
    trials[1]["trial_id"] = trials[0]["trial_id"]
    with pytest.raises(ValueError, match="duplicate"):
        build_diagnostic_packets(trials, round_number=1, seed=7)


def test_diagnostic_packets_reject_incomplete_evidence() -> None:
    trials = _trials()
    broken = copy.deepcopy(trials[0])
    broken["outcome"]["evidence"]["output_files"].pop("solution.py")
    trials[0] = broken

    with pytest.raises(ValueError, match="solution.py"):
        build_diagnostic_packets(trials, round_number=1, seed=7)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("failure_type", "provider_error", "infrastructure failure"),
        ("events", [], "non-empty transcript"),
        ("pytest_total", 0, "official verification"),
        ("total_tokens", "unknown", "token metrics"),
    ],
)
def test_diagnostic_packets_reject_ineligible_trial_fields(
    field: str, value: object, match: str
) -> None:
    trials = _trials()
    broken = copy.deepcopy(trials[0])
    if field == "failure_type":
        broken["outcome"][field] = value
    elif field == "events":
        evidence = broken["outcome"]["evidence"]
        evidence["transcript"][field] = value
        evidence["sha256"] = _canonical_sha256(
            {key: child for key, child in evidence.items() if key != "sha256"}
        )
    elif field == "pytest_total":
        evidence = broken["outcome"]["evidence"]
        evidence["verification"][field] = value
        evidence["sha256"] = _canonical_sha256(
            {key: child for key, child in evidence.items() if key != "sha256"}
        )
    else:
        broken["metrics"][field] = value
    trials[0] = broken

    with pytest.raises(ValueError, match=match):
        build_diagnostic_packets(trials, round_number=1, seed=7)


def test_diagnostic_packets_reject_missing_trial_structure() -> None:
    trials = _trials()
    broken = copy.deepcopy(trials[0])
    broken["trial_id"] = ""
    broken["task_id"] = ""
    broken["agent_name"] = ""
    broken["outcome"] = "invalid"
    trials[0] = broken
    with pytest.raises(ValueError, match="requires outcome"):
        build_diagnostic_packets(trials, round_number=1, seed=7)

    trials = _trials()
    broken = copy.deepcopy(trials[0])
    broken["outcome"] = {}
    trials[0] = broken
    with pytest.raises(ValueError, match="requires full evidence"):
        build_diagnostic_packets(trials, round_number=1, seed=7)

    trials = _trials()
    broken = copy.deepcopy(trials[0])
    evidence = broken["outcome"]["evidence"]
    evidence["schema_version"] = "unknown"
    evidence["task"]["description"] = ""
    evidence["sha256"] = _canonical_sha256(
        {key: child for key, child in evidence.items() if key != "sha256"}
    )
    trials[0] = broken
    with pytest.raises(ValueError, match="unknown evidence schema"):
        build_diagnostic_packets(trials, round_number=1, seed=7)


def test_diagnostic_packet_validation_detects_drift_and_identity_leakage() -> None:
    packets, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)
    packet = packets[0]
    packet["schema_version"] = "unknown"
    packet["rubric_version"] = "unknown"
    packet["dimension"] = "functional_evidence"
    packet["evidence"]["trace"]["agent_name"] = "leaked"

    errors = validate_diagnostic_packets(packets)

    assert any("hash mismatch" in error for error in errors)
    assert any("schema version" in error for error in errors)
    assert any("rubric version" in error for error in errors)
    assert any("ineligible dimension" in error for error in errors)
    assert any("leaks identity" in error for error in errors)


def test_diagnostic_packet_validation_detects_duplicate_ids() -> None:
    packets, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)
    packets[1]["packet_id"] = packets[0]["packet_id"]

    assert any("duplicate packet IDs" in error for error in validate_diagnostic_packets(packets))


def test_diagnostic_compact_evidence_preserves_authoritative_fields() -> None:
    packets, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)
    full = packets[0]["evidence"]

    compact = compact_diagnostic_evidence(full)

    assert compact["task"] == full["task"]
    assert compact["final_code"] == full["final_code"]
    assert compact["verification"] == full["verification"]
    assert len(json.dumps(compact)) < len(json.dumps(full))
    assert [event["event_type"] for event in compact["trace"]["events"]] == [
        event["event_type"] for event in full["trace"]["events"]
    ]


def test_diagnostic_judge_runs_full_and_compact_variants() -> None:
    packets, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)
    responses = [
        json.dumps({"score": 4, "reasoning": "The observable process is direct."})
        for _ in range(20)
    ]

    with patch(
        "codepulse.eval.calibration_diagnostic_judge.call_llm_with_retry",
        side_effect=responses,
    ) as call:
        observations = run_diagnostic_judge(packets, model="judge-a")

    assert call.call_count == 20
    assert {row["variant"] for row in observations} == {
        "length_full",
        "length_compact",
    }
    assert validate_diagnostic_judge_observations(packets, observations) == []


def test_diagnostic_judge_preserves_malformed_response_as_missing() -> None:
    packets, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)
    responses = ["not json"] + [
        json.dumps({"score": 3, "reasoning": "Some observable process weakness."})
        for _ in range(19)
    ]

    with patch(
        "codepulse.eval.calibration_diagnostic_judge.call_llm_with_retry",
        side_effect=responses,
    ):
        observations = run_diagnostic_judge(packets, model="judge-a")

    assert observations[0]["status"] == "missing"
    assert observations[0]["raw_response"] == "not json"
    assert validate_diagnostic_judge_observations(packets, observations) == []


def test_diagnostic_completed_responses_validate() -> None:
    packets, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)
    responses = build_diagnostic_response_template(packets, "human-a")
    for response in responses:
        response["score"] = 4
        response["rationale"] = "The Trace is direct and verification passes."
        response["reviewed_at"] = "2026-07-13T00:00:00Z"

    assert validate_diagnostic_responses(packets, responses) == []
    responses[0]["score"] = 6
    assert any("score" in error for error in validate_diagnostic_responses(packets, responses))


def test_diagnostic_response_validation_detects_coverage_and_metadata_drift() -> None:
    packets, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)
    responses = build_diagnostic_response_template(packets, "human-a")
    response = responses[0]
    response["score"] = True
    response["reviewer_id"] = ""
    response["rationale"] = ""
    response["reviewed_at"] = ""
    response["packet_sha256"] = "0" * 64

    errors = validate_diagnostic_responses(packets, responses[:1])

    assert any("coverage" in error for error in errors)
    assert any("packet_sha256 mismatch" in error for error in errors)
    assert any("invalid score" in error for error in errors)
    assert any("requires reviewer_id" in error for error in errors)
    assert any("requires rationale" in error for error in errors)
    assert any("requires reviewed_at" in error for error in errors)


def test_diagnostic_prepare_writes_two_rounds_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "trials.jsonl"
    source.write_text(
        "\n".join(json.dumps(row) for row in _trials()) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "diagnostic-study"

    manifest = prepare_diagnostic_review_files(
        source,
        output,
        seed=7,
        reviewer_1="human-a",
        reviewer_2="human-a",
    )

    assert manifest["sample_size"] == 10
    assert manifest["reviewer_mode"] == "intra_rater"
    assert manifest["rubric_version"] == "diagnostic-process-v1"
    assert (output / "review-packets-round-1.jsonl").exists()
    assert (output / "review-packets-round-2.jsonl").exists()
    assert (output / "human-review-round-1.jsonl").exists()
    assert (output / "human-review-round-2.jsonl").exists()
    with pytest.raises(FileExistsError):
        prepare_diagnostic_review_files(
            source,
            output,
            seed=7,
            reviewer_1="human-a",
            reviewer_2="human-a",
        )
    rewritten = prepare_diagnostic_review_files(
        source,
        output,
        seed=7,
        reviewer_1="human-a",
        reviewer_2="human-a",
        force=True,
    )
    assert rewritten["artifact_hashes"] == manifest["artifact_hashes"]


def test_diagnostic_prepare_cli_routes_to_diagnostic_workflow() -> None:
    argv = [
        "calibration_study",
        "prepare-diagnostic",
        "--input",
        "trials.jsonl",
        "--output-dir",
        "study",
        "--reviewer-1",
        "human-a",
        "--reviewer-2",
        "human-a",
    ]
    with (
        patch.object(sys, "argv", argv),
        patch(
            "codepulse.eval.calibration_study.prepare_diagnostic_review_files",
            return_value={"sample_size": 10},
        ) as prepare,
    ):
        main()

    prepare.assert_called_once_with(
        "trials.jsonl",
        "study",
        seed=20260713,
        reviewer_1="human-a",
        reviewer_2="human-a",
        force=False,
    )


def test_diagnostic_judge_cli_runs_and_writes_observations(tmp_path: Path) -> None:
    packets, _ = build_diagnostic_packets(_trials(), round_number=1, seed=7)
    packet_path = tmp_path / "packets.jsonl"
    packet_path.write_text(
        "\n".join(json.dumps(packet) for packet in packets) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "judge-observations.jsonl"
    observations = [
        {
            "packet_id": packet["packet_id"],
            "packet_sha256": packet["packet_sha256"],
            "judge_model": "judge-a",
            "variant": variant,
            "prompt_version": "diagnostic-process-judge-v1",
            "evidence_chars": 100,
            "status": "ok",
            "score": 4,
            "reasoning": "The observable process is direct.",
            "raw_response": '{"score":4,"reasoning":"direct"}',
            "error": None,
        }
        for packet in packets
        for variant in ("length_full", "length_compact")
    ]
    argv = [
        "calibration_study",
        "judge-diagnostic",
        "--packets",
        str(packet_path),
        "--output",
        str(output),
        "--model",
        "judge-a",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch(
            "codepulse.eval.calibration_study.run_diagnostic_judge",
            return_value=observations,
        ) as run,
    ):
        main()

    run.assert_called_once_with(packets, model="judge-a")
    assert len(output.read_text(encoding="utf-8").splitlines()) == 20
