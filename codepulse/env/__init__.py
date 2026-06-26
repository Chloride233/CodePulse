"""Layer 1: 环境层 — Docker 沙箱管理。

负责创建、管理和销毁隔离的 Docker 容器，确保评测任务在干净环境中运行。
"""

from codepulse.env.sandbox import (
    Container,
    ExecutionResult,
    ResourceLimits,
    SandboxError,
    SandboxManager,
    Snapshot,
)

__all__ = [
    "Container",
    "ExecutionResult",
    "ResourceLimits",
    "SandboxError",
    "SandboxManager",
    "Snapshot",
]
