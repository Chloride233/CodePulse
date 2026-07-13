"""CodePulse command-line interface.

Subcommands:
    codepulse init       Initialize a CodePulse project.
    codepulse evaluate   Run evaluation on a task.
    codepulse compare    Compare multiple agents on a task.
    codepulse inspect    Inspect evaluation results.
    codepulse report     Generate report from saved results.
    codepulse web        Start the web dashboard.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from codepulse.benchmark.cli import benchmark_group
from codepulse.commands.baseline_cli import baseline_group
from codepulse.commands.evolve_cli import evolve_group
from codepulse.config import DEFAULT_RESULTS_DIR
from codepulse.data.custom_loader import CustomDatasetLoader
from codepulse.env.sandbox import SandboxError, SandboxManager
from codepulse.eval.harness import EvaluationHarness
from codepulse.eval.scoring import weighted_total
from codepulse.observe.metrics import compute_pass_metrics
from codepulse.output.report import ReportGenerator

if TYPE_CHECKING:
    from codepulse.data.models import Task


def _load_first_task(task_file: str) -> Task:
    """Load the first task from a JSONL dataset file."""
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


def _load_all_tasks(task_file: str) -> list[Task]:
    """Load all tasks from a JSONL dataset file."""
    loader = CustomDatasetLoader()
    try:
        tasks = loader.load(task_file)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if not tasks:
        raise click.ClickException(f"No valid tasks found in {task_file}")

    return tasks


def _create_harness(sandbox: SandboxManager | None = None) -> EvaluationHarness:
    """Create an EvaluationHarness, optionally with a Docker sandbox.

    Args:
        sandbox: Docker sandbox. If None, creates a harness for mock agents
            that skips container-dependent operations.
    """
    return EvaluationHarness(sandbox=sandbox)


def _create_sandbox() -> SandboxManager:
    """Create a Docker sandbox or raise a clear error."""
    try:
        return SandboxManager()
    except SandboxError as exc:
        raise click.ClickException(
            "Docker 不可用。评测 protocol/cli 类型 Agent 需要 Docker。\n"
            "Mock Agent 不需要 Docker，可使用 --agent agents/mock-agent.yaml。\n"
            f"错误: {exc}"
        ) from exc


def _load_results(results_dir: str) -> dict[str, Any]:
    """Load task results from a results directory."""
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


@click.group(invoke_without_command=True)
@click.version_option(package_name="codepulse")
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v=INFO, -vv=DEBUG).")
def cli(verbose: int) -> None:
    """CodePulse — Code Agent 评测工具。

    评测你的 Agent，找到优化方向，追踪进步。
    """
    level = logging.DEBUG if verbose >= 2 else logging.INFO if verbose >= 1 else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# 注册子命令组
cli.add_command(benchmark_group)
cli.add_command(evolve_group)
cli.add_command(baseline_group)


# ------------------------------------------------------------------
# init
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--dir",
    "directory",
    default=".",
    show_default=True,
    help="Project root directory.",
)
@click.option(
    "--no-examples",
    is_flag=True,
    default=False,
    help="Skip creating example tasks and agent configs.",
)
def init(directory: str, no_examples: bool) -> None:
    """Initialize a CodePulse project.

    Creates the project structure with example tasks, agent configs,
    and a codepulse.yaml configuration file.

    \b
    Quick start:
        codepulse init
        codepulse evaluate --task-file datasets/example.jsonl --agent agents/mock-agent.yaml
    """
    from codepulse.init import init_project

    try:
        root = init_project(
            directory,
            with_examples=not no_examples,
            with_agent_config=not no_examples,
        )
    except Exception as exc:
        raise click.ClickException(f"Initialization failed: {exc}") from exc

    click.echo(f"\n✓ CodePulse project initialized at {root}\n")
    click.echo("Next steps:")
    click.echo(f"  cd {directory}")
    click.echo("  codepulse evaluate --task-file datasets/example.jsonl --agent agents/mock-agent.yaml")
    click.echo("")
    click.echo("Files created:")
    click.echo("  codepulse.yaml              # Project config")
    click.echo("  datasets/example.jsonl      # Example tasks")
    click.echo("  agents/deepseek-agent.yaml  # DeepSeek agent config")
    click.echo("  agents/mock-agent.yaml      # Mock agent (offline)")
    click.echo("  agents/cli-agent.yaml       # CLI agent (zero-invasion)")
    click.echo("  agents/example_cli_agent.py # Example CLI agent script")


# ------------------------------------------------------------------
# evaluate
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--task-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a JSONL file containing task(s) to evaluate.",
)
@click.option(
    "--agent",
    "agent_config",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to agent config YAML file.",
)
@click.option(
    "--n-trials",
    default=5,
    show_default=True,
    type=int,
    help="Number of trial runs per task.",
)
@click.option(
    "--results-dir",
    default=DEFAULT_RESULTS_DIR,
    show_default=True,
    help="Directory to save results.",
)
def evaluate(
    task_file: str,
    agent_config: str,
    n_trials: int,
    results_dir: str,
) -> None:
    """Evaluate an agent on task(s).

    Loads tasks from TASK_FILE, runs the agent configured in AGENT_CONFIG
    for N_TRIALS trials per task, and prints results.

    \b
    Examples:
        codepulse evaluate --task-file tasks.jsonl --agent agents/deepseek-agent.yaml
        codepulse evaluate --task-file tasks.jsonl --agent agents/mock-agent.yaml --n-trials 3
    """
    from codepulse.agent.adapter import AgentProfile

    # 加载 Agent 配置
    try:
        profile = AgentProfile.from_yaml(agent_config)
    except Exception as exc:
        raise click.ClickException(f"Failed to load agent config: {exc}") from exc

    tasks = _load_all_tasks(task_file)
    click.echo(f"Agent: {profile.name} ({profile.type})")
    click.echo(f"Tasks: {len(tasks)}, Trials: {n_trials}\n")

    # 创建沙箱（Protocol/CLI 模式需要）
    sandbox = None
    if profile.type in ("protocol", "cli"):
        sandbox = _create_sandbox()

    # 创建 harness（默认添加 PytestGrader 用于功能正确性评分）
    from codepulse.eval.pytest_grader import PytestGrader
    harness = _create_harness(sandbox)
    harness.graders.append(PytestGrader())

    all_results: list[dict[str, Any]] = []

    for task in tasks:
        click.echo(f"━━━ {task.task_id} ({task.category}) ━━━")

        if profile.type in ("protocol", "cli"):
            # 适配器模式：逐 trial 执行
            from codepulse.agent.adapter import run_adapter_trials
            trials = run_adapter_trials(
                profile, task, sandbox, harness, n_trials  # type: ignore[arg-type]
            )
        else:
            # Mock/内置 Agent 模式
            from codepulse.agent import create_agent
            agent = create_agent(profile)
            trials = harness.run_task(task, agent, n_trials=n_trials)

        # 汇总
        n_success = sum(1 for t in trials if t.success)
        pass_rate = n_success / len(trials) if trials else 0.0

        # 保存结果
        result_data = _save_task_results(task, trials, profile, results_dir)
        all_results.append(result_data)

        # 打印结果
        scores = trials[0].scores if trials else {}
        total = weighted_total(scores)
        status = click.style("PASSED", fg="green") if pass_rate >= 0.8 else click.style("FAILED", fg="red")
        click.echo(f"  {status}  {n_success}/{len(trials)} passed  score={total:.0f}  pass@1={pass_rate:.2f}\n")

    # 总结
    total_tasks = len(all_results)
    passed_tasks = sum(1 for r in all_results if r.get("pass_rate", 0) >= 0.8)
    click.echo(f"{'='*50}")
    click.echo(f"总计: {passed_tasks}/{total_tasks} 任务通过")
    click.echo(f"结果已保存到: {results_dir}/")


def _save_task_results(
    task: Task,
    trials: list[Any],
    profile: Any,
    results_dir: str,
) -> dict[str, Any]:
    """保存任务结果到文件。"""

    task_dir = Path(results_dir) / task.task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    n_success = sum(1 for t in trials if t.success)
    pass_rate = n_success / len(trials) if trials else 0.0

    # 保存每个 trial
    trial_dicts = []
    for trial in trials:
        trial_data = {
            "trial_id": trial.trial_id,
            "task_id": trial.task_id,
            "agent_config": {
                "name": trial.agent_config.name,
                "model": trial.agent_config.model,
                "temperature": trial.agent_config.temperature,
                "max_tokens": trial.agent_config.max_tokens,
            },
            "success": trial.success,
            "scores": trial.scores,
            "outcome": trial.outcome,
            "metrics": {
                "total_tokens": trial.metrics.total_tokens,
                "input_tokens": trial.metrics.input_tokens,
                "output_tokens": trial.metrics.output_tokens,
                "cache_tokens": trial.metrics.cache_tokens,
                "reasoning_tokens": trial.metrics.reasoning_tokens,
                "tool_roundtrip_tokens": trial.metrics.tool_roundtrip_tokens,
                "retry_count": trial.metrics.retry_count,
                "cache_hit_tokens": trial.metrics.cache_hit_tokens,
                "total_duration": trial.metrics.total_duration,
                "tool_call_count": trial.metrics.tool_call_count,
                "self_correction_count": trial.metrics.self_correction_count,
                "cost_usd": trial.metrics.cost_usd,
                "cost_breakdown": trial.metrics.cost_breakdown,
            },
            "tool_call_sequence": trial.tool_call_sequence,
            "failure_analysis": [
                {
                    "stage": item.stage,
                    "failure_type": item.failure_type,
                    "evidence": item.evidence,
                    "suggested_action": item.suggested_action,
                    "should_enter_regression": item.should_enter_regression,
                }
                for item in trial.failure_analysis
            ],
        }
        trial_dicts.append(trial_data)

        trial_path = task_dir / _result_filename(trial.trial_id)
        trial_path.write_text(json.dumps(trial_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 计算平均分
    avg_scores: dict[str, float] = {}
    if trials:
        for dim_name in trials[0].scores:
            values = [t.scores.get(dim_name, 0) for t in trials]
            avg_scores[dim_name] = sum(values) / len(values)

    avg_total = weighted_total(avg_scores)
    avg_cost = (
        sum(trial.metrics.cost_usd for trial in trials) / len(trials)
        if trials else 0.0
    )
    pass_metrics = compute_pass_metrics(len(trials), n_success, k=len(trials) if trials else 1)
    failure_types = sorted({
        analysis.failure_type
        for trial in trials
        for analysis in trial.failure_analysis
    })

    # 保存 summary
    summary = {
        "task_id": task.task_id,
        "agent_name": profile.name,
        "agent_type": profile.type,
        "model": profile.model,
        "source": task.source.value,
        "category": task.category.value,
        "difficulty": task.difficulty.value,
        "language": task.language,
        "suite_type": task.suite_type.value,
        "baseline_id": task.baseline_id,
        "acceptance_criteria": task.acceptance_criteria,
        "artifact_expectations": task.artifact_expectations,
        "n_total": len(trials),
        "n_passed": n_success,
        "pass_rate": pass_rate,
        "avg_score": avg_total,
        "avg_scores": avg_scores,
        "avg_cost_usd": avg_cost,
        "pass_metrics": {
            "pass_at_1": pass_metrics.pass_at_1,
            "pass_at_k": pass_metrics.pass_at_k,
            "pass_hat_k": pass_metrics.pass_hat_k,
            "k": pass_metrics.k,
        },
        "failure_types": failure_types,
        "trials": trial_dicts,
    }

    summary_path = task_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


def _result_filename(trial_id: str) -> str:
    """Convert a benchmark trial ID into one safe JSON filename."""
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "__", trial_id).strip("._")
    return f"{safe_id or 'trial'}.json"




# ------------------------------------------------------------------
# compare
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--task-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a JSONL file containing task(s) to compare on.",
)
@click.option(
    "--agents",
    "agent_configs",
    required=True,
    multiple=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Agent config YAML files (repeatable, minimum 2).",
)
@click.option(
    "--n-trials",
    default=5,
    show_default=True,
    type=int,
    help="Number of trial runs per agent per task.",
)
@click.option(
    "--results-dir",
    default=DEFAULT_RESULTS_DIR,
    show_default=True,
    help="Directory to save results.",
)
def compare(
    task_file: str,
    agent_configs: tuple[str, ...],
    n_trials: int,
    results_dir: str,
) -> None:
    """Compare multiple agents on task(s).

    Runs each agent through the evaluation harness and prints a
    comparison table.

    \b
    Examples:
        codepulse compare --task-file tasks.jsonl \\
            --agents agents/deepseek.yaml --agents agents/gpt4.yaml
    """
    if len(agent_configs) < 2:
        raise click.ClickException("At least two --agents configs are required.")

    from codepulse.agent.adapter import AgentProfile

    # 加载所有 Agent 配置
    profiles = []
    for config_path in agent_configs:
        try:
            profiles.append(AgentProfile.from_yaml(config_path))
        except Exception as exc:
            raise click.ClickException(f"Failed to load {config_path}: {exc}") from exc

    tasks = _load_all_tasks(task_file)
    click.echo(f"Agents: {', '.join(p.name for p in profiles)}")
    click.echo(f"Tasks: {len(tasks)}, Trials: {n_trials}\n")

    # 创建沙箱和 harness
    sandbox = _create_sandbox()
    harness = EvaluationHarness(sandbox=sandbox)

    # 结果汇总
    results: dict[str, dict[str, Any]] = {p.name: {"scores": [], "pass_rates": []} for p in profiles}

    for task in tasks:
        click.echo(f"━━━ {task.task_id} ━━━")

        for profile in profiles:
            try:
                if profile.type in ("protocol", "cli"):
                    from codepulse.agent.adapter import run_adapter_trials
                    trials = run_adapter_trials(profile, task, sandbox, harness, n_trials)
                else:
                    from codepulse.agent import create_agent
                    agent = create_agent(profile)
                    trials = harness.run_task(task, agent, n_trials=n_trials)

                n_success = sum(1 for t in trials if t.success)
                pass_rate = n_success / len(trials) if trials else 0.0
                scores = trials[0].scores if trials else {}
                total = weighted_total(scores)

                results[profile.name]["scores"].append(total)
                results[profile.name]["pass_rates"].append(pass_rate)

                status = "✓" if pass_rate >= 0.8 else "✗"
                click.echo(f"  {status} {profile.name}: score={total:.0f} pass@1={pass_rate:.2f}")
            except Exception as exc:
                click.echo(f"  ✗ {profile.name}: failed ({exc})", err=True)

        click.echo()

    # 打印对比表
    click.echo(f"\n{'='*60}")
    click.echo(f"{'Agent':<20} {'Avg Score':>10} {'Avg Pass@1':>12} {'Tasks Passed':>14}")
    click.echo(f"{'-'*60}")
    for profile in profiles:
        r = results[profile.name]
        avg_score = sum(r["scores"]) / len(r["scores"]) if r["scores"] else 0
        avg_pass = sum(r["pass_rates"]) / len(r["pass_rates"]) if r["pass_rates"] else 0
        passed = sum(1 for p in r["pass_rates"] if p >= 0.8)
        click.echo(f"{profile.name:<20} {avg_score:>10.1f} {avg_pass:>12.2f} {passed:>10}/{len(tasks)}")


# ------------------------------------------------------------------
# inspect
# ------------------------------------------------------------------


@cli.command()
@click.argument(
    "path",
    type=click.Path(exists=True),
)
def inspect(path: str) -> None:
    """Inspect evaluation results.

    PATH can be a summary.json file, a trial JSON file, or a task
    directory containing results.

    \b
    Examples:
        codepulse inspect results/fix-parse-int/summary.json
        codepulse inspect results/fix-parse-int/
    """
    from codepulse.inspect import inspect_result, inspect_task

    path_obj = Path(path)
    if path_obj.is_dir():
        # 目录：列出或检视任务
        summary = path_obj / "summary.json"
        if summary.exists():
            inspect_result(str(summary))
        else:
            # 尝试把目录名当 task_id
            inspect_task(str(path_obj.parent), path_obj.name)
    elif path_obj.is_file():
        inspect_result(str(path_obj))
    else:
        click.echo(f"Path not found: {path}")


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
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(dir_okay=False),
    help="Save report to a file instead of printing to stdout.",
)
def report(results_dir: str, fmt: str, output_path: str | None) -> None:
    """Generate a report from saved evaluation results."""
    results = _load_results(results_dir)

    if not results:
        raise click.ClickException(f"No result files found in {results_dir}")

    report_gen = ReportGenerator()

    if fmt == "html":
        html = report_gen.generate_html_report(results, title="CodePulse Evaluation Report")
        if output_path:
            Path(output_path).write_text(html, encoding="utf-8")
            click.echo(f"HTML report saved to: {output_path}")
        else:
            click.echo(html)
    else:
        md = report_gen.generate_comparison_report(results)
        if output_path:
            Path(output_path).write_text(md, encoding="utf-8")
            click.echo(f"Report saved to: {output_path}")
        else:
            click.echo(md)


# ------------------------------------------------------------------
# web
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--port",
    default=8000,
    show_default=True,
    type=int,
    help="Port for the API server.",
)
@click.option(
    "--results-dir",
    default=DEFAULT_RESULTS_DIR,
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory containing evaluation result files.",
)
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Skip opening the browser automatically.",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload (development only).",
)
def web(port: int, results_dir: str, no_browser: bool, reload: bool) -> None:
    """Start the CodePulse web dashboard."""
    import os
    import signal

    import uvicorn

    os.environ["CODEPULSE_RESULTS_DIR"] = results_dir

    click.echo(f"Starting CodePulse API on http://localhost:{port}")
    click.echo(f"Results directory: {results_dir}")
    click.echo(f"API docs: http://localhost:{port}/docs")

    if reload:
        click.echo("Frontend: cd web && npm run dev")
    else:
        static_dir = Path("web/dist")
        if static_dir.is_dir():
            click.echo(f"Serving static frontend from: {static_dir.resolve()}")

    if not no_browser:
        import webbrowser
        webbrowser.open(f"http://localhost:{port}/docs")

    # 优雅关闭：确保正在运行的评测容器被清理
    def _handle_signal(sig: int, frame: object | None = None) -> None:
        click.echo("\nShutting down...")
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _handle_signal)

    uvicorn.run(
        "codepulse.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    cli()
