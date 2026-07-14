"""Generate reproducible Markdown and HTML reports from pilot Trial JSONL."""

from __future__ import annotations

import html
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from codepulse.eval.comparison import align_exact
from codepulse.evolve.attribution import SampleAttribution
from codepulse.evolve.gate import ValidationGate


def _nearest_rank(values: list[float], quantile: float) -> float:
    return values[math.ceil(quantile * len(values)) - 1]


def summarize_pilot(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate protocol metrics for each Agent."""
    summaries: list[dict[str, Any]] = []
    for agent in sorted({row["agent_name"] for row in rows}):
        agent_rows = [row for row in rows if row["agent_name"] == agent]
        by_task: dict[str, list[bool]] = defaultdict(list)
        for row in agent_rows:
            by_task[row["task_id"]].append(bool(row["success"]))
        durations = sorted(row["metrics"]["duration_seconds"] for row in agent_rows)
        failures = Counter(
            row["failure_type"] or ("success" if row["success"] else "wrong_answer")
            for row in agent_rows
        )
        total_tokens = sum(row["metrics"]["total_tokens"] for row in agent_rows)
        summaries.append(
            {
                "agent": agent,
                "trials": len(agent_rows),
                "pass_at_1": sum(row["success"] for row in agent_rows) / len(agent_rows),
                "pass_at_3": sum(any(values) for values in by_task.values()) / len(by_task),
                "pass_hat_3": sum(all(values) for values in by_task.values()) / len(by_task),
                "avg_tokens": total_tokens / len(agent_rows),
                "total_tokens": total_tokens,
                "cost_cny_off_peak": sum(
                    row["metrics"]["cost_cny_off_peak"] for row in agent_rows
                ),
                "cost_cny_peak": sum(
                    row["metrics"]["cost_cny_peak"] for row in agent_rows
                ),
                "p50_seconds": _nearest_rank(durations, 0.5),
                "p95_seconds": _nearest_rank(durations, 0.95),
                "failures": dict(failures),
            }
        )
    return summaries


def compare_phase3_pilot(
    rows: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Compare the frozen Phase 3 baseline and candidate trial-by-trial.

    The comparison is only valid when both roles have exactly one result for each
    task and repetition. It returns observed metrics and candidate-minus-baseline
    deltas; it does not interpret those deltas as an improvement claim.
    """
    if manifest.get("protocol_version") != "phase3-evolution-v1":
        raise ValueError("Phase 3 comparison requires a phase3-evolution-v1 manifest")

    role_names = _phase3_role_names(manifest)
    expected_agents = set(role_names.values())
    actual_agents = {row.get("agent_name") for row in rows}
    if actual_agents != expected_agents:
        raise ValueError("Phase 3 rows must contain exactly the frozen baseline and candidate")

    baseline_rows = [row for row in rows if row["agent_name"] == role_names["baseline"]]
    candidate_rows = [row for row in rows if row["agent_name"] == role_names["candidate"]]
    align_exact(
        baseline_rows,
        candidate_rows,
        left_key=_trial_key,
        right_key=_trial_key,
        left_name="baseline",
        right_name="candidate",
    )
    actual_keys = {_trial_key(row) for row in baseline_rows}
    if actual_keys != _phase3_expected_keys(manifest):
        raise ValueError("Phase 3 trial coverage does not match the frozen task set")

    summaries = {summary["agent"]: summary for summary in summarize_pilot(rows)}
    baseline = _phase3_metrics(summaries[role_names["baseline"]])
    candidate = _phase3_metrics(summaries[role_names["candidate"]])
    deltas = {key: candidate[key] - baseline[key] for key in baseline}
    return {
        "k": manifest["n_trials"],
        "baseline": baseline,
        "candidate": candidate,
        "deltas": deltas,
    }


def classify_phase3_pilot(
    rows: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Classify each frozen task from its baseline and candidate pass^3 state."""
    compare_phase3_pilot(rows, manifest)
    role_names = _phase3_role_names(manifest)
    baseline_states = _task_pass_hat_states(rows, role_names["baseline"])
    candidate_states = _task_pass_hat_states(rows, role_names["candidate"])
    attribution = SampleAttribution()
    by_task = attribution.classify_all_states(baseline_states, candidate_states)
    summary = attribution.report(by_task)
    return {
        "by_task": {task_id: category.value for task_id, category in by_task.items()},
        "summary": {
            "improvements": summary.improvements,
            "regressions": summary.regressions,
            "persistent_failures": summary.persistent_failures,
            "stable_successes": summary.stable_successes,
            "improvement_rate": summary.improvement_rate,
            "regression_rate": summary.regression_rate,
            "total": summary.total,
        },
    }


def validate_phase3_pilot(
    rows: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Apply the Validation Gate to frozen Phase 3 Trial records."""
    try:
        comparison = compare_phase3_pilot(rows, manifest)
        attribution = classify_phase3_pilot(rows, manifest)
    except ValueError as exc:
        return {
            "accepted": False,
            "rejection_reasons": ["invalid_trial_coverage"],
            "detail": str(exc),
        }

    role_names = _phase3_role_names(manifest)
    candidate_peak_costs = [
        float(row["metrics"]["cost_cny_peak"])
        for row in rows
        if row["agent_name"] == role_names["candidate"]
    ]
    budget = manifest.get("budget")
    if not isinstance(budget, dict):
        return {
            "accepted": False,
            "rejection_reasons": ["invalid_budget"],
        }
    return ValidationGate.validate_phase3(
        comparison,
        attribution,
        candidate_peak_costs,
        budget,
    )


def _phase3_role_names(manifest: dict[str, Any]) -> dict[str, str]:
    agents = manifest.get("agents")
    if not isinstance(agents, list):
        raise ValueError("Phase 3 manifest agents must be a list")
    role_names: dict[str, str] = {}
    for agent in agents:
        if not isinstance(agent, dict):
            raise ValueError("Phase 3 manifest agents must be objects")
        role = agent.get("role")
        name = agent.get("name")
        if not isinstance(role, str) or not isinstance(name, str):
            raise ValueError("Phase 3 manifest agents require role and name")
        if role in role_names:
            raise ValueError(f"Phase 3 manifest has duplicate {role!r} role")
        role_names[role] = name
    if set(role_names) != {"baseline", "candidate"}:
        raise ValueError("Phase 3 manifest requires baseline and candidate roles")
    return role_names


def _trial_key(row: dict[str, Any]) -> tuple[str, int]:
    task_id = row.get("task_id")
    repetition = row.get("repetition")
    if not isinstance(task_id, str) or not isinstance(repetition, int):
        raise ValueError("Phase 3 rows require string task_id and integer repetition")
    return task_id, repetition


def _phase3_expected_keys(manifest: dict[str, Any]) -> set[tuple[str, int]]:
    task_ids = manifest.get("task_ids")
    n_trials = manifest.get("n_trials")
    if not isinstance(task_ids, list) or not all(isinstance(task_id, str) for task_id in task_ids):
        raise ValueError("Phase 3 manifest task_ids must be a list of strings")
    if n_trials != 3:
        raise ValueError("phase3-evolution-v1 requires exactly three trials per task")
    return {(task_id, repetition) for task_id in task_ids for repetition in range(n_trials)}


def _task_pass_hat_states(rows: list[dict[str, Any]], agent_name: str) -> dict[str, bool]:
    by_task: dict[str, list[bool]] = defaultdict(list)
    for row in rows:
        if row["agent_name"] == agent_name:
            by_task[row["task_id"]].append(bool(row["success"]))
    return {task_id: all(successes) for task_id, successes in by_task.items()}


def _phase3_metrics(summary: dict[str, Any]) -> dict[str, float]:
    return {
        "success_rate": float(summary["pass_at_1"]),
        "pass_at_k": float(summary["pass_at_3"]),
        "pass_hat_k": float(summary["pass_hat_3"]),
        "avg_tokens": float(summary["avg_tokens"]),
        "total_tokens": float(summary["total_tokens"]),
        "cost_cny_off_peak": float(summary["cost_cny_off_peak"]),
        "cost_cny_peak": float(summary["cost_cny_peak"]),
        "p50_seconds": float(summary["p50_seconds"]),
        "p95_seconds": float(summary["p95_seconds"]),
    }


def write_pilot_reports(run_dir: str | Path) -> list[dict[str, Any]]:
    """Write report.md and report.html beside a run's trials.jsonl."""
    directory = Path(run_dir)
    rows = [
        json.loads(line)
        for line in (directory / "trials.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summaries = summarize_pilot(rows)
    header = "| Agent | pass@1 | pass@3 | pass^3 | Avg tokens | Cost CNY (off/peak) | P50/P95 | Failures |"
    divider = "|---|---:|---:|---:|---:|---:|---:|---|"
    table_rows = [
        "| {agent} | {pass_at_1:.1%} | {pass_at_3:.1%} | {pass_hat_3:.1%} | "
        "{avg_tokens:.1f} | {cost_cny_off_peak:.6f}/{cost_cny_peak:.6f} | "
        "{p50_seconds:.3f}s/{p95_seconds:.3f}s | {failures} |".format(**summary)
        for summary in summaries
    ]
    markdown = "\n".join(
        [
            "# CodePulse Pilot V1 Report",
            "",
            f"Trials: {len(rows)} | Model versions: {sorted({v for row in rows for v in row['provider_model_versions']})}",
            "",
            header,
            divider,
            *table_rows,
            "",
            "Pricing schedule is pending; costs are reported as off-peak/peak bounds.",
        ]
    )
    (directory / "report.md").write_text(markdown + "\n", encoding="utf-8")
    (directory / "report.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>CodePulse Pilot V1</title>"
        "<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;line-height:1.5}"
        "pre{white-space:pre-wrap}</style><pre>"
        + html.escape(markdown)
        + "</pre>",
        encoding="utf-8",
    )
    return summaries


def write_phase3_reports(run_dir: str | Path, manifest: dict[str, Any]) -> tuple[Path, Path]:
    """Write the Phase 3 paired comparison report from complete frozen Trial records."""
    directory = Path(run_dir)
    rows = [
        json.loads(line)
        for line in (directory / "trials.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    comparison = compare_phase3_pilot(rows, manifest)
    attribution = classify_phase3_pilot(rows, manifest)
    gate = validate_phase3_pilot(rows, manifest)
    markdown = _render_phase3_report(rows, manifest, comparison, attribution, gate)
    markdown_path = directory / "phase3-report.md"
    html_path = directory / "phase3-report.html"
    markdown_path.write_text(markdown + "\n", encoding="utf-8")
    html_path.write_text(
        "<!doctype html><meta charset='utf-8'><title>CodePulse Phase 3</title>"
        "<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;line-height:1.5}"
        "pre{white-space:pre-wrap}</style><pre>"
        + html.escape(markdown)
        + "</pre>",
        encoding="utf-8",
    )
    return markdown_path, html_path


def _render_phase3_report(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    comparison: dict[str, Any],
    attribution: dict[str, Any],
    gate: dict[str, Any],
) -> str:
    metric_keys = [
        "success_rate",
        "pass_at_k",
        "pass_hat_k",
        "avg_tokens",
        "total_tokens",
        "cost_cny_off_peak",
        "cost_cny_peak",
        "p50_seconds",
        "p95_seconds",
    ]
    metric_rows = [
        "| {key} | {baseline} | {candidate} | {delta} |".format(
            key=key,
            baseline=_format_phase3_metric(key, comparison["baseline"][key]),
            candidate=_format_phase3_metric(key, comparison["candidate"][key]),
            delta=_format_phase3_metric(key, comparison["deltas"][key], signed=True),
        )
        for key in metric_keys
    ]
    role_names = _phase3_role_names(manifest)
    cases = _phase3_typical_cases(rows, attribution["by_task"], role_names)
    case_rows = [
        f"| {category} | {task_id} | {baseline} | {candidate} |"
        for category, task_id, baseline, candidate in cases
    ] or ["| none | - | - | - |"]
    reasons = ", ".join(gate["rejection_reasons"]) or "none"
    return "\n".join(
        [
            "# CodePulse Phase 3 Comparison Report",
            "",
            "Status: generated from supplied Trial records; this report does not itself prove a real-model benefit.",
            f"Protocol: `{manifest['protocol_version']}` | Trials: {len(rows)} | k: {comparison['k']}",
            "",
            "## Metric Comparison",
            "",
            "| Metric | Baseline | Candidate | Candidate - Baseline |",
            "|---|---:|---:|---:|",
            *metric_rows,
            "",
            "## Attribution",
            "",
            "| Improvements | Regressions | Persistent failures | Stable successes |",
            "|---:|---:|---:|---:|",
            "| {improvements} | {regressions} | {persistent_failures} | {stable_successes} |".format(
                **attribution["summary"]
            ),
            "",
            "## Validation Gate",
            "",
            f"Accepted: `{gate['accepted']}` | Rejection reasons: `{reasons}`",
            "",
            "## Typical Cases",
            "",
            "| Attribution | Task | Baseline trials | Candidate trials |",
            "|---|---|---|---|",
            *case_rows,
            "",
            "## Reproduce",
            "",
            "```bash",
            "codepulse benchmark preflight --manifest experiments/phase3-evolution-v1/manifest.json",
            "codepulse benchmark pilot-run --manifest experiments/phase3-evolution-v1/manifest.json --output-dir results/phase3/evolution-v1 --capture-evidence",
            "codepulse benchmark phase3-report --manifest experiments/phase3-evolution-v1/manifest.json --run-dir results/phase3/evolution-v1",
            "```",
        ]
    )


def _format_phase3_metric(key: str, value: float, *, signed: bool = False) -> str:
    sign = "+" if signed and value >= 0 else ""
    if key in {"success_rate", "pass_at_k", "pass_hat_k"}:
        return f"{sign}{value:.1%}"
    if "cost" in key:
        return f"{sign}{value:.6f} CNY"
    if key.endswith("seconds"):
        return f"{sign}{value:.3f} s"
    return f"{sign}{value:.1f}"


def _phase3_typical_cases(
    rows: list[dict[str, Any]],
    by_task: dict[str, str],
    role_names: dict[str, str],
) -> list[tuple[str, str, str, str]]:
    cases: list[tuple[str, str, str, str]] = []
    for category in ("improvement", "regression", "persistent_failure", "stable_success"):
        task_id = next((task for task, value in by_task.items() if value == category), None)
        if task_id is None:
            continue
        baseline = _task_trial_statuses(rows, role_names["baseline"], task_id)
        candidate = _task_trial_statuses(rows, role_names["candidate"], task_id)
        cases.append((category, task_id, baseline, candidate))
    return cases


def _task_trial_statuses(rows: list[dict[str, Any]], agent_name: str, task_id: str) -> str:
    statuses = [
        "pass" if row["success"] else "fail"
        for row in sorted(rows, key=lambda row: _trial_key(row))
        if row["agent_name"] == agent_name and row["task_id"] == task_id
    ]
    return ", ".join(statuses)
