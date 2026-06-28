"""评测评分系统测试。"""

from codepulse.eval.scoring import (
    ScoreDimension,
    aggregate_scores,
    is_passed,
    is_stable_pass,
    sequence_similarity,
    weighted_total,
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


class TestSequenceSimilarity:
    """sequence_similarity (LCS) 测试。"""

    def test_identical(self) -> None:
        assert sequence_similarity(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_disjoint(self) -> None:
        assert sequence_similarity(["a", "b"], ["x", "y"]) == 0.0

    def test_partial(self) -> None:
        s = sequence_similarity(["read", "write", "execute"], ["read", "execute"])
        assert 0.5 < s < 1.0

    def test_empty_both(self) -> None:
        assert sequence_similarity([], []) == 1.0

    def test_empty_one(self) -> None:
        assert sequence_similarity(["a"], []) == 0.0
        assert sequence_similarity([], ["a"]) == 0.0

    def test_reordered(self) -> None:
        """顺序不同影响匹配。"""
        s = sequence_similarity(["a", "b", "c"], ["c", "b", "a"])
        assert 0.3 < s < 0.7


class TestStablePass:
    """is_stable_pass 稳定性容忍阈值测试。"""

    def test_critical_requires_all(self) -> None:
        assert is_stable_pass(1.0, "critical") is True
        assert is_stable_pass(0.99, "critical") is False

    def test_normal_requires_80(self) -> None:
        assert is_stable_pass(0.8, "normal") is True
        assert is_stable_pass(0.79, "normal") is False

    def test_tolerant_requires_60(self) -> None:
        assert is_stable_pass(0.6, "tolerant") is True
        assert is_stable_pass(0.59, "tolerant") is False

    def test_default_is_normal(self) -> None:
        assert is_stable_pass(0.8) is True
        assert is_stable_pass(0.79) is False


class TestWeightedTotal:
    """weighted_total 从字符串键分数字典计算总分。"""

    def test_all_dimensions(self) -> None:
        s = {"functional": 1.0, "process": 1.0, "efficiency": 1.0, "robustness": 1.0, "alignment": 1.0}
        assert weighted_total(s) == 100.0

    def test_partial(self) -> None:
        s = {"functional": 1.0, "robustness": 0.5}
        assert weighted_total(s) == 40.0

    def test_unknown_dimension_ignored(self) -> None:
        s = {"functional": 1.0, "nonexistent": 0.5}
        assert weighted_total(s) == 30.0
