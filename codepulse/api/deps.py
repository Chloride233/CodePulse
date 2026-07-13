"""Shared dependencies for the API — result directory loading utilities."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import Query, Request

logger = logging.getLogger(__name__)


class _TTLCache:
    """Simple TTL-based in-memory cache."""

    def __init__(self, ttl_seconds: int = 5):
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any:
        entry = self._data.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self._ttl:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._data[key] = (time.time(), value)

    def invalidate(self) -> None:
        self._data.clear()


_cache = _TTLCache()


def get_results_dir(
    request: Request,
    results_dir: str | None = Query(
        None,
        description="Override the default results directory path",
    ),
) -> Path:
    """FastAPI dependency — resolve the results directory.

    If the ``results_dir`` query parameter is provided it takes precedence.
    Otherwise the value from ``request.app.state.results_dir`` is used
    (set by :func:`~codepulse.api.main.create_app`).

    Returns:
        The resolved results directory path.
    """
    if results_dir:
        return Path(results_dir)
    raw: str = getattr(request.app.state, "results_dir", "results")
    return Path(raw)


def load_all_summaries(results_dir: Path | None = None) -> dict[str, Any]:
    """Load all summary.json files from results directory."""
    base = results_dir or Path("results")
    if not base.exists():
        return {}
    cache_key = f"summaries:{base}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    results: dict[str, Any] = {}
    for summary_path in sorted(base.rglob("summary.json")):
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        task_id = data.get("task_id", summary_path.parent.name)
        results[task_id] = data
    _cache.set(cache_key, results)
    return results


def load_task_trials(results_dir: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Load all trial JSON/JSONL files grouped by task_id."""
    base = results_dir or Path("results")
    if not base.exists():
        return {}
    cache_key = f"trials:{base}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    trials: dict[str, list[dict[str, Any]]] = {}

    def append_trial(data: object) -> None:
        if not isinstance(data, dict):
            return
        trial_id = data.get("trial_id")
        task_id = data.get("task_id")
        if not isinstance(trial_id, str) or not isinstance(task_id, str):
            return
        trials.setdefault(task_id, []).append(data)

    trial_files = sorted(base.rglob("*.json")) + sorted(base.rglob("*.jsonl"))
    for trial_path in trial_files:
        if trial_path.name == "summary.json":
            continue
        if "-trace.jsonl" in trial_path.name or "-trace.json" in trial_path.name:
            continue
        try:
            raw = trial_path.read_text(encoding="utf-8").strip()
            if not raw:
                continue
            if trial_path.suffix == ".json":
                append_trial(json.loads(raw))
            else:
                for line in raw.splitlines():
                    if line.strip():
                        append_trial(json.loads(line))
        except (json.JSONDecodeError, OSError):
            continue

    _cache.set(cache_key, trials)
    return trials


def load_trace_events(trace_path: Path) -> list[dict[str, Any]]:
    """Load trace events from a trace JSONL file.

    Returns:
        List of trace event dicts.
    """
    if not trace_path.exists():
        return []

    events: list[dict[str, Any]] = []
    try:
        lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
        for line in lines:
            if line.strip():
                events.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        logger.warning("无法读取 trace 文件: %s", trace_path)

    return events


def find_trace_files(results_dir: Path | None = None) -> dict[str, Path]:
    """Find all trace JSONL files.

    Returns:
        Mapping of session_id to trace file path.
    """
    base = results_dir or Path("results")
    if not base.exists():
        return {}

    traces: dict[str, Path] = {}
    for trace_path in sorted(base.rglob("*-trace.jsonl")):
        # Extract session_id from filename: trial-{session_id}-trace.jsonl
        name = trace_path.stem  # trial-{id}-trace
        session_id = name.replace("trial-", "").replace("-trace", "")
        traces[session_id] = trace_path

    return traces
