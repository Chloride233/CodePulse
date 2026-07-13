"""Generate reproducible Markdown and HTML reports from pilot Trial JSONL."""

from __future__ import annotations

import html
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


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
