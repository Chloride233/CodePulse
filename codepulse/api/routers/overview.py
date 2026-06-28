"""Overview dashboard endpoint — aggregate metrics across all tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends

from codepulse.api.deps import get_results_dir, load_all_summaries, load_task_trials
from codepulse.api.schemas import AgentSummary, OverviewResponse

if TYPE_CHECKING:
    from pathlib import Path

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    results_dir: Path = Depends(get_results_dir),
) -> OverviewResponse:
    """Return aggregated dashboard metrics.

    Scans all summary.json and trial files to compute:
    - Total tasks and trials
    - Overall pass rate and average score
    - Per-dimension average scores
    - Recent score trend (last 10 trials)
    - Active agents with their stats
    """
    base = results_dir
    summaries = load_all_summaries(base)
    all_trials = load_task_trials(base)

    total_tasks = len(summaries)
    total_trials = 0
    total_passed = 0
    total_score_sum = 0.0
    total_cost = 0.0
    dimension_sums: dict[str, float] = {}
    dimension_counts: dict[str, int] = {}
    recent: list[dict[str, Any]] = []
    agent_map: dict[str, dict[str, Any]] = {}

    _dim_weights: dict[str, int] = {
        "functional": 30, "process": 25, "efficiency": 15,
        "robustness": 20, "alignment": 10,
    }

    def _compute_total(scores: dict[str, float]) -> float:
        return sum(
            _dim_weights.get(dim_str, 0) * max(0.0, min(1.0, val))
            for dim_str, val in scores.items()
        )

    for task_id, trial_list in all_trials.items():
        for trial_data in trial_list:
            total_trials += 1
            success = trial_data.get("success", False)
            if success:
                total_passed += 1

            # Scores
            scores = trial_data.get("scores", {})
            for dim, score in scores.items():
                dimension_sums[dim] = dimension_sums.get(dim, 0.0) + score
                dimension_counts[dim] = dimension_counts.get(dim, 0) + 1

            # Metrics
            metrics = trial_data.get("metrics", {})
            cost = metrics.get("cost_usd", 0.0)
            total_cost += cost

            total_score = _compute_total(scores)
            total_score_sum += total_score

            # Recent scores (keep last 10)
            recent.append({
                "task_id": task_id,
                "trial_id": trial_data.get("trial_id", ""),
                "total_score": total_score,
                "success": success,
            })

            # Agent tracking
            agent_cfg = trial_data.get("agent_config", {})
            agent_name = agent_cfg.get("name", "unknown")
            agent_model = agent_cfg.get("model", "unknown")
            if agent_name not in agent_map:
                agent_map[agent_name] = {
                    "name": agent_name,
                    "model": agent_model,
                    "n_total": 0,
                    "n_passed": 0,
                    "total_tokens": 0,
                }
            agent_map[agent_name]["n_total"] += 1
            if success:
                agent_map[agent_name]["n_passed"] += 1
            agent_map[agent_name]["total_tokens"] += metrics.get("total_tokens", 0)

    # Compute averages
    overall_pass_rate = total_passed / total_trials if total_trials > 0 else 0.0
    avg_score = total_score_sum / total_trials if total_trials > 0 else 0.0

    dimension_scores = {}
    for dim, total in dimension_sums.items():
        count = dimension_counts.get(dim, 1)
        dimension_scores[dim] = round(total / count, 3)

    # Recent: last 10
    recent = recent[-10:]

    # Active agents
    active_agents = []
    for info in agent_map.values():
        n = info["n_total"]
        active_agents.append(AgentSummary(
            name=info["name"],
            model=info["model"],
            pass_rate=round(info["n_passed"] / n, 3) if n > 0 else 0.0,
            avg_tokens=round(info["total_tokens"] / n) if n > 0 else 0,
        ))

    return OverviewResponse(
        total_tasks=total_tasks,
        total_trials=total_trials,
        overall_pass_rate=round(overall_pass_rate, 3),
        avg_score=round(avg_score, 2),
        total_cost_usd=round(total_cost, 4),
        dimension_scores=dimension_scores,
        recent_scores=recent,
        active_agents=active_agents,
    )
