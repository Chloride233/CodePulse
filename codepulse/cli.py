"""CodePulse command-line interface.

Subcommands:
    codepulse evaluate   Run evaluation on a task.
    codepulse compare    Compare multiple agents on a task.
    codepulse report     Generate report from saved results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from codepulse.data.custom_loader import CustomDatasetLoader
from codepulse.data.models import AgentConfig, Task
from codepulse.env.sandbox import SandboxError, SandboxManager
from codepulse.eval.harness import EvaluationHarness
from codepulse.observe.comparator import AgentComparator
from codepulse.output.report import ReportGenerator


def _load_first_task(task_file: str) -> Task:
    """Load the first task from a JSONL dataset file.

    Args:
        task_file: Path to the JSONL task file.

    Returns:
        The first parsed Task.

    Raises:
        click.ClickException: If the file cannot be loaded or contains no tasks.
    """
    loader = CustomDatasetLoader()
    try:
        tasks = loader.load(task_file)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if not tasks:
        raise click.ClickException(f"No valid tasks found in {task_file}")

    return tasks[0]


def _create_harness() -> EvaluationHarness:
    """Create an EvaluationHarness with a Docker sandbox.

    Returns:
        An EvaluationHarness instance with default graders.

    Raises:
        click.ClickException: If Docker is not available.
    """
    try:
        sandbox = SandboxManager()
    except SandboxError as exc:
        raise click.ClickException(f"Docker unavailable: {exc}") from exc

    return EvaluationHarness(sandbox=sandbox)


def _load_results(results_dir: str) -> dict[str, Any]:
    """Load task results from a results directory.

    Scans for ``summary.json`` files under *results_dir* and aggregates
    them into a metrics dict keyed by task_id.

    Args:
        results_dir: Path to the results root directory.

    Returns:
        Mapping of task_id to summary data.

    Raises:
        click.ClickException: If the directory does not exist.
    """
    base = Path(results_dir)
    if not base.exists():
        raise click.ClickException(f"Results directory not found: {results_dir}")
    if not base.is_dir():
        raise click.ClickException(f"Not a directory: {results_dir}")

    results: dict[str, Any] = {}
    for summary_path in sorted(base.rglob("summary.json")):
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            click.echo(f"Warning: skipping {summary_path}: {exc}", err=True)
            continue

        task_id = data.get("task_id", summary_path.parent.name)
        results[task_id] = data

    return results


# ------------------------------------------------------------------
# CLI group
# ------------------------------------------------------------------


@click.group()
@click.version_option(package_name="codepulse")
def cli() -> None:
    """CodePulse -- Code Agent evaluation and self-evolution framework."""


# ------------------------------------------------------------------
# evaluate
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--task-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a JSONL file containing the task(s) to evaluate.",
)
@click.option(
    "--agent-name",
    default="default-agent",
    show_default=True,
    help="Name of the agent being evaluated.",
)
@click.option(
    "--model",
    default="deepseek-chat",
    show_default=True,
    help="Model identifier for the agent (LiteLLM format).",
)
@click.option(
    "--n-trials",
    default=5,
    show_default=True,
    type=int,
    help="Number of trial runs per task.",
)
def evaluate(task_file: str, agent_name: str, model: str, n_trials: int) -> None:
    """Run evaluation on a task.

    Loads the first task from TASK_FILE, creates an agent with the given
    configuration, runs the evaluation harness for N_TRIALS trials, and
    prints the results to stdout.
    """
    task = _load_first_task(task_file)
    agent_config = AgentConfig(name=agent_name, model=model)

    harness = _create_harness()

    click.echo(
        f"Evaluating task '{task.task_id}' with agent '{agent_name}' "
        f"({n_trials} trials) ..."
    )

    try:
        trials = harness.run_task(task, agent_config, n_trials=n_trials)
    except Exception as exc:
        raise click.ClickException(f"Evaluation failed: {exc}") from exc

    # Summarise results
    n_success = sum(1 for t in trials if t.success)
    click.echo(f"\nResults: {n_success}/{len(trials)} trials passed\n")

    report_gen = ReportGenerator()
    for trial in trials:
        click.echo(report_gen.generate_trial_report(trial, task))
        click.echo("---")

    # Pass / fail verdict
    pass_rate = n_success / len(trials) if trials else 0.0
    click.echo(f"pass@1 = {pass_rate:.2f}")
    if pass_rate >= 0.8:
        click.echo("VERDICT: PASSED")
    else:
        click.echo("VERDICT: FAILED")
        sys.exit(1)


# ------------------------------------------------------------------
# compare
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--task-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a JSONL file containing the task to compare on.",
)
@click.option(
    "--agents",
    required=True,
    multiple=True,
    help="Agent names to compare (repeatable, e.g. --agents gpt-4 --agents deepseek).",
)
@click.option(
    "--n-trials",
    default=5,
    show_default=True,
    type=int,
    help="Number of trial runs per agent.",
)
def compare(task_file: str, agents: tuple[str, ...], n_trials: int) -> None:
    """Compare multiple agents on a task.

    Runs each agent through the evaluation harness and prints a Markdown
    comparison report to stdout.
    """
    if len(agents) < 2:
        raise click.ClickException("At least two --agents values are required.")

    task = _load_first_task(task_file)
    harness = _create_harness()

    agent_configs = [
        AgentConfig(name=name, model=name) for name in agents
    ]

    comparator = AgentComparator(harness)

    click.echo(
        f"Comparing {len(agent_configs)} agents on task '{task.task_id}' "
        f"({n_trials} trials each) ..."
    )

    try:
        results = comparator.compare(task, agent_configs, n_trials=n_trials)
    except Exception as exc:
        raise click.ClickException(f"Comparison failed: {exc}") from exc

    md_report = comparator.generate_report(results)
    click.echo(md_report)


# ------------------------------------------------------------------
# report
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--results-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory containing evaluation result files.",
)
@click.option(
    "--format",
    "fmt",
    default="markdown",
    show_default=True,
    type=click.Choice(["markdown", "html"], case_sensitive=False),
    help="Output format for the report.",
)
def report(results_dir: str, fmt: str) -> None:
    """Generate a report from saved evaluation results.

    Loads summary files from RESULTS_DIR and renders a report in the
    requested format (Markdown or HTML) to stdout.
    """
    results = _load_results(results_dir)

    if not results:
        raise click.ClickException(f"No result files found in {results_dir}")

    report_gen = ReportGenerator()
    md = report_gen.generate_comparison_report(results)

    if fmt == "markdown":
        click.echo(md)
    else:
        # Minimal HTML wrapper around the markdown content.
        # Full Jinja2 templates can be added later.
        html = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            "  <title>CodePulse Report</title>\n"
            "  <style>body{font-family:sans-serif;max-width:960px;margin:2em auto;}"
            "table{border-collapse:collapse;}th,td{border:1px solid #ccc;padding:6px 12px;}"
            "pre{background:#f5f5f5;padding:1em;overflow-x:auto;}</style>\n"
            "</head>\n"
            "<body>\n"
            f"<pre>{md}</pre>\n"
            "</body>\n"
            "</html>\n"
        )
        click.echo(html)


if __name__ == "__main__":
    cli()
