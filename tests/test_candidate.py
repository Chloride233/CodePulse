"""Tests for trace-derived SkillOpt candidate materialization."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from codepulse.agent.adapter import AgentProfile
from codepulse.eval.artifacts import file_sha256
from codepulse.evolve.candidate import (
    materialize_candidate,
    materialize_resource_bounded_candidate,
)

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


def test_candidate_third_iteration_escalates_persistent_exhaustion(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline-v2.yaml"
    trials_path = tmp_path / "trials.jsonl"
    candidate_path = tmp_path / "candidate-v3.yaml"
    provenance_path = tmp_path / "provenance-v3.json"
    profile = AgentProfile(
        name="baseline-skillopt-v2",
        type="protocol",
        model="model-v1",
        agent_class="codepulse.agent.real_agent.RealAgent",
        system_prompt="Solve the task.\nMake a targeted edit by iteration 4.",
        tools=["read_file", "write_file", "execute"],
        max_iterations=8,
        metadata={
            "skillopt_iteration": 2,
            "skillopt_edit_id": "skillopt-iteration_exhaustion-v1",
        },
    )
    profile.to_yaml(baseline_path)
    trials_path.write_text(
        json.dumps(
            {
                "trial_id": "train-1--r0--baseline-skillopt-v2",
                "agent_name": "baseline-skillopt-v2",
                "task_id": "train-1",
                "success": False,
                "failure_type": "wrong_answer",
                "outcome": {
                    "patch": "",
                    "trace": {
                        "events": [{"event_type": "llm_call"} for _ in range(8)]
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

    assert candidate.name == "baseline-skillopt-v3"
    assert candidate.max_iterations == 12
    assert candidate.metadata["skillopt_iteration"] == 3
    assert candidate.metadata["skillopt_edit_id"] == (
        "skillopt-persistent_iteration_exhaustion-v1"
    )
    assert "smallest defensible code change by iteration 6" in candidate.system_prompt
    assert result["protocol_version"] == "skillopt-candidate-v3"
    assert result["trace_analysis"]["observed_pattern"] == "iteration_exhaustion"
    assert result["trace_analysis"]["selected_pattern"] == (
        "persistent_iteration_exhaustion"
    )
    assert result["profile_changes"] == {
        "max_iterations": {"before": 8, "after": 12}
    }


def _write_resource_bounded_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    baseline_path = tmp_path / "baseline-v2-tools-v2.yaml"
    training_path = tmp_path / "training.jsonl"
    training_evidence_path = tmp_path / "training-evidence.json"
    rejected_evidence_path = tmp_path / "rejected-evidence.json"
    profile = AgentProfile(
        name="repository-agent-skillopt-v2-tools-v2",
        type="protocol",
        model="model-v1",
        agent_class="codepulse.agent.real_agent.RealAgent",
        system_prompt=(
            "Solve the task.\n"
            "Before finalizing, confirm that the working tree contains a concrete, "
            "minimal code change that addresses the reported behavior.\n"
            "Make the first targeted code edit by iteration 4 and reserve later "
            "iterations for tests and correction. For an existing large file, use a "
            "targeted transformation through execute instead of replacing the file "
            "with partially read content."
        ),
        tools=["read_file", "edit_file", "write_file", "execute"],
        max_iterations=8,
        metadata={
            "skillopt_iteration": 2,
            "skillopt_edit_id": "skillopt-iteration_exhaustion-v1",
            "tool_contract_version": "repository-tools-v2",
        },
    )
    profile.to_yaml(baseline_path)
    training_path.write_text(
        json.dumps(
            {
                "trial_id": "task-1--r0--source-v2",
                "agent_name": "source-v2",
                "task_id": "task-1",
                "success": False,
                "failure_type": "wrong_answer",
                "patch_empty": True,
                "llm_calls": 8,
                "iteration_exhausted": True,
                "unsupported_edit_calls": 1,
                "bounded_read_requests": 2,
                "offline_package_attempts": 0,
                "whole_file_write_calls": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    training_evidence_path.write_text(
        json.dumps(
            {
                "protocol_version": "phase3-swebench-training-evidence-v4",
                "training_trials_path": str(training_path),
                "training_trials_sha256": file_sha256(training_path),
                "selected_trials": 1,
                "feature_counts": {
                    "empty_patches": 1,
                    "iteration_exhausted": 1,
                    "unsupported_edit_calls": 1,
                    "bounded_read_requests": 2,
                    "offline_package_attempts": 0,
                    "whole_file_write_calls": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    rejected_evidence_path.write_text(
        json.dumps(
            {
                "protocol_version": "phase3-swebench-evolution-evidence-v4",
                "validation_gate": {
                    "accepted": False,
                    "rejection_reasons": ["no_stable_improvement"],
                },
                "phase3_complete": False,
            }
        ),
        encoding="utf-8",
    )
    return baseline_path, training_evidence_path, rejected_evidence_path


def test_candidate_fourth_iteration_replaces_rejected_resource_policy(
    tmp_path: Path,
) -> None:
    baseline_path, training_evidence_path, rejected_evidence_path = (
        _write_resource_bounded_inputs(tmp_path)
    )
    candidate_path = tmp_path / "candidate-v4.yaml"
    provenance_path = tmp_path / "provenance-v4.json"

    result = materialize_resource_bounded_candidate(
        baseline_path,
        training_evidence_path,
        rejected_evidence_path,
        candidate_path,
        provenance_path,
    )
    candidate = AgentProfile.from_yaml(candidate_path)

    assert candidate.name == "repository-agent-skillopt-v4"
    assert candidate.max_iterations == 8
    assert candidate.tools == ["read_file", "edit_file", "write_file", "execute"]
    assert "use at most two iterations" in candidate.system_prompt.lower()
    assert "Before finalizing, confirm" not in candidate.system_prompt
    assert "Make the first targeted code edit" not in candidate.system_prompt
    assert candidate.metadata["skillopt_iteration"] == 4
    assert candidate.metadata["tool_contract_version"] == "repository-tools-v2"
    assert result["protocol_version"] == "skillopt-candidate-v4"
    assert result["edit"]["edit_type"] == "replace"
    assert result["profile_changes"]["max_iterations"] == {"before": 8, "after": 8}
    assert result["rejected_candidate_evidence_sha256"] == file_sha256(
        rejected_evidence_path
    )


def test_candidate_fourth_iteration_requires_rejected_prior_candidate(
    tmp_path: Path,
) -> None:
    baseline_path, training_evidence_path, rejected_evidence_path = (
        _write_resource_bounded_inputs(tmp_path)
    )
    rejected = json.loads(rejected_evidence_path.read_text(encoding="utf-8"))
    rejected["validation_gate"]["accepted"] = True
    rejected_evidence_path.write_text(json.dumps(rejected), encoding="utf-8")

    with pytest.raises(ValueError, match="must be rejected"):
        materialize_resource_bounded_candidate(
            baseline_path,
            training_evidence_path,
            rejected_evidence_path,
            tmp_path / "candidate-v4.yaml",
            tmp_path / "provenance-v4.json",
        )
