"""Prompt edit model tests."""

import pytest

from codepulse.evolve.prompt_edit import (
    EditBatch,
    EditType,
    PromptEdit,
    RejectedEdit,
)


def _make_edit(**kwargs) -> PromptEdit:
    """Helper to create a PromptEdit with sensible defaults."""
    defaults = dict(
        edit_id="edit-1",
        edit_type=EditType.REPLACE,
        target_section="system_prompt",
        content="Be concise.",
        reasoning="Current prompt is too verbose.",
        confidence=0.8,
    )
    defaults.update(kwargs)
    return PromptEdit(**defaults)


class TestEditType:
    """EditType enum tests."""

    def test_values(self) -> None:
        """Enum has the four expected members with correct string values."""
        assert EditType.APPEND == "append"
        assert EditType.REPLACE == "replace"
        assert EditType.DELETE == "delete"
        assert EditType.INSERT == "insert"

    def test_member_count(self) -> None:
        """No unexpected members were added."""
        assert len(EditType) == 4

    def test_str_behavior(self) -> None:
        """StrEnum members are usable as plain strings."""
        assert EditType.APPEND == "append"
        assert isinstance(EditType.APPEND, str)


class TestPromptEdit:
    """PromptEdit dataclass tests."""

    def test_creation_all_fields(self) -> None:
        """All fields are stored correctly."""
        edit = _make_edit()
        assert edit.edit_id == "edit-1"
        assert edit.edit_type == EditType.REPLACE
        assert edit.target_section == "system_prompt"
        assert edit.content == "Be concise."
        assert edit.reasoning == "Current prompt is too verbose."
        assert edit.confidence == 0.8

    def test_frozen(self) -> None:
        """PromptEdit is frozen; attribute assignment raises FrozenInstanceError."""
        edit = _make_edit()
        with pytest.raises(AttributeError):
            edit.content = "mutated"  # type: ignore[misc]

    def test_confidence_boundary_valid(self) -> None:
        """Confidence at 0.0 and 1.0 is accepted."""
        assert _make_edit(confidence=0.0).confidence == 0.0
        assert _make_edit(confidence=1.0).confidence == 1.0

    def test_confidence_below_zero_raises(self) -> None:
        """Confidence < 0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be in"):
            _make_edit(confidence=-0.1)

    def test_confidence_above_one_raises(self) -> None:
        """Confidence > 1 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be in"):
            _make_edit(confidence=1.5)

    def test_edit_type_all_variants(self) -> None:
        """PromptEdit accepts every EditType variant."""
        for etype in EditType:
            edit = _make_edit(edit_type=etype)
            assert edit.edit_type == etype


class TestEditBatch:
    """EditBatch dataclass tests."""

    def test_creation_defaults(self) -> None:
        """Default lists are empty."""
        batch = EditBatch(batch_id="b-1")
        assert batch.batch_id == "b-1"
        assert batch.edits == []
        assert batch.source_task_ids == []

    def test_creation_with_edits(self) -> None:
        """Edits and source_task_ids are stored."""
        edit = _make_edit()
        batch = EditBatch(
            batch_id="b-2",
            edits=[edit],
            source_task_ids=["trace-1", "trace-2"],
        )
        assert len(batch.edits) == 1
        assert batch.edits[0] is edit
        assert batch.source_task_ids == ["trace-1", "trace-2"]

    def test_frozen(self) -> None:
        """EditBatch is frozen."""
        batch = EditBatch(batch_id="b-3")
        with pytest.raises(AttributeError):
            batch.batch_id = "mutated"  # type: ignore[misc]


class TestRejectedEdit:
    """RejectedEdit dataclass tests."""

    def test_creation(self) -> None:
        """All fields are stored correctly."""
        edit = _make_edit()
        rejected = RejectedEdit(
            edit=edit,
            score_delta=-5.0,
            rejection_reason="Regression on edge cases.",
            timestamp=1700000000.0,
        )
        assert rejected.edit is edit
        assert rejected.score_delta == -5.0
        assert rejected.rejection_reason == "Regression on edge cases."
        assert rejected.timestamp == 1700000000.0

    def test_frozen(self) -> None:
        """RejectedEdit is frozen."""
        rejected = RejectedEdit(
            edit=_make_edit(),
            score_delta=-2.0,
            rejection_reason="worse",
            timestamp=0.0,
        )
        with pytest.raises(AttributeError):
            rejected.score_delta = 0.0  # type: ignore[misc]

    def test_score_delta_is_negative(self) -> None:
        """Rejected edits carry a negative score_delta (regression)."""
        rejected = RejectedEdit(
            edit=_make_edit(),
            score_delta=-3.5,
            rejection_reason="Lowered overall score.",
            timestamp=1700000000.0,
        )
        assert rejected.score_delta < 0
