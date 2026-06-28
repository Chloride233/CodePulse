"""人工校准工具测试。"""

from pathlib import Path

import pytest

from codepulse.eval.calibrator import (
    CalibrationDataset,
    Calibrator,
)
from codepulse.eval.scoring import ScoreDimension


class TestCalibrationDataset:
    def test_empty_dataset(self) -> None:
        ds = CalibrationDataset()
        assert ds.size == 0
        assert ds.agreement_rate() == 0.0
        assert ds.mean_bias() == 0.0

    def test_add_samples(self) -> None:
        ds = CalibrationDataset()
        ds.add("grader-a", "task-1", "functional", 0.8, 0.7, "reason", "note")
        assert ds.size == 1
        assert ds.samples[0].grader == "grader-a"

    def test_agreement_rate_perfect(self) -> None:
        ds = CalibrationDataset()
        ds.add("g1", "t1", "functional", 0.8, 0.8)
        ds.add("g1", "t2", "functional", 0.5, 0.6)
        assert ds.agreement_rate() >= 0.5

    def test_agreement_rate_low(self) -> None:
        ds = CalibrationDataset()
        ds.add("g1", "t1", "functional", 1.0, 0.0)
        ds.add("g1", "t2", "functional", 0.9, 0.1)
        assert ds.agreement_rate() == 0.0

    def test_mean_bias(self) -> None:
        ds = CalibrationDataset()
        ds.add("g1", "t1", "functional", 0.8, 0.7)
        ds.add("g1", "t2", "functional", 0.6, 0.5)
        assert ds.mean_bias() == pytest.approx(0.1)

    def test_filter_by_grader(self) -> None:
        ds = CalibrationDataset()
        ds.add("g1", "t1", "functional", 0.8, 0.7)
        ds.add("g2", "t2", "functional", 0.6, 0.5)
        filtered = ds.filter_by_grader("g1")
        assert filtered.size == 1
        assert filtered.samples[0].grader == "g1"

    def test_filter_by_dimension(self) -> None:
        ds = CalibrationDataset()
        ds.add("g1", "t1", "functional", 0.8, 0.7)
        ds.add("g1", "t2", "process", 0.6, 0.5)
        filtered = ds.filter_by_dimension("functional")
        assert filtered.size == 1

    def test_to_jsonl_and_from_jsonl(self, tmp_path: Path) -> None:
        ds = CalibrationDataset()
        ds.add("g1", "t1", "functional", 0.8, 0.7)
        path = tmp_path / "calibration.jsonl"
        ds.to_jsonl(str(path))
        assert path.exists()
        loaded = CalibrationDataset.from_jsonl(str(path))
        assert loaded.size == 1
        assert loaded.samples[0].grader == "g1"


class TestCalibrator:
    def test_empty_analyze(self) -> None:
        cal = Calibrator()
        result = cal.analyze("grader-a")
        assert "error" in result

    def test_analyze_with_samples(self) -> None:
        cal = Calibrator()
        cal.dataset.add("g1", "t1", "functional", 0.8, 0.7)
        cal.dataset.add("g1", "t2", "functional", 0.6, 0.5)
        cal.dataset.add("g1", "t3", "functional", 0.9, 0.9)
        result = cal.analyze("g1")
        assert result["size"] == 3
        assert "agreement_rate" in result
        assert "kappa" in result

    def test_bias_offset(self) -> None:
        cal = Calibrator()
        cal.dataset.add("g1", "t1", "functional", 0.8, 0.7)
        cal.dataset.add("g1", "t2", "functional", 0.6, 0.5)
        offset = cal.bias_offset("g1")
        assert offset == 0.1

    def test_bias_offset_unknown_grader(self) -> None:
        cal = Calibrator()
        cal.dataset.add("g1", "t1", "functional", 0.8, 0.7)
        assert cal.bias_offset("nonexistent") == 0.0

    def test_cohens_kappa_perfect(self) -> None:
        k = Calibrator.cohens_kappa([0.8, 0.6, 0.9], [0.8, 0.6, 0.9])
        assert k == 1.0

    def test_cohens_kappa_no_agreement(self) -> None:
        k = Calibrator.cohens_kappa([0.0, 0.0, 0.0], [0.9, 0.9, 0.9])
        assert k < 0.5

    def test_cohens_kappa_empty(self) -> None:
        assert Calibrator.cohens_kappa([], []) == 0.0

    def test_calibrate_returns_calibrated_grader(self) -> None:
        cal = Calibrator()
        cal.dataset.add("mock", "t1", "functional", 0.8, 0.7)

        class MockGrader:
            name = "mock"
            def grade(self, task, trial):
                from codepulse.data.protocols import GraderResult
                return GraderResult(
                    dimension=ScoreDimension.FUNCTIONAL,
                    score=0.8,
                    details={"raw": 0.8},
                )

        cg = cal.calibrate(MockGrader())
        assert cg.name == "mock_calibrated"


class TestCalibratedGrader:
    def test_calibrated_grade_adjusts_score(self) -> None:
        from codepulse.data.protocols import GraderResult as _Gr

        cal = Calibrator()
        cal.dataset.add("mock", "t1", "functional", 0.8, 0.7)
        cal.dataset.add("mock", "t2", "functional", 0.6, 0.5)

        class MockGrader:
            name = "mock"
            def grade(self, task, trial):
                return _Gr(
                    dimension=ScoreDimension.FUNCTIONAL,
                    score=0.8,
                    details={"raw": 0.8},
                )

        cg = cal.calibrate(MockGrader())
        from codepulse.data.models import (
            AgentConfig,
            Difficulty,
            Task,
            TaskCategory,
            TaskSource,
            Trial,
        )

        task = Task(
            task_id="t1", source=TaskSource.CUSTOM, category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.EASY, language="python", input={}, ground_truth={},
        )
        trial = Trial(trial_id="tr1", task_id="t1", agent_config=AgentConfig(name="a", model="m"))

        result = cg.grade(task, trial)
        assert result.score < 0.8
        assert result.details["calibrated"] is True
