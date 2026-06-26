"""Layer 2: 数据层 — 数据集加载与管理。

支持 SWE-bench、AACR-Bench、自定义数据集的统一加载和版本管理。
"""

from codepulse.data.aacr_bench import AacrBenchLoader
from codepulse.data.custom_loader import CustomDatasetLoader
from codepulse.data.models import AgentConfig, GraderConfig, Task, Trial, TrialMetrics
from codepulse.data.protocols import Agent, DatasetLoader, Grader, GraderResult
from codepulse.data.swe_bench import SweBenchLoader

__all__ = [
    "AacrBenchLoader",
    "Agent",
    "AgentConfig",
    "CustomDatasetLoader",
    "DatasetLoader",
    "Grader",
    "GraderConfig",
    "GraderResult",
    "SweBenchLoader",
    "Task",
    "Trial",
    "TrialMetrics",
]
