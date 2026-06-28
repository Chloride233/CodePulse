"""集中配置管理。

模型定价、Agent 默认参数、沙箱设置。
配置优先级：YAML 文件 > 环境变量 > 硬编码默认值。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ======================================================================
# 默认路径
# ======================================================================

DEFAULT_RESULTS_DIR = "results"


# ======================================================================
# 模型定价（USD per 1M tokens）
# ======================================================================

MODEL_PRICING: dict[str, dict[str, float]] = {
    # DeepSeek
    "deepseek-chat": {"input": 0.14, "output": 0.28, "cache_read": 0.014},
    "deepseek-coder": {"input": 0.14, "output": 0.28, "cache_read": 0.014},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19, "cache_read": 0.14},
    "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28, "cache_read": 0.014},
    "deepseek/deepseek-v4-flash": {"input": 0.14, "output": 0.28, "cache_read": 0.014},
    "deepseek/deepseek-v4-pro": {"input": 0.55, "output": 2.19, "cache_read": 0.14},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00, "cache_read": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cache_read": 0.075},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00, "cache_read": 5.00},
    "o3-mini": {"input": 1.10, "output": 4.40, "cache_read": 0.55},
    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00, "cache_read": 0.08},
    # Qwen
    "qwen-coder-plus": {"input": 0.30, "output": 0.90, "cache_read": 0.03},
    "qwen-max": {"input": 1.60, "output": 6.40, "cache_read": 0.16},
}


def get_model_pricing(model: str) -> dict[str, float]:
    """获取模型定价。

    支持前缀匹配（如 ``deepseek-chat-0324`` 匹配 ``deepseek-chat``）。

    Args:
        model: LiteLLM 模型标识。

    Returns:
        定价字典 ``{"input": x, "output": y, "cache_read": z}``，
        单位 USD / 1M tokens。未知模型返回零价格。
    """
    # 精确匹配
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # 前缀匹配
    for prefix, pricing in MODEL_PRICING.items():
        if model.startswith(prefix):
            return pricing
    # 未知模型：返回零价格，不阻断流程
    logger.warning("未知模型定价: %s，成本将记为 0", model)
    return {"input": 0.0, "output": 0.0, "cache_read": 0.0}


def calc_cost(model: str, input_tokens: int, output_tokens: int, cache_tokens: int = 0) -> float:
    """计算单次调用成本。

    Args:
        model: 模型标识。
        input_tokens: 输入 token 数。
        output_tokens: 输出 token 数。
        cache_tokens: 缓存命中 token 数。

    Returns:
        成本（USD）。
    """
    pricing = get_model_pricing(model)
    # 缓存命中的 token 按 cache_read 价格计费，其余按 input 价格计费
    billed_input = max(0, input_tokens - cache_tokens)
    cost = (
        billed_input * pricing["input"]
        + output_tokens * pricing["output"]
        + cache_tokens * pricing["cache_read"]
    ) / 1_000_000
    return round(cost, 6)


# ======================================================================
# 配置数据类
# ======================================================================


@dataclass(frozen=True)
class AgentDefaults:
    """Agent 默认参数。"""

    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.0
    max_iterations: int = 20
    timeout_seconds: int = 300


@dataclass(frozen=True)
class SandboxDefaults:
    """沙箱默认参数。"""

    image: str = "python:3.11-slim"
    cpu_count: int = 2
    memory_mb: int = 2048
    timeout_seconds: int = 300


@dataclass(frozen=True)
class CodePulseConfig:
    """CodePulse 全局配置。"""

    agent: AgentDefaults = field(default_factory=AgentDefaults)
    sandbox: SandboxDefaults = field(default_factory=SandboxDefaults)
    api_key_env: str = ""  # 环境变量名，如 "DEEPSEEK_API_KEY"
    base_url: str = ""  # 自定义 API 端点
    results_dir: str = "results"

    @classmethod
    def from_yaml(cls, path: str | Path) -> CodePulseConfig:
        """从 YAML 文件加载配置。

        Args:
            path: YAML 配置文件路径。

        Returns:
            配置实例。文件不存在时返回默认配置。
        """
        file_path = Path(path)
        if not file_path.exists():
            logger.info("配置文件不存在，使用默认配置: %s", path)
            return cls()

        with file_path.open(encoding="utf-8") as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}

        agent_data = data.get("agent", {})
        sandbox_data = data.get("sandbox", {})

        return cls(
            agent=AgentDefaults(
                model=agent_data.get("model", AgentDefaults.model),
                max_tokens=agent_data.get("max_tokens", AgentDefaults.max_tokens),
                temperature=agent_data.get("temperature", AgentDefaults.temperature),
                max_iterations=agent_data.get("max_iterations", AgentDefaults.max_iterations),
                timeout_seconds=agent_data.get("timeout_seconds", AgentDefaults.timeout_seconds),
            ),
            sandbox=SandboxDefaults(
                image=sandbox_data.get("image", SandboxDefaults.image),
                cpu_count=sandbox_data.get("cpu_count", SandboxDefaults.cpu_count),
                memory_mb=sandbox_data.get("memory_mb", SandboxDefaults.memory_mb),
                timeout_seconds=sandbox_data.get("timeout_seconds", SandboxDefaults.timeout_seconds),
            ),
            api_key_env=data.get("api_key_env", ""),
            base_url=data.get("base_url", ""),
            results_dir=data.get("results_dir", "results"),
        )


def load_config(path: str | Path | None = None) -> CodePulseConfig:
    """加载配置。

    优先级：指定路径 > CODEPULSE_CONFIG 环境变量 > codepulse.yaml 默认位置。

    Args:
        path: 配置文件路径，None 时自动查找。

    Returns:
        配置实例。
    """
    if path is not None:
        return CodePulseConfig.from_yaml(path)

    env_path = os.environ.get("CODEPULSE_CONFIG")
    if env_path:
        return CodePulseConfig.from_yaml(env_path)

    # 默认查找顺序
    for candidate in ["codepulse.yaml", "codepulse.yml"]:
        if Path(candidate).exists():
            return CodePulseConfig.from_yaml(candidate)

    return CodePulseConfig()
