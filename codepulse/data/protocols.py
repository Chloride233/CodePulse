"""Protocol definitions for CodePulse components.

Defines structural typing contracts for agents, graders, and data loaders.
Protocols enable duck-typing without inheritance — any class with matching
signatures satisfies the protocol, keeping coupling minimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.env.sandbox import SandboxManager
    from codepulse.eval.scoring import ScoreDimension
    from codepulse.shared.trace_types import Transcript


@runtime_checkable
class Agent(Protocol):
    """Contract for an agent that executes tasks in a sandbox.

    Implementations wrap a specific LLM (e.g., DeepSeek, GPT, Claude)
    and translate a Task into execution steps captured by a Transcript.

    Example::

        class DeepSeekAgent:
            name = "deepseek-v3"
            model = "deepseek-chat"

            def run(self, task: Task, sandbox: SandboxManager) -> Transcript:
                ...
    """

    @property
    def name(self) -> str:
        """Human-readable identifier for this agent (e.g., 'deepseek-v3')."""
        ...

    @property
    def model(self) -> str:
        """Model identifier passed to LiteLLM (e.g., 'deepseek-chat')."""
        ...

    def run(self, task: Task, sandbox: SandboxManager) -> Transcript:
        """Execute a task and return the full execution transcript.

        Args:
            task: The task to solve, containing prompt and metadata.
            sandbox: Isolated environment for code execution.

        Returns:
            Transcript capturing all steps, tool calls, and final result.
        """
        ...


@dataclass(frozen=True)
class GraderResult:
    """Immutable result from grading a single trial.

    Frozen to prevent mutation after grading — results are audit artifacts.

    Attributes:
        dimension: Which evaluation dimension was scored.
        score: Normalized score in [0, 1] where 1 is perfect.
        details: Free-form breakdown (e.g., test pass counts, error types).
        evidence: Structured evidence for downstream diagnostics.
        diagnosis: Human-readable diagnostic summary.
    """

    dimension: ScoreDimension
    score: float
    details: dict[str, object]
    evidence: list[dict[str, object]] = field(default_factory=list)
    diagnosis: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(
                f"score must be in [0, 1], got {self.score}"
            )


@runtime_checkable
class Grader(Protocol):
    """Contract for grading a trial against a specific evaluation dimension.

    Each Grader owns exactly one dimension (functional correctness, process
    quality, etc.) and returns a normalized score with details.

    Implementations may be deterministic (test-based) or LLM-as-Judge.

    Example::

        class CorrectnessGrader:
            name = "correctness"

            def grade(self, task: Task, trial: Trial) -> GraderResult:
                ...
    """

    @property
    def name(self) -> str:
        """Identifier for this grader (e.g., 'correctness', 'robustness')."""
        ...

    def grade(self, task: Task, trial: Trial) -> GraderResult:
        """Evaluate a trial and return a scored result.

        Args:
            task: The original task definition (expected behavior).
            trial: The agent's execution trial to evaluate.

        Returns:
            GraderResult with score and diagnostic details.
        """
        ...


@runtime_checkable
class DatasetLoader(Protocol):
    """Contract for loading tasks from various dataset formats.

    Loaders handle format-specific parsing (YAML, JSON, SWE-bench, etc.)
    and validation. The data layer uses loaders as interchangeable adapters.

    Example::

        class SweBenchLoader:
            def load(self, path: str) -> list[Task]:
                ...

            def validate(self, task: Task) -> bool:
                ...
    """

    def load(self, path: str) -> list[Task]:
        """Load tasks from a dataset file or directory.

        Args:
            path: Path to the dataset file or directory.

        Returns:
            List of parsed Task objects.

        Raises:
            FileNotFoundError: If path does not exist.
            ValueError: If the dataset format is invalid.
        """
        ...

    def validate(self, task: Task) -> bool:
        """Check whether a task meets minimum quality requirements.

        Args:
            task: The task to validate.

        Returns:
            True if the task is well-formed and usable for evaluation.
        """
        ...
