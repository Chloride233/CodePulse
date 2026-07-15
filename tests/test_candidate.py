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
                {
                    "trial_id": "train-1--r0--baseline",
                    "agent_name": "baseline",
                    "task_id": "train-1",
                    "success": False,
                    "failure_type": "wrong_answer",
                    "outcome": {
                        "patch": "diff --git a/a.py b/a.py",
                        "trace": {
                            "events": [
                                {
                                    "event_type": "tool_call",
                                    "content": {
                                        "tool": "read_file",
                                        "arguments": {"path": "/workspace/a.py"},
                                        "success": True,
                                    },
                                }
                            ]
                        },
                    },
                },
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
    assert "run the most relevant existing tests" in candidate.system_prompt
    assert result["source_task_ids"] == ["train-1"]
    assert result["trace_analysis"]["selected_pattern"] == "no_verification"
    assert result["protocol_version"] == "skillopt-candidate-v1"
    assert json.loads(provenance_path.read_text(encoding="utf-8"))["candidate_profile_sha256"]


def test_candidate_refuses_training_without_failures(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.yaml"
    trials_path = tmp_path / "trials.jsonl"
    _write_baseline(baseline_path)
    trials_path.write_text(
        json.dumps({"agent_name": "baseline", "task_id": "train-1", "success": True}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no eligible failed baseline task"):
        materialize_candidate(
            baseline_path,
            trials_path,
            tmp_path / "candidate.yaml",
            tmp_path / "provenance.json",
        )


def test_candidate_second_iteration_targets_exhausted_empty_patch_trace(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline-v1.yaml"
    trials_path = tmp_path / "trials.jsonl"
    candidate_path = tmp_path / "candidate-v2.yaml"
    provenance_path = tmp_path / "provenance-v2.json"
    profile = AgentProfile(
        name="baseline-skillopt-v1",
        type="protocol",
        model="model-v1",
        agent_class="codepulse.agent.real_agent.RealAgent",
        system_prompt="Solve the task.\nMake a concrete change.",
        tools=["read_file", "write_file", "execute"],
        max_iterations=2,
        metadata={"skillopt_edit_id": "skillopt-empty_patch-v1"},
    )
    profile.to_yaml(baseline_path)
    trials_path.write_text(
        json.dumps(
            {
                "trial_id": "train-1--r0--baseline-skillopt-v1",
                "agent_name": "baseline-skillopt-v1",
                "task_id": "train-1",
                "success": False,
                "failure_type": "wrong_answer",
                "outcome": {
                    "patch": "",
                    "trace": {
                        "events": [
                            {"event_type": "llm_call"},
                            {"event_type": "llm_call"},
                        ]
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = materialize_candidate(
        baseline_path, trials_path, candidate_path, provenance_path
    )
    candidate = AgentProfile.from_yaml(candidate_path)

    assert candidate.name == "baseline-skillopt-v2"
    assert candidate.metadata["skillopt_iteration"] == 2
    assert result["protocol_version"] == "skillopt-candidate-v2"
    assert result["trace_analysis"]["selected_pattern"] == "iteration_exhaustion"
