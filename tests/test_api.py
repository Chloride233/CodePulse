"""Tests for the CodePulse FastAPI application.

Covers the main app creation, health endpoint, and all router endpoints
using FastAPI's TestClient with a temporary results directory.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from codepulse.api.deps import load_task_trials
from codepulse.api.main import create_app

if TYPE_CHECKING:
    from pathlib import Path


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def results_dir(tmp_path: Path) -> Path:
    """Create a temporary results directory with sample data."""
    base = tmp_path / "results"
    base.mkdir()

    # Task 1: summary + 2 trials
    task1_dir = base / "task-001"
    task1_dir.mkdir()

    summary1 = {
        "task_id": "task-001",
        "source": "custom",
        "category": "bug_fix",
        "difficulty": "easy",
        "language": "python",
        "suite_type": "regression",
        "baseline_id": "base-v1",
        "avg_cost_usd": 0.015,
        "failure_types": ["functional_weakness"],
    }
    (task1_dir / "summary.json").write_text(json.dumps(summary1))

    trial1 = {
        "trial_id": "run-a",
        "task_id": "task-001",
        "agent_config": {"name": "agent-1", "model": "deepseek-chat"},
        "success": True,
        "scores": {"functional": 0.9, "process": 0.8},
        "metrics": {
            "total_tokens": 1000,
            "input_tokens": 600,
            "output_tokens": 400,
            "reasoning_tokens": 50,
            "tool_roundtrip_tokens": 120,
            "retry_count": 1,
            "cache_hit_tokens": 20,
            "total_duration": 5.0,
            "tool_call_count": 3,
            "self_correction_count": 0,
            "cost_usd": 0.01,
            "cost_breakdown": {"input_cost": 0.006, "output_cost": 0.004},
        },
        "tool_call_sequence": ["Read", "Write", "Bash"],
        "failure_analysis": [],
    }
    trial2 = {
        "trial_id": "run-b",
        "task_id": "task-001",
        "agent_config": {"name": "agent-1", "model": "deepseek-chat"},
        "success": False,
        "scores": {"functional": 0.4, "process": 0.6},
        "metrics": {
            "total_tokens": 2000,
            "input_tokens": 1200,
            "output_tokens": 800,
            "reasoning_tokens": 100,
            "tool_roundtrip_tokens": 200,
            "retry_count": 2,
            "cache_hit_tokens": 0,
            "total_duration": 10.0,
            "tool_call_count": 6,
            "self_correction_count": 2,
            "cost_usd": 0.02,
            "cost_breakdown": {"input_cost": 0.012, "output_cost": 0.008},
        },
        "tool_call_sequence": ["Read", "Write", "Bash", "Bash"],
        "failure_analysis": [
            {
                "stage": "verification",
                "failure_type": "functional_weakness",
                "evidence": ["pytest_pass_rate=1/3"],
                "suggested_action": "补强核心测试",
                "should_enter_regression": True,
            }
        ],
    }
    (task1_dir / "run-a.json").write_text(json.dumps(trial1))
    (task1_dir / "trial-run-b.jsonl").write_text(json.dumps(trial2) + "\n")

    # Trace for run-a (find_trace_files extracts session_id by stripping
    # "trial-" prefix and "-trace" suffix from the filename).
    trace_events = [
        {"timestamp": 1.0, "event_type": "llm_call", "content": {"model": "deepseek-chat"},
         "token_usage": {"input": 300, "output": 200}, "duration": 2.0, "span_kind": "llm"},
        {"timestamp": 2.0, "event_type": "tool_call", "content": {"tool_name": "Bash"},
         "token_usage": {}, "duration": 1.0, "span_kind": "tool"},
        {"timestamp": 3.0, "event_type": "tool_result", "content": {"output": "ok"},
         "token_usage": {}, "duration": 0.5, "span_kind": "artifact"},
    ]
    (task1_dir / "trial-run-a-trace.jsonl").write_text(
        "\n".join(json.dumps(e) for e in trace_events) + "\n"
    )

    # Evolution data
    evolution_data = {
        "epochs": [
            {
                "epoch": 0,
                "baseline_score": 70.0,
                "candidate_score": 72.0,
                "improved": True,
                "improvements": 3,
                "regressions": 0,
                "persistent_failures": 5,
                "stable_successes": 2,
                "edits_applied": 2,
                "edits_rejected": 1,
            },
        ],
    }
    (base / "evolution.json").write_text(json.dumps(evolution_data))

    return base


@pytest.fixture()
def client(results_dir: Path) -> TestClient:
    """Create a TestClient with the temporary results directory."""
    app = create_app(results_dir=results_dir)
    return TestClient(app)


@pytest.fixture()
def empty_client(tmp_path: Path) -> TestClient:
    """Create a TestClient with a non-existent results directory."""
    app = create_app(results_dir=tmp_path / "no-such-dir")
    return TestClient(app)


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for the /api/health endpoint."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        """Health endpoint should return status ok."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


# ------------------------------------------------------------------
# Overview
# ------------------------------------------------------------------


class TestOverviewEndpoint:
    """Tests for the /api/overview endpoint."""

    def test_overview_with_data(self, client: TestClient) -> None:
        """Overview should return aggregated metrics when data exists."""
        resp = client.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tasks"] == 1
        assert data["total_trials"] == 2
        assert data["overall_pass_rate"] == 0.5
        assert data["avg_score"] > 0
        assert len(data["active_agents"]) == 1
        assert data["active_agents"][0]["name"] == "agent-1"
        assert data["weakest_dimension"] is not None
        assert "task_id" in data["costliest_task"]
        assert isinstance(data["regression_risks"], list)

    def test_overview_empty_results(self, empty_client: TestClient) -> None:
        """Overview should return zeros when results dir is empty/missing."""
        resp = empty_client.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tasks"] == 0
        assert data["total_trials"] == 0
        assert data["overall_pass_rate"] == 0.0

    def test_overview_query_override(self, client: TestClient, tmp_path: Path) -> None:
        """Overview should allow overriding results_dir via query param."""
        # Point to an empty directory
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        resp = client.get("/api/overview", params={"results_dir": str(empty_dir)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tasks"] == 0


class TestDepsLoadTaskTrials:
    def test_loads_non_prefixed_json_trials(self, results_dir: Path) -> None:
        """Trial loader should accept JSON files that do not start with trial-."""
        trials = load_task_trials(results_dir)
        assert "task-001" in trials
        assert len(trials["task-001"]) == 2


# ------------------------------------------------------------------
# Evaluations (Tasks)
# ------------------------------------------------------------------


class TestTasksEndpoints:
    """Tests for the /api/tasks endpoints."""

    def test_list_tasks(self, client: TestClient) -> None:
        """List tasks should return all tasks."""
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == "task-001"
        assert tasks[0]["n_trials"] == 2
        assert tasks[0]["suite_type"] == "regression"

    def test_list_tasks_filter_by_source(self, client: TestClient) -> None:
        """List tasks should support source filter."""
        resp = client.get("/api/tasks", params={"source": "custom"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = client.get("/api/tasks", params={"source": "swe-bench"})
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_list_tasks_filter_by_difficulty(self, client: TestClient) -> None:
        """List tasks should support difficulty filter."""
        resp = client.get("/api/tasks", params={"difficulty": "easy"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_tasks_empty(self, empty_client: TestClient) -> None:
        """List tasks should return empty list when no data."""
        resp = empty_client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_task_detail(self, client: TestClient) -> None:
        """Get task detail should return full task with trials."""
        resp = client.get("/api/tasks/task-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-001"
        assert len(data["trials"]) == 2
        assert data["trials"][0]["trial_id"] == "run-a"
        assert data["trials"][0]["success"] is True
        assert data["baseline_id"] == "base-v1"

    def test_get_task_not_found(self, client: TestClient) -> None:
        """Get task detail should 404 for unknown task."""
        resp = client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404

    def test_get_trial_trace(self, client: TestClient) -> None:
        """Get trial trace should return trace events."""
        resp = client.get("/api/tasks/task-001/trials/run-a/trace")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 3
        assert events[0]["event_type"] == "llm_call"

    def test_get_trial_trace_not_found(self, client: TestClient) -> None:
        """Get trial trace should 404 for missing trace."""
        resp = client.get("/api/tasks/task-001/trials/nonexistent/trace")
        assert resp.status_code == 404

    def test_detect_blackholes(self, client: TestClient) -> None:
        """Blackhole detection should return results (may be empty)."""
        resp = client.get("/api/tasks/task-001/blackholes")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ------------------------------------------------------------------
# Compare
# ------------------------------------------------------------------


class TestCompareEndpoint:
    """Tests for the /api/compare endpoint."""

    def test_compare_agents(self, client: TestClient) -> None:
        """Compare should return agent comparison data."""
        resp = client.get("/api/compare")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 1
        agent = data["agents"][0]
        assert agent["agent_name"] == "agent-1"
        assert agent["n_total"] == 2
        assert agent["n_success"] == 1
        assert agent["pass_at_1"] == 0.5

    def test_compare_empty(self, empty_client: TestClient) -> None:
        """Compare should return empty agents list when no data."""
        resp = empty_client.get("/api/compare")
        assert resp.status_code == 200
        assert resp.json()["agents"] == []


# ------------------------------------------------------------------
# Traces
# ------------------------------------------------------------------


class TestTracesEndpoints:
    """Tests for the /api/traces endpoints."""

    def test_list_traces(self, client: TestClient) -> None:
        """List traces should return available trace sessions."""
        resp = client.get("/api/traces")
        assert resp.status_code == 200
        traces = resp.json()
        assert len(traces) == 1
        assert traces[0]["session_id"] == "run-a"
        assert traces[0]["n_events"] == 3
        assert "span_kinds" in traces[0]

    def test_list_traces_empty(self, empty_client: TestClient) -> None:
        """List traces should return empty list when no data."""
        resp = empty_client.get("/api/traces")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_trace_detail(self, client: TestClient) -> None:
        """Get trace detail should return full trace session."""
        resp = client.get("/api/traces/run-a")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "run-a"
        assert len(data["events"]) == 3
        assert data["total_tokens"] > 0
        assert data["tool_call_count"] == 1
        assert "span_kind" in data["events"][0]

    def test_get_trace_not_found(self, client: TestClient) -> None:
        """Get trace detail should 404 for unknown session."""
        resp = client.get("/api/traces/nonexistent")
        assert resp.status_code == 404


# ------------------------------------------------------------------
# Evolution
# ------------------------------------------------------------------


class TestEvolutionEndpoint:
    """Tests for the /api/evolution endpoint."""

    def test_evolution_with_data(self, client: TestClient) -> None:
        """Evolution should return epoch data when file exists."""
        resp = client.get("/api/evolution")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["epochs"]) == 1
        epoch = data["epochs"][0]
        assert epoch["epoch"] == 0
        assert epoch["baseline_score"] == 70.0
        assert epoch["improved"] is True

    def test_evolution_empty(self, empty_client: TestClient) -> None:
        """Evolution should return empty epochs when no data."""
        resp = empty_client.get("/api/evolution")
        assert resp.status_code == 200
        assert resp.json()["epochs"] == []


# ------------------------------------------------------------------
# App creation
# ------------------------------------------------------------------


class TestCreateApp:
    """Tests for the create_app factory function."""

    def test_default_results_dir(self) -> None:
        """create_app with no args should default to 'results'."""
        application = create_app()
        assert application.state.results_dir == "results"

    def test_custom_results_dir(self, tmp_path: Path) -> None:
        """create_app with explicit results_dir should use it."""
        custom = str(tmp_path / "custom")
        application = create_app(results_dir=custom)
        assert application.state.results_dir == custom

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """create_app should fall back to CODEPULSE_RESULTS_DIR env var."""
        monkeypatch.setenv("CODEPULSE_RESULTS_DIR", "/env/results")
        application = create_app()
        assert application.state.results_dir == "/env/results"

    def test_explicit_overrides_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Explicit results_dir should take precedence over env var."""
        monkeypatch.setenv("CODEPULSE_RESULTS_DIR", "/env/results")
        custom = str(tmp_path / "explicit")
        application = create_app(results_dir=custom)
        assert application.state.results_dir == custom
