"""Benchmark CLI commands — ``codepulse benchmark`` subcommand group.

Provides:
- ``codepulse benchmark list``        — list known industry benchmarks
- ``codepulse benchmark info <name>`` — show benchmark details
- ``codepulse benchmark status``      — show download status
- ``codepulse benchmark run <name>``  — run a benchmark against an agent
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from codepulse.benchmark import BenchmarkRegistry
from codepulse.benchmark.downloader import BenchmarkDownloader, DownloadError
from codepulse.benchmark.pilot import (
    PilotBudgetGuard,
    build_pilot_schedule,
    deepseek_v4_flash_cost_cny,
    load_pilot_manifest,
    validate_pilot_manifest,
)
from codepulse.benchmark.pilot_report import write_phase3_reports, write_pilot_reports
from codepulse.benchmark.swebench_runner import (
    SWEbenchTrial,
    load_swebench_instances,
    run_swebench_trial,
    validate_swebench_evolution_manifest,
    validate_swebench_training_manifest,
)
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


def _swebench_trial_record(
    trial: SWEbenchTrial,
    *,
    task_id: str,
    repetition: int,
    agent_name: str,
    expected_model: str,
    guard: PilotBudgetGuard,
) -> tuple[dict[str, Any], list[str]]:
    """Convert one official trial to the shared Phase 3 record schema."""
    input_tokens = int(trial.metrics["input_tokens"])
    output_tokens = int(trial.metrics["output_tokens"])
    cache_tokens = int(trial.metrics["cache_tokens"])
    peak_cost = deepseek_v4_flash_cost_cny(
        input_tokens, output_tokens, cache_tokens, "peak"
    )
    off_peak_cost = deepseek_v4_flash_cost_cny(
        input_tokens, output_tokens, cache_tokens, "off_peak"
    )
    versions = trial.outcome.get("provider_model_versions", [])
    provider_failure = trial.outcome.get("failure_type")
    failure_type = (
        provider_failure
        if isinstance(provider_failure, str)
        else (None if trial.success else "wrong_answer")
    )
    stopped_reasons = guard.record_trial(agent_name, peak_cost, failure_type)
    if versions and versions != [expected_model]:
        stopped_reasons.append("model_version_drift")
    return (
        {
            "trial_id": f"{task_id}--r{repetition}--{agent_name}",
            "task_id": task_id,
            "repetition": repetition,
            "agent_name": agent_name,
            "provider_model_versions": versions,
            "success": trial.success,
            "outcome": trial.outcome,
            "scores": {"functional": 1.0 if trial.success else 0.0},
            "metrics": {
                **trial.metrics,
                "cost_cny_off_peak": off_peak_cost,
                "cost_cny_peak": peak_cost,
            },
            "failure_type": failure_type,
            "stop_reasons": stopped_reasons,
            "started_at": datetime.now(UTC).isoformat(),
        },
        stopped_reasons,
    )


def _write_swebench_summary(
    output: Path, guard: PilotBudgetGuard, planned_trials: int, stopped_reasons: list[str]
) -> None:
    summary = {
        "status": "aborted" if stopped_reasons else "completed",
        "completed_trials": guard.completed_trials,
        "planned_trials": planned_trials,
        "total_cost_cny_peak": round(guard.total_cost_cny, 6),
        "agent_costs_cny_peak": guard.agent_costs_cny,
        "stop_reasons": stopped_reasons,
    }
    (output / "run-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    click.echo(json.dumps(summary))


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


@benchmark_group.command(name="pilot-run")
@click.option(
    "--manifest",
    "manifest_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(file_okay=False),
)
@click.option("--repo-root", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--capture-evidence",
    is_flag=True,
    help="Persist full observable Trace and output files before sandbox teardown.",
)
def benchmark_pilot_run(
    manifest_path: str,
    output_dir: str,
    repo_root: str,
    capture_evidence: bool,
) -> None:
    """Run a frozen benchmark manifest in deterministic interleaved order."""
    from codepulse.agent.adapter import AgentProfile, run_adapter_trials
    from codepulse.env.sandbox import SandboxManager
    from codepulse.eval.pytest_grader import PytestGrader

    root = Path(repo_root)
    manifest = load_pilot_manifest(manifest_path)
    errors = validate_pilot_manifest(manifest, root)
    if errors:
        raise click.ClickException("Pilot preflight failed: " + "; ".join(errors))

    output = Path(output_dir)
    trials_path = output / "trials.jsonl"
    if trials_path.exists():
        raise click.ClickException(f"Refusing to merge with existing run: {trials_path}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    tasks = CustomDatasetLoader().load(str(root / manifest["dataset"]["task_path"]))
    tasks_by_id = {task.task_id: task for task in tasks}
    profiles = {
        item["name"]: AgentProfile.from_yaml(root / item["profile_path"])
        for item in manifest["agents"]
    }
    expected_models = {
        item["name"]: item["provider_model_version"] for item in manifest["agents"]
    }
    schedule = build_pilot_schedule(
        manifest["task_ids"], list(profiles), manifest["n_trials"], manifest["seed"]
    )
    budget = manifest["budget"]
    guard = PilotBudgetGuard(
        planned_trials=len(schedule),
        total_limit_cny=budget["total_cny"],
        per_agent_limit_cny=budget["per_agent_cny"],
        per_trial_limit_cny=budget["per_trial_cny"],
    )
    sandbox = SandboxManager()
    harness = EvaluationHarness(sandbox=sandbox, graders=[PytestGrader()])
    image = manifest["environment"]["image_digest"]
    stopped_reasons: list[str] = []

    with trials_path.open("a", encoding="utf-8") as trial_file:
        for index, (task_id, repetition, agent_name) in enumerate(schedule, start=1):
            click.echo(f"[{index}/{len(schedule)}] {task_id} r{repetition} {agent_name}")
            trial = run_adapter_trials(
                profiles[agent_name],
                tasks_by_id[task_id],
                sandbox,
                harness,
                1,
                sandbox_image=image,
                capture_evidence=capture_evidence,
            )[0]
            trial.trial_id = f"{task_id}--r{repetition}--{agent_name}"
            versions = trial.outcome.get("provider_model_versions", [])
            failure_type = trial.outcome.get("failure_type")
            if not isinstance(failure_type, str):
                failure_type = "agent_error" if "error" in trial.outcome else None
            peak_cost = deepseek_v4_flash_cost_cny(
                trial.metrics.input_tokens,
                trial.metrics.output_tokens,
                trial.metrics.cache_tokens,
                "peak",
            )
            off_peak_cost = deepseek_v4_flash_cost_cny(
                trial.metrics.input_tokens,
                trial.metrics.output_tokens,
                trial.metrics.cache_tokens,
                "off_peak",
            )
            stopped_reasons = guard.record_trial(agent_name, peak_cost, failure_type)
            if versions and versions != [expected_models[agent_name]]:
                stopped_reasons.append("model_version_drift")
            record = {
                "trial_id": trial.trial_id,
                "task_id": task_id,
                "repetition": repetition,
                "agent_name": agent_name,
                "provider_model_versions": versions,
                "success": trial.success,
                "outcome": trial.outcome,
                "scores": trial.scores,
                "metrics": {
                    "input_tokens": trial.metrics.input_tokens,
                    "output_tokens": trial.metrics.output_tokens,
                    "cache_tokens": trial.metrics.cache_tokens,
                    "total_tokens": trial.metrics.total_tokens,
                    "duration_seconds": trial.metrics.total_duration,
                    "cost_cny_off_peak": off_peak_cost,
                    "cost_cny_peak": peak_cost,
                },
                "failure_type": failure_type,
                "stop_reasons": stopped_reasons,
                "started_at": datetime.now(UTC).isoformat(),
            }
            trial_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            trial_file.flush()
            if stopped_reasons:
                break

    summary = {
        "status": "aborted" if stopped_reasons else "completed",
        "completed_trials": guard.completed_trials,
        "planned_trials": len(schedule),
        "total_cost_cny_peak": round(guard.total_cost_cny, 6),
        "agent_costs_cny_peak": guard.agent_costs_cny,
        "stop_reasons": stopped_reasons,
    }
    (output / "run-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not stopped_reasons:
        write_pilot_reports(output)
    click.echo(json.dumps(summary, ensure_ascii=False))


@benchmark_group.command(name="swebench-training-run")
@click.option("--manifest", "manifest_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--output-dir", required=True, type=click.Path(file_okay=False))
@click.option("--repo-root", default=".", type=click.Path(exists=True, file_okay=False))
def benchmark_swebench_training_run(manifest_path: str, output_dir: str, repo_root: str) -> None:
    """Run the frozen Phase 3 SWE-bench baseline-training cohort."""
    from codepulse.agent.adapter import AgentProfile
    from codepulse.env.sandbox import SandboxManager

    root = Path(repo_root)
    manifest = load_pilot_manifest(manifest_path)
    errors = validate_swebench_training_manifest(manifest, root)
    if errors:
        raise click.ClickException("SWE-bench preflight failed: " + "; ".join(errors))
    dataset = manifest["dataset"]
    agent = manifest["agents"][0]
    runner = manifest["runner"]
    assert isinstance(dataset, dict) and isinstance(agent, dict) and isinstance(runner, dict)
    instances = load_swebench_instances(root / str(dataset["task_path"]))
    profile = AgentProfile.from_yaml(root / str(agent["profile_path"]))
    output = Path(output_dir)
    trials_path = output / "trials.jsonl"
    if trials_path.exists():
        raise click.ClickException(f"Refusing to merge with existing run: {trials_path}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(
        Path(manifest_path).read_text(encoding="utf-8"), encoding="utf-8"
    )
    sandbox = SandboxManager()
    budget = manifest["budget"]
    guard = PilotBudgetGuard(
        planned_trials=len(manifest["task_ids"]),
        total_limit_cny=float(budget["total_cny"]),
        per_agent_limit_cny=float(budget["per_agent_cny"]),
        per_trial_limit_cny=float(budget["per_trial_cny"]),
    )
    expected_model = str(agent["provider_model_version"])
    stopped_reasons: list[str] = []
    with trials_path.open("w", encoding="utf-8") as trial_file:
        for index, task_id in enumerate(manifest["task_ids"], start=1):
            click.echo(f"[{index}/5] {task_id} baseline")
            trial = run_swebench_trial(
                profile,
                instances[task_id],
                sandbox,
                timeout_seconds=int(runner["timeout_seconds"]),
                architecture=str(runner["architecture"]),
                image_namespace=str(runner["image_namespace"]),
                image_digest=str(runner["image_digests"][task_id]),
                cpu_count=int(runner["cpu_count"]),
                memory_mb=int(runner["memory_mb"]),
            )
            record, stopped_reasons = _swebench_trial_record(
                trial,
                task_id=task_id,
                repetition=0,
                agent_name=profile.name,
                expected_model=expected_model,
                guard=guard,
            )
            trial_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            trial_file.flush()
            if stopped_reasons:
                break
    _write_swebench_summary(output, guard, len(manifest["task_ids"]), stopped_reasons)


@benchmark_group.command(name="swebench-training-preflight")
@click.option("--manifest", "manifest_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--repo-root", default=".", type=click.Path(exists=True, file_okay=False))
def benchmark_swebench_training_preflight(manifest_path: str, repo_root: str) -> None:
    """Validate a frozen SWE-bench training run without contacting Docker."""
    errors = validate_swebench_training_manifest(
        load_pilot_manifest(manifest_path), repo_root
    )
    if errors:
        raise click.ClickException("SWE-bench preflight failed: " + "; ".join(errors))
    click.echo("SWE-bench training preflight passed: manifest hashes and tasks are frozen.")


@benchmark_group.command(name="swebench-evolution-preflight")
@click.option("--manifest", "manifest_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--repo-root", default=".", type=click.Path(exists=True, file_okay=False))
def benchmark_swebench_evolution_preflight(manifest_path: str, repo_root: str) -> None:
    """Validate the frozen held-out paired comparison without contacting Docker."""
    errors = validate_swebench_evolution_manifest(
        load_pilot_manifest(manifest_path), repo_root
    )
    if errors:
        raise click.ClickException("SWE-bench evolution preflight failed: " + "; ".join(errors))
    click.echo("SWE-bench evolution preflight passed: candidate, provenance, and tasks are frozen.")


@benchmark_group.command(name="swebench-evolution-run")
@click.option("--manifest", "manifest_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--output-dir", required=True, type=click.Path(file_okay=False))
@click.option("--repo-root", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--resume", is_flag=True, help="Resume a valid partial frozen run.")
def benchmark_swebench_evolution_run(
    manifest_path: str,
    output_dir: str,
    repo_root: str,
    resume: bool,
) -> None:
    """Run the frozen held-out SWE-bench baseline/candidate comparison."""
    from codepulse.agent.adapter import AgentProfile
    from codepulse.env.sandbox import SandboxManager

    root = Path(repo_root)
    manifest = load_pilot_manifest(manifest_path)
    errors = validate_swebench_evolution_manifest(manifest, root)
    if errors:
        raise click.ClickException("SWE-bench evolution preflight failed: " + "; ".join(errors))
    dataset = manifest["dataset"]
    runner = manifest["runner"]
    budget = manifest["budget"]
    assert isinstance(dataset, dict) and isinstance(runner, dict) and isinstance(budget, dict)
    instances = load_swebench_instances(root / str(dataset["task_path"]))
    profiles = {
        item["name"]: AgentProfile.from_yaml(root / item["profile_path"])
        for item in manifest["agents"]
    }
    expected_models = {
        item["name"]: str(item["provider_model_version"])
        for item in manifest["agents"]
    }
    schedule = build_pilot_schedule(
        manifest["task_ids"], list(profiles), manifest["n_trials"], manifest["seed"]
    )
    output = Path(output_dir)
    trials_path = output / "trials.jsonl"
    manifest_copy = output / "manifest.json"
    source_manifest = Path(manifest_path).read_text(encoding="utf-8")
    if trials_path.exists() and not resume:
        raise click.ClickException(f"Refusing to merge with existing run: {trials_path}")
    output.mkdir(parents=True, exist_ok=True)
    if resume:
        if not manifest_copy.is_file() or manifest_copy.read_text(encoding="utf-8") != source_manifest:
            raise click.ClickException("Cannot resume: output manifest differs from the frozen manifest")
    else:
        manifest_copy.write_text(source_manifest, encoding="utf-8")

    existing_rows = []
    if trials_path.exists():
        existing_rows = [
            json.loads(line)
            for line in trials_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    expected_keys = set(schedule)
    completed_keys: set[tuple[str, int, str]] = set()
    guard = PilotBudgetGuard(
        planned_trials=len(schedule),
        total_limit_cny=float(budget["total_cny"]),
        per_agent_limit_cny=float(budget["per_agent_cny"]),
        per_trial_limit_cny=float(budget["per_trial_cny"]),
    )
    for row in existing_rows:
        key = (row.get("task_id"), row.get("repetition"), row.get("agent_name"))
        if key not in expected_keys or key in completed_keys:
            raise click.ClickException("Cannot resume: existing trials are duplicate or outside schedule")
        completed_keys.add(key)
        reasons = guard.record_trial(
            str(row["agent_name"]),
            float(row["metrics"]["cost_cny_peak"]),
            row.get("failure_type"),
        )
        if reasons or row.get("stop_reasons"):
            raise click.ClickException("Cannot resume a run that already triggered a stop condition")

    sandbox = SandboxManager()
    stopped_reasons: list[str] = []
    with trials_path.open("a", encoding="utf-8") as trial_file:
        for index, (task_id, repetition, agent_name) in enumerate(schedule, start=1):
            if (task_id, repetition, agent_name) in completed_keys:
                continue
            click.echo(f"[{index}/{len(schedule)}] {task_id} r{repetition} {agent_name}")
            trial = run_swebench_trial(
                profiles[agent_name],
                instances[task_id],
                sandbox,
                timeout_seconds=int(runner["timeout_seconds"]),
                architecture=str(runner["architecture"]),
                image_namespace=str(runner["image_namespace"]),
                image_digest=str(runner["image_digests"][task_id]),
                cpu_count=int(runner["cpu_count"]),
                memory_mb=int(runner["memory_mb"]),
            )
            record, stopped_reasons = _swebench_trial_record(
                trial,
                task_id=task_id,
                repetition=repetition,
                agent_name=agent_name,
                expected_model=expected_models[agent_name],
                guard=guard,
            )
            trial_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            trial_file.flush()
            if stopped_reasons:
                break
    _write_swebench_summary(output, guard, len(schedule), stopped_reasons)
    if not stopped_reasons and guard.completed_trials == len(schedule):
        write_phase3_reports(output, manifest)


@benchmark_group.command(name="phase3-report")
@click.option(
    "--manifest",
    "manifest_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the frozen Phase 3 JSON manifest.",
)
@click.option(
    "--run-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory containing the complete Phase 3 trials.jsonl file.",
)
def benchmark_phase3_report(manifest_path: str, run_dir: str) -> None:
    """Generate a Phase 3 paired comparison report from frozen Trial records."""
    try:
        manifest = load_pilot_manifest(manifest_path)
        markdown_path, html_path = write_phase3_reports(run_dir, manifest)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote {markdown_path} and {html_path}")


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

    harness = EvaluationHarness(sandbox=sandbox)

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
