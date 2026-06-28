"""报告生成器 — Markdown 和 HTML 报告。

支持：
- 单次试运行报告
- 多 Agent 对比报告
- 自进化归因报告
- HTML 报告（含 Chart.js 图表）
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.evolve.attribution import AttributionReport

from codepulse.eval.scoring import PASS_THRESHOLD, ScoreDimension

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_DIMENSION_LABELS: dict[str, str] = {
    "correctness": "功能正确性",
    "process_quality": "过程质量",
    "efficiency": "效率成本",
    "robustness": "鲁棒安全",
    "alignment": "体验对齐",
    ScoreDimension.FUNCTIONAL.value: "功能正确性",
    ScoreDimension.PROCESS.value: "过程质量",
    ScoreDimension.EFFICIENCY.value: "效率成本",
    ScoreDimension.ROBUSTNESS.value: "鲁棒安全",
    ScoreDimension.ALIGNMENT.value: "体验对齐",
}

# 权重用于总分计算
_DIMENSION_WEIGHTS: dict[str, float] = {
    "correctness": 30,
    "process_quality": 25,
    "efficiency": 15,
    "robustness": 20,
    "alignment": 10,
    ScoreDimension.FUNCTIONAL.value: 30,
    ScoreDimension.PROCESS.value: 25,
    ScoreDimension.EFFICIENCY.value: 15,
    ScoreDimension.ROBUSTNESS.value: 20,
    ScoreDimension.ALIGNMENT.value: 10,
}


# ---------------------------------------------------------------------------
# 报告生成器
# ---------------------------------------------------------------------------


class ReportGenerator:
    """Markdown / HTML 报告生成器。"""

    def __init__(self, template_dir: str | None = None) -> None:
        self.template_dir = template_dir

    # ------------------------------------------------------------------
    # Trial 报告 (Markdown)
    # ------------------------------------------------------------------

    def generate_trial_report(self, trial: Trial, task: Task) -> str:
        """生成单次试运行的 Markdown 报告。"""
        sections: list[str] = []
        sections.append(f"# 试运行报告 — {trial.trial_id}\n")
        sections.append("## 任务信息\n")
        sections.append("| 属性 | 值 |")
        sections.append("|------|-----|")
        sections.append(f"| 任务 ID | `{task.task_id}` |")
        sections.append(f"| 类别 | {task.category.value} |")
        sections.append(f"| 难度 | {task.difficulty.value} |")
        sections.append(f"| 语言 | {task.language} |")
        sections.append(f"| 套件类型 | {task.suite_type.value} |")
        sections.append(f"| 基线 ID | {task.baseline_id or '-'} |")
        sections.append("")
        status = "✅ 通过" if trial.success else "❌ 未通过"
        sections.append(f"## 结果：{status}\n")
        total = sum(trial.scores.values()) if trial.scores else 0.0
        sections.append(f"**总分：{total:.1f} / 100**（通过阈值 {PASS_THRESHOLD}）\n")
        sections.append("## 维度得分\n")
        sections.append("| 维度 | 权重 | 得分 |")
        sections.append("|------|------|------|")
        for key, label in _DIMENSION_LABELS.items():
            weight = _DIMENSION_WEIGHTS.get(key, 0)
            score = trial.scores.get(key, 0.0) if trial.scores else 0.0
            sections.append(f"| {label} | {weight:.0f} | {score:.1f} |")
        sections.append("")
        m = trial.metrics
        sections.append("## 关键指标\n")
        sections.append("| 指标 | 值 |")
        sections.append("|------|-----|")
        sections.append(f"| 总 Token | {m.total_tokens:,} |")
        sections.append(f"| 输入 Token | {m.input_tokens:,} |")
        sections.append(f"| 输出 Token | {m.output_tokens:,} |")
        sections.append(f"| 推理 Token | {m.reasoning_tokens:,} |")
        sections.append(f"| 工具往返 Token | {m.tool_roundtrip_tokens:,} |")
        sections.append(f"| 重试次数 | {m.retry_count} |")
        sections.append(f"| 耗时 | {m.total_duration:.1f}s |")
        sections.append(f"| 工具调用次数 | {m.tool_call_count} |")
        sections.append(f"| 自纠正次数 | {m.self_correction_count} |")
        sections.append(f"| 费用 (USD) | ${m.cost_usd:.4f} |")
        sections.append("")
        if trial.failure_analysis:
            sections.append("## 失败归因\n")
            sections.append("| 阶段 | 类型 | 证据 | 建议动作 | 回归候选 |")
            sections.append("|------|------|------|----------|----------|")
            for item in trial.failure_analysis:
                evidence = "; ".join(item.evidence[:2]) if item.evidence else "-"
                sections.append(
                    f"| {item.stage} | {item.failure_type} | {evidence} | "
                    f"{item.suggested_action or '-'} | "
                    f"{'是' if item.should_enter_regression else '否'} |"
                )
            sections.append("")
        sections.append("## Agent 配置\n")
        ac = trial.agent_config
        sections.append(f"- **名称**: {ac.name}")
        sections.append(f"- **模型**: {ac.model}")
        sections.append(f"- **温度**: {ac.temperature}")
        sections.append(f"- **最大 Token**: {ac.max_tokens}")
        sections.append("")
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # 结构化评测报告 — 全局概览 + 任务详情 + 聚合统计
    # ------------------------------------------------------------------

    def generate_evaluation_report(
        self,
        results: dict[str, dict[str, Any]],
        title: str = "CodePulse 评测报告",
    ) -> str:
        """Generate a structured multi-level evaluation report."""
        if not results:
            return f"# {title}\n\nNo data.\n"

        sections: list[str] = []
        sections.append(f"# {title}\n")

        total = len(results)
        passed = sum(1 for r in results.values() if r.get("pass_rate", 0) >= 0.8)
        avg_score = sum(r.get("avg_score", 0) for r in results.values()) / total if total else 0

        dim_sums: dict[str, float] = {}
        dim_counts: dict[str, int] = {}
        for r in results.values():
            for dim, score in r.get("avg_scores", {}).items():
                dim_sums[dim] = dim_sums.get(dim, 0) + score
                dim_counts[dim] = dim_counts.get(dim, 0) + 1

        sections.append("## Overview\n")
        sections.append("| Metric | Value |")
        sections.append("|--------|-------|")
        sections.append(f"| Total tasks | {total} |")
        sections.append(f"| Passed | {passed} |")
        sections.append(f"| Pass rate | {passed / total:.1%}" if total else "| — |")
        sections.append(f"| Avg score | {avg_score:.1f} / 100 |")
        for dim, label in _DIMENSION_LABELS.items():
            if dim in dim_sums:
                avg = dim_sums[dim] / dim_counts[dim]
                sections.append(f"| {label} | {avg:.3f} / 1.0 |")
        failure_type_counts: dict[str, int] = {}
        regression_candidates = 0
        for r in results.values():
            for item in r.get("failure_analysis", []):
                failure_type = str(item.get("failure_type", "unknown"))
                failure_type_counts[failure_type] = failure_type_counts.get(failure_type, 0) + 1
                if item.get("should_enter_regression", False):
                    regression_candidates += 1
        if failure_type_counts:
            top_failure = max(failure_type_counts.items(), key=lambda item: item[1])[0]
            sections.append(f"| Top failure type | {top_failure} |")
            sections.append(f"| Regression candidates | {regression_candidates} |")
        sections.append("")

        sections.append("## Per-Task Detail\n")
        sections.append("| Task ID | Status | Score | Pass rate | Avg tokens | Avg duration |")
        sections.append("|---------|--------|-------|-----------|------------|--------------|")
        for tid in sorted(results.keys()):
            r = results[tid]
            status = "✅" if r.get("pass_rate", 0) >= 0.8 else "❌"
            sections.append(
                f"| `{tid}` | {status} | {r.get('avg_score', 0):.1f} "
                f"| {r.get('pass_rate', 0):.1%} | {r.get('avg_tokens', 0):,} "
                f"| {r.get('avg_duration', 0):.1f}s |"
            )
        sections.append("")

        n_success = sum(1 for r in results.values() if r.get("pass_rate", 0) >= 0.8)
        n_fail = total - n_success
        sections.append("## Aggregated Stats\n")
        sections.append(f"- Passed: **{n_success}**")
        sections.append(f"- Failed: **{n_fail}**")
        sections.append(f"- Avg pass rate: **{n_success / total:.1%}**" if total else "-")
        all_tokens = [r.get("avg_tokens", 0) for r in results.values()]
        all_durations = [r.get("avg_duration", 0) for r in results.values()]
        if all_tokens:
            sections.append(f"- Token range: {min(all_tokens):,} ~ {max(all_tokens):,} (avg {sum(all_tokens) / len(all_tokens):,.0f})")
        if all_durations:
            sections.append(f"- Duration range: {min(all_durations):.1f}s ~ {max(all_durations):.1f}s (avg {sum(all_durations) / len(all_durations):.1f}s)")
        if failure_type_counts:
            sections.append(f"- Top failure type: **{max(failure_type_counts.items(), key=lambda item: item[1])[0]}**")
        sections.append("")
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # 对比报告 (Markdown)
    # ------------------------------------------------------------------

    def generate_comparison_report(self, results: dict[str, dict[str, Any]]) -> str:
        """生成多 Agent 对比的 Markdown 报告。"""
        if not results:
            return "# 对比报告\n\n暂无数据。\n"
        sections: list[str] = []
        sections.append("# Agent 对比报告\n")
        all_keys: list[str] = []
        seen: set[str] = set()
        for metrics in results.values():
            for k in metrics:
                if k not in seen:
                    all_keys.append(k)
                    seen.add(k)
        header = "| Agent | " + " | ".join(all_keys) + " |"
        sep = "|-------|" + "|".join("------" for _ in all_keys) + "|"
        sections.append(header)
        sections.append(sep)
        for agent_name, metrics in results.items():
            cells = [f"**{agent_name}**"]
            for k in all_keys:
                v = metrics.get(k, "—")
                cells.append(self._format_cell(v))
            sections.append("| " + " | ".join(cells) + " |")
        sections.append("")
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # 归因报告 (Markdown)
    # ------------------------------------------------------------------

    def generate_evolution_report(self, attribution: AttributionReport) -> str:
        """生成自进化归因的 Markdown 报告。"""
        sections: list[str] = []
        sections.append("# 自进化归因报告\n")
        total = attribution.total
        sections.append("## 总览\n")
        sections.append("| 指标 | 值 |")
        sections.append("|------|-----|")
        sections.append(f"| 总样本数 | {total} |")
        sections.append(f"| 改进率 | {attribution.improvement_rate:.1%} |")
        sections.append(f"| 退化率 | {attribution.regression_rate:.1%} |")
        sections.append("")
        sections.append("## 四类归因\n")
        sections.append("| 归因类型 | 数量 | 占比 |")
        sections.append("|----------|------|------|")
        for label, count in [
            ("改进", attribution.improvements),
            ("退化", attribution.regressions),
            ("持续失败", attribution.persistent_failures),
            ("稳定成功", attribution.stable_successes),
        ]:
            pct = f"{count / total:.1%}" if total > 0 else "—"
            sections.append(f"| {label} | {count} | {pct} |")
        sections.append("")
        net = attribution.improvements - attribution.regressions
        if net > 0:
            verdict = f"净改进 **+{net}**，自进化有效。"
        elif net < 0:
            verdict = f"净退化 **{net}**，需要排查退化原因。"
        else:
            verdict = "改进与退化持平，无净变化。"
        sections.append(f"## 结论\n\n{verdict}\n")
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # HTML 报告
    # ------------------------------------------------------------------

    def generate_html_report(
        self,
        results: dict[str, Any],
        *,
        title: str = "CodePulse 评测报告",
    ) -> str:
        """生成带 Chart.js 图表的 HTML 报告。

        Args:
            results: 评测结果数据（支持 summary 格式或对比结果）。
            title: HTML 页面标题。

        Returns:
            完整的 HTML 文档字符串。
        """
        # 提取维度数据用于雷达图
        dim_data = self._extract_dimension_data(results)
        agents = list(results.keys())
        has_agent_data = len(agents) > 0

        return self._render_html(
            title=title,
            agents=agents,
            results=results,
            dim_data=dim_data,
            has_agent_data=has_agent_data,
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _format_cell(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    @staticmethod
    def _extract_dimension_data(results: dict[str, Any]) -> list[dict[str, Any]]:
        """从结果中提取维度得分数据。"""
        dim_data: list[dict[str, Any]] = []
        for agent_name, metrics in results.items():
            entry: dict[str, Any] = {"agent": agent_name}
            for dim in ScoreDimension:
                val = metrics.get(dim.value)
                if val is not None:
                    entry[dim.value] = val
                elif metrics.get("avg_scores") and isinstance(metrics["avg_scores"], dict):
                    entry[dim.value] = metrics["avg_scores"].get(dim.value, 0)
            dim_data.append(entry)
        return dim_data

    @staticmethod
    def _get_score(val: Any) -> float:
        """Normalize a value to a float score."""
        if isinstance(val, (int, float)):
            return float(val)
        return 0.0

    @staticmethod
    def _extract_radar_data(dim_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Extract per-agent per-dimension data for Chart.js.

        Returns:
            ``{"agents": [...], "datasets": [{"label":..., "data":[...], ...}, ...]}``
        """
        agents = [e["agent"] for e in dim_data]
        colors = [
            "rgba(59,130,246,0.8)", "rgba(16,185,129,0.8)",
            "rgba(245,158,11,0.8)", "rgba(239,68,68,0.8)",
            "rgba(139,92,246,0.8)",
        ]
        datasets = []
        for i, entry in enumerate(dim_data):
            c = colors[i % len(colors)]
            data = [entry.get(dim.value, 0) for dim in ScoreDimension]
            datasets.append({
                "label": entry["agent"],
                "data": data,
                "backgroundColor": c.replace("0.8", "0.2"),
                "borderColor": c,
                "borderWidth": 2,
            })
        return {"agents": agents, "datasets": datasets}

    def _render_html(
        self,
        title: str,
        agents: list[str],
        results: dict[str, Any],
        dim_data: list[dict[str, Any]],
        has_agent_data: bool,
    ) -> str:
        """Render the full HTML document."""
        dim_labels = [d.value.capitalize() for d in ScoreDimension]
        dim_labels_json = json.dumps(dim_labels, ensure_ascii=False)

        # Pre-build radar and bar data
        radar_payload = self._extract_radar_data(dim_data)
        radar_json = json.dumps(radar_payload["datasets"], ensure_ascii=False)
        agents_json = json.dumps(agents, ensure_ascii=False)

        # Bar chart: one dataset per dimension, one bar per agent
        bar_datasets = []
        bar_colors = [
            "rgba(59,130,246,0.8)", "rgba(16,185,129,0.8)",
            "rgba(245,158,11,0.8)", "rgba(239,68,68,0.8)",
            "rgba(139,92,246,0.8)",
        ]
        for di, dim in enumerate(ScoreDimension):
            bar_datasets.append({
                "label": dim_labels[di],
                "data": [e.get(dim.value, 0) for e in dim_data],
                "backgroundColor": bar_colors[di % len(bar_colors)],
            })
        bar_json = json.dumps(bar_datasets, ensure_ascii=False)

        # Build overview table
        table_rows = ""
        if has_agent_data:
            table_rows = (
                "<tr>"
                "<th>Agent</th>"
                + "".join(f"<th>{d.value}</th>" for d in ScoreDimension)
                + "<th>Avg Score</th><th>Pass Rate</th>"
                "</tr>"
            )
            for agent_name in agents:
                metrics = results.get(agent_name, {})
                pass_rate = self._get_score(metrics.get("pass_rate", 0))
                dim_scores = ""
                score_total = 0.0
                for dim in ScoreDimension:
                    val = self._get_score(metrics.get(dim.value, 0))
                    dim_scores += f"<td>{val:.2f}</td>"
                    score_total += val
                avg = score_total / max(len(list(ScoreDimension)), 1)
                table_rows += (
                    f"<tr>"
                    f"<td><strong>{agent_name}</strong></td>"
                    f"{dim_scores}"
                    f"<td>{avg:.2f}</td>"
                    f"<td>{pass_rate:.1%}</td>"
                    f"</tr>"
                )

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f8fafc;
    color: #1e293b;
    line-height: 1.6;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
  h1 {{ font-size: 2rem; font-weight: 700; margin-bottom: 0.5rem; }}
  h2 {{ font-size: 1.5rem; font-weight: 600; margin: 2rem 0 1rem; }}
  .header {{ border-bottom: 2px solid #e2e8f0; padding-bottom: 1rem; margin-bottom: 2rem; }}
  .subtitle {{ color: #64748b; font-size: 0.95rem; }}
  .chart-box {{
    background: white;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    padding: 1.5rem;
    margin-bottom: 2rem;
  }}
  .chart-box canvas {{ max-height: 400px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin: 1.5rem 0; }}
  @media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .card {{
    background: white;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    padding: 1.5rem;
  }}
  .card h3 {{ font-size: 1rem; font-weight: 600; margin-bottom: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }}
  .stat {{ font-size: 2rem; font-weight: 700; }}
  .stat.blue {{ color: #2563eb; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  th, td {{ text-align: left; padding: 0.75rem 1rem; }}
  th {{ background: #f1f5f9; font-weight: 600; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #475569; }}
  tr:not(:last-child) td {{ border-bottom: 1px solid #f1f5f9; }}
  tr:hover td {{ background: #f8fafc; }}
  footer {{ margin-top: 3rem; color: #94a3b8; font-size: 0.8rem; text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{title}</h1>
    <p class="subtitle">Generated by CodePulse — {len(agents)} agent(s)</p>
  </div>

  <div class="grid">
    <div class="card">
      <h3>Agents Compared</h3>
      <div class="stat blue">{len(agents)}</div>
    </div>
    <div class="card">
      <h3>Scoring Dimensions</h3>
      <div class="stat blue">{len(dim_labels)}</div>
    </div>
  </div>

  <div class="chart-box">
    <h2>Dimension Score Radar</h2>
    <canvas id="radarChart"></canvas>
  </div>

  <div class="chart-box">
    <h2>Per-Dimension Comparison</h2>
    <canvas id="barChart"></canvas>
  </div>

  <h2>Detailed Results</h2>
  <table>
    {table_rows}
  </table>

  <footer>CodePulse — Code Agent Evaluation Framework</footer>
</div>

<script>
const dimLabels = {dim_labels_json};
const agents = {agents_json};

new Chart(document.getElementById('radarChart'), {{
  type: 'radar',
  data: {{
    labels: dimLabels,
    datasets: {radar_json}
  }},
  options: {{
    responsive: true,
    scales: {{ r: {{ beginAtZero: true, max: 1.0, ticks: {{ stepSize: 0.2 }} }} }},
    plugins: {{ legend: {{ position: 'bottom' }} }}
  }}
}});

new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{
    labels: agents,
    datasets: {bar_json}
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ position: 'bottom' }} }},
    scales: {{ x: {{ stacked: false }}, y: {{ beginAtZero: true, max: 1.0 }} }}
  }}
}});
</script>
</body>
</html>"""
