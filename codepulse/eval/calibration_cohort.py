"""Deterministic cohort eligibility for Phase 2 qualitative calibration."""

from __future__ import annotations

import random
from collections import Counter
from typing import Any

from codepulse.eval.artifacts import canonical_sha256

COHORT_PROTOCOL_VERSION = "phase2-cohort-v1"
COHORT_SIZE = 10
ELIGIBLE_STRATA = (
    "recovered_success",
    "unresolved_failure",
    "multi_attempt_success",
    "direct_success",
)
_SUCCESS_STRATA = {
    "recovered_success",
    "multi_attempt_success",
    "direct_success",
}
_PROCESS_FIELDS = (
    "execution_attempts",
    "code_writes",
    "failed_tool_results",
    "llm_calls",
)


class CohortNotReadyError(ValueError):
    """Raised when a diagnostic candidate pool fails the frozen cohort policy."""

    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile
        messages = "; ".join(str(reason["message"]) for reason in profile["reasons"])
        super().__init__(f"diagnostic cohort is not ready: {messages}")


def profile_diagnostic_cohort(
    trials: list[dict[str, Any]], *, seed: int
) -> dict[str, Any]:
    """Classify, select, and validate a diagnostic candidate pool."""
    records = [_profile_trial(trial, index) for index, trial in enumerate(trials)]
    selected = _round_robin_selection(records, seed=seed)
    stratum_counts = Counter(str(record["status"]) for record in selected)
    eligible_count = sum(record["status"] in ELIGIBLE_STRATA for record in records)
    duplicate_ids = sorted(
        trial_id
        for trial_id, count in Counter(
            str(record["trial_id"]) for record in records
        ).items()
        if trial_id and count > 1
    )
    reasons = _gate_reasons(
        selected,
        eligible_count=eligible_count,
        duplicate_ids=duplicate_ids,
    )
    pool_counts = Counter(
        str(record["status"])
        for record in records
        if record["status"] in ELIGIBLE_STRATA
    )
    return {
        "protocol_version": COHORT_PROTOCOL_VERSION,
        "status": "ready" if not reasons else "not_ready",
        "seed": seed,
        "candidate_count": len(trials),
        "eligible_count": eligible_count,
        "excluded_count": len(trials) - eligible_count,
        "selected_count": len(selected),
        "pool_stratum_counts": dict(sorted(pool_counts.items())),
        "stratum_counts": dict(sorted(stratum_counts.items())),
        "excluded_counts": {
            "incomplete_evidence": sum(
                record["status"] == "incomplete_evidence" for record in records
            ),
            "infrastructure_failure": sum(
                record["status"] == "infrastructure_failure" for record in records
            ),
        },
        "selected_trial_ids": [str(record["trial_id"]) for record in selected],
        "selected_evidence_sha256": [
            str(record["evidence_sha256"]) for record in selected
        ],
        "reasons": reasons,
        "records": records,
    }


def select_diagnostic_cohort(
    trials: list[dict[str, Any]], *, seed: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the frozen 10-trial cohort or raise with its failed profile."""
    profile = profile_diagnostic_cohort(trials, seed=seed)
    if profile["status"] != "ready":
        raise CohortNotReadyError(profile)
    trial_by_id = {str(trial["trial_id"]): trial for trial in trials}
    selected = [trial_by_id[trial_id] for trial_id in profile["selected_trial_ids"]]
    return selected, profile


def validate_diagnostic_trial(trial: dict[str, Any], index: int) -> list[str]:
    """Return structural errors for one full-evidence diagnostic trial."""
    trial_id = str(trial.get("trial_id", f"index-{index}"))
    errors: list[str] = []
    if not _nonempty_string(trial.get("trial_id")):
        errors.append(f"trial {trial_id} requires trial_id")
    if not _nonempty_string(trial.get("task_id")):
        errors.append(f"trial {trial_id} requires task_id")
    if not _nonempty_string(trial.get("agent_name")):
        errors.append(f"trial {trial_id} requires agent_name")
    if not isinstance(trial.get("success"), bool):
        errors.append(f"trial {trial_id} requires boolean success")

    outcome = trial.get("outcome")
    if not isinstance(outcome, dict):
        errors.append(f"trial {trial_id} requires outcome")
        return errors
    failure_type = outcome.get("failure_type") or trial.get("failure_type")
    if failure_type:
        errors.append(f"trial {trial_id} has infrastructure failure: {failure_type}")
    evidence = outcome.get("evidence")
    if not isinstance(evidence, dict):
        errors.append(f"trial {trial_id} requires full evidence")
        return errors

    supplied_hash = evidence.get("sha256")
    unhashed = {key: value for key, value in evidence.items() if key != "sha256"}
    if supplied_hash != canonical_sha256(unhashed):
        errors.append(f"trial {trial_id} evidence hash mismatch")
    if evidence.get("schema_version") != "calibration-evidence-v1":
        errors.append(f"trial {trial_id} has unknown evidence schema")

    task = evidence.get("task")
    if not isinstance(task, dict) or not _nonempty_string(task.get("description")):
        errors.append(f"trial {trial_id} requires task description")
    output_files = evidence.get("output_files")
    if not isinstance(output_files, dict) or not _nonempty_string(
        output_files.get("solution.py")
    ):
        errors.append(f"trial {trial_id} requires final solution.py")
    transcript = evidence.get("transcript")
    if not isinstance(transcript, dict) or not isinstance(
        transcript.get("events"), list
    ) or not transcript.get("events"):
        errors.append(f"trial {trial_id} requires a non-empty transcript")
    verification = evidence.get("verification")
    if not isinstance(verification, dict) or not _valid_verification(verification):
        errors.append(f"trial {trial_id} requires complete official verification")
    elif trial.get("success") is not _verification_passed(verification):
        errors.append(f"trial {trial_id} success contradicts official verification")
    metrics = trial.get("metrics")
    if not isinstance(metrics, dict) or not isinstance(
        metrics.get("total_tokens"), int
    ):
        errors.append(f"trial {trial_id} requires token metrics")
    return errors


def _profile_trial(trial: dict[str, Any], index: int) -> dict[str, Any]:
    trial_id = str(trial.get("trial_id", f"index-{index}"))
    failure_type = _failure_type(trial)
    if failure_type:
        return _profile_record(
            trial_id,
            "infrastructure_failure",
            errors=[f"infrastructure failure: {failure_type}"],
        )

    errors = validate_diagnostic_trial(trial, index)
    if errors:
        return _profile_record(trial_id, "incomplete_evidence", errors=errors)

    outcome = trial["outcome"]
    evidence = outcome["evidence"]
    transcript = evidence["transcript"]
    events = transcript["events"]
    execution_attempts = _tool_call_count(events, "execute")
    code_writes = _tool_call_count(events, "write_file")
    failed_tool_results = sum(
        _failed_tool_result(event) for event in events
    )
    failed_execution = any(
        _failed_execution_call(event) for event in events
    )
    llm_calls = sum(event.get("event_type") == "llm_call" for event in events)

    if not _verification_passed(evidence["verification"]):
        status = "unresolved_failure"
    elif failed_tool_results or failed_execution:
        status = "recovered_success"
    elif execution_attempts > 1 or code_writes > 1:
        status = "multi_attempt_success"
    else:
        status = "direct_success"
    return _profile_record(
        trial_id,
        status,
        evidence_sha256=str(evidence["sha256"]),
        execution_attempts=execution_attempts,
        code_writes=code_writes,
        failed_tool_results=failed_tool_results,
        llm_calls=llm_calls,
    )


def _profile_record(
    trial_id: str,
    status: str,
    *,
    evidence_sha256: str = "",
    execution_attempts: int = 0,
    code_writes: int = 0,
    failed_tool_results: int = 0,
    llm_calls: int = 0,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "trial_id": trial_id,
        "status": status,
        "evidence_sha256": evidence_sha256,
        "execution_attempts": execution_attempts,
        "code_writes": code_writes,
        "failed_tool_results": failed_tool_results,
        "llm_calls": llm_calls,
        "errors": errors or [],
    }


def _round_robin_selection(
    records: list[dict[str, Any]], *, seed: int
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {
        stratum: sorted(
            (record for record in records if record["status"] == stratum),
            key=lambda record: str(record["trial_id"]),
        )
        for stratum in ELIGIBLE_STRATA
    }
    generator = random.Random(seed)
    for group in groups.values():
        generator.shuffle(group)

    selected: list[dict[str, Any]] = []
    while len(selected) < COHORT_SIZE and any(groups.values()):
        for stratum in ELIGIBLE_STRATA:
            if groups[stratum] and len(selected) < COHORT_SIZE:
                selected.append(groups[stratum].pop())
    return selected


def _gate_reasons(
    selected: list[dict[str, Any]],
    *,
    eligible_count: int,
    duplicate_ids: list[str],
) -> list[dict[str, str]]:
    counts = Counter(str(record["status"]) for record in selected)
    reasons: list[dict[str, str]] = []
    if duplicate_ids:
        reasons.append({
            "code": "duplicate_trial_ids",
            "message": "duplicate trial IDs: " + ", ".join(duplicate_ids),
        })
    if eligible_count < COHORT_SIZE:
        reasons.append({
            "code": "insufficient_eligible_trials",
            "message": f"need {COHORT_SIZE} eligible trials; found {eligible_count}",
        })
    if len(counts) < 3:
        reasons.append({
            "code": "insufficient_strata",
            "message": f"need at least 3 process strata; found {len(counts)}",
        })
    dominant = max(counts.values(), default=0)
    if selected and dominant / len(selected) > 0.5:
        reasons.append({
            "code": "dominant_stratum",
            "message": "one process stratum exceeds 50% of the selected cohort",
        })
    if not any(status in counts for status in _SUCCESS_STRATA):
        reasons.append({
            "code": "missing_success",
            "message": "selected cohort requires at least one final success",
        })
    if "unresolved_failure" not in counts:
        reasons.append({
            "code": "missing_failure",
            "message": "selected cohort requires at least one final failure",
        })
    if not _has_process_variation(selected):
        reasons.append({
            "code": "constant_process_counts",
            "message": "selected cohort process counts are constant",
        })
    return reasons


def _has_process_variation(records: list[dict[str, Any]]) -> bool:
    return any(
        len({record[field] for record in records}) > 1 for field in _PROCESS_FIELDS
    )


def _failure_type(trial: dict[str, Any]) -> str:
    outcome = trial.get("outcome")
    outcome_failure = outcome.get("failure_type") if isinstance(outcome, dict) else None
    value = outcome_failure or trial.get("failure_type")
    return str(value).strip() if value else ""


def _tool_call_count(events: list[dict[str, Any]], tool: str) -> int:
    return sum(
        event.get("event_type") == "tool_call"
        and isinstance(event.get("content"), dict)
        and event["content"].get("tool") == tool
        for event in events
    )


def _failed_tool_result(event: dict[str, Any]) -> bool:
    content = event.get("content")
    return (
        event.get("event_type") == "tool_result"
        and isinstance(content, dict)
        and content.get("success") is False
    )


def _failed_execution_call(event: dict[str, Any]) -> bool:
    content = event.get("content")
    return (
        event.get("event_type") == "tool_call"
        and isinstance(content, dict)
        and content.get("tool") == "execute"
        and content.get("success") is False
    )


def _valid_verification(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    exit_code = value.get("exit_code")
    total = value.get("pytest_total")
    passed = value.get("pytest_passed")
    return (
        isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and isinstance(total, int)
        and not isinstance(total, bool)
        and total > 0
        and isinstance(passed, int)
        and not isinstance(passed, bool)
        and 0 <= passed <= total
        and isinstance(value.get("stdout"), str)
        and isinstance(value.get("stderr"), str)
    )


def _verification_passed(verification: dict[str, Any]) -> bool:
    return bool(
        verification["exit_code"] == 0
        and verification["pytest_passed"] == verification["pytest_total"]
    )


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
