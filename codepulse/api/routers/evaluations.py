"""Evaluation endpoints — task list and detail views."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException

from codepulse.api.deps import (
    get_results_dir,
    load_all_summaries,
    load_task_trials,
    load_trace_events,
)
from codepulse.api.schemas import (
    AgentConfigResponse,
    BlackholeDetectionResponse,
    TaskDetailResponse,
    TaskResponse,
    TrialMetricsResponse,
    TrialResponse,
)

_dim_weights: dict[str, int] = {
    "functional": 30, "process": 25, "efficiency": 15,
    "robustness": 20, "alignment": 10,
}


def _compute_total_score(scores: dict[str, float]) -> float:
    """Convert dimension score dict to 0-100 total."""
    return sum(
        _dim_weights.get(dim_str, 0) * max(0.0, min(1.0, val))
        for dim_str, val in scores.items()
    )


def _trial_from_data(data: dict[str, Any]) -> TrialResponse:
    """Convert raw trial dict to TrialResponse."""
    agent_cfg = data.get("agent_config", {})
    metrics = data.get("metrics", {})
    scores = data.get("scores", {})

    return TrialResponse(
        trial_id=data.get("trial_id", ""),
        task_id=data.get("task_id", ""),
        agent_config=AgentConfigResponse(
            name=agent_cfg.get("name", "unknown"),
            model=agent_cfg.get("model", "unknown"),
            temperature=agent_cfg.get("temperature", 0.0),
            max_tokens=agent_cfg.get("max_tokens", 4096),
        ),
        outcome=data.get("outcome", {}),
        scores=scores,
        metrics=TrialMetricsResponse(
            total_tokens=metrics.get("total_tokens", 0),
            input_tokens=metrics.get("input_tokens", 0),
            output_tokens=metrics.get("output_tokens", 0),
            cache_tokens=metrics.get("cache_tokens", 0),
            reasoning_tokens=metrics.get("reasoning_tokens", 0),
            tool_roundtrip_tokens=metrics.get("tool_roundtrip_tokens", 0),
            retry_count=metrics.get("retry_count", 0),
            cache_hit_tokens=metrics.get("cache_hit_tokens", 0),
            total_duration=metrics.get("total_duration", 0.0),
            tool_call_count=metrics.get("tool_call_count", 0),
            self_correction_count=metrics.get("self_correction_count", 0),
            cost_usd=metrics.get("cost_usd", 0.0),
            cost_breakdown=metrics.get("cost_breakdown", {}),
        ),
        success=data.get("success", False),
        total_score=_compute_total_score(scores),
        tool_call_sequence=data.get("tool_call_sequence", []),
        failure_analysis=data.get("failure_analysis", []),
    )


if TYPE_CHECKING:
    from pathlib import Path

router = APIRouter(prefix="/api", tags=["evaluations"])


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    results_dir: Path = Depends(get_results_dir),
    source: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
) -> list[TaskResponse]:
    """List all evaluated tasks with summary stats."""
    base = results_dir
    summaries = load_all_summaries(base)
    all_trials = load_task_trials(base)

    tasks: list[TaskResponse] = []
    for task_id, summary in summaries.items():
        # Extract metadata from summary
        task_source = summary.get("source", "custom")
        task_category = summary.get("category", "bug_fix")
        task_difficulty = summary.get("difficulty", "medium")
        task_language = summary.get("language", "python")

        # Apply filters
        if source and task_source != source:
            continue
        if category and task_category != category:
            continue
        if difficulty and task_difficulty != difficulty:
            continue

        # Compute trial stats
        trial_list = all_trials.get(task_id, [])
        n_trials = len(trial_list)
        n_passed = sum(1 for t in trial_list if t.get("success", False))
        pass_rate = n_passed / n_trials if n_trials > 0 else 0.0

        # Average total score
        score_sum = 0.0
        for t in trial_list:
            score_sum += _compute_total_score(t.get("scores", {}))
        avg_score = score_sum / n_trials if n_trials > 0 else 0.0

        tasks.append(TaskResponse(
            task_id=task_id,
            source=task_source,
            category=task_category,
            difficulty=task_difficulty,
            language=task_language,
            suite_type=summary.get("suite_type", "capability"),
            baseline_id=summary.get("baseline_id"),
            n_trials=n_trials,
            pass_rate=round(pass_rate, 3),
            avg_score=round(avg_score, 2),
        ))

    return tasks


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
def get_task(
    task_id: str,
    results_dir: Path = Depends(get_results_dir),
) -> TaskDetailResponse:
    """Get full task detail including all trials."""
    base = results_dir
    summaries = load_all_summaries(base)
    all_trials = load_task_trials(base)

    if task_id not in summaries:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    summary = summaries[task_id]
    trial_list = all_trials.get(task_id, [])
    n_trials = len(trial_list)
    n_passed = sum(1 for t in trial_list if t.get("success", False))
    pass_rate = n_passed / n_trials if n_trials > 0 else 0.0

    score_sum = 0.0
    trials_response = []
    for t in trial_list:
        trial_resp = _trial_from_data(t)
        trials_response.append(trial_resp)
        score_sum += trial_resp.total_score

    avg_score = score_sum / n_trials if n_trials > 0 else 0.0

    return TaskDetailResponse(
        task_id=task_id,
        source=summary.get("source", "custom"),
        category=summary.get("category", "bug_fix"),
        difficulty=summary.get("difficulty", "medium"),
        language=summary.get("language", "python"),
        suite_type=summary.get("suite_type", "capability"),
        baseline_id=summary.get("baseline_id"),
        n_trials=n_trials,
        pass_rate=round(pass_rate, 3),
        avg_score=round(avg_score, 2),
        trials=trials_response,
    )


@router.get(
    "/tasks/{task_id}/trials/{trial_id}/trace",
    response_model=list[dict[str, Any]],
)
def get_trial_trace(
    task_id: str,
    trial_id: str,
    results_dir: Path = Depends(get_results_dir),
) -> list[dict[str, Any]]:
    """Get trace events for a specific trial."""
    base = results_dir
    trace_path = base / task_id / f"trial-{trial_id}-trace.jsonl"
    events = load_trace_events(trace_path)
    if not events:
        raise HTTPException(
            status_code=404,
            detail=f"Trace not found for task '{task_id}' trial '{trial_id}'",
        )
    return events


@router.get(
    "/tasks/{task_id}/blackholes",
    response_model=list[BlackholeDetectionResponse],
)
def detect_blackholes(
    task_id: str,
    results_dir: Path = Depends(get_results_dir),
) -> list[BlackholeDetectionResponse]:
    """Detect token blackhole patterns in task traces."""
    base = results_dir
    all_trials = load_task_trials(base)
    trial_list = all_trials.get(task_id, [])

    detections: list[BlackholeDetectionResponse] = []
    for trial_data in trial_list:
        trial_id = trial_data.get("trial_id", "")
        trace_path = base / task_id / f"trial-{trial_id}-trace.jsonl"
        events = load_trace_events(trace_path)
        if not events:
            continue

        # Detect loop patterns: Write+Bash repeated >= 3 times
        tool_sequence = [
            e.get("content", {}).get("tool_name", "")
            for e in events
            if e.get("event_type") == "tool_call"
        ]
        consecutive_pairs = 0
        for i in range(len(tool_sequence) - 1):
            if tool_sequence[i] == "Write" and tool_sequence[i + 1] == "Bash":
                consecutive_pairs += 1
        if consecutive_pairs >= 3:
            detections.append(BlackholeDetectionResponse(
                blackhole_type="loop_trial",
                details={
                    "trial_id": trial_id,
                    "consecutive_write_bash_pairs": consecutive_pairs,
                },
            ))

        # Detect context bloat: input_tokens growth rate > 2x
        llm_events = [e for e in events if e.get("event_type") == "llm_call"]
        if len(llm_events) >= 2:
            first_input = llm_events[0].get("token_usage", {}).get("input", 0)
            last_input = llm_events[-1].get("token_usage", {}).get("input", 0)
            if first_input > 0 and last_input / first_input > 2.0:
                detections.append(BlackholeDetectionResponse(
                    blackhole_type="context_bloat",
                    details={
                        "trial_id": trial_id,
                        "first_input_tokens": first_input,
                        "last_input_tokens": last_input,
                        "growth_rate": round(last_input / first_input, 2),
                    },
                ))

    return detections
