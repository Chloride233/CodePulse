"""Compare endpoint — multi-agent comparison."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends

from codepulse.api.deps import get_results_dir, load_task_trials
from codepulse.api.schemas import AgentComparisonItem, CompareResponse

if TYPE_CHECKING:
    from pathlib import Path

router = APIRouter(prefix="/api", tags=["compare"])


@router.get("/compare", response_model=CompareResponse)
def compare_agents(
    results_dir: Path = Depends(get_results_dir),
) -> CompareResponse:
    """Compare all agents across all tasks.

    Aggregates trial data by agent name to produce per-agent metrics.
    """
    base = results_dir
    all_trials = load_task_trials(base)

    # Aggregate by agent
    agents: dict[str, dict[str, Any]] = {}

    for _task_id, trial_list in all_trials.items():
        for trial_data in trial_list:
            agent_cfg = trial_data.get("agent_config", {})
            agent_name = agent_cfg.get("name", "unknown")
            metrics = trial_data.get("metrics", {})
            success = trial_data.get("success", False)

            if agent_name not in agents:
                agents[agent_name] = {
                    "agent_name": agent_name,
                    "n_success": 0,
                    "n_total": 0,
                    "total_tokens": 0,
                    "total_duration": 0.0,
                    "total_cost": 0.0,
                    "total_self_corrections": 0,
                }

            entry = agents[agent_name]
            entry["n_total"] += 1
            if success:
                entry["n_success"] += 1
            entry["total_tokens"] += metrics.get("total_tokens", 0)
            entry["total_duration"] += metrics.get("total_duration", 0.0)
            entry["total_cost"] += metrics.get("cost_usd", 0.0)
            entry["total_self_corrections"] += metrics.get("self_correction_count", 0)

    result: list[AgentComparisonItem] = []
    for info in agents.values():
        n = info["n_total"]
        if n == 0:
            continue

        # pass@k with k=1
        pass_at_1 = info["n_success"] / n
        # Simplified pass^k (stability) for k=1: same as pass@1
        pass_hat_k = pass_at_1
        # Self-correction rate
        sc_rate = info["total_self_corrections"] / n

        result.append(AgentComparisonItem(
            agent_name=info["agent_name"],
            n_success=info["n_success"],
            n_total=n,
            pass_at_1=round(pass_at_1, 3),
            pass_at_k=round(pass_at_1, 3),
            pass_hat_k=round(pass_hat_k, 3),
            avg_tokens=round(info["total_tokens"] / n),
            avg_duration=round(info["total_duration"] / n, 3),
            avg_cost=round(info["total_cost"] / n, 6),
            self_correction_rate=round(sc_rate, 3),
        ))

    # Sort by pass_at_1 descending
    result.sort(key=lambda x: x.pass_at_1, reverse=True)

    return CompareResponse(agents=result)
