"""Tests for the local qualitative diagnostic review browser."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from codepulse.eval.calibration_diagnostic import (
    DIAGNOSTIC_PACKET_VERSION,
    DIAGNOSTIC_RUBRIC_VERSION,
    build_diagnostic_response_template,
)
from codepulse.eval.calibration_diagnostic_review_server import (
    _REVIEW_PAGE,
    DiagnosticReviewSession,
    _valid_token,
    _validate_partial_responses,
    create_diagnostic_review_server,
    run_diagnostic_review_server,
)
from codepulse.eval.calibration_review import load_jsonl, write_jsonl
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


def _packet(index: int) -> dict[str, object]:
    packet: dict[str, object] = {
        "schema_version": DIAGNOSTIC_PACKET_VERSION,
        "packet_id": f"diag-packet-{index}",
        "round": 1,
        "rubric_version": DIAGNOSTIC_RUBRIC_VERSION,
        "dimension": "process_quality",
        "evidence": {
            "task": {
                "description": "Return the input value.",
                "input_code": "def identity(value):\n    pass",
                "expected_output": "Return value unchanged.",
                "test_cases": ["assert identity(1) == 1"],
            },
            "final_code": "def identity(value):\n    return value\n",
            "trace": {
                "events": [
                    {
                        "event_type": "tool_result",
                        "content": {"tool": "execute", "success": True, "output": "1 passed"},
                    }
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
            "metrics": {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "duration_seconds": 0.6,
            },
        },
    }
    packet["packet_sha256"] = _canonical_sha256(packet)
    return packet


def _study(tmp_path: Path) -> tuple[Path, Path, list[dict[str, object]]]:
    packets = [_packet(1), _packet(2)]
    responses = build_diagnostic_response_template(packets, "human-a")
    packet_path = tmp_path / "packets.jsonl"
    response_path = tmp_path / "responses.jsonl"
    write_jsonl(packet_path, packets)
    write_jsonl(response_path, responses)
    return packet_path, response_path, responses


def test_diagnostic_review_session_pristine_starts_at_first_packet(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)

    session = DiagnosticReviewSession.from_files(packet_path, response_path)
    state = session.state()

    assert state["index"] == 0
    assert state["completed"] == 0
    assert state["complete"] is False
    assert state["packet"]["evidence"]["final_code"].startswith("def identity")
    assert "agent_name" not in json.dumps(state)


def test_diagnostic_review_save_changes_only_human_fields(tmp_path: Path) -> None:
    packet_path, response_path, original = _study(tmp_path)
    session = DiagnosticReviewSession.from_files(packet_path, response_path)
    packet_id = str(session.state()["packet"]["packet_id"])

    state = session.save(packet_id, 4, "The observable tool use is direct and verified.")

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
    assert after["score"] == 4
    assert after["rationale"].startswith("The observable tool use")
    assert str(after["reviewed_at"]).endswith("Z")
    assert state["completed"] == 1
    assert state["index"] == 1


def test_diagnostic_review_resume_skips_completed_response(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    first = DiagnosticReviewSession.from_files(packet_path, response_path)
    packet_id = str(first.state()["packet"]["packet_id"])
    first.save(packet_id, 3, "The result passes but the process has a material gap.")

    resumed = DiagnosticReviewSession.from_files(packet_path, response_path)

    assert resumed.state()["index"] == 1
    assert resumed.state()["completed"] == 1

    with pytest.raises(ValueError, match="out of range"):
        resumed.state(20)


def test_diagnostic_review_save_failure_rolls_back_memory(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    session = DiagnosticReviewSession.from_files(packet_path, response_path)
    packet_id = str(session.state()["packet"]["packet_id"])

    with (
        patch(
            "codepulse.eval.calibration_diagnostic_review_server._atomic_write_jsonl",
            side_effect=OSError("disk full"),
        ),
        pytest.raises(OSError, match="disk full"),
    ):
        session.save(packet_id, 5, "Direct and fully supported process.")

    assert session.state()["completed"] == 0
    assert load_jsonl(response_path)[0]["score"] is None


@pytest.mark.parametrize(
    ("packet_id", "score", "rationale", "match"),
    [
        ("unknown", 4, "Enough evidence.", "unknown packet"),
        (None, 0, "Enough evidence.", "invalid score"),
        (None, 6, "Enough evidence.", "invalid score"),
        (None, True, "Enough evidence.", "invalid score"),
        (None, 4, " ", "rationale is required"),
    ],
)
def test_diagnostic_review_rejects_invalid_updates(
    tmp_path: Path,
    packet_id: str | None,
    score: object,
    rationale: str,
    match: str,
) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    session = DiagnosticReviewSession.from_files(packet_path, response_path)
    target = packet_id or str(session.state()["packet"]["packet_id"])

    with pytest.raises(ValueError, match=match):
        session.save(target, score, rationale)


def test_diagnostic_review_rejects_partial_field_drift(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    rows = load_jsonl(response_path)
    rows[0]["score"] = 4
    write_jsonl(response_path, rows)

    with pytest.raises(ValueError, match="partial response"):
        DiagnosticReviewSession.from_files(packet_path, response_path)


def test_diagnostic_review_partial_validation_reports_metadata_and_fields() -> None:
    packets = [_packet(1), _packet(2)]
    responses = build_diagnostic_response_template(packets, "human-a")
    responses[0].update(
        packet_sha256="drifted",
        reviewer_id="",
        score=6,
        rationale="",
        reviewed_at="",
    )

    errors = _validate_partial_responses(packets, responses)

    assert any("packet_sha256 mismatch" in error for error in errors)
    assert any("requires reviewer_id" in error for error in errors)
    assert any("invalid score" in error for error in errors)
    assert any("requires rationale" in error for error in errors)
    assert any("requires reviewed_at" in error for error in errors)
    assert any(
        "coverage" in error
        for error in _validate_partial_responses(packets, responses[:1])
    )


def test_diagnostic_review_complete_round_runs_existing_validator(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    session = DiagnosticReviewSession.from_files(packet_path, response_path)
    for index, score in enumerate((4, 5)):
        packet_id = str(session.state(index)["packet"]["packet_id"])
        state = session.save(packet_id, score, f"Observable rationale {index}.")

    assert state["complete"] is True
    assert state["valid"] is True
    assert state["errors"] == []


def test_diagnostic_review_command_starts_local_server() -> None:
    argv = [
        "calibration_study",
        "review-diagnostic",
        "--packets",
        "packets.jsonl",
        "--responses",
        "responses.jsonl",
    ]
    with (
        patch.object(sys, "argv", argv),
        patch(
            "codepulse.eval.calibration_study.run_diagnostic_review_server"
        ) as run,
    ):
        main()

    run.assert_called_once_with("packets.jsonl", "responses.jsonl")


def test_diagnostic_review_server_creation_uses_loopback_and_token(tmp_path: Path) -> None:
    packet_path, response_path, _ = _study(tmp_path)
    server = MagicMock()
    server.server_address = ("127.0.0.1", 4321)

    with (
        patch(
            "codepulse.eval.calibration_diagnostic_review_server.ThreadingHTTPServer",
            return_value=server,
        ) as create,
        patch(
            "codepulse.eval.calibration_diagnostic_review_server.secrets.token_urlsafe",
            return_value="secret-token",
        ),
    ):
        created, url = create_diagnostic_review_server(packet_path, response_path)

    assert created is server
    assert url == "http://127.0.0.1:4321/?token=secret-token"
    assert create.call_args.args[0] == ("127.0.0.1", 0)


def test_diagnostic_review_server_opens_and_closes_cleanly() -> None:
    server = MagicMock()
    server.serve_forever.side_effect = KeyboardInterrupt
    with (
        patch(
            "codepulse.eval.calibration_diagnostic_review_server.create_diagnostic_review_server",
            return_value=(server, "http://127.0.0.1:4321/?token=secret"),
        ),
        patch(
            "codepulse.eval.calibration_diagnostic_review_server.webbrowser.open"
        ) as open_browser,
    ):
        run_diagnostic_review_server("packets.jsonl", "responses.jsonl")

    open_browser.assert_called_once()
    server.server_close.assert_called_once()


def test_diagnostic_review_page_has_full_evidence_and_five_scores() -> None:
    assert 'id="taskDescription"' in _REVIEW_PAGE
    assert 'id="finalCode"' in _REVIEW_PAGE
    assert 'id="traceEvents"' in _REVIEW_PAGE
    assert 'id="verification"' in _REVIEW_PAGE
    assert _REVIEW_PAGE.count('class="score-option"') == 5


def test_diagnostic_review_server_rejects_invalid_session_token() -> None:
    assert _valid_token("token=secret", "secret") is True
    assert _valid_token("token=wrong", "secret") is False
    assert _valid_token("", "secret") is False
