"""Tests for codepulse.config module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from codepulse.config import (
    MODEL_PRICING,
    AgentDefaults,
    CodePulseConfig,
    SandboxDefaults,
    calc_cost,
    get_model_pricing,
    load_config,
)


class TestModelPricing:
    """Tests for model pricing lookup."""

    def test_exact_match(self) -> None:
        pricing = get_model_pricing("deepseek-chat")
        assert pricing["input"] == 0.14
        assert pricing["output"] == 0.28
        assert pricing["cache_read"] == 0.014

    def test_prefix_match(self) -> None:
        pricing = get_model_pricing("deepseek-chat-0324")
        assert pricing["input"] == 0.14

    def test_unknown_model_returns_zero(self) -> None:
        pricing = get_model_pricing("unknown-model-xyz")
        assert pricing["input"] == 0.0
        assert pricing["output"] == 0.0
        assert pricing["cache_read"] == 0.0

    def test_all_models_have_required_keys(self) -> None:
        for model, pricing in MODEL_PRICING.items():
            assert "input" in pricing, f"{model} missing 'input'"
            assert "output" in pricing, f"{model} missing 'output'"
            assert "cache_read" in pricing, f"{model} missing 'cache_read'"


class TestCalcCost:
    """Tests for cost calculation."""

    def test_basic_cost(self) -> None:
        cost = calc_cost("deepseek-chat", input_tokens=1000, output_tokens=500)
        # (1000 * 0.14 + 500 * 0.28) / 1_000_000 = 0.000280
        assert cost == pytest.approx(0.000280, abs=1e-6)

    def test_cache_tokens(self) -> None:
        cost = calc_cost("deepseek-chat", input_tokens=1000, output_tokens=500, cache_tokens=800)
        # billed_input = 1000 - 800 = 200
        # (200 * 0.14 + 500 * 0.28 + 800 * 0.014) / 1_000_000
        expected = (200 * 0.14 + 500 * 0.28 + 800 * 0.014) / 1_000_000
        assert cost == pytest.approx(expected, abs=1e-6)

    def test_zero_tokens(self) -> None:
        cost = calc_cost("deepseek-chat", input_tokens=0, output_tokens=0)
        assert cost == 0.0

    def test_unknown_model_zero_cost(self) -> None:
        cost = calc_cost("nonexistent", input_tokens=1000, output_tokens=1000)
        assert cost == 0.0


class TestAgentDefaults:
    """Tests for AgentDefaults dataclass."""

    def test_default_values(self) -> None:
        defaults = AgentDefaults()
        assert defaults.model == "deepseek-chat"
        assert defaults.max_tokens == 4096
        assert defaults.temperature == 0.0
        assert defaults.max_iterations == 20
        assert defaults.timeout_seconds == 300


class TestSandboxDefaults:
    """Tests for SandboxDefaults dataclass."""

    def test_default_values(self) -> None:
        defaults = SandboxDefaults()
        assert defaults.image == "python:3.11-slim"
        assert defaults.cpu_count == 2
        assert defaults.memory_mb == 2048


class TestCodePulseConfig:
    """Tests for CodePulseConfig."""

    def test_default_config(self) -> None:
        config = CodePulseConfig()
        assert config.agent.model == "deepseek-chat"
        assert config.sandbox.image == "python:3.11-slim"
        assert config.results_dir == "results"

    def test_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """
agent:
  model: gpt-4o
  max_tokens: 8192
  temperature: 0.1
sandbox:
  image: python:3.12-slim
  memory_mb: 4096
results_dir: /tmp/results
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")

        config = CodePulseConfig.from_yaml(config_file)
        assert config.agent.model == "gpt-4o"
        assert config.agent.max_tokens == 8192
        assert config.agent.temperature == 0.1
        assert config.sandbox.image == "python:3.12-slim"
        assert config.sandbox.memory_mb == 4096
        assert config.results_dir == "/tmp/results"

    def test_from_yaml_missing_file(self) -> None:
        config = CodePulseConfig.from_yaml("/nonexistent/config.yaml")
        # 应返回默认配置
        assert config.agent.model == "deepseek-chat"

    def test_from_yaml_partial(self, tmp_path: Path) -> None:
        yaml_content = """
agent:
  model: claude-sonnet-4-20250514
"""
        config_file = tmp_path / "partial.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")

        config = CodePulseConfig.from_yaml(config_file)
        assert config.agent.model == "claude-sonnet-4-20250514"
        assert config.sandbox.image == "python:3.11-slim"  # 默认值


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_with_explicit_path(self, tmp_path: Path) -> None:
        yaml_content = "agent:\n  model: gpt-4o-mini\n"
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")

        config = load_config(config_file)
        assert config.agent.model == "gpt-4o-mini"

    def test_load_default(self) -> None:
        config = load_config()
        assert isinstance(config, CodePulseConfig)
