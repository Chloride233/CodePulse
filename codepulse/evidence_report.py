"""Build the deterministic offline CodePulse evidence report."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from codepulse.benchmark.pilot_report import summarize_pilot
from codepulse.eval.artifacts import file_sha256, load_jsonl

PHASE1_RUN = Path("results/pilot-v1/runs/20260713-v1")
PHASE1_DIRECT_AGENT = "deepseek-v4-flash-direct"
PHASE1_ITERATIVE_AGENT = "deepseek-v4-flash-iterative"
PHASE2_ANALYSIS = Path("results/phase2/calibration-analysis.json")
PHASE3_EVIDENCE = (
    Path("experiments/phase3-swebench-evolution-v4/evidence.json"),
    Path("experiments/phase3-swebench-screen-v3/evidence.json"),
    Path("experiments/phase3-strong-model-screen-v1/evidence.json"),
)
PHASE3_PROTOCOLS = {
    PHASE3_EVIDENCE[0]: "phase3-swebench-evolution-evidence-v4",
    PHASE3_EVIDENCE[1]: "phase3-swebench-screen-evidence-v3",
    PHASE3_EVIDENCE[2]: "phase3-strong-model-screen-evidence-v1",
}


class EvidenceReportError(ValueError):
    """Raised when the committed evidence bundle is incomplete or inconsistent."""


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceReportError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceReportError(f"cannot read required evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceReportError(f"required evidence must be a JSON object: {path}")
    return value


def _load_phase1(root: Path) -> list[dict[str, Any]]:
    run = root / PHASE1_RUN
    manifest = _load_json(run / "manifest.json")
    summary = _load_json(run / "run-summary.json")

    _expect(manifest.get("protocol_version") == "pilot-v1", "unexpected Phase 1 protocol")
    task_ids = manifest.get("task_ids")
    agents = manifest.get("agents")
    if not isinstance(task_ids, list) or len(task_ids) != 20:
        raise EvidenceReportError("Phase 1 requires 20 task_ids")
    if not isinstance(agents, list) or len(agents) != 2:
        raise EvidenceReportError("Phase 1 requires two agents")
    _expect(manifest.get("n_trials") == 3, "Phase 1 requires n_trials 3")

    agent_names: list[str] = []
    for agent in agents:
        if not isinstance(agent, dict):
            raise EvidenceReportError("Phase 1 agent names are invalid")
        name = agent.get("name")
        if not isinstance(name, str) or not name:
            raise EvidenceReportError("Phase 1 agent names are invalid")
        agent_names.append(name)
    _expect(
        set(agent_names) == {PHASE1_DIRECT_AGENT, PHASE1_ITERATIVE_AGENT},
        "Phase 1 agents do not match the frozen profiles",
    )
    _expect(summary.get("status") == "completed", "Phase 1 run summary status is not completed")
    _expect(
        summary.get("completed_trials") == 120 and summary.get("planned_trials") == 120,
        "Phase 1 run summary must declare 120 completed Trial rows",
    )

    try:
        rows = load_jsonl(run / "trials.jsonl")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise EvidenceReportError(f"cannot read Phase 1 Trial rows: {exc}") from exc
    _expect(len(rows) == 120, "Phase 1 requires exactly 120 Trial rows")

    expected = {
        (task_id, agent_name, repetition)
        for task_id in task_ids
        for agent_name in agent_names
        for repetition in range(3)
    }
    try:
        actual = Counter((row["task_id"], row["agent_name"], row["repetition"]) for row in rows)
    except (KeyError, TypeError) as exc:
        raise EvidenceReportError(f"Phase 1 Trial identity is malformed: {exc}") from exc
    _expect(
        set(actual) == expected and all(count == 1 for count in actual.values()),
        "Phase 1 Trial coverage does not match the frozen manifest",
    )

    try:
        metrics = summarize_pilot(rows)
    except (KeyError, TypeError, ZeroDivisionError) as exc:
        raise EvidenceReportError(f"Phase 1 Trial metrics are malformed: {exc}") from exc
    _expect(
        [metric["agent"] for metric in metrics] == sorted(agent_names),
        "Phase 1 metric agents do not match the frozen manifest",
    )
    return metrics


def _load_phase2(root: Path) -> dict[str, Any]:
    analysis = _load_json(root / PHASE2_ANALYSIS)
    functional = analysis.get("functional_calibration")
    qualitative = analysis.get("judge_human_agreement")
    boundaries = analysis.get("usage_boundaries")

    _expect(analysis.get("status") == "complete", "Phase 2 calibration status is not complete")
    _expect(
        isinstance(functional, dict) and functional.get("sample_size") == 100,
        "Phase 2 requires 100 functional calibration samples",
    )
    _expect(analysis.get("sample_size") == 10, "Phase 2 requires 10 qualitative samples")
    _expect(
        analysis.get("missing_judge_observations") == 0,
        "Phase 2 has missing Judge observations",
    )
    _expect(
        isinstance(qualitative, dict) and isinstance(qualitative.get("length_full"), dict),
        "Phase 2 qualitative agreement is missing",
    )
    _expect(
        isinstance(boundaries, dict)
        and {"deterministic_grader", "llm_judge", "human_calibration"} <= boundaries.keys(),
        "Phase 2 usage boundaries are incomplete",
    )
    return analysis


def _verify_referenced_file(
    root: Path,
    evidence: dict[str, Any],
    path_key: str,
) -> None:
    relative_path = evidence.get(path_key)
    expected_hash = evidence.get(path_key.removesuffix("_path") + "_sha256")
    if not isinstance(relative_path, str):
        raise EvidenceReportError(f"Phase 3 {path_key} is missing")
    if not isinstance(expected_hash, str):
        raise EvidenceReportError(f"Phase 3 {path_key} hash is missing")
    path = root / relative_path
    _expect(path.is_file(), f"required committed evidence is missing: {relative_path}")
    _expect(
        file_sha256(path) == expected_hash,
        f"{path_key.removesuffix('_path')}_sha256 mismatch: {relative_path}",
    )


def _load_phase3(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative_path in PHASE3_EVIDENCE:
        evidence = _load_json(root / relative_path)
        _expect(
            evidence.get("protocol_version") == PHASE3_PROTOCOLS[relative_path],
            f"{relative_path} has an unexpected protocol",
        )
        _expect(evidence.get("status") == "completed", f"{relative_path} is not completed")
        _expect(
            evidence.get("completed_trials") == evidence.get("planned_trials"),
            f"{relative_path} has incomplete Trial coverage",
        )

        if "validation_gate" in evidence:
            gate = evidence.get("validation_gate")
            if not isinstance(gate, dict) or gate.get("accepted") is not False:
                raise EvidenceReportError(f"{relative_path} was not rejected")
            reasons = gate.get("rejection_reasons")
        else:
            _expect(evidence.get("accepted") is False, f"{relative_path} was not rejected")
            reasons = evidence.get("rejection_reasons")
        _expect(
            isinstance(reasons, list) and bool(reasons), f"{relative_path} has no rejection reasons"
        )

        _verify_referenced_file(root, evidence, "manifest_path")
        if "report_path" in evidence:
            _verify_referenced_file(root, evidence, "report_path")
        if "screen_report_path" in evidence:
            _verify_referenced_file(root, evidence, "screen_report_path")
        if "aborted_attempt_evidence_path" in evidence:
            _verify_referenced_file(root, evidence, "aborted_attempt_evidence_path")

        records.append(evidence)
    return records


def _phase1_table(metrics: list[dict[str, Any]]) -> list[str]:
    rows = [
        "| Agent | pass@1 | pass@3 | pass^3 | Total tokens | Peak cost (CNY) | P50 / P95 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    rows.extend(
        "| {agent} | {pass_at_1:.1%} | {pass_at_3:.1%} | {pass_hat_3:.1%} | "
        "{total_tokens:,} | {cost_cny_peak:.6f} | {p50_seconds:.3f}s / {p95_seconds:.3f}s |".format(
            **metric
        )
        for metric in metrics
    )
    return rows


def _rejection_reasons(evidence: dict[str, Any]) -> list[str]:
    if "validation_gate" in evidence:
        return list(evidence["validation_gate"]["rejection_reasons"])
    return list(evidence["rejection_reasons"])


def _render_report(
    phase1_metrics: list[dict[str, Any]],
    phase2: dict[str, Any],
    phase3: list[dict[str, Any]],
) -> str:
    functional = phase2["functional_calibration"]
    full_agreement = phase2["judge_human_agreement"]["length_full"]
    boundaries = phase2["usage_boundaries"]
    evolution, patch_guard, strong_model = phase3
    baseline = evolution["metrics"]["baseline"]
    candidate = evolution["metrics"]["candidate"]
    phase1_by_agent = {metric["agent"]: metric for metric in phase1_metrics}
    direct = phase1_by_agent[PHASE1_DIRECT_AGENT]
    iterative = phase1_by_agent[PHASE1_ITERATIVE_AGENT]
    token_delta = candidate["total_tokens"] / baseline["total_tokens"] - 1

    lines = [
        "# CodePulse Evidence Report",
        "",
        "## 1. Executive conclusion",
        "",
        "CodePulse reproduced the Phase 1 comparison and verified the Phase 2 calibration boundary. "
        "All preserved Phase 3 candidates were rejected. The evidence does not support a claim that "
        "self-evolution improved stable Code Agent performance.",
        "",
        "## 2. Proven and unsupported claims",
        "",
        "**Supported by the preserved evidence:**",
        "",
        "- Phase 1 contains a complete 120-Trial, two-Agent comparison over 20 tasks and 3 repetitions.",
        "- Phase 2 calibrates functional Judge behavior against deterministic outcomes and limits qualitative Judge use to evidence-complete cases.",
        "- Phase 3 Gate records reject candidates without stable gain or acceptable resource use.",
        "",
        "**Not supported by the preserved evidence:**",
        "",
        "- CodePulse does not show that self-evolution produces stable improvement.",
        "- The small qualitative calibration does not justify unrestricted LLM-as-Judge use.",
        "- Phase 3 summaries cannot replace the deleted raw Trial records.",
        "",
        "## 3. Phase 1 reproducible Agent comparison",
        "",
        *_phase1_table(phase1_metrics),
        "",
        f"The iterative profile reached {iterative['pass_hat_3']:.1%} pass^3; the direct profile "
        f"reached {direct['pass_hat_3']:.1%}. These are pilot results on the frozen HumanEval "
        "subset, not a general repository-level claim.",
        "",
        "## 4. Phase 2 Judge calibration and usage boundaries",
        "",
        f"- Functional exact agreement: {functional['before']['exact_agreement']:.1%} -> {functional['after']['exact_agreement']:.1%} over 100 samples.",
        f"- Full Judge-human exact agreement: {full_agreement['exact_agreement']:.1%} over 10 qualitative samples.",
        f"- Full Judge-human mean absolute error: {full_agreement['mean_absolute_error']:.1f}.",
        f"- Missing Judge observations: {phase2['missing_judge_observations']}.",
        f"- Deterministic grader: {boundaries['deterministic_grader']}.",
        f"- LLM Judge: {boundaries['llm_judge']}.",
        f"- Human calibration: {boundaries['human_calibration']}.",
        "",
        "## 5. Phase 3 candidate rejection evidence",
        "",
        "| Experiment | Baseline | Candidate | Stable result | Decision |",
        "|---|---:|---:|---|---|",
        f"| V4 Flash full comparison | {baseline['success_rate']:.1%} success | {candidate['success_rate']:.1%} success | pass^3 {baseline['pass_hat_3']:.1%} -> {candidate['pass_hat_3']:.1%}; tokens +{token_delta:.1%} | Rejected: {', '.join(_rejection_reasons(evolution))} |",
        f"| Patch Guard screen | {patch_guard['baseline']['resolved']}/{patch_guard['tasks']} resolved | {patch_guard['candidate']['resolved']}/{patch_guard['tasks']} resolved | cost ratio {patch_guard['candidate_cost_ratio']:.1%} | Rejected: {', '.join(_rejection_reasons(patch_guard))} |",
        f"| V4 Pro screen | {strong_model['baseline']['resolved']}/{strong_model['tasks']} resolved | {strong_model['candidate']['resolved']}/{strong_model['tasks']} resolved | stable delta {strong_model['candidate_resolved_delta']} | Rejected: {', '.join(_rejection_reasons(strong_model))} |",
        "",
        "## 6. Why the Gate rejected apparent improvement",
        "",
        f"The V4 Flash candidate raised single-run success from {baseline['success_rate']:.1%} to "
        f"{candidate['success_rate']:.1%}, but pass^3 remained "
        f"{baseline['pass_hat_3']:.1%} -> {candidate['pass_hat_3']:.1%} and task attribution "
        "contained no stable improvement. Its token use increased by "
        f"{token_delta:.1%}. The Patch Guard screen resolved "
        f"{patch_guard['baseline']['resolved']}/{patch_guard['tasks']} baseline tasks and "
        f"{patch_guard['candidate']['resolved']}/{patch_guard['tasks']} candidate tasks but "
        "exceeded the frozen cost ratio. The V4 Pro screen resolved "
        f"{strong_model['baseline']['resolved']}/{strong_model['tasks']} baseline tasks and "
        f"{strong_model['candidate']['resolved']}/{strong_model['tasks']} candidate tasks. The "
        "recorded decisions therefore separate occasional success from stable, zero-regression, "
        "resource-bounded improvement.",
        "",
        "## 7. Evidence index and preservation boundary",
        "",
        f"- `{PHASE1_RUN / 'manifest.json'}`",
        f"- `{PHASE1_RUN / 'run-summary.json'}`",
        f"- `{PHASE1_RUN / 'trials.jsonl'}`",
        f"- `{PHASE2_ANALYSIS}`",
        *[f"- `{path}`" for path in PHASE3_EVIDENCE],
        "",
        "Phase 1 raw Trials and the Phase 2 calibration summary are locally preserved. Phase 3 "
        "raw evidence not locally preserved: the cleanup removed the referenced `results/phase3/` "
        "Trial and run-summary files. The committed evidence records retain their original paths and "
        "SHA-256 values, but those summaries are not substitutes for the raw records.",
        "",
    ]
    return "\n".join(lines)


def build_evidence_report(root: str | Path) -> str:
    """Verify the committed bundle under root and return deterministic Markdown."""
    repository_root = Path(root)
    phase1_metrics = _load_phase1(repository_root)
    phase2 = _load_phase2(repository_root)
    phase3 = _load_phase3(repository_root)
    try:
        return _render_report(phase1_metrics, phase2, phase3)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise EvidenceReportError(f"report metrics are malformed: {exc}") from exc
