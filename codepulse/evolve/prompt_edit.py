"""SkillOpt prompt edit model.

Defines the data structures for prompt edits in the SkillOpt self-evolution
cycle. An edit is a discrete change to a prompt template (system prompt,
examples, constraints, etc.) that can be applied, validated, and rolled back.
Edits are grouped into batches tied to the task traces that inspired them,
and rejected edits are recorded with their regression scores for learning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class EditType(StrEnum):
    """Type of prompt edit operation."""

    APPEND = "append"
    REPLACE = "replace"
    DELETE = "delete"
    INSERT = "insert"


@dataclass(frozen=True)
class PromptEdit:
    """A single, atomic edit to a prompt template.

    Attributes:
        edit_id: Unique identifier for this edit.
        edit_type: The kind of edit operation.
        target_section: Which section of the prompt to modify
            (e.g. "system_prompt", "examples", "constraints").
        content: The edit content (meaning depends on edit_type).
        reasoning: Why this edit was suggested by the backward pass.
        confidence: Confidence score in [0, 1] that this edit will improve
            evaluation scores.
    """

    edit_id: str
    edit_type: EditType
    target_section: str
    content: str
    reasoning: str
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0, 1], got {self.confidence}"
            )


@dataclass(frozen=True)
class EditBatch:
    """A batch of prompt edits produced by one backward-pass invocation.

    Attributes:
        batch_id: Unique identifier for this batch.
        edits: Ordered list of edits to apply together.
        source_task_ids: Task trace IDs that triggered these edits.
    """

    batch_id: str
    edits: list[PromptEdit] = field(default_factory=list)
    source_task_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RejectedEdit:
    """Record of an edit that was validated and found to cause regression.

    Stored in the rejection buffer so the backward pass can learn to avoid
    similar edits in future iterations.

    Attributes:
        edit: The original edit that was rejected.
        score_delta: Change in aggregate score (negative means regression).
        rejection_reason: Human-readable reason for the rejection.
        timestamp: Unix timestamp when the rejection was recorded.
    """

    edit: PromptEdit
    score_delta: float
    rejection_reason: str
    timestamp: float
