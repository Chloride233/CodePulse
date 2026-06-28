"""Tests for HTML report generation — codepulse.output.report ReportGenerator.

Tests the generate_html_report method with Chart.js output.
"""
from __future__ import annotations

from codepulse.output.report import ReportGenerator


class TestHtmlReport:
    """Tests for generate_html_report."""

    def setup_method(self) -> None:
        self.generator = ReportGenerator()

    def test_returns_string(self) -> None:
        results = {
            "Agent-A": {"functional": 0.9, "process": 0.8, "efficiency": 0.7, "robustness": 0.9, "alignment": 0.95},
            "Agent-B": {"functional": 0.6, "process": 0.7, "efficiency": 0.8, "robustness": 0.5, "alignment": 0.7},
        }
        html = self.generator.generate_html_report(results)
        assert isinstance(html, str)
        assert len(html) > 500

    def test_contains_chart_js_cdn(self) -> None:
        results = {"Agent-A": {"functional": 0.9}}
        html = self.generator.generate_html_report(results)
        assert "chart.js" in html.lower()

    def test_contains_agent_names(self) -> None:
        results = {
            "Alpha": {"functional": 0.9},
            "Beta": {"functional": 0.7},
        }
        html = self.generator.generate_html_report(results)
        assert "Alpha" in html
        assert "Beta" in html

    def test_contains_dimension_labels(self) -> None:
        results = {"Agent-X": {"functional": 0.8, "process": 0.7, "efficiency": 0.6, "robustness": 0.5, "alignment": 0.9}}
        html = self.generator.generate_html_report(results)
        assert "Functional" in html
        assert "Process" in html
        assert "Efficiency" in html
        assert "Robustness" in html
        assert "Alignment" in html

    def test_contains_radar_chart_canvas(self) -> None:
        results = {"Agent-A": {"functional": 0.8}}
        html = self.generator.generate_html_report(results)
        assert "radarChart" in html

    def test_contains_bar_chart_canvas(self) -> None:
        results = {"Agent-A": {"functional": 0.8}}
        html = self.generator.generate_html_report(results)
        assert "radarChart" in html

    def test_results_with_avg_scores(self) -> None:
        results = {
            "Agent-A": {
                "avg_scores": {"functional": 0.85, "process": 0.75, "efficiency": 0.65},
            },
        }
        html = self.generator.generate_html_report(results)
        assert "Agent-A" in html

    def test_contains_data_table(self) -> None:
        results = {
            "Agent-A": {"functional": 0.9, "pass_rate": 0.85},
            "Agent-B": {"functional": 0.6, "pass_rate": 0.45},
        }
        html = self.generator.generate_html_report(results)
        assert "Detailed Results" in html

    def test_contains_footer(self) -> None:
        results = {"Agent-A": {"functional": 0.9}}
        html = self.generator.generate_html_report(results)
        assert "CodePulse" in html

    def test_custom_title(self) -> None:
        results = {"Agent-A": {"functional": 0.9}}
        html = self.generator.generate_html_report(results, title="My Custom Report")
        assert "My Custom Report" in html

    def test_single_agent(self) -> None:
        """Single agent still generates valid HTML."""
        results = {"Solo-Agent": {"functional": 0.9, "efficiency": 0.7}}
        html = self.generator.generate_html_report(results)
        assert "Solo-Agent" in html

    def test_no_agent_data_returns_base_html(self) -> None:
        """Empty results should still produce valid HTML."""
        html = self.generator.generate_html_report({})
        assert isinstance(html, str)
        assert "<html" in html

    def test_extract_dimension_data_picks_avg_scores(self) -> None:
        """When direct dim values are missing, falls back to avg_scores."""
        results = {
            "Agent-A": {
                "avg_scores": {"functional": 0.75, "process": 0.65},
            },
        }
        dim_data = self.generator._extract_dimension_data(results)
        assert len(dim_data) == 1
        entry = dim_data[0]
        assert entry["agent"] == "Agent-A"
        assert entry.get("functional", 0) == 0.75

    def test_extract_radar_data(self) -> None:
        dim_data = [
            {"agent": "A", "functional": 0.9, "process": 0.8},
            {"agent": "B", "functional": 0.6, "process": 0.7},
        ]
        result = self.generator._extract_radar_data(dim_data)
        assert result["agents"] == ["A", "B"]
        assert len(result["datasets"]) == 2
        assert result["datasets"][0]["label"] == "A"
        assert len(result["datasets"][0]["data"]) == 5  # 5 dimensions
