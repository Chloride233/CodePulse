"""学习率调度器测试。"""


from codepulse.evolve.scheduler import AdaptiveScheduler, CombinedScheduler, CosineDecayScheduler


class TestCosineDecayScheduler:
    def test_single_epoch(self) -> None:
        s = CosineDecayScheduler()
        assert s.scale(0, 1) == 1.0

    def test_warmup_increases(self) -> None:
        s = CosineDecayScheduler(warmup_fraction=0.5, min_scale=0.0)
        scale_0 = s.scale(0, 10)
        scale_4 = s.scale(4, 10)
        assert scale_4 >= scale_0

    def test_decay_after_warmup(self) -> None:
        s = CosineDecayScheduler(warmup_fraction=0.1, min_scale=0.0)
        scales = [s.scale(i, 20) for i in range(20)]
        # After warmup, should eventually decrease
        assert scales[-1] < scales[5]

    def test_min_scale_respected(self) -> None:
        s = CosineDecayScheduler(min_scale=0.3)
        scale = s.scale(100, 100)
        assert scale >= 0.3

    def test_large_epochs(self) -> None:
        s = CosineDecayScheduler()
        scale = s.scale(999, 1000)
        assert 0.0 <= scale <= 1.0


class TestAdaptiveScheduler:
    def test_no_history_returns_base(self) -> None:
        s = AdaptiveScheduler(base_scale=0.5)
        assert s.scale(0, 10) == 0.5

    def test_strong_improvement_boosts(self) -> None:
        s = AdaptiveScheduler(base_scale=0.5)
        scale = s.scale(1, 10, improvement_rate=0.5, regression_rate=0.0)
        assert scale > 0.5

    def test_regression_penalizes(self) -> None:
        s = AdaptiveScheduler(base_scale=0.5)
        scale = s.scale(1, 10, improvement_rate=0.0, regression_rate=0.3)
        assert scale < 0.5

    def test_mixed_no_change(self) -> None:
        s = AdaptiveScheduler(base_scale=0.5)
        scale = s.scale(1, 10, improvement_rate=0.1, regression_rate=0.05)
        assert scale == 0.5

    def test_min_scale_respected(self) -> None:
        s = AdaptiveScheduler(base_scale=0.5, min_scale=0.05)
        scale = s.scale(1, 10, improvement_rate=0.0, regression_rate=0.9)
        assert scale >= 0.05

    def test_max_scale_respected(self) -> None:
        s = AdaptiveScheduler(base_scale=0.5, max_scale=0.9)
        scale = s.scale(1, 10, improvement_rate=1.0, regression_rate=0.0)
        assert scale <= 0.9


class TestCombinedScheduler:
    def test_blend_defaults(self) -> None:
        s = CombinedScheduler()
        scale = s.scale(0, 10)
        assert 0.0 <= scale <= 1.0

    def test_pure_cosine(self) -> None:
        s = CombinedScheduler(adaptive_weight=0.0)
        c = CosineDecayScheduler()
        assert s.scale(5, 10) == c.scale(5, 10)

    def test_out_of_range_clamped(self) -> None:
        s = CombinedScheduler(adaptive_weight=2.0)
        scale = s.scale(0, 10)
        assert 0.0 <= scale <= 1.0
