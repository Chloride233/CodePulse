"""Pydantic response schemas for the CodePulse API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TrialMetricsResponse(BaseModel):
    """Token and performance metrics for a single trial."""

    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    total_duration: float = 0.0
    tool_call_count: int = 0
    self_correction_count: int = 0
    cost_usd: float = 0.0


class AgentConfigResponse(BaseModel):
    """Agent configuration summary."""

    name: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096


# ---------------------------------------------------------------------------
# Trial
# ---------------------------------------------------------------------------


class TrialResponse(BaseModel):
    """Single trial result."""

    trial_id: str
    task_id: str
    agent_config: AgentConfigResponse
    outcome: dict[str, Any] = {}
    scores: dict[str, float] = {}
    metrics: TrialMetricsResponse
    success: bool = False
    total_score: float = 0.0


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class TaskResponse(BaseModel):
    """Task summary for list views."""

    task_id: str
    source: str
    category: str
    difficulty: str
    language: str
    n_trials: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0


class TaskDetailResponse(TaskResponse):
    """Full task detail with trials."""

    trials: list[TrialResponse] = []


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------


class TraceEventResponse(BaseModel):
    """Single trace event."""

    timestamp: float
    event_type: str
    content: dict[str, Any] = {}
    token_usage: dict[str, int] = {}
    duration: float = 0.0


class TraceSessionResponse(BaseModel):
    """Full trace session with events."""

    session_id: str
    agent_config: dict[str, Any] = {}
    events: list[TraceEventResponse] = []
    total_tokens: int = 0
    total_duration: float = 0.0
    tool_call_count: int = 0


# ---------------------------------------------------------------------------
# Blackhole
# ---------------------------------------------------------------------------


class BlackholeDetectionResponse(BaseModel):
    """Token blackhole detection result."""

    blackhole_type: str
    details: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


class AgentSummary(BaseModel):
    """Agent summary for overview."""

    name: str
    model: str
    pass_rate: float = 0.0
    avg_tokens: float = 0.0


class OverviewResponse(BaseModel):
    """Dashboard overview metrics."""

    total_tasks: int = 0
    total_trials: int = 0
    overall_pass_rate: float = 0.0
    avg_score: float = 0.0
    total_cost_usd: float = 0.0
    dimension_scores: dict[str, float] = {}
    recent_scores: list[dict[str, Any]] = []
    active_agents: list[AgentSummary] = []


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


class AgentComparisonItem(BaseModel):
    """Single agent in a comparison."""

    agent_name: str
    n_success: int = 0
    n_total: int = 0
    pass_at_1: float = 0.0
    pass_at_k: float = 0.0
    pass_hat_k: float = 0.0
    avg_tokens: float = 0.0
    avg_duration: float = 0.0
    avg_cost: float = 0.0
    self_correction_rate: float = 0.0


class CompareResponse(BaseModel):
    """Multi-agent comparison result."""

    agents: list[AgentComparisonItem] = []


# ---------------------------------------------------------------------------
# Evolution
# ---------------------------------------------------------------------------


class EvolutionEpochResponse(BaseModel):
    """Single epoch in an evolution run."""

    epoch: int
    baseline_score: float = 0.0
    candidate_score: float = 0.0
    improved: bool = False
    improvements: int = 0
    regressions: int = 0
    persistent_failures: int = 0
    stable_successes: int = 0
    edits_applied: int = 0
    edits_rejected: int = 0


class EvolutionResponse(BaseModel):
    """Full evolution run with all epochs."""

    epochs: list[EvolutionEpochResponse] = []
