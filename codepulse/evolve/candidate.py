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
    "iteration_exhaustion": (
        "Make the first targeted code edit by iteration 4 and reserve later iterations for tests "
        "and correction. For an existing large file, use a targeted transformation through execute "
        "instead of replacing the file with partially read content."
    ),
    "persistent_iteration_exhaustion": (
        "Stop broad exploration once the relevant code path is identified. If no patch exists, "
        "make the smallest defensible code change by iteration 6, then use the remaining "
        "iterations to inspect git diff and run a targeted check. Do not spend iterations "
        "installing missing dependencies or retrying unavailable network access."
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
_RESOURCE_BOUNDED_POLICY = (
    "Use at most two iterations to identify the likely code path, then make one exact, "
    "minimal edit by iteration 4. Use edit_file for a unique text replacement and never "
    "overwrite a file from a partial read. Use the repository's existing environment; "
    "do not spend iterations installing unavailable dependencies or retrying network "
    "access. Use the remaining iterations for one targeted check and git diff. If a test "
    "cannot start for an environment reason, retain a defensible patch and verify it "
    "statically instead of reverting to an empty diff."
)
_RESOURCE_TOOL_NAMES = ["read_file", "edit_file", "write_file", "execute"]
_RESOURCE_FEATURES = (
    "empty_patches",
    "iteration_exhausted",
    "unsupported_edit_calls",
    "bounded_read_requests",
    "offline_package_attempts",
    "whole_file_write_calls",
)


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
    pattern_counts = Counter(
        _trace_failure_pattern(row, baseline.max_iterations) for row in failures
    )
    observed_pattern = pattern_counts.most_common(1)[0][0]
    selected_pattern = observed_pattern
    if (
        observed_pattern == "iteration_exhaustion"
        and baseline.metadata.get("skillopt_edit_id") == "skillopt-iteration_exhaustion-v1"
    ):
        selected_pattern = "persistent_iteration_exhaustion"
    iteration = _next_skillopt_iteration(baseline)
    edit = PromptEdit(
        edit_id=f"skillopt-{selected_pattern}-v1",
        edit_type=EditType.APPEND,
        target_section="system_prompt",
        content=_TRACE_EDITS[selected_pattern],
        reasoning=(
            f"Observed {observed_pattern!r} in {pattern_counts[observed_pattern]} of "
            f"{len(failures)} eligible failed baseline traces."
        ),
        confidence=0.7,
    )
    max_iterations = (
        max(baseline.max_iterations, 12)
        if selected_pattern == "persistent_iteration_exhaustion"
        else baseline.max_iterations
    )
    candidate = _apply_system_prompt_edit(
        baseline, edit, iteration, max_iterations=max_iterations
    )
    candidate.to_yaml(candidate_path)
    edit_payload = _edit_payload(edit)
    provenance = {
        "protocol_version": f"skillopt-candidate-v{iteration}",
        "baseline_profile_path": str(baseline_path),
        "baseline_profile_sha256": file_sha256(baseline_path),
        "training_trials_path": str(training_path),
        "training_trials_sha256": file_sha256(training_path),
        "source_task_ids": source_task_ids,
        "trace_analysis": {
            "eligible_failure_count": len(failures),
            "pattern_counts": dict(sorted(pattern_counts.items())),
            "observed_pattern": observed_pattern,
            "selected_pattern": selected_pattern,
            "source_trial_ids": sorted(str(row["trial_id"]) for row in failures),
        },
        "edit": edit_payload,
        "edit_sha256": canonical_sha256(edit_payload),
        "candidate_profile_path": str(candidate_path),
        "candidate_profile_sha256": file_sha256(candidate_path),
    }
    if candidate.max_iterations != baseline.max_iterations:
        provenance["profile_changes"] = {
            "max_iterations": {
                "before": baseline.max_iterations,
                "after": candidate.max_iterations,
            }
        }
    provenance_target.parent.mkdir(parents=True, exist_ok=True)
    provenance_target.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return provenance


def materialize_resource_bounded_candidate(
    baseline_profile_path: str | Path,
    training_evidence_path: str | Path,
    rejected_candidate_evidence_path: str | Path,
    candidate_profile_path: str | Path,
    provenance_path: str | Path,
) -> dict[str, Any]:
    """Derive candidate v4 without promoting the rejected v3 candidate."""
    baseline_path = Path(baseline_profile_path)
    training_evidence_target = Path(training_evidence_path)
    rejected_evidence_target = Path(rejected_candidate_evidence_path)
    candidate_path = Path(candidate_profile_path)
    provenance_target = Path(provenance_path)
    if candidate_path.exists() or provenance_target.exists():
        raise FileExistsError("candidate profile or provenance already exists")

    baseline = AgentProfile.from_yaml(baseline_path)
    if baseline.max_iterations != 8 or baseline.metadata.get("skillopt_iteration") != 2:
        raise ValueError("resource-bounded candidate requires the eight-iteration v2 baseline")
    tool_contract_version = baseline.metadata.get("tool_contract_version")
    if baseline.tools != _RESOURCE_TOOL_NAMES or tool_contract_version != "repository-tools-v2":
        raise ValueError("baseline must freeze repository-tools-v2")

    training_evidence = _load_json_object(
        training_evidence_target, "training evidence"
    )
    if training_evidence.get("protocol_version") != (
        "phase3-swebench-training-evidence-v4"
    ):
        raise ValueError("training evidence has the wrong protocol_version")
    training_trials_path = training_evidence.get("training_trials_path")
    training_trials_digest = training_evidence.get("training_trials_sha256")
    if not isinstance(training_trials_path, str) or not isinstance(
        training_trials_digest, str
    ):
        raise ValueError("training evidence must bind its compact trials")
    training_path = Path(training_trials_path)
    if not training_path.is_file() or file_sha256(training_path) != training_trials_digest:
        raise ValueError("training trials are missing or hash-mismatched")
    rows = load_jsonl(training_path)
    if training_evidence.get("selected_trials") != len(rows) or not rows:
        raise ValueError("training evidence selected_trials does not match compact trials")
    if any(
        bool(row.get("success")) or row.get("failure_type") != "wrong_answer"
        for row in rows
    ):
        raise ValueError("compact training trials must contain functional failures only")

    feature_counts = {
        "empty_patches": sum(bool(row.get("patch_empty")) for row in rows),
        "iteration_exhausted": sum(
            bool(row.get("iteration_exhausted")) for row in rows
        ),
        "unsupported_edit_calls": sum(
            int(row.get("unsupported_edit_calls", 0)) for row in rows
        ),
        "bounded_read_requests": sum(
            int(row.get("bounded_read_requests", 0)) for row in rows
        ),
        "offline_package_attempts": sum(
            int(row.get("offline_package_attempts", 0)) for row in rows
        ),
        "whole_file_write_calls": sum(
            int(row.get("whole_file_write_calls", 0)) for row in rows
        ),
    }
    expected_counts = training_evidence.get("feature_counts")
    if not isinstance(expected_counts, dict) or any(
        expected_counts.get(name) != feature_counts[name] for name in _RESOURCE_FEATURES
    ):
        raise ValueError("training evidence feature_counts do not match compact trials")

    rejected_evidence = _load_json_object(
        rejected_evidence_target, "rejected candidate evidence"
    )
    gate = rejected_evidence.get("validation_gate")
    if (
        not isinstance(gate, dict)
        or gate.get("accepted") is not False
        or rejected_evidence.get("phase3_complete") is not False
    ):
        raise ValueError("prior candidate evidence must be rejected")

    prompt = baseline.system_prompt
    for old_suffix in (
        _TRACE_EDITS["empty_patch"],
        _TRACE_EDITS["iteration_exhaustion"],
    ):
        if old_suffix not in prompt:
            raise ValueError("v2 baseline prompt is missing its frozen SkillOpt suffix")
        prompt = prompt.replace(old_suffix, "")
    replacement_prompt = "\n".join(
        part for part in (prompt.strip(), _RESOURCE_BOUNDED_POLICY) if part
    )
    edit = PromptEdit(
        edit_id="skillopt-resource_bounded_execution-v1",
        edit_type=EditType.REPLACE,
        target_section="system_prompt",
        content=replacement_prompt,
        reasoning=(
            f"Observed {feature_counts['empty_patches']} empty patches and "
            f"{feature_counts['iteration_exhausted']} iteration-exhausted traces across "
            f"{len(rows)} eligible v2 failures after v3 failed the stable-improvement gate."
        ),
        confidence=0.7,
    )
    edit_payload = _edit_payload(edit)
    base_name = baseline.name.split("-skillopt-v", 1)[0]
    candidate = replace(
        baseline,
        name=f"{base_name}-skillopt-v4",
        description=f"Resource-bounded SkillOpt candidate derived from {baseline.name}",
        system_prompt=replacement_prompt,
        max_iterations=8,
        version="skillopt-v4",
        metadata={
            **baseline.metadata,
            "skillopt_iteration": 4,
            "skillopt_edit_id": edit.edit_id,
            "skillopt_edit_sha256": canonical_sha256(edit_payload),
            "tool_contract_version": tool_contract_version,
        },
    )
    candidate.to_yaml(candidate_path)
    provenance = {
        "protocol_version": "skillopt-candidate-v4",
        "baseline_profile_path": str(baseline_path),
        "baseline_profile_sha256": file_sha256(baseline_path),
        "training_evidence_path": str(training_evidence_target),
        "training_evidence_sha256": file_sha256(training_evidence_target),
        "training_trials_path": str(training_path),
        "training_trials_sha256": training_trials_digest,
        "rejected_candidate_evidence_path": str(rejected_evidence_target),
        "rejected_candidate_evidence_sha256": file_sha256(rejected_evidence_target),
        "source_task_ids": sorted({str(row["task_id"]) for row in rows}),
        "trace_analysis": {
            "eligible_failure_count": len(rows),
            "feature_counts": feature_counts,
            "selected_pattern": "resource_bounded_execution",
            "source_trial_ids": sorted(str(row["trial_id"]) for row in rows),
        },
        "edit": edit_payload,
        "edit_sha256": canonical_sha256(edit_payload),
        "tool_contract_version": tool_contract_version,
        "candidate_profile_path": str(candidate_path),
        "candidate_profile_sha256": file_sha256(candidate_path),
        "profile_changes": {
            "max_iterations": {"before": 8, "after": 8},
            "system_prompt": {"operation": "replace"},
        },
    }
    provenance_target.parent.mkdir(parents=True, exist_ok=True)
    provenance_target.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return provenance


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} cannot be loaded: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _trace_failure_pattern(row: dict[str, Any], max_iterations: int | None = None) -> str:
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
        llm_calls = sum(event.get("event_type") == "llm_call" for event in events)
        if max_iterations is not None and llm_calls >= max_iterations:
            return "iteration_exhaustion"
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


def _next_skillopt_iteration(profile: AgentProfile) -> int:
    current = profile.metadata.get("skillopt_iteration")
    if isinstance(current, int) and current >= 1:
        return current + 1
    return 2 if "skillopt_edit_id" in profile.metadata else 1


def _apply_system_prompt_edit(
    profile: AgentProfile,
    edit: PromptEdit,
    iteration: int,
    *,
    max_iterations: int,
) -> AgentProfile:
    if edit.target_section != "system_prompt" or edit.edit_type is not EditType.APPEND:
        raise ValueError("only APPEND edits to system_prompt are supported")
    prompt = "\n".join(part for part in (profile.system_prompt.strip(), edit.content) if part)
    payload = _edit_payload(edit)
    base_name = profile.name.rsplit("-skillopt-v", 1)[0]
    return replace(
        profile,
        name=f"{base_name}-skillopt-v{iteration}",
        description=f"SkillOpt candidate derived from {profile.name}",
        system_prompt=prompt,
        max_iterations=max_iterations,
        version=f"skillopt-v{iteration}",
        metadata={
            **profile.metadata,
            "skillopt_iteration": iteration,
            "skillopt_edit_id": edit.edit_id,
            "skillopt_edit_sha256": canonical_sha256(payload),
        },
    )


def _edit_payload(edit: PromptEdit) -> dict[str, object]:
    payload = asdict(edit)
    payload["edit_type"] = edit.edit_type.value
    return payload
