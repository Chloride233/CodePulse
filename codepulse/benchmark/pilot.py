"""Deterministic preflight validation for the Phase 1 benchmark pilot."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PILOT_TASK_IDS = [f"HumanEval/{task_id}" for task_id in range(20)]
MUTABLE_MODEL_NAMES = {"latest", "deepseek-chat", "deepseek/deepseek-chat"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
INFRA_FAILURES = {"provider_error", "agent_error", "sandbox_error"}


@dataclass
class PilotBudgetGuard:
    """Track pilot cost and infrastructure stop conditions across trials."""

    planned_trials: int = 120
    total_limit_usd: float = 20.0
    per_agent_limit_usd: float = 10.0
    per_trial_limit_usd: float = 0.2
    total_cost_usd: float = 0.0
    completed_trials: int = 0
    infrastructure_failures: int = 0
    consecutive_infrastructure_failures: int = 0
    agent_costs_usd: dict[str, float] = field(default_factory=dict)

    def record_trial(
        self,
        agent_name: str,
        cost_usd: float | None,
        failure_type: str | None = None,
    ) -> list[str]:
        """Record one trial and return every triggered stop reason."""
        self.completed_trials += 1
        reasons: list[str] = []

        if cost_usd is None:
            reasons.append("cost_unavailable")
        elif cost_usd < 0:
            reasons.append("cost_invalid")
        else:
            self.total_cost_usd += cost_usd
            agent_total = self.agent_costs_usd.get(agent_name, 0.0) + cost_usd
            self.agent_costs_usd[agent_name] = agent_total
            if cost_usd >= self.per_trial_limit_usd:
                reasons.append("per_trial_budget_reached")
            if agent_total >= self.per_agent_limit_usd:
                reasons.append("per_agent_budget_reached")
            if self.total_cost_usd >= self.total_limit_usd:
                reasons.append("total_budget_reached")
            projected_cost = self.total_cost_usd / self.completed_trials * self.planned_trials
            if projected_cost > self.total_limit_usd:
                reasons.append("projected_budget_exceeded")

        if failure_type in INFRA_FAILURES:
            self.infrastructure_failures += 1
            self.consecutive_infrastructure_failures += 1
        else:
            self.consecutive_infrastructure_failures = 0
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

    _require_equal(errors, manifest, "protocol_version", "pilot-v1")
    _require_equal(errors, manifest, "benchmark", "humaneval")
    _require_equal(errors, manifest, "task_ids", PILOT_TASK_IDS)
    _require_equal(errors, manifest, "n_trials", 3)
    _require_equal(errors, manifest, "seed", 20260712)

    agents = manifest.get("agents")
    if not isinstance(agents, list) or len(agents) != 2:
        errors.append("agents must contain exactly two entries")
    else:
        for index, agent in enumerate(agents):
            _validate_agent(errors, agent, index, root)

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
    expected_budget = {"total_usd": 20.0, "per_agent_usd": 10.0, "per_trial_usd": 0.2}
    if not isinstance(budget, dict):
        errors.append("budget must be an object")
    else:
        for key, expected in expected_budget.items():
            _require_equal(errors, budget, key, expected, prefix="budget.")

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
