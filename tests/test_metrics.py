"""指标计算测试。"""

from codepulse.observe.metrics import calc_pass_at_k, calc_pass_hat_k, compute_pass_metrics


class TestCalcPassAtK:
    """pass@k 计算测试。"""

    def test_all_success(self) -> None:
        """全部成功，pass@k = 1。"""
        assert calc_pass_at_k(5, 5, 1) == 1.0
        assert calc_pass_at_k(5, 5, 3) == 1.0

    def test_all_failure(self) -> None:
        """全部失败，pass@k = 0。"""
        assert calc_pass_at_k(5, 0, 1) == 0.0
        assert calc_pass_at_k(5, 0, 3) == 0.0

    def test_partial_success(self) -> None:
        """部分成功，pass@k 递增。"""
        # 5 次中 3 次成功
        pass_1 = calc_pass_at_k(5, 3, 1)
        pass_3 = calc_pass_at_k(5, 3, 3)
        assert 0 < pass_1 < 1
        assert pass_3 > pass_1

    def test_k_greater_than_n(self) -> None:
        """k > n 时，k 被截断为 n。"""
        assert calc_pass_at_k(3, 3, 5) == 1.0

    def test_invalid_input(self) -> None:
        """无效输入返回 0。"""
        assert calc_pass_at_k(0, 0, 1) == 0.0
        assert calc_pass_at_k(5, 0, 0) == 0.0


class TestCalcPassHatK:
    """pass^k 计算测试。"""

    def test_all_success(self) -> None:
        """全部成功，pass^k = 1。"""
        assert calc_pass_hat_k(5, 5, 5) == 1.0

    def test_all_failure(self) -> None:
        """全部失败，pass^k = 0。"""
        assert calc_pass_hat_k(5, 0, 5) == 0.0

    def test_partial_success(self) -> None:
        """部分成功，pass^k 随 k 递减。"""
        hat_1 = calc_pass_hat_k(5, 4, 1)
        hat_5 = calc_pass_hat_k(5, 4, 5)
        assert hat_1 > hat_5

    def test_zero_total(self) -> None:
        """总次数为 0，返回 0。"""
        assert calc_pass_hat_k(0, 0, 5) == 0.0


class TestComputePassMetrics:
    """compute_pass_metrics 测试。"""

    def test_returns_all_metrics(self) -> None:
        """返回完整指标。"""
        metrics = compute_pass_metrics(10, 8, 5)
        assert metrics.pass_at_1 > 0
        assert metrics.pass_at_k > 0
        assert metrics.pass_hat_k > 0
        assert metrics.k == 5
