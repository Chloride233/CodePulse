"""评测评分系统测试。"""

from codepulse.eval.scoring import (
    ScoreDimension,
    aggregate_scores,
    is_passed,
)


class TestAggregateScores:
    """aggregate_scores 测试。"""

    def test_all_dimensions_perfect(self) -> None:
        """所有维度满分，总分 100。"""
        scores = {
            ScoreDimension.FUNCTIONAL: 1.0,
            ScoreDimension.PROCESS: 1.0,
            ScoreDimension.EFFICIENCY: 1.0,
            ScoreDimension.ROBUSTNESS: 1.0,
            ScoreDimension.ALIGNMENT: 1.0,
        }
        assert aggregate_scores(scores) == 100.0

    def test_all_dimensions_zero(self) -> None:
        """所有维度零分，总分 0。"""
        scores = {
            ScoreDimension.FUNCTIONAL: 0.0,
            ScoreDimension.PROCESS: 0.0,
            ScoreDimension.EFFICIENCY: 0.0,
            ScoreDimension.ROBUSTNESS: 0.0,
            ScoreDimension.ALIGNMENT: 0.0,
        }
        assert aggregate_scores(scores) == 0.0

    def test_partial_dimensions(self) -> None:
        """部分维度有分。"""
        scores = {
            ScoreDimension.FUNCTIONAL: 1.0,  # 30
            ScoreDimension.ROBUSTNESS: 0.5,  # 10
        }
        assert aggregate_scores(scores) == 40.0

    def test_ratio_clamped(self) -> None:
        """比率超出范围时被截断。"""
        scores = {
            ScoreDimension.FUNCTIONAL: 1.5,  # 截断为 1.0
            ScoreDimension.PROCESS: -0.1,   # 截断为 0.0
        }
        assert aggregate_scores(scores) == 30.0


class TestIsPassed:
    """is_passed 测试。"""

    def test_above_threshold(self) -> None:
        """分数 >= 阈值，通过。"""
        assert is_passed(80) is True
        assert is_passed(100) is True

    def test_below_threshold(self) -> None:
        """分数 < 阈值，不通过。"""
        assert is_passed(79) is False
        assert is_passed(0) is False

    def test_custom_threshold(self) -> None:
        """自定义阈值。"""
        assert is_passed(70, threshold=70) is True
        assert is_passed(69, threshold=70) is False
