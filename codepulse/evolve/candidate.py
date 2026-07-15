"""Materialize trace-derived SkillOpt candidate profiles."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from codepulse.agent.adapter import AgentProfile
from codepulse.eval.artifacts import canonical_sha256, file_sha256, load_jsonl
from codepulse.evolve.prompt_edit import EditType, PromptEdit

_INFRA_FAILURES = {"provider_auth_error", "provider_error", "agent_error", "sandbox_error"}
_TRACE_EDITS = {
    "empty_patch": (
        "Before finalizing, confirm that the working tree contains a concrete, minimal code change "
        "that addresses the reported behavior."
    ),
    "no_verification": (
        "Before finalizing, run the most relevant existing tests for the changed behavior. If they "
        "fail, diagnose the concrete failure and revise only the necessary code."
    ),
    "tool_failure": (
        "Treat failed repository commands as unresolved work: diagnose the command failure, correct "
        "the implementation or invocation, and rerun the relevant check before finalizing."
    ),
    "insufficient_verification": (
        "After local checks pass, inspect nearby tests and reason through issue-specific edge cases "
        "that the first verification command may not cover before finalizing."
    ),
}


def materialize_candidate(
    baseline_profile_path: str | Path,
    training_trials_path: str | Path,
    candidate_profile_path: str | Path,
    provenance_path: str | Path,
) -> dict[str, Any]:
    """Derive one candidate prompt edit from failed baseline training trials."""
    baseline_path = Path(baseline_profile_path)
    training_path = Path(training_trials_path)
    candidate_path = Path(candidate_profile_path)
    provenance_target = Path(provenance_path)
    if candidate_path.exists() or provenance_target.exists():
        raise FileExistsError("candidate profile or provenance already exists")

    baseline = AgentProfile.from_yaml(baseline_path)
    rows = load_jsonl(training_path)
    failures = [
        row
        for row in rows
        if row.get("agent_name") == baseline.name and not bool(row.get("success"))
        and row.get("failure_type") not in _INFRA_FAILURES
    ]
    if not failures:
        raise ValueError("training trials contain no eligible failed baseline task")

    source_task_ids = sorted({str(row["task_id"]) for row in failures})
    pattern_counts = Counter(_trace_failure_pattern(row) for row in failures)
    selected_pattern = pattern_counts.most_common(1)[0][0]
    edit = PromptEdit(
        edit_id=f"skillopt-{selected_pattern}-v1",
        edit_type=EditType.APPEND,
        target_section="system_prompt",
        content=_TRACE_EDITS[selected_pattern],
        reasoning=(
            f"Observed {selected_pattern!r} in {pattern_counts[selected_pattern]} of "
            f"{len(failures)} eligible failed baseline traces."
        ),
        confidence=0.7,
    )
    candidate = _apply_system_prompt_edit(baseline, edit)
    candidate.to_yaml(candidate_path)
    edit_payload = _edit_payload(edit)
    provenance = {
        "protocol_version": "skillopt-candidate-v1",
        "baseline_profile_path": str(baseline_path),
        "baseline_profile_sha256": file_sha256(baseline_path),
        "training_trials_path": str(training_path),
        "training_trials_sha256": file_sha256(training_path),
        "source_task_ids": source_task_ids,
        "trace_analysis": {
            "eligible_failure_count": len(failures),
            "pattern_counts": dict(sorted(pattern_counts.items())),
            "selected_pattern": selected_pattern,
            "source_trial_ids": sorted(str(row["trial_id"]) for row in failures),
        },
        "edit": edit_payload,
        "edit_sha256": canonical_sha256(edit_payload),
        "candidate_profile_path": str(candidate_path),
        "candidate_profile_sha256": file_sha256(candidate_path),
    }
    provenance_target.parent.mkdir(parents=True, exist_ok=True)
    provenance_target.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return provenance


def _trace_failure_pattern(row: dict[str, Any]) -> str:
    """Classify one observable failed trial into a deterministic prompt-edit signal."""
    outcome = row.get("outcome")
    if not isinstance(outcome, dict):
        raise ValueError("failed training trials require an observable outcome")
    patch = outcome.get("patch")
    trace = outcome.get("trace")
    if not isinstance(patch, str) or not isinstance(trace, dict):
        raise ValueError("failed training trials require patch and trace evidence")
    events = trace.get("events")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValueError("failed training trial trace.events must be a list of objects")
    if not patch.strip():
        return "empty_patch"

    tool_calls = [event for event in events if event.get("event_type") == "tool_call"]
    if any(not bool(event.get("content", {}).get("success", True)) for event in tool_calls):
        return "tool_failure"
    commands = [
        str(event.get("content", {}).get("arguments", {}).get("command", "")).lower()
        for event in tool_calls
        if event.get("content", {}).get("tool") == "execute"
    ]
    verification_markers = ("pytest", " test", "tox", "nox", "unittest", "make check")
    if not any(marker in command for command in commands for marker in verification_markers):
        return "no_verification"
    return "insufficient_verification"


def _apply_system_prompt_edit(profile: AgentProfile, edit: PromptEdit) -> AgentProfile:
    if edit.target_section != "system_prompt" or edit.edit_type is not EditType.APPEND:
        raise ValueError("only APPEND edits to system_prompt are supported")
    prompt = "\n".join(part for part in (profile.system_prompt.strip(), edit.content) if part)
    payload = _edit_payload(edit)
    return replace(
        profile,
        name=f"{profile.name}-skillopt-v1",
        description=f"SkillOpt candidate derived from {profile.name}",
        system_prompt=prompt,
        version="skillopt-v1",
        metadata={
            **profile.metadata,
            "skillopt_edit_id": edit.edit_id,
            "skillopt_edit_sha256": canonical_sha256(payload),
        },
    )


def _edit_payload(edit: PromptEdit) -> dict[str, object]:
    payload = asdict(edit)
    payload["edit_type"] = edit.edit_type.value
    return payload
