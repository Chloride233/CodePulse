"""``codepulse baseline`` CLI commands.

Baseline management for tracking agent performance over time.
Supports LCS-based process alignment, output diff, and efficiency comparison.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import click

from codepulse.eval.scoring import sequence_similarity

BASELINE_DIR = "results/baselines"


def _iter_trial_files(task_dir: Path) -> list[Path]:
    files = sorted(task_dir.glob("*.json")) + sorted(task_dir.glob("*.jsonl"))
    return [
        path
        for path in files
        if path.name != "summary.json" and "trace" not in path.name
    ]


def _load_trial_payloads(task_dir: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for trial_file in _iter_trial_files(task_dir):
        try:
            raw = trial_file.read_text(encoding="utf-8").strip()
            if not raw:
                continue
            if trial_file.suffix == ".json":
                payloads.append(json.loads(raw))
            else:
                for line in raw.splitlines():
                    if line.strip():
                        payloads.append(json.loads(line))
        except (json.JSONDecodeError, OSError):
            continue
    return payloads


@click.group(name="baseline")
def baseline_group() -> None:
    """Manage evaluation baselines for tracking progress over time."""


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


@baseline_group.command(name="save")
@click.option(
    "--name", required=True, type=str,
    help="Name for this baseline (e.g. 'v1.0', 'before-optimization').",
)
@click.option(
    "--results-dir", required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory with evaluation results to save as baseline.",
)
@click.option(
    "--description", default=None, type=str,
    help="Optional description for this baseline.",
)
def baseline_save(name: str, results_dir: str, description: str | None) -> None:
    """Save current evaluation results as a named baseline.

    Captures summary.json per task AND per-trial tool_call_sequence
    for later LCS-based process alignment.
    """
    source = Path(results_dir)
    if not source.exists():
        raise click.ClickException(f"Results directory not found: {results_dir}")

    baseline_path = Path(BASELINE_DIR) / _sanitize_name(name)
    if baseline_path.exists():
        raise click.ClickException(
            f"Baseline '{name}' already exists at {baseline_path}. "
            f"Use a different name or delete it first."
        )

    summaries = list(source.rglob("summary.json"))
    if not summaries:
        raise click.ClickException(f"No summary.json files found in {results_dir}")

    total_tasks = 0
    total_passed = 0
    task_scores: dict[str, float] = {}
    # NEW: Capture tool_call_sequences per task from trial files
    task_sequences: dict[str, list[list[str]]] = {}
    task_summaries: dict[str, dict[str, object]] = {}

    for summary_path in summaries:
        rel = summary_path.relative_to(source)
        target = baseline_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(summary_path), str(target))

        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            total_tasks += 1
            if data.get("pass_rate", 0) >= 0.8:
                total_passed += 1
            tid = data.get("task_id", summary_path.parent.name)
            task_scores[tid] = data.get("avg_score", 0)
            task_summaries[tid] = {
                "suite_type": data.get("suite_type", "capability"),
                "baseline_id": data.get("baseline_id"),
                "avg_scores": data.get("avg_scores", {}),
                "avg_cost_usd": data.get("avg_cost_usd", 0.0),
                "failure_types": data.get("failure_types", []),
                "model": data.get("model", ""),
                "agent_name": data.get("agent_name", ""),
            }

            # Collect tool_call_sequences from trial files in same task dir
            task_dir = summary_path.parent
            sequences: list[list[str]] = []
            for tdata in _load_trial_payloads(task_dir):
                seq = tdata.get("tool_call_sequence", [])
                if isinstance(seq, list) and seq:
                    sequences.append([str(item) for item in seq])
            if sequences:
                task_sequences[tid] = sequences
        except (json.JSONDecodeError, OSError):
            pass

    manifest: dict[str, object] = {
        "name": name,
        "description": description or "",
        "created_at": datetime.now().isoformat(),
        "source_dir": str(source),
        "n_tasks": total_tasks,
        "n_passed": total_passed,
        "avg_score": sum(task_scores.values()) / len(task_scores) if task_scores else 0,
        "task_scores": task_scores,
        "task_sequences": {k: v for k, v in task_sequences.items()},
        "task_summaries": task_summaries,
    }
    manifest_path = baseline_path / "baseline.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"✓ Baseline '{name}' saved to {baseline_path}")
    click.echo(f"  Tasks: {total_tasks}, Passed: {total_passed}")
    click.echo(f"  Avg score: {manifest['avg_score']:.1f}")
    if task_sequences:
        click.echo(f"  Tool-call sequences captured for {len(task_sequences)} tasks")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@baseline_group.command(name="list")
def baseline_list() -> None:
    """List all saved baselines."""
    baseline_root = Path(BASELINE_DIR)
    if not baseline_root.exists() or not any(baseline_root.iterdir()):
        click.echo("No baselines found. Use `codepulse baseline save` to create one.")
        return

    click.echo(f"{'Name':<24} {'Created':<22} {'Tasks':>6} {'Passed':>6} {'Avg Score':>10}")
    click.echo(f"{'-'*24} {'-'*22} {'-'*6:>6} {'-'*6:>6} {'-'*10:>10}")

    for baseline_dir in sorted(baseline_root.iterdir()):
        if not baseline_dir.is_dir():
            continue
        manifest_path = baseline_dir / "baseline.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            created = manifest.get("created_at", "unknown")[:19]
            click.echo(
                f"{manifest['name']:<24} {created:<22} "
                f"{manifest['n_tasks']:>6} {manifest['n_passed']:>6} {manifest['avg_score']:>8.1f}"
            )
        except (json.JSONDecodeError, OSError):
            continue


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------


@baseline_group.command(name="compare")
@click.option("--against", "baseline_name", required=True, type=str, help="Baseline name to compare against.")
@click.option(
    "--results-dir", required=True, type=click.Path(exists=True, file_okay=False),
    help="Current evaluation results directory.",
)
@click.option("--diff", "show_diff", is_flag=True, default=False, help="Show output diff for each task.")
def baseline_compare(baseline_name: str, results_dir: str, show_diff: bool) -> None:
    """Compare current results against a saved baseline.

    Compares scores, tool-call process similarity (LCS),
    output diff, and efficiency metrics.
    """
    baseline_path = Path(BASELINE_DIR) / _sanitize_name(baseline_name)
    if not baseline_path.exists():
        raise click.ClickException(f"Baseline '{baseline_name}' not found.")

    manifest_path = baseline_path / "baseline.json"
    if not manifest_path.exists():
        raise click.ClickException(f"Baseline manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline_scores: dict[str, float] = manifest.get("task_scores", {})
    baseline_sequences: dict[str, list[list[str]]] = manifest.get("task_sequences", {})
    baseline_summaries: dict[str, dict[str, object]] = manifest.get("task_summaries", {})

    current = Path(results_dir)
    if not current.exists():
        raise click.ClickException(f"Results directory not found: {results_dir}")

    current_scores: dict[str, float] = {}
    current_sequences: dict[str, list[list[str]]] = {}
    current_summaries: dict[str, dict[str, object]] = {}

    for summary_path in current.rglob("summary.json"):
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            tid = data.get("task_id", summary_path.parent.name)
            current_scores[tid] = data.get("avg_score", 0)
            current_summaries[tid] = {
                "suite_type": data.get("suite_type", "capability"),
                "avg_cost_usd": data.get("avg_cost_usd", 0.0),
                "failure_types": data.get("failure_types", []),
            }

            # Collect current tool_call_sequences
            task_dir = summary_path.parent
            sequences: list[list[str]] = []
            for tdata in _load_trial_payloads(task_dir):
                seq = tdata.get("tool_call_sequence", [])
                if isinstance(seq, list) and seq:
                    sequences.append([str(item) for item in seq])
            if sequences:
                current_sequences[tid] = sequences
        except (json.JSONDecodeError, OSError):
            continue

    if not current_scores:
        raise click.ClickException(f"No results found in {results_dir}")

    all_tasks = set(baseline_scores.keys()) | set(current_scores.keys())
    improvements = 0
    regressions = 0
    same = 0
    new = 0
    missing = 0

    click.echo(f"Baseline: {baseline_name} ({manifest.get('created_at', 'unknown')[:10]})")
    click.echo(f"Current:  {results_dir}")
    click.echo()
    click.echo(f"{'Task':<32} {'Base':>7} {'Curr':>7} {'Δ':>7}  {'Process':>8} {'Eff':>6} {'Diag':>8}")
    click.echo(f"{'-'*32} {'-'*7:>7} {'-'*7:>7} {'-'*7:>7}  {'-'*8:>8} {'-'*6:>6} {'-'*8:>8}")

    for task_id in sorted(all_tasks):
        base_score = baseline_scores.get(task_id)
        curr_score = current_scores.get(task_id)

        if base_score is None:
            curr_d = f"{curr_score:.1f}" if curr_score is not None else "—"
            click.echo(f"{task_id:<32} {'—':>7} {curr_d:>7} {'NEW':>7}  {'—':>8} {'—':>6} {'—':>8}")
            new += 1
        elif curr_score is None:
            click.echo(f"{task_id:<32} {base_score:>7.1f} {'—':>7} {'MISS':>7}  {'—':>8} {'—':>6} {'—':>8}")
            missing += 1
        else:
            diff_score = curr_score - base_score
            tag = f"{diff_score:+7.1f}"
            if diff_score > 1:
                tag = click.style(f"{diff_score:+7.1f}", fg="green")
                improvements += 1
            elif diff_score < -1:
                tag = click.style(f"{diff_score:+7.1f}", fg="red")
                regressions += 1
            else:
                same += 1

            # Process similarity (LCS)
            base_seqs = baseline_sequences.get(task_id, [])
            curr_seqs = current_sequences.get(task_id, [])
            proc_score = _process_similarity(base_seqs, curr_seqs)
            proc_str = f"{proc_score:.2f}" if proc_score >= 0 else "N/A"

            # Efficiency change (tokens)
            eff_str = _efficiency_change(task_id, baseline_path, current)
            diag_str = _compare_failure_types(
                baseline_summaries.get(task_id, {}),
                current_summaries.get(task_id, {}),
            )
            click.echo(
                f"{task_id:<32} "
                f"{base_score:>7.1f} {curr_score:>7.1f} {tag}  "
                f"{proc_str:>8} {eff_str:>6} {diag_str:>8}"
            )

    click.echo()
    click.echo(f"Summary: {improvements} ↑, {regressions} ↓, {same} —, {new} ✦, {missing} ✗")

    common_tasks = [t for t in all_tasks if t in baseline_scores and t in current_scores]
    if common_tasks:
        avg_base = sum(baseline_scores[t] for t in common_tasks) / len(common_tasks)
        avg_curr = sum(current_scores[t] for t in common_tasks) / len(common_tasks)
        net = avg_curr - avg_base
        symbol = "+" if net >= 0 else ""
        click.echo(f"Average Δ on {len(common_tasks)} common tasks: {symbol}{net:.2f}")

    if show_diff:
        _show_diffs(baseline_path, current)


def _process_similarity(
    base_sequences: list[list[str]], curr_sequences: list[list[str]]
) -> float:
    """Compute average LCS process similarity across trials."""
    if not base_sequences or not curr_sequences:
        return -1.0
    scores: list[float] = []
    for bs in base_sequences:
        for cs in curr_sequences:
            scores.append(sequence_similarity(bs, cs))
    return round(sum(scores) / len(scores), 4) if scores else -1.0


def _efficiency_change(
    task_id: str, baseline_path: Path, current: Path
) -> str:
    """Compare token efficiency between baseline and current."""
    base_total = 0
    base_count = 0
    for data in _load_trial_payloads(baseline_path / task_id):
        m = data.get("metrics", {})
        if isinstance(m, dict):
            base_total += int(m.get("total_tokens", 0))
            base_count += 1

    curr_total = 0
    curr_count = 0
    for data in _load_trial_payloads(current / task_id):
        m = data.get("metrics", {})
        if isinstance(m, dict):
            curr_total += int(m.get("total_tokens", 0))
            curr_count += 1

    if not base_count or not curr_count:
        return "N/A"
    avg_base = base_total / base_count
    avg_curr = curr_total / curr_count
    ratio = avg_curr / avg_base if avg_base > 0 else 0
    if ratio <= 0:
        return "N/A"
    pct = round((ratio - 1) * 100)
    if pct <= -5:
        return click.style(f"{pct:+d}%", fg="green")
    if pct >= 5:
        return click.style(f"{pct:+d}%", fg="red")
    return f"{pct:+d}%"


def _compare_failure_types(
    baseline_summary: dict[str, object],
    current_summary: dict[str, object],
) -> str:
    base_raw = baseline_summary.get("failure_types", [])
    curr_raw = current_summary.get("failure_types", [])
    base = {str(item) for item in base_raw} if isinstance(base_raw, list) else set()
    curr = {str(item) for item in curr_raw} if isinstance(curr_raw, list) else set()
    if not base and not curr:
        return "—"
    if curr - base:
        return click.style("new-risk", fg="red")
    if base - curr:
        return click.style("better", fg="green")
    return "same"


def _show_diffs(baseline_path: Path, current: Path) -> None:
    """Show per-task diff between baseline and current."""
    for summary_path in sorted(current.rglob("summary.json")):
        tid = summary_path.parent.name
        base_summary = baseline_path / tid / "summary.json"
        if not base_summary.exists():
            continue
        try:
            base_data = json.loads(base_summary.read_text(encoding="utf-8"))
            curr_data = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        base_scores = base_data.get("avg_scores", {})
        curr_scores = curr_data.get("avg_scores", {})
        all_dims = set(base_scores.keys()) | set(curr_scores.keys())
        diffs: list[str] = []
        for dim in sorted(all_dims):
            b = base_scores.get(dim, 0)
            c = curr_scores.get(dim, 0)
            if abs(c - b) > 0.01:
                diffs.append(f"{dim}: {b:.2f}→{c:.2f}")

        if diffs:
            click.echo(f"\n  {tid}:")
            for d in diffs:
                click.echo(f"    {d}")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@baseline_group.command(name="delete")
@click.argument("name", type=str)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
def baseline_delete(name: str, yes: bool) -> None:
    """Delete a saved baseline."""
    baseline_path = Path(BASELINE_DIR) / _sanitize_name(name)
    if not baseline_path.exists():
        raise click.ClickException(f"Baseline '{name}' not found at {baseline_path}.")

    if not yes:
        click.confirm(f"Delete baseline '{name}'? This cannot be undone.", abort=True)

    shutil.rmtree(baseline_path)
    click.echo(f"✓ Baseline '{name}' deleted.")


def _sanitize_name(name: str) -> str:
    """Sanitize a baseline name for use as a directory name."""
    import re
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())


# ---------------------------------------------------------------------------
# capture-failures — 将失败用例纳入回归集
# ---------------------------------------------------------------------------


@baseline_group.command(name="capture-failures")
@click.option(
    "--results-dir", required=True, type=click.Path(exists=True, file_okay=False),
    help="Directory with evaluation results to scan for failures.",
)
@click.option(
    "--output", "output_path", default="datasets/regression.jsonl",
    show_default=True, type=str,
    help="Output JSONL file for regression test cases.",
)
@click.option(
    "--threshold", default=80, type=int,
    help="Score threshold below which a task is considered failed (default: 80).",
)
def capture_failures(results_dir: str, output_path: str, threshold: int) -> None:
    """Capture failed tasks as regression test cases.

    Scans evaluation results, finds tasks with avg_score below threshold,
    and appends them to a regression dataset for future regression testing.
    """
    source = Path(results_dir)
    if not source.exists():
        raise click.ClickException(f"Results directory not found: {results_dir}")

    summaries = list(source.rglob("summary.json"))
    if not summaries:
        raise click.ClickException(f"No summary files found in {results_dir}")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    captured = 0
    for summary_path in summaries:
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            score = data.get("avg_score", 0)
            if score >= threshold:
                continue
            # Build regression task from failed result
            reg_task = {
                "task_id": f"regression/{data.get('task_id', 'unknown')}",
                "category": data.get("agent_type", "bug_fix"),
                "difficulty": "medium",
                "language": "python",
                "description": f"Regression: {data.get('task_id', '')} (score={score:.1f}, agent={data.get('agent_name', '')})",
                "input_code": "",
                "expected_output": "",
                "test_cases": [],
                "source": "regression",
                "metadata": {
                    "original_score": score,
                    "agent_name": data.get("agent_name", ""),
                    "original_task_id": data.get("task_id", ""),
                    "captured_at": datetime.now().isoformat(),
                },
            }
            with output_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(reg_task, ensure_ascii=False) + "\n")
            captured += 1
        except (json.JSONDecodeError, OSError):
            continue

    if captured:
        click.echo(f"✓ {captured} failures captured → {output_file}")
    else:
        click.echo(f"No failures found (threshold={threshold}). Nothing captured.")
