"""Tests for trace-derived SkillOpt candidate materialization."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from codepulse.agent.adapter import AgentProfile
from codepulse.evolve.candidate import materialize_candidate

if TYPE_CHECKING:
    from pathlib import Path


def _write_baseline(path: Path) -> None:
    AgentProfile(
        name="baseline",
        type="protocol",
        model="model-v1",
        agent_class="codepulse.agent.real_agent.RealAgent",
        system_prompt="Solve the task.",
        tools=["read_file", "write_file", "execute"],
        max_iterations=2,
        temperature=0.0,
        max_tokens=4096,
    ).to_yaml(path)


def test_candidate_materializes_trace_derived_prompt_and_provenance(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.yaml"
    trials_path = tmp_path / "trials.jsonl"
    candidate_path = tmp_path / "candidate.yaml"
    provenance_path = tmp_path / "provenance.json"
    _write_baseline(baseline_path)
    trials_path.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"agent_name": "baseline", "task_id": "train-1", "success": False},
                {"agent_name": "baseline", "task_id": "train-2", "success": True},
            )
        )
        + "\n",
        encoding="utf-8",
    )

    result = materialize_candidate(
        baseline_path, trials_path, candidate_path, provenance_path
    )
    candidate = AgentProfile.from_yaml(candidate_path)

    assert candidate.name == "baseline-skillopt-v1"
    assert candidate.max_iterations == 2
    assert candidate.temperature == 0.0
    assert "Before finalizing, run the supplied tests." in candidate.system_prompt
    assert result["source_task_ids"] == ["train-1"]
    assert json.loads(provenance_path.read_text(encoding="utf-8"))["candidate_profile_sha256"]


def test_candidate_refuses_training_without_failures(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.yaml"
    trials_path = tmp_path / "trials.jsonl"
    _write_baseline(baseline_path)
    trials_path.write_text(
        json.dumps({"agent_name": "baseline", "task_id": "train-1", "success": True}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no failed baseline task"):
        materialize_candidate(
            baseline_path,
            trials_path,
            tmp_path / "candidate.yaml",
            tmp_path / "provenance.json",
        )
