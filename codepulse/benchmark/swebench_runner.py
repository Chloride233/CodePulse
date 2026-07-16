"""Run a CodePulse Agent against official SWE-bench repository environments."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from docker.errors import ImageNotFound

from codepulse.agent.adapter import (
    AgentProfile,
    _is_provider_auth_error,
    _load_agent_class,
    _serialize_transcript,
)
from codepulse.data.models import Difficulty, Task, TaskCategory, TaskSource
from codepulse.env.sandbox import Container, ResourceLimits, SandboxManager
from codepulse.eval.artifacts import canonical_sha256, file_sha256, load_jsonl

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class OfficialHarness:
    """Official SWE-bench operations used by a single repository trial."""

    make_test_spec: Callable[..., Any]
    build_container: Callable[..., Any]
    setup_logger: Callable[..., Any]
    close_logger: Callable[..., Any]
    copy_to_container: Callable[..., Any]
    exec_run_with_timeout: Callable[..., Any]
    get_eval_report: Callable[..., Any]


@dataclass(frozen=True)
class SWEbenchTrial:
    """Observable result of one Agent attempt on an official SWE-bench instance."""

    success: bool
    outcome: dict[str, Any]
    metrics: dict[str, Any]


SWE_BENCH_TRAINING_TASK_IDS = [
    "django__django-10097",
    "sympy__sympy-19495",
    "scikit-learn__scikit-learn-15100",
    "django__django-13449",
    "django__django-15127",
]
SWE_BENCH_EVALUATION_TASK_IDS = [
    "pydata__xarray-4695",
    "pydata__xarray-3993",
    "sympy__sympy-24562",
    "django__django-14771",
    "sphinx-doc__sphinx-8595",
    "sphinx-doc__sphinx-9602",
    "matplotlib__matplotlib-23299",
    "django__django-16139",
]
SWE_BENCH_EVALUATION_V2_TASK_IDS = [
    "astropy__astropy-12907",
    "mwaskom__seaborn-3069",
    "pallets__flask-5014",
    "psf__requests-1142",
    "pylint-dev__pylint-4551",
    "pytest-dev__pytest-10051",
    "django__django-10554",
    "matplotlib__matplotlib-13989",
]
SWE_BENCH_EVALUATION_V3_TASK_IDS = [
    "django__django-15741",
    "pytest-dev__pytest-10081",
    "sympy__sympy-16886",
    "scikit-learn__scikit-learn-13328",
    "pydata__xarray-4629",
    "psf__requests-5414",
    "pylint-dev__pylint-7277",
    "sphinx-doc__sphinx-8621",
]
SWE_BENCH_SCREEN_TASK_IDS = [
    "django__django-10554",
    "mwaskom__seaborn-3069",
    "psf__requests-1142",
]
SWE_BENCH_SCREEN_V2_TASK_IDS = [
    "pytest-dev__pytest-10081",
    "scikit-learn__scikit-learn-13328",
    "sphinx-doc__sphinx-8621",
]
_SCREEN_INFRA_FAILURES = {
    "provider_auth_error",
    "provider_error",
    "agent_error",
    "sandbox_error",
    "patch_guard_check_error",
}


def load_swebench_instances(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load a frozen SWE-bench JSONL snapshot keyed by instance ID."""
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not all(isinstance(row, dict) and isinstance(row.get("instance_id"), str) for row in rows):
        raise ValueError("SWE-bench snapshot must contain object records with instance_id")
    instances = {str(row["instance_id"]): row for row in rows}
    if len(instances) != len(rows):
        raise ValueError("SWE-bench snapshot contains duplicate instance IDs")
    return instances


def validate_swebench_training_manifest(
    manifest: dict[str, Any], repo_root: str | Path
) -> list[str]:
    """Return frozen-training manifest validation errors without invoking Docker."""
    root = Path(repo_root)
    errors: list[str] = []
    if manifest.get("protocol_version") != "phase3-swebench-training-v1":
        errors.append("protocol_version must equal 'phase3-swebench-training-v1'")
    if manifest.get("benchmark") != "swe-bench-verified":
        errors.append("benchmark must equal 'swe-bench-verified'")
    if manifest.get("n_trials") != 1:
        errors.append("n_trials must equal 1")
    if manifest.get("seed") != 20260717:
        errors.append("seed must equal 20260717")
    task_ids = manifest.get("task_ids")
    if task_ids != SWE_BENCH_TRAINING_TASK_IDS:
        errors.append("task_ids must equal the frozen five-instance training cohort")
    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict):
        return errors + ["dataset must be an object"]
    path = dataset.get("task_path")
    digest = dataset.get("task_sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        return errors + ["dataset.task_path and dataset.task_sha256 are required"]
    snapshot = root / path
    if not snapshot.is_file():
        return errors + [f"dataset.task_path does not exist: {path}"]
    if file_sha256(snapshot) != digest:
        errors.append(f"dataset.task_sha256 mismatch for {path}")
    try:
        instances = load_swebench_instances(snapshot)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"dataset snapshot cannot be loaded: {exc}"]
    if isinstance(task_ids, list) and any(task_id not in instances for task_id in task_ids):
        errors.append("task_ids must all exist in the frozen SWE-bench snapshot")
    agents = manifest.get("agents")
    if not isinstance(agents, list) or len(agents) != 1 or not isinstance(agents[0], dict):
        return errors + ["agents must contain exactly one baseline entry"]
    agent = agents[0]
    if agent.get("role") != "baseline":
        errors.append("training agent role must equal 'baseline'")
    profile_path = agent.get("profile_path")
    profile_digest = agent.get("profile_sha256")
    if not isinstance(profile_path, str) or not isinstance(profile_digest, str):
        return errors + ["baseline profile_path and profile_sha256 are required"]
    profile = root / profile_path
    if not profile.is_file():
        errors.append(f"baseline profile_path does not exist: {profile_path}")
    elif file_sha256(profile) != profile_digest:
        errors.append(f"baseline profile_sha256 mismatch for {profile_path}")
    _validate_swebench_runner(errors, manifest.get("runner"), SWE_BENCH_TRAINING_TASK_IDS)
    if manifest.get("budget") != {"total_cny": 20.0, "per_agent_cny": 20.0, "per_trial_cny": 4.0}:
        errors.append("budget must equal the frozen SWE-bench training limits")
    return errors


def validate_swebench_evolution_manifest(
    manifest: dict[str, Any], repo_root: str | Path
) -> list[str]:
    """Validate the frozen held-out SWE-bench paired-comparison manifest."""
    root = Path(repo_root)
    errors: list[str] = []
    protocol_version = manifest.get("protocol_version")
    if protocol_version not in {
        "phase3-swebench-evolution-v1",
        "phase3-swebench-evolution-v2",
        "phase3-swebench-evolution-v3",
        "phase3-swebench-evolution-v4",
    }:
        errors.append("protocol_version must identify a frozen SWE-bench evolution protocol")
    if manifest.get("benchmark") != "swe-bench-verified":
        errors.append("benchmark must equal 'swe-bench-verified'")
    if protocol_version == "phase3-swebench-evolution-v4":
        expected_task_ids = SWE_BENCH_EVALUATION_V3_TASK_IDS
    elif protocol_version == "phase3-swebench-evolution-v3":
        expected_task_ids = SWE_BENCH_EVALUATION_V2_TASK_IDS
    else:
        expected_task_ids = SWE_BENCH_EVALUATION_TASK_IDS
    if manifest.get("task_ids") != expected_task_ids:
        errors.append("task_ids must equal the frozen eight-instance evaluation cohort")
    if manifest.get("n_trials") != 3:
        errors.append("n_trials must equal 3")
    expected_seed = {
        "phase3-swebench-evolution-v3": 20260719,
        "phase3-swebench-evolution-v4": 20260720,
    }.get(str(protocol_version), 20260718)
    if manifest.get("seed") != expected_seed:
        errors.append(f"seed must equal {expected_seed}")
    dataset = manifest.get("dataset")
    instances = _validate_swebench_dataset(errors, dataset, root)
    if instances is not None and any(task_id not in instances for task_id in expected_task_ids):
        errors.append("task_ids must all exist in the frozen SWE-bench snapshot")
    agents = manifest.get("agents")
    if not isinstance(agents, list) or len(agents) != 2 or not all(isinstance(agent, dict) for agent in agents):
        errors.append("agents must contain exactly baseline and candidate entries")
        agents = []
    roles = {agent.get("role") for agent in agents}
    if roles != {"baseline", "candidate"}:
        errors.append("agents must contain one baseline and one candidate role")
    for index, agent in enumerate(agents):
        _validate_swebench_agent(errors, agent, root, index)
    _validate_swebench_runner(errors, manifest.get("runner"), expected_task_ids)
    runner = manifest.get("runner")
    if protocol_version == "phase3-swebench-screen-v3" and (
        manifest.get("controller_edit_id") != "patch-guard-v1"
        or not isinstance(runner, dict)
        or runner.get("image_transport_prefix") != "dockerproxy.net"
    ):
        errors.append("screen v3 must freeze patch-guard-v1 and dockerproxy.net")
    runner = manifest.get("runner")
    if protocol_version == "phase3-swebench-evolution-v4" and (
        not isinstance(runner, dict)
        or runner.get("image_transport_prefix") != "dockerproxy.net"
    ):
        errors.append("runner.image_transport_prefix must equal 'dockerproxy.net' for v4")
    per_trial_limit = 0.2 if protocol_version == "phase3-swebench-evolution-v1" else 1.0
    if manifest.get("budget") != {
        "total_cny": 10.0,
        "per_agent_cny": 5.0,
        "per_trial_cny": per_trial_limit,
    }:
        errors.append("budget must equal the frozen SWE-bench evolution limits")
    _validate_swebench_candidate_provenance(errors, manifest, agents, root)
    if protocol_version == "phase3-swebench-evolution-v4":
        _validate_swebench_v4_dataset(errors, dataset)
        _validate_swebench_candidate_screen(errors, manifest, root)
    return errors


def validate_swebench_screen_manifest(
    manifest: dict[str, Any], repo_root: str | Path
) -> list[str]:
    """Validate a frozen low-cost SWE-bench training screen."""
    root = Path(repo_root)
    errors: list[str] = []
    protocol_version = manifest.get("protocol_version")
    if protocol_version not in {
        "phase3-swebench-screen-v1",
        "phase3-swebench-screen-v2",
        "phase3-swebench-screen-v3",
        "phase3-strong-model-screen-v1",
    }:
        errors.append("protocol_version must identify a frozen SWE-bench screen")
    paired_screen = protocol_version in {
        "phase3-swebench-screen-v2",
        "phase3-swebench-screen-v3",
        "phase3-strong-model-screen-v1",
    }
    expected_task_ids = (
        SWE_BENCH_SCREEN_V2_TASK_IDS if paired_screen else SWE_BENCH_SCREEN_TASK_IDS
    )
    if manifest.get("benchmark") != "swe-bench-verified":
        errors.append("benchmark must equal 'swe-bench-verified'")
    if manifest.get("task_ids") != expected_task_ids:
        errors.append("task_ids must equal the frozen three-instance screen cohort")
    if manifest.get("n_trials") != 1:
        errors.append("n_trials must equal 1")
    expected_seed = {
        "phase3-swebench-screen-v2": 20260721,
        "phase3-swebench-screen-v3": 20260722,
        "phase3-strong-model-screen-v1": 20260723,
    }.get(str(protocol_version), 20260720)
    if manifest.get("seed") != expected_seed:
        errors.append(f"seed must equal {expected_seed}")

    instances = _validate_swebench_dataset(errors, manifest.get("dataset"), root)
    if instances is not None and any(
        task_id not in instances for task_id in expected_task_ids
    ):
        errors.append("task_ids must all exist in the frozen SWE-bench snapshot")

    agents = manifest.get("agents")
    expected_agent_count = 2 if paired_screen else 1
    if (
        not isinstance(agents, list)
        or len(agents) != expected_agent_count
        or not all(isinstance(agent, dict) for agent in agents)
    ):
        errors.append(f"agents must contain exactly {expected_agent_count} screen entries")
        agents = []
    for index, agent in enumerate(agents):
        _validate_swebench_agent(errors, agent, root, index)
    roles = {agent.get("role") for agent in agents}
    expected_roles = {"baseline", "candidate"} if paired_screen else {"candidate"}
    if roles != expected_roles:
        errors.append("screen agent roles do not match the frozen protocol")

    _validate_swebench_runner(errors, manifest.get("runner"), expected_task_ids)
    expected_budget = {
        "phase3-swebench-screen-v3": {
            "total_cny": 1.0,
            "per_agent_cny": 0.6,
            "per_trial_cny": 0.25,
        },
        "phase3-strong-model-screen-v1": {
            "total_cny": 2.0,
            "per_agent_cny": 1.2,
            "per_trial_cny": 0.4,
        },
    }.get(
        str(protocol_version),
        {"total_cny": 2.0, "per_agent_cny": 2.0, "per_trial_cny": 1.0},
    )
    if manifest.get("budget") != expected_budget:
        errors.append("budget must equal the frozen screen limits")
    expected_acceptance = (
        {
            "min_candidate_non_empty_patches": 2,
            "min_candidate_resolved": 2,
            "min_candidate_resolved_delta": 1,
            "require_zero_candidate_regressions": True,
            "max_candidate_token_ratio": 1.25,
            "max_candidate_cost_ratio": 1.25,
        }
        if protocol_version == "phase3-strong-model-screen-v1"
        else
        {
            "min_candidate_non_empty_patches": 2,
            "min_candidate_resolved": 2,
            "require_candidate_resolved_gte_baseline": True,
            "max_candidate_token_ratio": 1.25,
            "max_candidate_cost_ratio": 1.25,
        }
        if paired_screen
        else {"min_non_empty_patches": 2, "min_resolved": 1}
    )
    if manifest.get("acceptance") != expected_acceptance:
        errors.append("acceptance must equal the frozen screen thresholds")
    if paired_screen and manifest.get("tool_contract_version") != "repository-tools-v2":
        errors.append("tool_contract_version must equal 'repository-tools-v2'")
    if protocol_version == "phase3-strong-model-screen-v1":
        runner = manifest.get("runner")
        pricing = manifest.get("pricing")
        expected_pricing = {
            "currency": "CNY",
            "unit_tokens": 1_000_000,
            "model": "deepseek/deepseek-v4-pro",
            "off_peak": {"cache_hit": 1.0, "cache_miss": 4.0, "output": 16.0},
            "peak": {"cache_hit": 1.0, "cache_miss": 4.0, "output": 16.0},
            "budget_tier": "peak",
        }
        if (
            manifest.get("controller_edit_id") != "patch-guard-v1"
            or not isinstance(runner, dict)
            or runner.get("image_policy") != "local_only"
        ):
            errors.append("strong-model screen must freeze Patch Guard and local-only images")
        if pricing != expected_pricing:
            errors.append("strong-model screen pricing must equal the frozen V4 Pro table")
        if manifest.get("execution_policy") != {
            "server": "forbidden",
            "new_image_downloads": "forbidden",
            "existing_evidence_images": "preserve",
            "no_proxy": "127.0.0.1,localhost,127.0.0.0/8",
        }:
            errors.append("strong-model screen must freeze the local-only execution policy")
        if any(
            agent.get("model_version") != "deepseek/deepseek-v4-pro"
            or agent.get("provider_model_version") != "deepseek-v4-pro"
            for agent in agents
        ):
            errors.append("strong-model screen agents must freeze DeepSeek V4 Pro")
    _validate_swebench_screen_provenance(errors, manifest, agents, root)
    return errors


def evaluate_swebench_screen(
    rows: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate a complete training screen without weakening the final Phase 3 Gate."""
    if manifest.get("protocol_version") in {
        "phase3-swebench-screen-v2",
        "phase3-swebench-screen-v3",
        "phase3-strong-model-screen-v1",
    }:
        return _evaluate_swebench_screen_v2(rows, manifest)
    agents = manifest.get("agents")
    if not isinstance(agents, list) or len(agents) != 1 or not isinstance(agents[0], dict):
        raise ValueError("screen manifest requires exactly one agent")
    agent_name = agents[0].get("name")
    task_ids = manifest.get("task_ids")
    if not isinstance(agent_name, str) or not isinstance(task_ids, list):
        raise ValueError("screen manifest requires agent name and task_ids")
    expected = {(str(task_id), 0, agent_name) for task_id in task_ids}
    actual = {
        (str(row.get("task_id")), row.get("repetition"), str(row.get("agent_name")))
        for row in rows
    }
    if len(actual) != len(rows) or actual != expected:
        raise ValueError("screen trial coverage does not match the frozen task set")

    acceptance = manifest.get("acceptance")
    budget = manifest.get("budget")
    if not isinstance(acceptance, dict) or not isinstance(budget, dict):
        raise ValueError("screen manifest requires acceptance and budget")
    non_empty_patches = sum(
        bool(str(row.get("outcome", {}).get("patch", "")).strip()) for row in rows
    )
    resolved = sum(bool(row.get("success")) for row in rows)
    infrastructure_failures = sum(
        row.get("failure_type") in _SCREEN_INFRA_FAILURES for row in rows
    )
    costs = [float(row.get("metrics", {}).get("cost_cny_peak", 0.0)) for row in rows]
    total_cost = round(sum(costs), 6)
    max_trial_cost = max(costs, default=0.0)
    rejection_reasons: list[str] = []
    if non_empty_patches < int(acceptance["min_non_empty_patches"]):
        rejection_reasons.append("insufficient_non_empty_patches")
    if resolved < int(acceptance["min_resolved"]):
        rejection_reasons.append("insufficient_resolved")
    if infrastructure_failures:
        rejection_reasons.append("infrastructure_failure")
    if max_trial_cost > float(budget["per_trial_cny"]):
        rejection_reasons.append("per_trial_budget_exceeded")
    if total_cost > float(budget["total_cny"]):
        rejection_reasons.append("total_budget_exceeded")
    return {
        "accepted": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "completed_trials": len(rows),
        "non_empty_patches": non_empty_patches,
        "resolved": resolved,
        "infrastructure_failures": infrastructure_failures,
        "total_cost_cny_peak": total_cost,
        "max_trial_cost_cny_peak": max_trial_cost,
    }


def _evaluate_swebench_screen_v2(
    rows: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    agents = manifest.get("agents")
    task_ids = manifest.get("task_ids")
    if (
        not isinstance(agents, list)
        or len(agents) != 2
        or not all(isinstance(agent, dict) for agent in agents)
        or not isinstance(task_ids, list)
    ):
        raise ValueError("screen v2 manifest requires paired agents and task_ids")
    role_names = {str(agent.get("role")): agent.get("name") for agent in agents}
    if set(role_names) != {"baseline", "candidate"} or not all(
        isinstance(name, str) and name for name in role_names.values()
    ):
        raise ValueError("screen v2 manifest requires baseline and candidate names")
    expected = {
        (str(task_id), 0, str(agent_name))
        for task_id in task_ids
        for agent_name in role_names.values()
    }
    actual = {
        (str(row.get("task_id")), row.get("repetition"), str(row.get("agent_name")))
        for row in rows
    }
    if len(actual) != len(rows) or actual != expected:
        raise ValueError("screen trial coverage does not match the frozen paired task set")

    acceptance = manifest.get("acceptance")
    budget = manifest.get("budget")
    if not isinstance(acceptance, dict) or not isinstance(budget, dict):
        raise ValueError("screen manifest requires acceptance and budget")

    def agent_stats(agent_name: object) -> dict[str, Any]:
        agent_rows = [row for row in rows if row.get("agent_name") == agent_name]
        return {
            "non_empty_patches": sum(
                bool(str(row.get("outcome", {}).get("patch", "")).strip())
                for row in agent_rows
            ),
            "resolved": sum(bool(row.get("success")) for row in agent_rows),
            "total_tokens": sum(
                int(row.get("metrics", {}).get("total_tokens", 0))
                for row in agent_rows
            ),
            "total_cost_cny_peak": round(
                sum(
                    float(row.get("metrics", {}).get("cost_cny_peak", 0.0))
                    for row in agent_rows
                ),
                6,
            ),
            "patch_guard_checks": sum(
                int(row.get("metrics", {}).get("patch_guard_checks", 0))
                for row in agent_rows
            ),
            "patch_guard_triggers": sum(
                int(row.get("metrics", {}).get("patch_guard_triggers", 0))
                for row in agent_rows
            ),
            "patch_guard_retries_used": sum(
                int(row.get("metrics", {}).get("patch_guard_retries_used", 0))
                for row in agent_rows
            ),
            "patch_guard_check_failures": sum(
                int(row.get("metrics", {}).get("patch_guard_check_failures", 0))
                for row in agent_rows
            ),
            "effective_call_limits": sorted(
                int(row.get("metrics", {}).get("effective_call_limit", 0))
                for row in agent_rows
                if int(row.get("metrics", {}).get("effective_call_limit", 0)) > 0
            ),
        }

    baseline = agent_stats(role_names["baseline"])
    candidate = agent_stats(role_names["candidate"])
    task_attribution: dict[str, str] = {}
    for task_id in task_ids:
        baseline_success = any(
            bool(row.get("success"))
            for row in rows
            if row.get("task_id") == task_id
            and row.get("agent_name") == role_names["baseline"]
        )
        candidate_success = any(
            bool(row.get("success"))
            for row in rows
            if row.get("task_id") == task_id
            and row.get("agent_name") == role_names["candidate"]
        )
        task_attribution[str(task_id)] = {
            (False, True): "improvement",
            (True, False): "regression",
            (False, False): "persistent_failure",
            (True, True): "stable_success",
        }[(baseline_success, candidate_success)]
    attribution_counts = {
        category: sum(value == category for value in task_attribution.values())
        for category in (
            "improvement",
            "regression",
            "persistent_failure",
            "stable_success",
        )
    }
    baseline_tokens = int(baseline["total_tokens"])
    candidate_tokens = int(candidate["total_tokens"])
    baseline_cost = float(baseline["total_cost_cny_peak"])
    candidate_cost = float(candidate["total_cost_cny_peak"])
    candidate_resolved_delta = int(candidate["resolved"]) - int(baseline["resolved"])
    token_ratio = (
        round(candidate_tokens / baseline_tokens, 6) if baseline_tokens else None
    )
    cost_ratio = round(candidate_cost / baseline_cost, 6) if baseline_cost else None
    infrastructure_failures = sum(
        row.get("failure_type") in _SCREEN_INFRA_FAILURES for row in rows
    )
    costs = [float(row.get("metrics", {}).get("cost_cny_peak", 0.0)) for row in rows]
    total_cost = round(sum(costs), 6)
    max_trial_cost = max(costs, default=0.0)
    rejection_reasons: list[str] = []
    if int(candidate["non_empty_patches"]) < int(
        acceptance["min_candidate_non_empty_patches"]
    ):
        rejection_reasons.append("insufficient_candidate_non_empty_patches")
    if int(candidate["resolved"]) < int(acceptance["min_candidate_resolved"]):
        rejection_reasons.append("insufficient_candidate_resolved")
    if acceptance.get("require_candidate_resolved_gte_baseline", False) and int(
        candidate["resolved"]
    ) < int(baseline["resolved"]):
        rejection_reasons.append("candidate_resolved_below_baseline")
    if candidate_resolved_delta < int(acceptance.get("min_candidate_resolved_delta", 0)):
        rejection_reasons.append("insufficient_candidate_resolved_delta")
    if acceptance.get("require_zero_candidate_regressions", False) and int(
        attribution_counts["regression"]
    ):
        rejection_reasons.append("candidate_task_regression")
    if candidate_tokens > baseline_tokens * float(acceptance["max_candidate_token_ratio"]):
        rejection_reasons.append("candidate_token_ratio_exceeded")
    if candidate_cost > baseline_cost * float(acceptance["max_candidate_cost_ratio"]):
        rejection_reasons.append("candidate_cost_ratio_exceeded")
    if infrastructure_failures:
        rejection_reasons.append("infrastructure_failure")
    if max_trial_cost > float(budget["per_trial_cny"]):
        rejection_reasons.append("per_trial_budget_exceeded")
    if total_cost > float(budget["total_cny"]):
        rejection_reasons.append("total_budget_exceeded")
    if max(baseline_cost, candidate_cost) > float(budget["per_agent_cny"]):
        rejection_reasons.append("per_agent_budget_exceeded")
    return {
        "accepted": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "completed_trials": len(rows),
        "baseline": baseline,
        "candidate": candidate,
        "candidate_resolved_delta": candidate_resolved_delta,
        "task_attribution": task_attribution,
        "attribution_counts": attribution_counts,
        "candidate_token_ratio": token_ratio,
        "candidate_cost_ratio": cost_ratio,
        "infrastructure_failures": infrastructure_failures,
        "total_cost_cny_peak": total_cost,
        "max_trial_cost_cny_peak": max_trial_cost,
    }


def _validate_swebench_dataset(
    errors: list[str], dataset: object, root: Path
) -> dict[str, dict[str, Any]] | None:
    if not isinstance(dataset, dict):
        errors.append("dataset must be an object")
        return None
    path = dataset.get("task_path")
    digest = dataset.get("task_sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        errors.append("dataset.task_path and dataset.task_sha256 are required")
        return None
    snapshot = root / path
    if not snapshot.is_file():
        errors.append(f"dataset.task_path does not exist: {path}")
        return None
    if file_sha256(snapshot) != digest:
        errors.append(f"dataset.task_sha256 mismatch for {path}")
    try:
        return load_swebench_instances(snapshot)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"dataset snapshot cannot be loaded: {exc}")
        return None


def _validate_swebench_agent(errors: list[str], agent: dict[str, Any], root: Path, index: int) -> None:
    prefix = f"agents[{index}]"
    if agent.get("role") not in {"baseline", "candidate"}:
        errors.append(f"{prefix}.role must be baseline or candidate")
    for key in ("name", "model_version", "provider_model_version"):
        if not isinstance(agent.get(key), str) or not agent[key]:
            errors.append(f"{prefix}.{key} is required")
    profile_path = agent.get("profile_path")
    profile_digest = agent.get("profile_sha256")
    if not isinstance(profile_path, str) or not isinstance(profile_digest, str):
        errors.append(f"{prefix}.profile_path and profile_sha256 are required")
    elif not (root / profile_path).is_file():
        errors.append(f"{prefix}.profile_path does not exist: {profile_path}")
    elif file_sha256(root / profile_path) != profile_digest:
        errors.append(f"{prefix}.profile_sha256 mismatch for {profile_path}")


def _validate_swebench_runner(errors: list[str], runner: object, task_ids: list[str]) -> None:
    if not isinstance(runner, dict):
        errors.append("runner must be an object")
        return
    for key, expected in (
        ("harness_version", "swebench==4.1.0"),
        ("architecture", "x86_64"),
        ("image_namespace", "swebench"),
        ("timeout_seconds", 900),
        ("cpu_count", 2),
        ("memory_mb", 4096),
        ("network", "none"),
    ):
        if runner.get(key) != expected:
            errors.append(f"runner.{key} must equal {expected!r}")
    image_digests = runner.get("image_digests")
    if not isinstance(image_digests, dict) or set(image_digests) != set(task_ids):
        errors.append("runner.image_digests must cover exactly the frozen task_ids")
    elif not all(
        isinstance(digest, str)
        and digest.startswith("sha256:")
        and len(digest) == 71
        and all(character in "0123456789abcdef" for character in digest[7:])
        for digest in image_digests.values()
    ):
        errors.append("runner.image_digests values must be sha256 digests")


def _validate_swebench_candidate_provenance(
    errors: list[str], manifest: dict[str, Any], agents: list[dict[str, Any]], root: Path
) -> None:
    section = manifest.get("candidate_provenance")
    if not isinstance(section, dict):
        errors.append("candidate_provenance must be an object")
        return
    path = section.get("path")
    digest = section.get("sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        errors.append("candidate_provenance.path and sha256 are required")
        return
    provenance_path = root / path
    if not provenance_path.is_file() or file_sha256(provenance_path) != digest:
        errors.append("candidate_provenance file is missing or hash-mismatched")
        return
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"candidate_provenance cannot be loaded: {exc}")
        return
    if not isinstance(provenance, dict) or provenance.get("protocol_version") not in {
        "skillopt-candidate-v1",
        "skillopt-candidate-v2",
        "skillopt-candidate-v3",
    }:
        errors.append("candidate_provenance.protocol_version must identify a frozen candidate")
        return
    roles = {agent.get("role"): agent for agent in agents}
    baseline = roles.get("baseline", {})
    candidate = roles.get("candidate", {})
    for key, expected in (
        ("baseline_profile_path", baseline.get("profile_path")),
        ("baseline_profile_sha256", baseline.get("profile_sha256")),
        ("candidate_profile_path", candidate.get("profile_path")),
        ("candidate_profile_sha256", candidate.get("profile_sha256")),
    ):
        if provenance.get(key) != expected:
            errors.append(f"candidate_provenance.{key} must match the frozen manifest")
    trials_path = provenance.get("training_trials_path")
    trials_digest = provenance.get("training_trials_sha256")
    if not isinstance(trials_path, str) or not isinstance(trials_digest, str):
        errors.append("candidate_provenance training trials binding is required")
        return
    trials_file = root / trials_path
    if not trials_file.is_file() or file_sha256(trials_file) != trials_digest:
        errors.append("candidate_provenance training trials are missing or hash-mismatched")
        return
    try:
        rows = load_jsonl(trials_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"candidate_provenance training trials cannot be loaded: {exc}")
        return
    failed = {
        str(row.get("task_id"))
        for row in rows
        if row.get("agent_name") == baseline.get("name")
        and not bool(row.get("success"))
        and row.get("failure_type") not in {"provider_auth_error", "provider_error", "agent_error", "sandbox_error"}
    }
    source_ids = provenance.get("source_task_ids")
    if not isinstance(source_ids, list) or not source_ids or not set(source_ids).issubset(failed):
        errors.append("candidate_provenance.source_task_ids must reference failed baseline trials")
    if isinstance(source_ids, list) and set(source_ids) & set(manifest.get("task_ids", [])):
        errors.append("candidate_provenance.source_task_ids must not overlap evaluation tasks")


def _validate_swebench_screen_provenance(
    errors: list[str], manifest: dict[str, Any], agents: list[dict[str, Any]], root: Path
) -> None:
    """Bind the training screen to its candidate profile and source traces."""
    protocol_version = manifest.get("protocol_version")
    section_name = (
        "profile_provenance"
        if protocol_version == "phase3-strong-model-screen-v1"
        else "candidate_provenance"
    )
    section = manifest.get(section_name)
    if not isinstance(section, dict):
        errors.append(f"{section_name} must be an object")
        return
    path = section.get("path")
    digest = section.get("sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        errors.append("candidate_provenance.path and sha256 are required")
        return
    provenance_path = root / path
    if not provenance_path.is_file() or file_sha256(provenance_path) != digest:
        errors.append("candidate_provenance file is missing or hash-mismatched")
        return
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"candidate_provenance cannot be loaded: {exc}")
        return
    expected_provenance = {
        "phase3-swebench-screen-v2": "skillopt-candidate-v4",
        "phase3-swebench-screen-v3": "skillopt-candidate-v5",
        "phase3-strong-model-screen-v1": "phase3-strong-model-profiles-v1",
    }.get(str(protocol_version), "skillopt-candidate-v3")
    if not isinstance(provenance, dict) or provenance.get(
        "protocol_version"
    ) != expected_provenance:
        errors.append(
            f"candidate_provenance.protocol_version must equal {expected_provenance!r}"
        )
        return
    roles = {agent.get("role"): agent for agent in agents}
    agent = roles.get("candidate", {})
    for key, expected in (
        ("candidate_profile_path", agent.get("profile_path")),
        ("candidate_profile_sha256", agent.get("profile_sha256")),
    ):
        if provenance.get(key) != expected:
            errors.append(f"candidate_provenance.{key} must match the frozen manifest")
    if protocol_version == "phase3-strong-model-screen-v1":
        baseline = roles.get("baseline", {})
        for key, expected in (
            ("baseline_profile_path", baseline.get("profile_path")),
            ("baseline_profile_sha256", baseline.get("profile_sha256")),
        ):
            if provenance.get(key) != expected:
                errors.append(f"profile_provenance.{key} must match the frozen manifest")
        controller_edit = provenance.get("controller_edit")
        if (
            provenance.get("model") != "deepseek/deepseek-v4-pro"
            or provenance.get("provider_model_version") != "deepseek-v4-pro"
            or provenance.get("tool_contract_version") != "repository-tools-v2"
            or not isinstance(controller_edit, dict)
            or controller_edit.get("edit_id") != "patch-guard-v1"
            or provenance.get("runtime_changes")
            != {"empty_patch_retries": {"before": 0, "after": 1}}
        ):
            errors.append("profile_provenance must freeze the V4 Pro Patch Guard pair")
        provenance_pricing = provenance.get("pricing_cny_per_million_tokens")
        manifest_pricing = manifest.get("pricing")
        if not isinstance(manifest_pricing, dict) or provenance_pricing != {
            "off_peak": manifest_pricing.get("off_peak"),
            "peak": manifest_pricing.get("peak"),
        }:
            errors.append("profile_provenance pricing must match the frozen manifest")
        return
    if protocol_version in {
        "phase3-swebench-screen-v2",
        "phase3-swebench-screen-v3",
    }:
        baseline = roles.get("baseline", {})
        for key, expected in (
            ("baseline_profile_path", baseline.get("profile_path")),
            ("baseline_profile_sha256", baseline.get("profile_sha256")),
        ):
            if provenance.get(key) != expected:
                errors.append(f"candidate_provenance.{key} must match the frozen manifest")
        if provenance.get("tool_contract_version") != "repository-tools-v2":
            errors.append("candidate_provenance must freeze repository-tools-v2")
        controller_edit = provenance.get("controller_edit")
        if protocol_version == "phase3-swebench-screen-v3" and (
            not isinstance(controller_edit, dict)
            or controller_edit.get("edit_id") != "patch-guard-v1"
            or provenance.get("profile_changes")
            != {"empty_patch_retries": {"before": 0, "after": 1}}
        ):
            errors.append("candidate_provenance must freeze the patch guard-only change")
    trials_path = provenance.get("training_trials_path")
    trials_digest = provenance.get("training_trials_sha256")
    if not isinstance(trials_path, str) or not isinstance(trials_digest, str):
        errors.append("candidate_provenance training trials binding is required")
    elif not (root / trials_path).is_file() or file_sha256(root / trials_path) != trials_digest:
        errors.append("candidate_provenance training trials are missing or hash-mismatched")
    source_ids = provenance.get("source_task_ids")
    if not isinstance(source_ids, list) or not set(manifest.get("task_ids", [])).issubset(
        set(source_ids)
    ):
        errors.append("screen task_ids must be included in candidate training sources")


def _validate_swebench_v4_dataset(errors: list[str], dataset: object) -> None:
    """Validate the frozen source artifact and metadata-only selection rule for v4."""
    if not isinstance(dataset, dict):
        return
    if dataset.get("source_name") != "princeton-nlp/SWE-bench_Verified":
        errors.append("dataset.source_name must identify SWE-bench Verified")
    if dataset.get("source_revision") != "c104f840cc67f8b6eec6f759ebc8b2693d585d4a":
        errors.append("dataset.source_revision must equal the frozen Verified revision")
    if dataset.get("source_artifact_sha256") != (
        "a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd"
    ):
        errors.append("dataset.source_artifact_sha256 must equal the frozen Parquet digest")
    if dataset.get("selection") != {
        "exclude_snapshots": [
            "datasets/swe-bench/phase3-swebench-v1.jsonl",
            "datasets/swe-bench/phase3-swebench-v2.jsonl",
        ],
        "difficulty": "<15 min fix",
        "seed": 20260720,
        "max_tasks_per_repo": 1,
    }:
        errors.append("dataset.selection must equal the frozen metadata-only selection rule")


def _validate_swebench_candidate_screen(
    errors: list[str], manifest: dict[str, Any], root: Path
) -> None:
    """Require immutable evidence that candidate v3 passed its training-only screen."""
    section = manifest.get("candidate_screen")
    if not isinstance(section, dict):
        errors.append("candidate_screen must be an object")
        return
    path = section.get("path")
    digest = section.get("sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        errors.append("candidate_screen.path and sha256 are required")
        return
    evidence_path = root / path
    if not evidence_path.is_file() or file_sha256(evidence_path) != digest:
        errors.append("candidate_screen evidence is missing or hash-mismatched")
        return
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"candidate_screen evidence cannot be loaded: {exc}")
        return
    if not isinstance(evidence, dict) or evidence.get("protocol_version") != (
        "phase3-swebench-screen-evidence-v1"
    ):
        errors.append("candidate_screen evidence has the wrong protocol_version")
        return
    if evidence.get("accepted") is not True:
        errors.append("candidate_screen must be accepted")
    report_path = evidence.get("screen_report_path")
    report_digest = evidence.get("screen_report_sha256")
    if (
        not isinstance(report_path, str)
        or not isinstance(report_digest, str)
        or not (root / report_path).is_file()
        or file_sha256(root / report_path) != report_digest
    ):
        errors.append("candidate_screen report is missing or hash-mismatched")


def run_swebench_trial(
    profile: AgentProfile,
    instance: dict[str, Any],
    sandbox: SandboxManager,
    *,
    timeout_seconds: int,
    architecture: str,
    image_namespace: str,
    image_digest: str,
    cpu_count: int,
    memory_mb: int,
    image_transport_prefix: str = "",
    allow_image_pull: bool = True,
) -> SWEbenchTrial:
    """Run one Agent in an official repository image and grade its submitted patch."""
    harness = _official_harness()
    test_spec = harness.make_test_spec(
        instance,
        namespace=image_namespace,
        arch=architecture,
    )
    client = sandbox._client
    image_ref = _prepare_official_image(
        client,
        test_spec,
        image_digest,
        image_transport_prefix=image_transport_prefix,
        allow_pull=allow_image_pull,
    )
    log_path = Path("results") / "swebench-harness" / str(instance["instance_id"]) / "agent.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = harness.setup_logger(str(instance["instance_id"]), log_path)
    official_container = None
    try:
        official_container = harness.build_container(
            test_spec, client, "codepulse", logger, False, False
        )
        _start_isolated_container(client, official_container, cpu_count, memory_mb)
        container = Container(
            id=str(official_container.id),
            image=str(test_spec.instance_image_key),
            resource_limits=ResourceLimits(
                cpu_count=cpu_count,
                memory_mb=memory_mb,
                timeout_seconds=timeout_seconds,
            ),
        )
        _bind_workspace(sandbox, container)
        task = _task_from_instance(instance)
        agent = _load_agent_class(profile)
        sandbox.set_active_container(container)
        transcript = agent.run(task, sandbox)
        sandbox.clear_active_container()
        error_event = next(
            (event for event in reversed(transcript.events) if event.event_type == "error"),
            None,
        )
        failure_type = None
        if error_event is not None:
            failure_type = (
                "provider_auth_error"
                if _is_provider_auth_error(error_event.content)
                else "provider_error"
            )
        elif int(transcript.agent_config.get("patch_guard_check_failures", 0)):
            failure_type = "patch_guard_check_error"
        patch_result = sandbox.execute(container, "cd /testbed && git diff")
        report, test_output = _evaluate_patch(
            harness, official_container, test_spec, instance, patch_result.stdout, timeout_seconds
        )
        resolved = bool(report.get(str(instance["instance_id"]), {}).get("resolved", False))
        outcome = {
            "official_resolved": resolved,
            "official_report": report,
            "instance_image": image_ref,
            "patch": patch_result.stdout,
            "patch_sha256": canonical_sha256(patch_result.stdout),
            "test_output": test_output[:4096],
            "trace": _serialize_transcript(transcript),
            "failure_type": failure_type,
            "provider_model_versions": transcript.agent_config.get(
                "provider_model_versions", []
            ),
        }
        if image_transport_prefix:
            outcome["image_transport"] = (
                f"{image_transport_prefix.rstrip('/')}/{image_ref}"
            )
        return SWEbenchTrial(
            success=resolved,
            outcome=outcome,
            metrics=_transcript_metrics(transcript),
        )
    finally:
        sandbox.clear_active_container()
        if official_container is not None:
            official_container.remove(force=True)
        harness.close_logger(logger)


def _prepare_official_image(
    client: Any,
    test_spec: Any,
    digest: str,
    *,
    image_transport_prefix: str = "",
    allow_pull: bool = True,
) -> str:
    """Pull the frozen official image by digest and expose its expected local tag."""
    repository, tag = str(test_spec.instance_image_key).rsplit(":", 1)
    image_ref = f"{repository}@{digest}"
    try:
        image = client.images.get(image_ref)
    except ImageNotFound:
        transport_repository = (
            f"{image_transport_prefix.rstrip('/')}/{repository}"
            if image_transport_prefix
            else repository
        )
        transport_ref = f"{transport_repository}@{digest}"
        try:
            image = client.images.get(transport_ref)
        except ImageNotFound:
            if not allow_pull:
                raise
            image = client.images.pull(transport_ref)
    image.tag(repository, tag=tag)
    return image_ref


def _require_local_image_digests(
    client: Any, image_digests: dict[str, str]
) -> None:
    """Fail before model calls when any local-only screen image is absent."""
    for task_id, digest in image_digests.items():
        try:
            client.images.get(digest)
        except ImageNotFound as exc:
            raise RuntimeError(
                f"local-only image digest is missing for {task_id}: {digest}"
            ) from exc


def _transcript_metrics(transcript: Any) -> dict[str, int | float]:
    """Return comparable token metrics without counting cache hits twice."""
    input_tokens = int(transcript.agent_config.get("input_tokens", 0))
    output_tokens = int(transcript.agent_config.get("output_tokens", 0))
    patch_guard_triggers = sum(
        event.event_type == "reflection"
        and event.content.get("kind") == "patch_guard"
        for event in transcript.events
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_tokens": int(transcript.agent_config.get("cache_tokens", 0)),
        "total_tokens": input_tokens + output_tokens,
        "duration_seconds": transcript.total_duration,
        "cost_usd": float(transcript.agent_config.get("cost_usd", 0.0)),
        "patch_guard_checks": int(
            transcript.agent_config.get("patch_guard_checks", 0)
        ),
        "patch_guard_triggers": patch_guard_triggers,
        "patch_guard_retries_used": int(
            transcript.agent_config.get("patch_guard_retries_used", 0)
        ),
        "patch_guard_check_failures": int(
            transcript.agent_config.get("patch_guard_check_failures", 0)
        ),
        "base_max_iterations": int(
            transcript.agent_config.get("base_max_iterations", 0)
        ),
        "effective_call_limit": int(
            transcript.agent_config.get("effective_call_limit", 0)
        ),
    }


def _start_isolated_container(
    client: Any, official_container: Any, cpu_count: int, memory_mb: int
) -> None:
    """Apply frozen resource limits and remove every Docker network attachment."""
    official_container.update(
        cpu_period=100_000,
        cpu_quota=cpu_count * 100_000,
        mem_limit=f"{memory_mb}m",
        memswap_limit=f"{memory_mb}m",
    )
    official_container.start()
    official_container.reload()
    networks = official_container.attrs.get("NetworkSettings", {}).get("Networks", {})
    for network_name in networks:
        client.networks.get(network_name).disconnect(official_container, force=True)


def _task_from_instance(instance: dict[str, Any]) -> Task:
    """Expose only the issue context to the Agent, never the oracle patch or tests."""
    return Task(
        task_id=str(instance["instance_id"]),
        source=TaskSource.SWE_BENCH,
        category=TaskCategory.BUG_FIX,
        difficulty=Difficulty.MEDIUM,
        language="python",
        input={"description": str(instance["problem_statement"])},
        ground_truth={},
        metadata={
            "repo": str(instance["repo"]),
            "base_commit": str(instance["base_commit"]),
        },
    )


def _bind_workspace(sandbox: SandboxManager, container: Container) -> None:
    """Map the Agent's existing /workspace tools onto the official /testbed repo."""
    result = sandbox.execute(
        container, "test -d /testbed && (test -e /workspace || ln -s /testbed /workspace)"
    )
    if result.exit_code != 0:
        raise RuntimeError("official SWE-bench container does not expose /testbed")


def _evaluate_patch(
    harness: OfficialHarness,
    official_container: Any,
    test_spec: Any,
    instance: dict[str, Any],
    patch: str,
    timeout_seconds: int,
) -> tuple[dict[str, Any], str]:
    """Run the official evaluation script against the Agent-generated patch."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        patch_path = root / "patch.diff"
        eval_path = root / "eval.sh"
        output_path = root / "test_output.txt"
        patch_path.write_text(patch, encoding="utf-8")
        eval_path.write_text(str(test_spec.eval_script), encoding="utf-8")
        harness.copy_to_container(official_container, patch_path, PurePosixPath("/tmp/patch.diff"))
        for command in (["git", "reset", "--hard", "HEAD"], ["git", "clean", "-fd"]):
            result = official_container.exec_run(command, workdir="/testbed", user="root")
            if result.exit_code != 0:
                output = result.output.decode("utf-8", errors="replace")
                raise RuntimeError(f"failed to prepare SWE-bench workspace: {output}")
        apply_result = official_container.exec_run(
            ["git", "apply", "--verbose", "/tmp/patch.diff"],
            workdir="/testbed",
            user="root",
        )
        if apply_result.exit_code != 0:
            return {}, apply_result.output.decode("utf-8", errors="replace")
        harness.copy_to_container(official_container, eval_path, PurePosixPath("/eval.sh"))
        test_output, timed_out, _ = harness.exec_run_with_timeout(
            official_container, "/bin/bash /eval.sh", timeout_seconds
        )
        if timed_out:
            return {}, test_output + f"\nTimeout after {timeout_seconds}s"
        output_path.write_text(test_output, encoding="utf-8")
        prediction = {
            "instance_id": str(instance["instance_id"]),
            "model_name_or_path": "codepulse",
            "model_patch": patch,
        }
        return harness.get_eval_report(test_spec, prediction, output_path, True), test_output


def _official_harness() -> OfficialHarness:
    """Load the official harness lazily so core CodePulse stays lightweight."""
    try:
        from swebench.harness.docker_build import (  # type: ignore[import-untyped]
            build_container,
            close_logger,
            setup_logger,
        )
        from swebench.harness.docker_utils import (  # type: ignore[import-untyped]
            copy_to_container,
            exec_run_with_timeout,
        )
        from swebench.harness.grading import get_eval_report  # type: ignore[import-untyped]
        from swebench.harness.test_spec import test_spec  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "SWE-bench support requires `pip install -e '.[swebench]'`"
        ) from exc
    return OfficialHarness(
        make_test_spec=test_spec.make_test_spec,
        build_container=build_container,
        setup_logger=setup_logger,
        close_logger=close_logger,
        copy_to_container=copy_to_container,
        exec_run_with_timeout=exec_run_with_timeout,
        get_eval_report=get_eval_report,
    )
