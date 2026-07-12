"""Benchmark CLI commands — ``codepulse benchmark`` subcommand group.

Provides:
- ``codepulse benchmark list``        — list known industry benchmarks
- ``codepulse benchmark info <name>`` — show benchmark details
- ``codepulse benchmark status``      — show download status
- ``codepulse benchmark run <name>``  — run a benchmark against an agent
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from codepulse.benchmark import BenchmarkRegistry
from codepulse.benchmark.downloader import BenchmarkDownloader, DownloadError
from codepulse.benchmark.pilot import load_pilot_manifest, validate_pilot_manifest
from codepulse.config import DEFAULT_RESULTS_DIR
from codepulse.data.aacr_bench import AacrBenchLoader
from codepulse.data.custom_loader import CustomDatasetLoader
from codepulse.data.swe_bench import SweBenchLoader
from codepulse.eval.harness import EvaluationHarness
from codepulse.eval.scoring import MAX_SCORES, PASS_THRESHOLD, ScoreDimension, weighted_total

try:
    from codepulse.env.sandbox import SandboxManager
    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False

REGISTRY = BenchmarkRegistry()
DOWNLOADER = BenchmarkDownloader()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_benchmark_tasks(defn: Any, data_path: str) -> list[Any]:
    """Load tasks from a benchmark dataset path.

    Args:
        defn: The ``BenchmarkDef``.
        data_path: Path to the data file.

    Returns:
        List of ``Task`` objects.
    """
    loader_cls = defn.loader_cls

    if loader_cls == "custom":
        loader: Any = CustomDatasetLoader()
    elif loader_cls == "codepulse.data.swe_bench.SweBenchLoader":
        loader = SweBenchLoader()
    elif loader_cls == "codepulse.data.aacr_bench.AacrBenchLoader":
        loader = AacrBenchLoader()
    else:
        raise click.ClickException(f"Unknown loader: {loader_cls}")

    return loader.load(data_path)  # type: ignore[no-any-return]


def _format_score_bar(ratio: float, width: int = 20) -> str:
    """Render a horizontal bar for score display."""
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return bar


def _format_benchmark_table(benchmarks: list[Any]) -> str:
    """Format benchmark list as a table string."""
    lines = [
        f"{'Name':<22} {'Tasks':>6} {'Lang':>10} {'Category':>14} {'Available':>10}",
        f"{'-'*22} {'-'*6:>6} {'-'*10:>10} {'-'*14:>14} {'-'*10:>10}",
    ]
    for b in benchmarks:
        avail = "✓" if REGISTRY.is_available(b) else "—"
        cat = b.category.value.replace("_", " ")
        lang = b.languages[0] if len(b.languages) == 1 else f"{len(b.languages)} langs"
        lines.append(
            f"{b.name:<22} {b.n_tasks:>6} {lang:>10} {cat:>14} {avail:>10}"
        )
    return "\n".join(lines)


def _load_agent_profile(config_path: str) -> Any:
    """Load an AgentProfile from a YAML path."""
    from codepulse.agent.adapter import AgentProfile
    try:
        return AgentProfile.from_yaml(config_path)
    except Exception as exc:
        raise click.ClickException(f"Failed to load agent config: {exc}") from exc


def _save_benchmark_summary(
    benchmark_name: str,
    agent_name: str,
    n_trials: int,
    results: list[dict[str, Any]],
    output_dir: str,
) -> Path:
    """Save benchmark run summary and return the path."""
    total_passed = sum(1 for r in results if r.get("pass_rate", 0) >= 0.8)
    avg_scores: dict[str, float] = {}
    for r in results:
        for dim, score in r.get("avg_scores", {}).items():
            avg_scores[dim] = avg_scores.get(dim, 0) + score
    n = len(results)
    if n:
        for dim in avg_scores:
            avg_scores[dim] /= n

    summary = {
        "benchmark": benchmark_name,
        "agent": agent_name,
        "n_tasks": n,
        "n_passed": total_passed,
        "pass_rate": total_passed / n if n else 0.0,
        "avg_scores": avg_scores,
        "tasks": results,
    }

    # Save under results/benchmarks/<name>/
    save_dir = Path(output_dir) / "benchmarks" / benchmark_name
    save_dir.mkdir(parents=True, exist_ok=True)
    summary_path = save_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary_path


# ---------------------------------------------------------------------------
# Benchmark group
# ---------------------------------------------------------------------------


@click.group(name="benchmark")
def benchmark_group() -> None:
    """Manage and run industry-standard benchmarks.

    Lists known benchmarks (SWE-bench, HumanEval, MBPP, AACR-Bench),
    checks download status, and runs evaluations against your agents.
    """


@benchmark_group.command(name="preflight")
@click.option(
    "--manifest",
    "manifest_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the frozen pilot JSON manifest.",
)
@click.option(
    "--repo-root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False),
    help="Repository root used to resolve manifest file paths.",
)
def benchmark_preflight(manifest_path: str, repo_root: str) -> None:
    """Validate every no-cost reproducibility gate before a pilot run."""
    try:
        manifest = load_pilot_manifest(manifest_path)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    errors = validate_pilot_manifest(manifest, repo_root)
    if errors:
        for error in errors:
            click.echo(f"FAIL: {error}", err=True)
        raise click.ClickException(f"Pilot preflight failed with {len(errors)} error(s)")
    click.echo("Pilot preflight passed: manifest is frozen and file hashes match.")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@benchmark_group.command(name="list")
def benchmark_list() -> None:
    """List all available benchmarks."""
    benches = REGISTRY.list_benchmarks()
    if not benches:
        click.echo("No benchmarks registered.")
        return

    click.echo(_format_benchmark_table(benches))
    click.echo("\nUse `codepulse benchmark info <name>` for details.")
    click.echo("Use `codepulse benchmark status` for download info.")


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


@benchmark_group.command(name="info")
@click.argument("name", type=str)
def benchmark_info(name: str) -> None:
    """Show details about a specific benchmark."""
    defn = REGISTRY.get(name)
    if defn is None:
        raise click.ClickException(f"Unknown benchmark: {name}")

    available = REGISTRY.is_available(defn)
    click.echo(f"Benchmark: {defn.name}")
    click.echo(f"  Description: {defn.description}")
    click.echo(f"  Source: {defn.source.value}")
    click.echo(f"  Category: {defn.category.value}")
    click.echo(f"  Tasks: {defn.n_tasks}")
    click.echo(f"  Languages: {', '.join(defn.languages)}")
    click.echo(f"  Data path: datasets/{defn.expected_path}")
    click.echo(f"  Available: {'✓' if available else '—'}")

    if defn.download_url:
        click.echo(f"  Download URL: {defn.download_url}")

    if defn.published_baselines:
        click.echo("  Published baselines:")
        for metric, val in defn.published_baselines.items():
            click.echo(f"    {metric}: {val}")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@benchmark_group.command(name="status")
def benchmark_status() -> None:
    """Show download status for all benchmarks."""
    benches = REGISTRY.list_benchmarks()
    if not benches:
        click.echo("No benchmarks registered.")
        return

    click.echo(f"{'Benchmark':<22} {'Path':<40} {'Status':<10}")
    click.echo(f"{'-'*22} {'-'*40} {'-'*10}")
    for b in benches:
        path = f"datasets/{b.expected_path}"
        available = REGISTRY.is_available(b)
        status = click.style("✓ cached", fg="green") if available else click.style("— missing", fg="yellow")
        click.echo(f"{b.name:<22} {path:<40} {status:<10}")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@benchmark_group.command(name="run")
@click.argument("name", type=str)
@click.option(
    "--agent",
    "agent_config",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to agent config YAML file.",
)
@click.option(
    "--n-trials",
    default=3,
    show_default=True,
    type=int,
    help="Number of trial runs per task.",
)
@click.option(
    "--max-tasks",
    default=0,
    type=int,
    help="Limit tasks (0 = all). Useful for quick smoke tests.",
)
@click.option(
    "--output-dir",
    default=DEFAULT_RESULTS_DIR,
    show_default=True,
    help="Directory to save benchmark results.",
)
def benchmark_run(
    name: str,
    agent_config: str,
    n_trials: int,
    max_tasks: int,
    output_dir: str,
) -> None:
    """Run a benchmark against an agent.

    Loads the benchmark dataset, evaluates the agent on every task,
    and prints a summary with per-task pass rates and dimension scores.
    """
    # --- resolve benchmark ---
    defn = REGISTRY.get(name)
    if defn is None:
        raise click.ClickException(f"Unknown benchmark: {name}")

    # --- check data availability ---
    data_path = REGISTRY.resolve_data_path(defn)
    if not data_path.exists():
        if defn.download_url:
            click.echo(f"Dataset not found at {data_path}. Attempting download...")
            try:
                data_path = DOWNLOADER.download(defn)
            except DownloadError as exc:
                raise click.ClickException(str(exc)) from exc
        else:
            raise click.ClickException(
                f"Dataset not found at {data_path} and no download URL available. "
                f"Please place the data file manually."
            )

    # --- load tasks ---
    click.echo(f"Loading {defn.name} from {data_path} ...")
    tasks = _load_benchmark_tasks(defn, str(data_path))
    if max_tasks > 0:
        tasks = tasks[:max_tasks]
    click.echo(f"Loaded {len(tasks)} tasks.\n")

    # --- load agent ---
    profile = _load_agent_profile(agent_config)
    click.echo(f"Agent: {profile.name} ({profile.type})")
    click.echo(f"Trials per task: {n_trials}\n")

    # --- setup sandbox ---
    sandbox = None
    if profile.type in ("protocol", "cli"):
        if not SANDBOX_AVAILABLE:
            raise click.ClickException("Docker sandbox is not available.")
        try:
            sandbox = SandboxManager()
        except Exception as exc:
            raise click.ClickException(f"Sandbox error: {exc}") from exc

    harness = EvaluationHarness(sandbox=sandbox)  # type: ignore[arg-type]

    # --- run ---
    task_results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    for idx, task in enumerate(tasks, start=1):
        click.echo(f"[{idx}/{len(tasks)}] {task.task_id} ... ", nl=False)

        try:
            from codepulse.agent import create_agent
            agent = create_agent(profile)
            if profile.type in ("protocol", "cli"):
                from codepulse.agent.adapter import run_adapter_trials
                trials = run_adapter_trials(profile, task, sandbox, harness, n_trials)  # type: ignore[arg-type]
            else:
                trials = harness.run_task(task, agent, n_trials=n_trials)

            # --- aggregate ---
            n_success = sum(1 for t in trials if t.success)
            rate = n_success / len(trials) if trials else 0.0
            scores = trials[0].scores if trials else {}
            total = weighted_total(scores)

            if rate >= 0.8:
                click.echo(click.style(f"PASSED ({n_success}/{n_trials}) score={total:.0f}", fg="green"))
                passed += 1
            else:
                click.echo(click.style(f"FAILED ({n_success}/{n_trials}) score={total:.0f}", fg="red"))
                failed += 1

            task_results.append({
                "task_id": task.task_id,
                "n_total": len(trials),
                "n_passed": n_success,
                "pass_rate": rate,
                "avg_score": total,
                "avg_scores": scores,
            })
        except Exception as exc:
            click.echo(click.style(f"ERROR: {exc}", fg="red"))
            task_results.append({
                "task_id": task.task_id,
                "n_total": 0,
                "n_passed": 0,
                "pass_rate": 0.0,
                "avg_score": 0.0,
                "avg_scores": {},
                "error": str(exc),
            })
            failed += 1

    # --- summary ---
    total = passed + failed
    click.echo()
    click.echo(f"{'='*60}")
    click.echo(f"Benchmark: {defn.name}")
    click.echo(f"Agent: {profile.name}")
    click.echo(f"Tasks: {passed}/{total} passed ({passed/total*100:.1f}%)")
    click.echo()

    # Dimension averages
    if task_results:
        dim_totals: dict[str, float] = {}
        dim_counts: dict[str, int] = {}
        for r in task_results:
            for dim, score in r.get("avg_scores", {}).items():
                dim_totals[dim] = dim_totals.get(dim, 0) + score
                dim_counts[dim] = dim_counts.get(dim, 0) + 1

        click.echo(f"{'Dimension':<20} {'Avg Ratio':>10} {'Score':>8}")
        click.echo(f"{'-'*20} {'-'*10:>10} {'-'*8:>8}")
        for dim in ScoreDimension:
            if dim.value in dim_totals and dim_counts.get(dim.value, 0) > 0:
                avg_ratio = dim_totals[dim.value] / dim_counts[dim.value]
                max_score = MAX_SCORES.get(dim, 0)
                weighted = avg_ratio * max_score
                bar = _format_score_bar(avg_ratio)
                click.echo(f"{dim.value:<20} {avg_ratio:>8.2f}  {bar}  {weighted:>4.0f}/{max_score}")

        final_avg = sum(r.get("avg_score", 0) for r in task_results) / len(task_results)
        click.echo(f"\nAverage total score: {final_avg:.1f} / 100")
        click.echo(f"Pass threshold: {PASS_THRESHOLD}")

    # --- save ---
    summary_path = _save_benchmark_summary(
        defn.name, profile.name, n_trials, task_results, output_dir
    )
    click.echo(f"\nResults saved to: {summary_path}")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

