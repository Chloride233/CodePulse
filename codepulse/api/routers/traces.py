"""Trace endpoints — session-level trace viewing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException

from codepulse.api.deps import find_trace_files, get_results_dir, load_trace_events
from codepulse.api.schemas import TraceEventResponse, TraceSessionResponse

if TYPE_CHECKING:
    from pathlib import Path

router = APIRouter(prefix="/api", tags=["traces"])


@router.get("/traces", response_model=list[dict[str, Any]])
def list_traces(
    results_dir: Path = Depends(get_results_dir),
) -> list[dict[str, Any]]:
    """List all available trace sessions."""
    base = results_dir
    traces = find_trace_files(base)

    result = []
    for session_id, trace_path in traces.items():
        events = load_trace_events(trace_path)
        total_tokens = sum(
            sum(e.get("token_usage", {}).values()) for e in events
        )
        total_duration = sum(e.get("duration", 0.0) for e in events)
        tool_calls = sum(
            1 for e in events if e.get("event_type") == "tool_call"
        )
        result.append({
            "session_id": session_id,
            "n_events": len(events),
            "total_tokens": total_tokens,
            "total_duration": round(total_duration, 3),
            "tool_call_count": tool_calls,
            "span_kinds": sorted({
                str(e.get("span_kind"))
                for e in events
                if e.get("span_kind")
            }),
        })

    return result


@router.get("/traces/{session_id}", response_model=TraceSessionResponse)
def get_trace(
    session_id: str,
    results_dir: Path = Depends(get_results_dir),
) -> TraceSessionResponse:
    """Get full trace events for a session."""
    base = results_dir
    traces = find_trace_files(base)

    if session_id not in traces:
        raise HTTPException(
            status_code=404,
            detail=f"Trace session '{session_id}' not found",
        )

    events = load_trace_events(traces[session_id])

    event_responses = [
        TraceEventResponse(
            timestamp=e.get("timestamp", 0.0),
            event_type=e.get("event_type", "unknown"),
            content=e.get("content", {}),
            token_usage=e.get("token_usage", {}),
            duration=e.get("duration", 0.0),
            span_kind=e.get("span_kind"),
            parent_id=e.get("parent_id"),
            span_id=e.get("span_id"),
        )
        for e in events
    ]

    total_tokens = sum(
        sum(e.token_usage.values()) for e in event_responses
    )
    total_duration = sum(e.duration for e in event_responses)
    tool_calls = sum(
        1 for e in event_responses if e.event_type == "tool_call"
    )

    return TraceSessionResponse(
        session_id=session_id,
        events=event_responses,
        total_tokens=total_tokens,
        total_duration=round(total_duration, 3),
        tool_call_count=tool_calls,
    )
