"""数据模型定义。

统一的 Task/Trial/Grader schema，所有数据源共享。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskSource(StrEnum):
    """任务数据源。"""

    SWE_BENCH = "swe-bench"
    AACR_BENCH = "aacr-bench"
    HUMANEVAL = "humaneval"
    MBPP = "mbpp"
    CUSTOM = "custom"


class TaskCategory(StrEnum):
    """任务类别。"""

    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    CODE_REVIEW = "code_review"


class Difficulty(StrEnum):
    """难度等级。"""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class SuiteType(StrEnum):
    """评测套件类型。"""

    CAPABILITY = "capability"
    REGRESSION = "regression"


class GraderType(StrEnum):
    """评分器类型。"""

    DETERMINISTIC = "deterministic"
    LLM_JUDGE = "llm_judge"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class FailureAnalysis:
    """结构化失败归因。"""

    stage: str
    failure_type: str
    evidence: list[str] = field(default_factory=list)
    suggested_action: str = ""
    should_enter_regression: bool = False


@dataclass(frozen=True)
class GraderConfig:
    """评分器配置。"""

    name: str
    grader_type: GraderType
    weight: float
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentConfig:
    """Agent 配置。"""

    name: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Task:
    """评测任务。"""

    task_id: str
    source: TaskSource
    category: TaskCategory
    difficulty: Difficulty
    language: str
    input: dict[str, Any]
    ground_truth: dict[str, Any]
    graders: list[GraderConfig] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    suite_type: SuiteType = SuiteType.CAPABILITY
    acceptance_criteria: list[str] = field(default_factory=list)
    baseline_id: str | None = None
    artifact_expectations: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrialMetrics:
    """试运行指标。"""

    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    reasoning_tokens: int = 0
    tool_roundtrip_tokens: int = 0
    retry_count: int = 0
    cache_hit_tokens: int = 0
    total_duration: float = 0.0
    tool_call_count: int = 0
    self_correction_count: int = 0
    cost_usd: float = 0.0
    cost_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class Trial:
    """一次试运行记录。"""

    trial_id: str
    task_id: str
    agent_config: AgentConfig
    outcome: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    metrics: TrialMetrics = field(default_factory=TrialMetrics)
    success: bool = False
    tool_call_sequence: list[str] = field(default_factory=list)
    failure_analysis: list[FailureAnalysis] = field(default_factory=list)
