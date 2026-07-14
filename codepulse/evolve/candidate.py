"""Materialize trace-derived SkillOpt candidate profiles."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from codepulse.agent.adapter import AgentProfile
from codepulse.eval.artifacts import canonical_sha256, file_sha256, load_jsonl
from codepulse.evolve.prompt_edit import EditType, PromptEdit

_FAILURE_EDIT = (
    "Before finalizing, run the supplied tests. If they fail, diagnose the concrete "
    "failure and revise only the solution needed to make those tests pass."
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
    ]
    if not failures:
        raise ValueError("training trials contain no failed baseline task")

    source_task_ids = sorted({str(row["task_id"]) for row in failures})
    edit = PromptEdit(
        edit_id="skillopt-training-failure-v1",
        edit_type=EditType.APPEND,
        target_section="system_prompt",
        content=_FAILURE_EDIT,
        reasoning=(
            f"Observed {len(failures)} failed baseline trials across "
            f"{len(source_task_ids)} training tasks."
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
