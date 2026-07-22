"""Tests for the deterministic offline evidence report."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from codepulse.cli import cli
from codepulse.evidence_report import EvidenceReportError, build_evidence_report

REPOSITORY_ROOT = Path(__file__).parents[1]
BUNDLE_FILES = (
    "results/pilot-v1/runs/20260713-v1/manifest.json",
    "results/pilot-v1/runs/20260713-v1/run-summary.json",
    "results/pilot-v1/runs/20260713-v1/trials.jsonl",
    "results/phase2/calibration-analysis.json",
    "experiments/phase3-swebench-evolution-v4/evidence.json",
    "experiments/phase3-swebench-evolution-v4/manifest.json",
    "experiments/phase3-swebench-evolution-v4/phase3-report.md",
    "experiments/phase3-swebench-screen-v3/evidence.json",
    "experiments/phase3-swebench-screen-v3/manifest.json",
    "experiments/phase3-swebench-screen-v3/screen-report.json",
    "experiments/phase3-strong-model-screen-v1/evidence.json",
    "experiments/phase3-strong-model-screen-v1/manifest.json",
    "experiments/phase3-strong-model-screen-v1/screen-report.json",
    "experiments/phase3-strong-model-screen-v1/aborted-evidence-v1.json",
)


def _copy_bundle(destination: Path) -> None:
    for relative_path in BUNDLE_FILES:
        source = REPOSITORY_ROOT / relative_path
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def test_report_uses_committed_evidence_and_is_deterministic() -> None:
    first = build_evidence_report(REPOSITORY_ROOT)
    second = build_evidence_report(REPOSITORY_ROOT)

    assert first == second
    assert first == (REPOSITORY_ROOT / "docs/codepulse-evidence-report.md").read_text(
        encoding="utf-8"
    )
    assert first.count("\n## ") == 7
    assert "96.7%" in first
    assert "90.0%" in first
    assert "91.0% -> 100.0%" in first
    assert "25.0%" in first
    assert "29.2%" in first
    assert "no_stable_improvement" in first
    assert "raw evidence not locally preserved" in first
    assert str(REPOSITORY_ROOT) not in first


def test_report_rejects_malformed_required_summary(tmp_path: Path) -> None:
    _copy_bundle(tmp_path)
    summary_path = tmp_path / "results/pilot-v1/runs/20260713-v1/run-summary.json"
    summary_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(EvidenceReportError, match="run summary status"):
        build_evidence_report(tmp_path)


def test_report_rejects_missing_required_summary(tmp_path: Path) -> None:
    _copy_bundle(tmp_path)
    (tmp_path / "results/phase2/calibration-analysis.json").unlink()

    with pytest.raises(EvidenceReportError, match="cannot read required evidence"):
        build_evidence_report(tmp_path)


def test_report_rejects_phase1_coverage_drift(tmp_path: Path) -> None:
    _copy_bundle(tmp_path)
    trials_path = tmp_path / "results/pilot-v1/runs/20260713-v1/trials.jsonl"
    rows = trials_path.read_text(encoding="utf-8").splitlines()
    trials_path.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")

    with pytest.raises(EvidenceReportError, match="120 Trial rows"):
        build_evidence_report(tmp_path)


def test_report_rejects_malformed_phase1_manifest_shape(tmp_path: Path) -> None:
    _copy_bundle(tmp_path)
    manifest_path = tmp_path / "results/pilot-v1/runs/20260713-v1/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["task_ids"] = None
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(EvidenceReportError, match="20 task_ids"):
        build_evidence_report(tmp_path)


def test_report_rejects_available_file_hash_mismatch(tmp_path: Path) -> None:
    _copy_bundle(tmp_path)
    manifest_path = tmp_path / "experiments/phase3-swebench-evolution-v4/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["seed"] = "tampered"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(EvidenceReportError, match="manifest_sha256 mismatch"):
        build_evidence_report(tmp_path)


def test_report_rejects_malformed_phase3_reference_shape(tmp_path: Path) -> None:
    _copy_bundle(tmp_path)
    evidence_path = tmp_path / "experiments/phase3-swebench-evolution-v4/evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["manifest_path"] = None
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(EvidenceReportError, match="manifest_path is missing"):
        build_evidence_report(tmp_path)


def test_report_rejects_malformed_phase3_gate_shape(tmp_path: Path) -> None:
    _copy_bundle(tmp_path)
    evidence_path = tmp_path / "experiments/phase3-swebench-evolution-v4/evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["validation_gate"] = None
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(EvidenceReportError, match="was not rejected"):
        build_evidence_report(tmp_path)


def test_report_rejects_malformed_nested_metrics_with_domain_error(tmp_path: Path) -> None:
    _copy_bundle(tmp_path)
    analysis_path = tmp_path / "results/phase2/calibration-analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    del analysis["functional_calibration"]["after"]["exact_agreement"]
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

    with pytest.raises(EvidenceReportError, match="report metrics are malformed"):
        build_evidence_report(tmp_path)


def test_report_narrative_uses_evidence_metrics(tmp_path: Path) -> None:
    _copy_bundle(tmp_path)
    evidence_path = tmp_path / "experiments/phase3-swebench-evolution-v4/evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["metrics"]["candidate"]["success_rate"] = 0.5
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    report = build_evidence_report(tmp_path)

    assert "25.0% success | 50.0% success" in report
    assert "single-run success from 25.0% to 50.0%" in report


def test_demo_cli_writes_report_accepts_identical_output_and_guards_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    _copy_bundle(root)
    monkeypatch.chdir(root)
    runner = CliRunner()

    first = runner.invoke(cli, ["demo", "--output", "evidence.md"])
    assert first.exit_code == 0, first.output
    report_path = root / "evidence.md"
    original = report_path.read_bytes()

    current = runner.invoke(cli, ["demo", "--output", "evidence.md"])
    assert current.exit_code == 0, current.output
    assert "already current" in current.output
    assert report_path.read_bytes() == original

    report_path.write_text("changed\n", encoding="utf-8")
    refused = runner.invoke(cli, ["demo", "--output", "evidence.md"])
    assert refused.exit_code != 0
    assert "refusing to overwrite" in refused.output
    assert report_path.read_text(encoding="utf-8") == "changed\n"

    forced = runner.invoke(cli, ["demo", "--output", "evidence.md", "--force"])
    assert forced.exit_code == 0, forced.output
    assert report_path.read_bytes() == original
