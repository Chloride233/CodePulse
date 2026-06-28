"""Tests for codepulse.evolve.suggest — suggestion engine."""
from __future__ import annotations

from codepulse.evolve.suggest import SuggestionEngine, SuggestionPriority


class TestSuggestionEngine:
    """Tests for SuggestionEngine."""

    def setup_method(self) -> None:
        self.engine = SuggestionEngine()

    def test_all_scores_high_returns_no_suggestions(self) -> None:
        scores = {
            "functional": 0.95,
            "process": 0.90,
            "efficiency": 0.85,
            "robustness": 0.90,
            "alignment": 0.95,
        }
        suggestions = self.engine.analyze(scores)
        assert len(suggestions) == 0

    def test_low_functional_returns_critical(self) -> None:
        scores = {
            "functional": 0.4,
            "process": 0.9,
            "efficiency": 0.9,
            "robustness": 0.9,
            "alignment": 0.9,
        }
        suggestions = self.engine.analyze(scores)
        critical = [s for s in suggestions if s.priority == SuggestionPriority.CRITICAL]
        assert len(critical) >= 1
        assert any("functional" in s.dimension for s in critical)

    def test_low_robustness_returns_high(self) -> None:
        scores = {
            "functional": 0.9,
            "process": 0.9,
            "efficiency": 0.9,
            "robustness": 0.3,
            "alignment": 0.9,
        }
        suggestions = self.engine.analyze(scores)
        high = [s for s in suggestions if s.priority == SuggestionPriority.HIGH]
        assert len(high) >= 1
        assert any("robustness" in s.dimension for s in high)

    def test_suggestions_sorted_by_priority(self) -> None:
        scores = {
            "functional": 0.4,
            "process": 0.5,
            "efficiency": 0.9,
            "robustness": 0.3,
            "alignment": 0.9,
        }
        suggestions = self.engine.analyze(scores)
        # Critical should come before High, High before Medium, etc.
        priority_order = {
            SuggestionPriority.CRITICAL: 0,
            SuggestionPriority.HIGH: 1,
            SuggestionPriority.MEDIUM: 2,
            SuggestionPriority.LOW: 3,
        }
        priorities = [priority_order.get(s.priority, 99) for s in suggestions]
        assert priorities == sorted(priorities)

    def test_summarize_with_suggestions(self) -> None:
        scores = {"functional": 0.5, "process": 0.9, "efficiency": 0.9, "robustness": 0.9, "alignment": 0.9}
        suggestions = self.engine.analyze(scores)
        summary = self.engine.summarize(suggestions)
        assert "优化建议" in summary
        assert "功能正确性不足" in summary

    def test_summarize_without_suggestions(self) -> None:
        scores = {"functional": 0.95, "process": 0.9, "efficiency": 0.95, "robustness": 0.9, "alignment": 0.95}
        suggestions = self.engine.analyze(scores)
        summary = self.engine.summarize(suggestions)
        assert "无需优化建议" in summary

    def test_accepts_enum_keys(self) -> None:
        from codepulse.eval.scoring import ScoreDimension
        scores = {
            ScoreDimension.FUNCTIONAL: 0.4,
            ScoreDimension.PROCESS: 0.9,
            ScoreDimension.EFFICIENCY: 0.9,
            ScoreDimension.ROBUSTNESS: 0.9,
            ScoreDimension.ALIGNMENT: 0.9,
        }
        suggestions = self.engine.analyze(scores)
        assert len(suggestions) > 0
        assert any("functional" in s.dimension for s in suggestions)

    def test_analyze_benchmark_empty(self) -> None:
        result = self.engine.analyze_benchmark([])
        assert result["pass_rate"] == 0.0
        assert result["avg_scores"] == {}
        assert result["suggestions"] == []

    def test_analyze_benchmark_with_data(self) -> None:
        results = [
            {
                "task_id": "task-1",
                "pass_rate": 0.8,
                "avg_scores": {"functional": 0.6, "process": 0.7, "efficiency": 0.9},
            },
            {
                "task_id": "task-2",
                "pass_rate": 0.4,
                "avg_scores": {"functional": 0.5, "process": 0.6, "efficiency": 0.8},
            },
        ]
        result = self.engine.analyze_benchmark(results)
        assert result["n_total"] == 2
        assert result["n_passed"] == 1
        assert result["pass_rate"] == 0.5
        assert "functional" in result["avg_scores"]
        assert result["avg_scores"]["functional"] == 0.55  # (0.6 + 0.5) / 2
        assert len(result["suggestions"]) > 0

    def test_cross_dimension_pattern_triggers(self) -> None:
        """Both functional and process below 0.6 triggers cross-dimension suggestion."""
        scores = {
            "functional": 0.4,
            "process": 0.5,
            "efficiency": 0.9,
            "robustness": 0.9,
            "alignment": 0.9,
        }
        suggestions = self.engine.analyze(scores)
        titles = [s.title for s in suggestions]
        assert "基础能力薄弱" in titles

    def test_suggestion_has_action_text(self) -> None:
        scores = {"functional": 0.4, "process": 0.9, "efficiency": 0.9, "robustness": 0.9, "alignment": 0.9}
        suggestions = self.engine.analyze(scores)
        for s in suggestions:
            assert s.action, f"Suggestion '{s.title}' missing action text"
            assert s.title
            assert s.dimension
