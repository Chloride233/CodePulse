"""样本归因测试。"""

from codepulse.evolve.attribution import (
    AttributionType,
    SampleAttribution,
)


class TestSampleAttribution:
    """SampleAttribution 测试。"""

    def setup_method(self) -> None:
        self.attr = SampleAttribution(pass_threshold=80)

    def test_classify_improvement(self) -> None:
        """未通过 → 通过 = 改进。"""
        assert self.attr.classify(60, 90) == AttributionType.IMPROVEMENT

    def test_classify_regression(self) -> None:
        """通过 → 未通过 = 退化。"""
        assert self.attr.classify(90, 60) == AttributionType.REGRESSION

    def test_classify_persistent_failure(self) -> None:
        """未通过 → 未通过 = 持续失败。"""
        assert self.attr.classify(50, 60) == AttributionType.PERSISTENT_FAILURE

    def test_classify_stable_success(self) -> None:
        """通过 → 通过 = 稳定成功。"""
        assert self.attr.classify(90, 95) == AttributionType.STABLE_SUCCESS

    def test_classify_states_uses_explicit_passes(self) -> None:
        """显式通过状态不依赖分数阈值。"""
        assert self.attr.classify_states(False, True) == AttributionType.IMPROVEMENT

    def test_classify_all(self) -> None:
        """批量分类。"""
        old = {"t1": 60, "t2": 90, "t3": 50, "t4": 90}
        new = {"t1": 90, "t2": 60, "t3": 60, "t4": 95}
        result = self.attr.classify_all(old, new)
        assert result["t1"] == AttributionType.IMPROVEMENT
        assert result["t2"] == AttributionType.REGRESSION
        assert result["t3"] == AttributionType.PERSISTENT_FAILURE
        assert result["t4"] == AttributionType.STABLE_SUCCESS

    def test_classify_all_states_rejects_coverage_drift(self) -> None:
        """状态归因要求基线与候选覆盖完全一致。"""
        result = self.attr.classify_all_states({"t1": False}, {"t1": True})
        assert result["t1"] == AttributionType.IMPROVEMENT

        import pytest

        with pytest.raises(ValueError, match="identical coverage"):
            self.attr.classify_all_states({"t1": False}, {"t2": True})

    def test_report(self) -> None:
        """生成报告。"""
        attributions = {
            "t1": AttributionType.IMPROVEMENT,
            "t2": AttributionType.REGRESSION,
            "t3": AttributionType.STABLE_SUCCESS,
            "t4": AttributionType.STABLE_SUCCESS,
        }
        report = self.attr.report(attributions)
        assert report.improvements == 1
        assert report.regressions == 1
        assert report.stable_successes == 2
        assert report.persistent_failures == 0
        assert report.improvement_rate == 0.25
        assert report.regression_rate == 0.25
        assert report.total == 4
