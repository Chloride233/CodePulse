"""``codepulse evolve`` CLI commands.

Subcommands:
- ``evolve suggest`` — Analyze results and suggest improvements.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from codepulse.evolve.candidate import materialize_candidate
from codepulse.evolve.suggest import SuggestionEngine


@click.group(name="evolve")
def evolve_group() -> None:
    """Self-evolution tools — analyze and improve agent performance."""


@evolve_group.command(name="materialize-candidate")
@click.option("--baseline-profile", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--training-trials", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--candidate-profile", required=True, type=click.Path(dir_okay=False))
@click.option("--provenance", required=True, type=click.Path(dir_okay=False))
def materialize_candidate_command(
    baseline_profile: str,
    training_trials: str,
    candidate_profile: str,
    provenance: str,
) -> None:
    """Generate a provenance-backed candidate profile from failed training trials."""
    try:
        result = materialize_candidate(
            baseline_profile,
            training_trials,
            candidate_profile,
            provenance,
        )
    except (FileExistsError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Candidate profile: {result['candidate_profile_path']}")
    click.echo(f"Provenance: {provenance}")


@evolve_group.command(name="suggest")
@click.option(
    "--results-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory containing evaluation result files.",
)
@click.option(
    "--task",
    "task_id",
    default=None,
    type=str,
    help="Optional: analyze only a specific task ID.",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(dir_okay=False),
    help="Optional: save suggestions Markdown to a file.",
)
def suggest(results_dir: str, task_id: str | None, output_path: str | None) -> None:
    """Analyze evaluation results and suggest improvements.

    Scans result files, computes dimension-level and cross-dimension
    score analysis, and produces actionable optimization suggestions.
    """
    base = Path(results_dir)
    if not base.exists():
        raise click.ClickException(f"Results directory not found: {results_dir}")

    # Load results
    results = _load_results_suggest(base)
    if task_id:
        results = {k: v for k, v in results.items() if k == task_id}
        if not results:
            raise click.ClickException(f"No results found for task: {task_id}")

    if not results:
        raise click.ClickException(f"No result files found in {results_dir}")

    # Aggregate scores across tasks
    engine = SuggestionEngine()
    dim_totals: dict[str, float] = {}
    dim_counts: dict[str, int] = {}
    pass_count = 0
    task_count = len(results)

    for task_data in results.values():
        if task_data.get("pass_rate", 0) >= 0.8:
            pass_count += 1
        avg_scores = task_data.get("avg_scores", {})
        for dim, score in avg_scores.items():
            dim_totals[dim] = dim_totals.get(dim, 0) + score
            dim_counts[dim] = dim_counts.get(dim, 0) + 1

    # Compute averages
    avg_scores_final: dict[str, float] = {}
    for dim in dim_totals:
        avg_scores_final[dim] = dim_totals[dim] / dim_counts[dim]

    # Generate suggestions
    suggestions = engine.analyze(avg_scores_final)
    summary = engine.summarize(suggestions)
    pass_rate = pass_count / task_count if task_count > 0 else 0.0

    # Print summary
    click.echo(f"Tasks analyzed: {task_count}")
    click.echo(f"Pass rate: {pass_rate:.1%}")
    click.echo()

    # Print scores
    click.echo(f"{'Dimension':<20} {'Avg Ratio':>10}")
    click.echo(f"{'-'*20} {'-'*10:>10}")
    for dim in sorted(avg_scores_final.keys()):
        click.echo(f"{dim:<20} {avg_scores_final[dim]:>8.2f}")
    click.echo()

    # Print suggestions
    click.echo(summary)

    # Optionally save
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(summary, encoding="utf-8")
        click.echo(f"Suggestions saved to: {output_file}")


def _load_results_suggest(base: Path) -> dict[str, Any]:
    """Load task result summaries from a directory."""
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
