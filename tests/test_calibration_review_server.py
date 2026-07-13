"""Tests for the local Phase 2 browser review workflow."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from codepulse.eval.calibration_review import (
    build_response_template,
    build_review_packets,
    load_jsonl,
    write_jsonl,
)
from codepulse.eval.calibration_review_server import ReviewSession, _valid_token
from codepulse.eval.calibration_study import main

if TYPE_CHECKING:
    from pathlib import Path


def _study(tmp_path: Path) -> tuple[Path, Path, list[dict[str, object]]]:
    records = [
        {
            "sample_id": f"sample-{index}",
            "task_id": f"HumanEval/{index}",
            "deterministic_evidence": {
                "outcome": {
                    "exit_code": exit_code,
                    "stdout": summary,
                    "stderr": "",
                }
            },
            "artifact_status": "missing_final_code_and_full_transcript",
            "eligible_dimensions": ["functional_evidence"],
        }
        for index, exit_code, summary in (
            (1, 0, "1 passed in 0.01s"),
            (2, 1, "1 failed in 0.01s"),
        )
    ]
    packets, _ = build_review_packets(records, round_number=1, seed=7)
    responses = build_response_template(packets, "human-a")
    packet_path = tmp_path / "packets.jsonl"
    response_path = tmp_path / "responses.jsonl"
    write_jsonl(packet_path, packets)
    write_jsonl(response_path, responses)
    return packet_path, response_path, responses


def test_review_session_pristine_template_starts_at_first_packet(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)

    session = ReviewSession.from_files(packet_path, response_path)
    state = session.state()

    assert state["index"] == 0
    assert state["completed"] == 0
    assert state["complete"] is False
    assert state["packet"]["task_id"].startswith("HumanEval/")


def test_review_session_save_changes_only_human_fields(tmp_path: Path) -> None:
    packet_path, response_path, original = _study(tmp_path)
    session = ReviewSession.from_files(packet_path, response_path)
    packet_id = str(session.state()["packet"]["packet_id"])

    state = session.save(
        packet_id,
        "supported_pass",
        "The official exit status and test summary report a completed passing run.",
    )

    saved = load_jsonl(response_path)
    before = original[0]
    after = saved[0]
    for key in (
        "packet_id",
        "round",
        "reviewer_id",
        "rubric_version",
        "packet_sha256",
    ):
        assert after[key] == before[key]
    assert after["label"] == "supported_pass"
    assert after["rationale"].startswith("The official exit status")
    assert str(after["reviewed_at"]).endswith("Z")
    assert state["completed"] == 1
    assert state["index"] == 1


def test_review_session_resume_skips_completed_response(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    first = ReviewSession.from_files(packet_path, response_path)
    packet_id = str(first.state()["packet"]["packet_id"])
    first.save(packet_id, "supported_fail", "Official verification reports failure.")

    resumed = ReviewSession.from_files(packet_path, response_path)

    assert resumed.state()["index"] == 1
    assert resumed.state()["completed"] == 1


def test_review_session_save_failure_rolls_back_memory(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    session = ReviewSession.from_files(packet_path, response_path)
    packet_id = str(session.state()["packet"]["packet_id"])

    with (
        patch(
            "codepulse.eval.calibration_review_server._atomic_write_jsonl",
            side_effect=OSError("disk full"),
        ),
        pytest.raises(OSError, match="disk full"),
    ):
        session.save(packet_id, "supported_pass", "Human rationale.")

    assert session.state()["completed"] == 0
    assert load_jsonl(response_path)[0]["label"] is None


@pytest.mark.parametrize(
    ("packet_id", "label", "rationale", "match"),
    [
        ("unknown", "supported_pass", "Enough evidence.", "unknown packet"),
        (None, "not-a-label", "Enough evidence.", "invalid label"),
        (None, "supported_pass", " ", "rationale is required"),
    ],
)
def test_review_session_rejects_invalid_updates(
    tmp_path: Path,
    packet_id: str | None,
    label: str,
    rationale: str,
    match: str,
) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    session = ReviewSession.from_files(packet_path, response_path)
    target = packet_id or str(session.state()["packet"]["packet_id"])

    with pytest.raises(ValueError, match=match):
        session.save(target, label, rationale)


def test_review_session_rejects_partial_field_drift(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    rows = load_jsonl(response_path)
    rows[0]["label"] = "supported_pass"
    write_jsonl(response_path, rows)

    with pytest.raises(ValueError, match="partial response"):
        ReviewSession.from_files(packet_path, response_path)


def test_review_session_complete_round_runs_existing_validator(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    session = ReviewSession.from_files(packet_path, response_path)
    for index, label in enumerate(("supported_pass", "supported_fail")):
        packet_id = str(session.state(index)["packet"]["packet_id"])
        state = session.save(packet_id, label, f"Human rationale {index}.")

    assert state["complete"] is True
    assert state["valid"] is True
    assert state["errors"] == []
    assert json.loads(json.dumps(state))["completed"] == 2


def test_calibration_study_review_command_starts_local_server() -> None:
    argv = [
        "calibration_study",
        "review",
        "--packets",
        "packets.jsonl",
        "--responses",
        "responses.jsonl",
    ]
    with (
        patch.object(sys, "argv", argv),
        patch("codepulse.eval.calibration_study.run_review_server") as run,
    ):
        main()

    run.assert_called_once_with("packets.jsonl", "responses.jsonl")


def test_review_server_rejects_invalid_session_token() -> None:
    assert _valid_token("token=secret", "secret") is True
    assert _valid_token("token=wrong", "secret") is False
    assert _valid_token("", "secret") is False
