"""Deterministic preflight validation for reproducible benchmark runs."""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PILOT_TASK_IDS = [f"HumanEval/{task_id}" for task_id in range(20)]
DIAGNOSTIC_TASK_IDS = [f"HumanEval/{task_id}" for task_id in range(10)]
DIAGNOSTIC_HARD_TASK_IDS = [f"HumanEval/{task_id}" for task_id in range(100, 140)]
PHASE3_TRAINING_TASK_IDS = [f"HumanEval/{task_id}" for task_id in range(100, 110)]
PHASE3_TRAINING_HARD_TASK_IDS = [f"HumanEval/{task_id}" for task_id in range(130, 140)]
MUTABLE_MODEL_NAMES = {"latest", "deepseek-chat", "deepseek/deepseek-chat"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
INFRA_FAILURES = {
    "provider_auth_error",
    "provider_error",
    "agent_error",
    "sandbox_error",
}
V4_FLASH_PRICING_CNY = {
    "off_peak": {"cache_hit": 0.02, "cache_miss": 1.0, "output": 2.0},
    "peak": {"cache_hit": 0.04, "cache_miss": 2.0, "output": 4.0},
}


def build_pilot_schedule(
    task_ids: list[str], agent_names: list[str], n_trials: int, seed: int
) -> list[tuple[str, int, str]]:
    """Build task -> repetition -> seeded Agent order for the pilot."""
    rng = random.Random(seed)
    schedule: list[tuple[str, int, str]] = []
    for task_id in task_ids:
        for repetition in range(n_trials):
            order = agent_names.copy()
            rng.shuffle(order)
            schedule.extend((task_id, repetition, name) for name in order)
    return schedule


def deepseek_v4_flash_cost_cny(
    input_tokens: int,
    output_tokens: int,
    cache_hit_tokens: int,
    pricing_tier: str,
) -> float:
    """Calculate V4 Flash cost in CNY for an explicit pricing tier."""
    if pricing_tier not in V4_FLASH_PRICING_CNY:
        raise ValueError(f"Unknown V4 Flash pricing tier: {pricing_tier}")
    if min(input_tokens, output_tokens, cache_hit_tokens) < 0:
        raise ValueError("Token counts cannot be negative")
    if cache_hit_tokens > input_tokens:
        raise ValueError("Cache-hit tokens cannot exceed input tokens")
    pricing = V4_FLASH_PRICING_CNY[pricing_tier]
    cache_miss_tokens = input_tokens - cache_hit_tokens
    return round(
        (
            cache_hit_tokens * pricing["cache_hit"]
            + cache_miss_tokens * pricing["cache_miss"]
            + output_tokens * pricing["output"]
        )
        / 1_000_000,
        6,
    )


@dataclass
class PilotBudgetGuard:
    """Track pilot cost and infrastructure stop conditions across trials."""

    planned_trials: int = 120
    total_limit_cny: float = 10.0
    per_agent_limit_cny: float = 5.0
    per_trial_limit_cny: float = 0.1
    total_cost_cny: float = 0.0
    completed_trials: int = 0
    infrastructure_failures: int = 0
    consecutive_infrastructure_failures: int = 0
    agent_costs_cny: dict[str, float] = field(default_factory=dict)

    def record_trial(
        self,
        agent_name: str,
        cost_cny: float | None,
        failure_type: str | None = None,
    ) -> list[str]:
        """Record one trial and return every triggered stop reason."""
        self.completed_trials += 1
        reasons: list[str] = []

        if cost_cny is None:
            reasons.append("cost_unavailable")
        elif cost_cny < 0:
            reasons.append("cost_invalid")
        else:
            self.total_cost_cny += cost_cny
            agent_total = self.agent_costs_cny.get(agent_name, 0.0) + cost_cny
            self.agent_costs_cny[agent_name] = agent_total
            if cost_cny >= self.per_trial_limit_cny:
                reasons.append("per_trial_budget_reached")
            if agent_total >= self.per_agent_limit_cny:
                reasons.append("per_agent_budget_reached")
            if self.total_cost_cny >= self.total_limit_cny:
                reasons.append("total_budget_reached")
            projected_cost = self.total_cost_cny / self.completed_trials * self.planned_trials
            if projected_cost > self.total_limit_cny:
                reasons.append("projected_budget_exceeded")

        if failure_type in INFRA_FAILURES:
            self.infrastructure_failures += 1
            self.consecutive_infrastructure_failures += 1
        else:
            self.consecutive_infrastructure_failures = 0
        if failure_type == "provider_auth_error":
            reasons.append("provider_authentication_failed")
        if self.consecutive_infrastructure_failures >= 3:
            reasons.append("consecutive_infrastructure_failures")
        if (
            self.completed_trials >= 10
            and self.infrastructure_failures / self.completed_trials > 0.1
        ):
            reasons.append("infrastructure_failure_rate_exceeded")

        return reasons


def load_pilot_manifest(path: str | Path) -> dict[str, Any]:
    """Load a pilot manifest from JSON."""
    manifest_path = Path(path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load pilot manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Pilot manifest must be a JSON object")
    return data


def validate_pilot_manifest(manifest: dict[str, Any], repo_root: str | Path) -> list[str]:
    """Return all reproducibility gate failures in a pilot manifest."""
    root = Path(repo_root)
    errors: list[str] = []

    protocol_version = manifest.get("protocol_version")
    if protocol_version == "pilot-v1":
        expected_task_ids = PILOT_TASK_IDS
        expected_trials = 3
        expected_seed = 20260712
        expected_agents = 2
        expected_budget = {
            "total_cny": 10.0,
            "per_agent_cny": 5.0,
            "per_trial_cny": 0.1,
        }
    elif protocol_version == "phase2-diagnostic-v1":
        expected_task_ids = DIAGNOSTIC_TASK_IDS
        expected_trials = 1
        expected_seed = 20260713
        expected_agents = 1
        expected_budget = {
            "total_cny": 1.0,
            "per_agent_cny": 1.0,
            "per_trial_cny": 0.1,
        }
    elif protocol_version == "phase2-diagnostic-v2":
        expected_task_ids = PILOT_TASK_IDS
        expected_trials = 1
        expected_seed = 20260713
        expected_agents = 2
        expected_budget = {
            "total_cny": 4.0,
            "per_agent_cny": 2.0,
            "per_trial_cny": 0.1,
        }
    elif protocol_version == "phase2-diagnostic-v3":
        expected_task_ids = DIAGNOSTIC_HARD_TASK_IDS
        expected_trials = 1
        expected_seed = 20260713
        expected_agents = 1
        expected_budget = {
            "total_cny": 4.0,
            "per_agent_cny": 4.0,
            "per_trial_cny": 0.1,
        }
    elif protocol_version == "phase3-evolution-v1":
        expected_task_ids = PILOT_TASK_IDS
        expected_trials = 3
        expected_seed = 20260714
        expected_agents = 2
        expected_budget = {
            "total_cny": 10.0,
            "per_agent_cny": 5.0,
            "per_trial_cny": 0.1,
        }
    elif protocol_version == "phase3-training-v1":
        expected_task_ids = PHASE3_TRAINING_TASK_IDS
        expected_trials = 1
        expected_seed = 20260715
        expected_agents = 1
        expected_budget = {
            "total_cny": 1.0,
            "per_agent_cny": 1.0,
            "per_trial_cny": 0.1,
        }
    elif protocol_version == "phase3-training-v2":
        expected_task_ids = PHASE3_TRAINING_HARD_TASK_IDS
        expected_trials = 1
        expected_seed = 20260716
        expected_agents = 1
        expected_budget = {
            "total_cny": 0.9,
            "per_agent_cny": 0.9,
            "per_trial_cny": 0.1,
        }
    else:
        errors.append(
            "protocol_version must equal 'pilot-v1', 'phase2-diagnostic-v1', "
            "'phase2-diagnostic-v2', 'phase2-diagnostic-v3', 'phase3-evolution-v1', "
            "'phase3-training-v1', or 'phase3-training-v2'"
        )
        expected_task_ids = PILOT_TASK_IDS
        expected_trials = 3
        expected_seed = 20260712
        expected_agents = 2
        expected_budget = {
            "total_cny": 10.0,
            "per_agent_cny": 5.0,
            "per_trial_cny": 0.1,
        }

    _require_equal(errors, manifest, "benchmark", "humaneval")
    _require_equal(errors, manifest, "task_ids", expected_task_ids)
    _require_equal(errors, manifest, "n_trials", expected_trials)
    _require_equal(errors, manifest, "seed", expected_seed)

    agents = manifest.get("agents")
    if not isinstance(agents, list) or len(agents) != expected_agents:
        errors.append(f"agents must contain exactly {expected_agents} entries")
    else:
        for index, agent in enumerate(agents):
            _validate_agent(errors, agent, index, root)
        if protocol_version == "phase3-evolution-v1":
            _validate_phase3_roles(errors, agents)

    _validate_file(errors, manifest.get("dataset"), "source_path", "source_sha256", root)
    _validate_file(errors, manifest.get("dataset"), "task_path", "task_sha256", root)
    _validate_file(errors, manifest.get("dependencies"), "lockfile", "lockfile_sha256", root)

    commit = manifest.get("codepulse_commit")
    if not isinstance(commit, str) or COMMIT_PATTERN.fullmatch(commit) is None:
        errors.append("codepulse_commit must be a full 40-character Git SHA")

    environment = manifest.get("environment")
    expected_environment = {
        "cpus": 2,
        "memory_mb": 2048,
        "network": "none",
        "timeout_seconds": 300,
    }
    if not isinstance(environment, dict):
        errors.append("environment must be an object")
    else:
        for key, expected in expected_environment.items():
            _require_equal(errors, environment, key, expected, prefix="environment.")
        image_digest = environment.get("image_digest")
        if not isinstance(image_digest, str) or not image_digest.startswith("sha256:"):
            errors.append("environment.image_digest must be pinned by sha256 digest")

    budget = manifest.get("budget")
    if not isinstance(budget, dict):
        errors.append("budget must be an object")
    else:
        for key, expected in expected_budget.items():
            _require_equal(errors, budget, key, expected, prefix="budget.")

    pricing = manifest.get("pricing")
    expected_pricing: dict[str, object] = {
        "currency": "CNY",
        "unit_tokens": 1_000_000,
        "schedule_status": "pending_official_schedule",
        "off_peak": V4_FLASH_PRICING_CNY["off_peak"],
        "peak": V4_FLASH_PRICING_CNY["peak"],
        "budget_tier": "peak",
    }
    if not isinstance(pricing, dict):
        errors.append("pricing must be an object")
    else:
        for key, expected in expected_pricing.items():
            _require_equal(errors, pricing, key, expected, prefix="pricing.")

    return errors


def sha256_file(path: str | Path) -> str:
    """Return a file's SHA-256 digest."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_agent(errors: list[str], agent: object, index: int, root: Path) -> None:
    prefix = f"agents[{index}]"
    if not isinstance(agent, dict):
        errors.append(f"{prefix} must be an object")
        return
    for field_name in ("name", "provider", "model_version", "provider_model_version"):
        if not isinstance(agent.get(field_name), str) or not agent[field_name].strip():
            errors.append(f"{prefix}.{field_name} is required")
    model_version = agent.get("model_version")
    if isinstance(model_version, str) and model_version.lower() in MUTABLE_MODEL_NAMES:
        errors.append(f"{prefix}.model_version must be immutable, got {model_version!r}")
    _validate_file(errors, agent, "profile_path", "profile_sha256", root, prefix=f"{prefix}.")


def _validate_phase3_roles(errors: list[str], agents: list[object]) -> None:
    """Require an explicitly paired, same-model Phase 3 comparison."""
    if not all(isinstance(agent, dict) for agent in agents):
        return
    typed_agents = [agent for agent in agents if isinstance(agent, dict)]
    roles = {agent.get("role") for agent in typed_agents}
    if roles != {"baseline", "candidate"}:
        errors.append("phase3 agents must contain one baseline and one candidate role")
    model_versions = {agent.get("model_version") for agent in typed_agents}
    if len(model_versions) != 1:
        errors.append("phase3 baseline and candidate must use the same model_version")


def _validate_file(
    errors: list[str],
    section: object,
    path_key: str,
    digest_key: str,
    root: Path,
    *,
    prefix: str = "",
) -> None:
    if not isinstance(section, dict):
        errors.append(f"{prefix or path_key.removesuffix('_path')} must be an object")
        return
    raw_path = section.get(path_key)
    expected_digest = section.get(digest_key)
    if not isinstance(raw_path, str) or not raw_path:
        errors.append(f"{prefix}{path_key} is required")
        return
    if not isinstance(expected_digest, str) or SHA256_PATTERN.fullmatch(expected_digest) is None:
        errors.append(f"{prefix}{digest_key} must be a SHA-256 hex digest")
        return
    file_path = root / raw_path
    if not file_path.is_file():
        errors.append(f"{prefix}{path_key} does not exist: {raw_path}")
        return
    actual_digest = sha256_file(file_path)
    if actual_digest != expected_digest:
        errors.append(f"{prefix}{digest_key} mismatch for {raw_path}")


def _require_equal(
    errors: list[str],
    data: dict[str, Any],
    key: str,
    expected: object,
    *,
    prefix: str = "",
) -> None:
    if data.get(key) != expected:
        errors.append(f"{prefix}{key} must equal {expected!r}")
