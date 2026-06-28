"""结果检视 — codepulse inspect。

提供结构化的评测结果展示，帮助开发者快速定位问题。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from codepulse.eval.scoring import MAX_SCORES, PASS_THRESHOLD, ScoreDimension

console = Console()

# 维度中文名
_DIMENSION_LABELS: dict[str, str] = {
    "functional": "功能正确性",
    "process": "过程质量",
    "efficiency": "效率成本",
    "robustness": "鲁棒安全",
    "alignment": "体验对齐",
}


def inspect_result(result_path: str) -> None:
    """检视单个评测结果。

    Args:
        result_path: 结果文件路径（summary.json 或 trial JSON）。
    """
    path = Path(result_path)
    if not path.exists():
        console.print(f"[red]文件不存在: {result_path}[/red]")
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        console.print(f"[red]读取失败: {exc}[/red]")
        return

    if "trials" in data:
        _inspect_summary(data)
    else:
        _inspect_trial(data)


def inspect_task(results_dir: str, task_id: str) -> None:
    """检视某个任务的所有评测结果。

    Args:
        results_dir: 结果目录。
        task_id: 任务 ID。
    """
    base = Path(results_dir)
    task_dir = base / task_id

    if not task_dir.exists():
        # 搜索子目录
        found = list(base.rglob(f"*/{task_id}/summary.json"))
        if not found:
            console.print(f"[red]未找到任务 {task_id} 的结果[/red]")
            return
        task_dir = found[0].parent

    summary_path = task_dir / "summary.json"
    if summary_path.exists():
        inspect_result(str(summary_path))
    else:
        # 列出可用的 trial 文件
        trial_files = [
            path
            for path in sorted(task_dir.glob("*.json"))
            if path.name != "summary.json" and "trace" not in path.name
        ]
        if trial_files:
            console.print(f"任务 [bold]{task_id}[/bold] 有 {len(trial_files)} 个 trial:")
            for f in trial_files:
                console.print(f"  {f.name}")
            console.print(f"\n用 [bold]codepulse inspect {trial_files[0]}[/bold] 查看详情")
        else:
            console.print(f"[red]任务 {task_id} 目录为空[/red]")


def _inspect_summary(data: dict[str, Any]) -> None:
    """检视汇总结果。"""
    task_id = data.get("task_id", "unknown")
    n_total = data.get("n_total", 0)
    n_passed = data.get("n_passed", 0)
    pass_rate = n_passed / n_total if n_total > 0 else 0
    avg_score = data.get("avg_score", 0)
    suite_type = data.get("suite_type", "capability")

    # 标题
    status = "[green]PASSED[/green]" if pass_rate >= 0.8 else "[red]FAILED[/red]"
    console.print()
    console.print(Panel(
        f"任务: [bold]{task_id}[/bold]\n"
        f"套件: {suite_type}\n"
        f"状态: {status}\n"
        f"试运行: {n_passed}/{n_total} 通过 (pass@1 = {pass_rate:.0%})\n"
        f"平均分: {avg_score:.1f}/{PASS_THRESHOLD}",
        title="📊 评测结果",
        border_style="blue",
    ))

    # 维度得分
    avg_scores = data.get("avg_scores", {})
    if avg_scores:
        _print_dimension_table(avg_scores)

    # 稳定性指标
    pass_metrics = data.get("pass_metrics", {})
    if pass_metrics:
        console.print()
        console.print(Panel(
            f"pass@1 = {pass_metrics.get('pass_at_1', 0):.2f}  |  "
            f"pass@k = {pass_metrics.get('pass_at_k', 0):.2f}  |  "
            f"pass^k = {pass_metrics.get('pass_hat_k', 0):.2f}  |  "
            f"k = {pass_metrics.get('k', 5)}",
            title="📈 稳定性指标",
            border_style="cyan",
        ))

    # Trial 概览
    trials = data.get("trials", [])
    if trials:
        _print_trial_table(trials)

    # 失败分析
    failed_trials = [t for t in trials if not t.get("success", False)]
    if failed_trials:
        _print_failure_analysis(failed_trials, avg_scores)
    if data.get("failure_types"):
        console.print()
        console.print(f"[bold]主要失败类型:[/bold] {', '.join(data['failure_types'])}")


def _inspect_trial(data: dict[str, Any]) -> None:
    """检视单个 trial 结果。"""
    trial_id = data.get("trial_id", "unknown")
    task_id = data.get("task_id", "unknown")
    success = data.get("success", False)
    scores = data.get("scores", {})
    outcome = data.get("outcome", {})

    status = "[green]PASSED[/green]" if success else "[red]FAILED[/red]"
    total = sum(
        MAX_SCORES.get(ScoreDimension(k), 0) * v
        for k, v in scores.items()
    )

    console.print()
    console.print(Panel(
        f"Trial: [bold]{trial_id}[/bold]\n"
        f"任务: {task_id}\n"
        f"状态: {status}\n"
        f"总分: {total:.1f}/{PASS_THRESHOLD}",
        title="🔍 Trial 详情",
        border_style="blue",
    ))

    # 维度得分
    if scores:
        _print_dimension_table(scores)

    # 执行信息
    if outcome:
        console.print()
        _print_outcome_details(outcome)
    if data.get("failure_analysis"):
        console.print()
        _print_failure_items(data["failure_analysis"])


def _print_dimension_table(scores: dict[str, float]) -> None:
    """打印维度得分表格。"""
    table = Table(title="维度得分", show_header=True, header_style="bold")
    table.add_column("维度", style="cyan", min_width=12)
    table.add_column("得分", justify="right", min_width=8)
    table.add_column("满分", justify="right", min_width=8)
    table.add_column("得分率", justify="right", min_width=8)
    table.add_column("可视化", min_width=20)

    for dim_name, ratio in scores.items():
        dim = ScoreDimension(dim_name) if dim_name in ScoreDimension.__members__.values() else None
        if dim is None:
            continue
        max_score = MAX_SCORES.get(dim, 0)
        actual = max_score * max(0.0, min(1.0, ratio))
        pct = ratio * 100
        label = _DIMENSION_LABELS.get(dim_name, dim_name)

        # 进度条
        bar_len = 20
        filled = int(ratio * bar_len)
        if pct >= 80:
            bar = f"[green]{'█' * filled}{'░' * (bar_len - filled)}[/green]"
        elif pct >= 50:
            bar = f"[yellow]{'█' * filled}{'░' * (bar_len - filled)}[/yellow]"
        else:
            bar = f"[red]{'█' * filled}{'░' * (bar_len - filled)}[/red]"

        table.add_row(label, f"{actual:.1f}", str(max_score), f"{pct:.0f}%", bar)

    console.print()
    console.print(table)


def _print_trial_table(trials: list[dict[str, Any]]) -> None:
    """打印 trial 概览表格。"""
    table = Table(title="试运行概览", show_header=True, header_style="bold")
    table.add_column("#", justify="right", min_width=3)
    table.add_column("状态", min_width=6)
    table.add_column("总分", justify="right", min_width=6)
    table.add_column("耗时", justify="right", min_width=8)
    table.add_column("Token", justify="right", min_width=8)

    for i, trial in enumerate(trials):
        success = trial.get("success", False)
        scores = trial.get("scores", {})
        outcome = trial.get("outcome", {})

        total = sum(
            MAX_SCORES.get(ScoreDimension(k), 0) * v
            for k, v in scores.items()
        )
        status = "[green]✓[/green]" if success else "[red]✗[/red]"
        duration = outcome.get("total_duration", 0)
        tokens = outcome.get("total_tokens", 0)

        table.add_row(
            str(i + 1),
            status,
            f"{total:.0f}",
            f"{duration:.1f}s" if duration else "-",
            f"{tokens:,}" if tokens else "-",
        )

    console.print()
    console.print(table)


def _print_outcome_details(outcome: dict[str, Any]) -> None:
    """打印执行详情。"""
    # 执行信息
    exit_code = outcome.get("exit_code", -1)
    stdout = outcome.get("stdout", "")
    stderr = outcome.get("stderr", "")
    pytest_total = outcome.get("pytest_total", 0)
    pytest_passed = outcome.get("pytest_passed", 0)

    console.print("[bold]执行信息[/bold]")
    console.print(f"  Exit Code: {exit_code}")
    if pytest_total:
        console.print(f"  测试结果: {pytest_passed}/{pytest_total} 通过")
    if outcome.get("ruff_violations"):
        console.print(f"  Ruff 违规: {outcome['ruff_violations']}")
    if outcome.get("mypy_errors"):
        console.print(f"  Mypy 错误: {outcome['mypy_errors']}")

    # 失败的输出
    if stderr and exit_code != 0:
        console.print()
        console.print("[bold red]错误输出:[/bold red]")
        # 只显示最后 20 行
        lines = stderr.strip().split("\n")
        for line in lines[-20:]:
            console.print(f"  [dim]{line}[/dim]")

    if stdout and exit_code != 0:
        console.print()
        console.print("[bold]标准输出:[/bold]")
        lines = stdout.strip().split("\n")
        for line in lines[-20:]:
            console.print(f"  [dim]{line}[/dim]")


def _print_failure_analysis(
    failed_trials: list[dict[str, Any]],
    avg_scores: dict[str, float],
) -> None:
    """打印失败分析。"""
    console.print()
    console.print("[bold red]失败分析[/bold red]")

    # 找出最弱的维度
    if avg_scores:
        weakest = min(avg_scores.items(), key=lambda x: x[1])
        dim_label = _DIMENSION_LABELS.get(weakest[0], weakest[0])
        console.print(f"  最弱维度: [bold]{dim_label}[/bold] ({weakest[1]:.0%})")

        # 给出建议
        suggestions = _get_suggestions(avg_scores)
        if suggestions:
            console.print()
            console.print("[bold]优化建议:[/bold]")
            for s in suggestions:
                console.print(f"  💡 {s}")

    # 共性错误
    exit_codes = [t.get("outcome", {}).get("exit_code", -1) for t in failed_trials]
    if all(c == exit_codes[0] for c in exit_codes):
        console.print(f"\n  所有失败 trial 的 exit code 均为 {exit_codes[0]}，问题可能是系统性的。")


def _print_failure_items(items: list[dict[str, Any]]) -> None:
    """打印结构化失败归因。"""
    table = Table(title="失败归因", show_header=True, header_style="bold")
    table.add_column("阶段", min_width=10)
    table.add_column("类型", min_width=18)
    table.add_column("建议", min_width=28)
    table.add_column("回归", min_width=6)

    for item in items:
        table.add_row(
            str(item.get("stage", "-")),
            str(item.get("failure_type", "-")),
            str(item.get("suggested_action", "-")),
            "是" if item.get("should_enter_regression", False) else "否",
        )

    console.print(table)


def _get_suggestions(scores: dict[str, float]) -> list[str]:
    """根据维度得分给出优化建议。"""
    suggestions: list[str] = []

    functional = scores.get("functional", 1.0)
    process = scores.get("process", 1.0)
    efficiency = scores.get("efficiency", 1.0)
    robustness = scores.get("robustness", 1.0)

    if functional < 0.5:
        suggestions.append("功能正确性低：检查 Agent 是否正确理解了任务需求，是否运行了测试")
    if functional >= 0.5 and functional < 1.0:
        suggestions.append("功能部分通过：Agent 能处理简单 case，但边界条件遗漏，增加错误处理")
    if process < 0.5:
        suggestions.append("过程质量差：Agent 的代码质量或推理链有问题，优化系统提示词")
    if efficiency < 0.5:
        suggestions.append("效率低：Token 消耗过多，可能是循环试错，减少最大迭代次数或优化提示词")
    if robustness < 0.5:
        suggestions.append("鲁棒性差：代码有 lint 或类型错误，要求 Agent 在提交前运行 ruff/mypy")

    return suggestions
